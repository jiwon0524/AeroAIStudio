#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <memory>
#include <optional>
#include <string>
#include <vector>

#include <gz/plugin/Register.hh>
#include <gz/sim/Joint.hh>
#include <gz/sim/System.hh>
#include <gz/sim/Util.hh>
#include <gz/sim/components/Joint.hh>
#include <gz/sim/components/Model.hh>
#include <gz/sim/components/Name.hh>
#include <gz/sim/components/World.hh>

namespace aero_diagnostic
{
class JointTransmittedWrenchObserver final : public gz::sim::System,
    public gz::sim::ISystemConfigure, public gz::sim::ISystemReset,
    public gz::sim::ISystemPreUpdate,
    public gz::sim::ISystemPostUpdate
{
  private: struct JointState
  {
    std::string name;
    std::string axisXYZ;
    std::string axisFrame;
    gz::sim::Entity entity{gz::sim::kNullEntity};
    bool resolved{false};
    bool wrenchCheckRequested{false};
    bool velocityCheckRequested{false};
    bool wrenchEverAvailable{false};
  };

  public: void Configure(const gz::sim::Entity &_world,
      const std::shared_ptr<const sdf::Element> &_sdf,
      gz::sim::EntityComponentManager &_ecm, gz::sim::EventManager &) override
  {
    this->world = _world;
    this->configured = true;
    if (_sdf && _sdf->HasElement("model_name")) this->modelName = _sdf->Get<std::string>("model_name");
    if (_sdf && _sdf->HasElement("output")) this->outputPath = _sdf->Get<std::string>("output");
    if (_sdf && _sdf->HasElement("left_axis_xyz")) this->left.axisXYZ = _sdf->Get<std::string>("left_axis_xyz");
    if (_sdf && _sdf->HasElement("right_axis_xyz")) this->right.axisXYZ = _sdf->Get<std::string>("right_axis_xyz");
    if (_sdf && _sdf->HasElement("left_axis_frame")) this->left.axisFrame = _sdf->Get<std::string>("left_axis_frame");
    if (_sdf && _sdf->HasElement("right_axis_frame")) this->right.axisFrame = _sdf->Get<std::string>("right_axis_frame");
    this->left.name = "left_joint";
    this->right.name = "right_joint";
    this->out.open(this->outputPath, std::ios::out | std::ios::trunc);
    this->out << std::setprecision(17);
    if (!this->out) std::cerr << "JointTransmittedWrenchObserver: cannot open output " << this->outputPath << '\n';
    this->Resolve(_ecm);
    this->Health("configured");
  }

  public: ~JointTransmittedWrenchObserver() override { this->Health("shutdown"); }

  public: void Reset(const gz::sim::UpdateInfo &_info,
      gz::sim::EntityComponentManager &) override
  {
    ++this->epoch;
    this->haveIteration = true;
    this->lastIteration = _info.iterations;
    this->lastNs = std::chrono::duration_cast<std::chrono::nanoseconds>(_info.simTime).count();
    this->Health("reset_boundary");
    this->WriteBoundary(_info);
  }

  public: void PreUpdate(const gz::sim::UpdateInfo &,
      gz::sim::EntityComponentManager &_ecm) override
  {
    ++this->preCount;
    const bool wasResolved = this->left.resolved && this->right.resolved;
    const bool hadChecks = this->left.wrenchCheckRequested && this->right.wrenchCheckRequested &&
      this->left.velocityCheckRequested && this->right.velocityCheckRequested;
    this->Resolve(_ecm);
    for (auto *j : {&this->left, &this->right})
    {
      if (!j->resolved) continue;
      gz::sim::Joint joint(j->entity);
      if (!j->wrenchCheckRequested) { joint.EnableTransmittedWrenchCheck(_ecm); j->wrenchCheckRequested = true; }
      if (!j->velocityCheckRequested) { joint.EnableVelocityCheck(_ecm); j->velocityCheckRequested = true; }
    }
    if ((!wasResolved && this->left.resolved && this->right.resolved) ||
        (!hadChecks && this->left.wrenchCheckRequested && this->right.wrenchCheckRequested &&
         this->left.velocityCheckRequested && this->right.velocityCheckRequested))
      this->Health("joint_checks_requested");
  }

  public: void PostUpdate(const gz::sim::UpdateInfo &_info,
      const gz::sim::EntityComponentManager &_ecm) override
  {
    ++this->postCount;
    if (_info.paused) { ++this->pausedCount; this->pausedLast = true; return; }
    if (this->pausedLast) { ++this->epoch; this->pausedLast = false; this->Health("resume_boundary"); }
    const auto ns = std::chrono::duration_cast<std::chrono::nanoseconds>(_info.simTime).count();
    if (this->haveIteration && (_info.iterations < this->lastIteration || ns < this->lastNs))
    {
      ++this->epoch;
      this->lastIteration = _info.iterations;
      this->lastNs = ns;
      this->Health("iteration_reset_boundary");
      this->WriteBoundary(_info);
      return;
    }
    if (this->haveIteration && _info.iterations == this->lastIteration) { ++this->duplicateCount; return; }
    this->haveIteration = true;
    this->lastIteration = _info.iterations;
    this->lastNs = ns;
    ++this->sampleCount;
    const bool leftAvailableBefore = this->left.wrenchEverAvailable;
    const bool rightAvailableBefore = this->right.wrenchEverAvailable;
    this->out << "{\"kind\":\"joint_wrench_sample\",\"schema_version\":1,\"epoch\":" << this->epoch
      << ",\"iteration\":" << _info.iterations << ",\"sim_time_ns\":" << ns << ",\"paused\":false,\"wrench_semantics\":\"composite_joint_transmitted_wrench_parent_on_child_in_joint_frame\",\"force_frame\":\"joint_frame_force_at_joint_origin\",\"torque_frame\":\"joint_frame\",\"force_unit\":\"N\",\"torque_unit\":\"N_m\",\"left\":";
    this->WriteJoint(this->left, _ecm);
    this->out << ",\"right\":";
    this->WriteJoint(this->right, _ecm);
    this->out << "}\n";
    this->out.flush();
    if ((!leftAvailableBefore && this->left.wrenchEverAvailable) ||
        (!rightAvailableBefore && this->right.wrenchEverAvailable)) this->Health("wrench_became_available");
  }

  private: void Resolve(gz::sim::EntityComponentManager &_ecm)
  {
    if (this->model != gz::sim::kNullEntity) return;
    const auto matches = gz::sim::entitiesFromScopedName(this->modelName, _ecm, this->world);
    this->modelMatches = matches.size();
    if (matches.size() != 1 || !_ecm.Component<gz::sim::components::Model>(*matches.begin())) return;
    this->model = *matches.begin();
    this->worldResolved = _ecm.Component<gz::sim::components::World>(this->world) != nullptr;
    for (auto *j : {&this->left, &this->right})
    {
      if (j->resolved) continue;
      const auto found = gz::sim::entitiesFromScopedName(j->name, _ecm, this->model);
      if (found.size() != 1 || !_ecm.Component<gz::sim::components::Joint>(*found.begin())) continue;
      j->entity = *found.begin(); j->resolved = true;
    }
  }

  private: static void Number(std::ostream &_out, double _v)
  { if (std::isfinite(_v)) _out << _v; else _out << "null"; }

  private: void WriteJoint(JointState &_j, const gz::sim::EntityComponentManager &_ecm)
  {
    std::optional<std::vector<gz::msgs::Wrench>> wrench;
    std::optional<std::vector<double>> velocity;
    if (_j.resolved)
    {
      gz::sim::Joint joint(_j.entity);
      wrench = joint.TransmittedWrench(_ecm);
      velocity = joint.Velocity(_ecm);
    }
    const bool dimensionOk = wrench && wrench->size() == 1;
    const bool finite = dimensionOk && std::isfinite(wrench->front().force().x()) &&
      std::isfinite(wrench->front().force().y()) && std::isfinite(wrench->front().force().z()) &&
      std::isfinite(wrench->front().torque().x()) && std::isfinite(wrench->front().torque().y()) &&
      std::isfinite(wrench->front().torque().z());
    const char *state = !wrench ? "UNAVAILABLE" : (finite ? "VALID_WRENCH" : "INVALID_WRENCH");
    if (wrench) _j.wrenchEverAvailable = true;
    this->out << "{\"joint_name\":\"" << _j.name << "\",\"entity_id\":" << _j.entity
      << ",\"resolved\":" << (_j.resolved ? "true" : "false") << ",\"state\":\"" << state
      << "\",\"wrench_check_requested\":" << (_j.wrenchCheckRequested ? "true" : "false")
      << ",\"wrench_available\":" << (wrench ? "true" : "false")
      << ",\"wrench_dimension\":" << (wrench ? wrench->size() : 0)
      << ",\"wrench_frame\":\"joint\",\"axis_xyz_in_sdf_frame\":[" << _j.axisXYZ << ']'
      << ",\"axis_frame\":\"" << _j.axisFrame << "\""
      << ",\"actual_velocity_available\":" << ((velocity && velocity->size()==1) ? "true" : "false");
    if (velocity && velocity->size() == 1) { this->out << ",\"actual_velocity_rad_s\":"; Number(this->out, velocity->front()); }
    if (finite)
    {
      const auto &w = wrench->front();
      this->out << ",\"force_xyz_N\":["; Number(this->out,w.force().x()); this->out << ','; Number(this->out,w.force().y()); this->out << ','; Number(this->out,w.force().z());
      this->out << "],\"torque_xyz_N_m\":["; Number(this->out,w.torque().x()); this->out << ','; Number(this->out,w.torque().y()); this->out << ','; Number(this->out,w.torque().z()); this->out << ']';
    }
    this->out << '}';
  }

  private: void Health(const char *_event)
  {
    if (!this->out) return;
    this->out << "{\"kind\":\"observer_health\",\"event\":\"" << _event << "\",\"plugin_loaded\":true,\"configure_called\":" << (this->configured ? "true":"false")
      << ",\"world_resolved\":" << (this->worldResolved ? "true":"false") << ",\"model_name\":\"" << this->modelName << "\",\"model_match_count\":" << this->modelMatches
      << ",\"model_resolved\":" << (this->model != gz::sim::kNullEntity ? "true":"false") << ",\"preupdate_count\":" << this->preCount << ",\"postupdate_count\":" << this->postCount
      << ",\"advancing_sample_count\":" << this->sampleCount << ",\"paused_heartbeat_count\":" << this->pausedCount << ",\"duplicate_iteration_count\":" << this->duplicateCount
      << ",\"left_joint_resolved\":" << (this->left.resolved ? "true":"false") << ",\"left_wrench_check_requested\":" << (this->left.wrenchCheckRequested ? "true":"false") << ",\"left_wrench_ever_available\":" << (this->left.wrenchEverAvailable ? "true":"false")
      << ",\"right_joint_resolved\":" << (this->right.resolved ? "true":"false") << ",\"right_wrench_check_requested\":" << (this->right.wrenchCheckRequested ? "true":"false") << ",\"right_wrench_ever_available\":" << (this->right.wrenchEverAvailable ? "true":"false") << "}\n";
    this->out.flush();
  }

  private: void WriteBoundary(const gz::sim::UpdateInfo &_info)
  {
    if (!this->out) return;
    const auto ns = std::chrono::duration_cast<std::chrono::nanoseconds>(_info.simTime).count();
    this->out << "{\"kind\":\"observer_epoch_boundary\",\"reason\":\"reset\",\"epoch\":" << this->epoch
      << ",\"iteration\":" << _info.iterations << ",\"sim_time_ns\":" << ns << ",\"paused\":"
      << (_info.paused ? "true":"false") << "}\n";
    this->out.flush();
  }

  private: gz::sim::Entity world{gz::sim::kNullEntity}, model{gz::sim::kNullEntity};
  private: std::string modelName{"simple_agent"}, outputPath;
  private: JointState left, right;
  private: std::ofstream out;
  private: bool configured{false}, worldResolved{false}, pausedLast{false}, haveIteration{false};
  private: std::size_t modelMatches{0};
  private: std::uint64_t epoch{0}, lastIteration{0}, sampleCount{0}, preCount{0}, postCount{0}, pausedCount{0}, duplicateCount{0};
  private: std::int64_t lastNs{0};
};
}

GZ_ADD_PLUGIN(aero_diagnostic::JointTransmittedWrenchObserver,
  gz::sim::System, aero_diagnostic::JointTransmittedWrenchObserver::ISystemConfigure,
  aero_diagnostic::JointTransmittedWrenchObserver::ISystemReset,
  aero_diagnostic::JointTransmittedWrenchObserver::ISystemPreUpdate,
  aero_diagnostic::JointTransmittedWrenchObserver::ISystemPostUpdate)
GZ_ADD_PLUGIN_ALIAS(aero_diagnostic::JointTransmittedWrenchObserver,
  "aero_diagnostic::JointTransmittedWrenchObserver")
