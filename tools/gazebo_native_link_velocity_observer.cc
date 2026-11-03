#include <chrono>
#include <algorithm>
#include <atomic>
#include <gz/msgs/empty.pb.h>
#include <gz/msgs/boolean.pb.h>
#include "gazebo_paused_physical_checkpoint.hh"
#include <iomanip>
#include <memory>
#include <sstream>
#include <string>
#include <vector>

#include <gz/plugin/Register.hh>
#include <gz/sim/Link.hh>
#include <gz/sim/System.hh>
#include <gz/sim/Util.hh>
#include <gz/sim/components/Name.hh>
#include <gz/sim/components/PoseCmd.hh>
#include <gz/transport/Node.hh>
#include <gz/msgs/stringmsg.pb.h>

namespace aero_diagnostic
{
class NativeLinkVelocityObserver final : public gz::sim::System,
    public gz::sim::ISystemConfigure, public gz::sim::ISystemPreUpdate,
    public gz::sim::ISystemPostUpdate
{
  public: void Configure(const gz::sim::Entity &_entity,
      const std::shared_ptr<const sdf::Element> &_sdf,
      gz::sim::EntityComponentManager &_ecm,
      gz::sim::EventManager &) override
  {
    this->configureCalled = true;
    this->worldEntity = _entity;
    if (_sdf->HasElement("audit_world_pose_commands"))
      this->auditWorldPoseCommands = _sdf->Get<bool>("audit_world_pose_commands");
    if (_sdf->HasElement("topic")) this->topic = _sdf->Get<std::string>("topic");
    this->publisher = this->node.Advertise<gz::msgs::StringMsg>(this->topic);
    this->ResolveLinks(_ecm);
    if (this->auditWorldPoseCommands) this->ObservePoseCommands(_ecm);
    if (_sdf->HasElement("checkpoint_service"))
    {
      const auto service = _sdf->Get<std::string>("checkpoint_service");
      this->checkpointEnabled = this->node.Advertise(service,
          &NativeLinkVelocityObserver::RequestCheckpoint, this);
      if (!this->checkpointEnabled) throw std::runtime_error("checkpoint service advertisement failed");
    }
  }

  private: bool RequestCheckpoint(const gz::msgs::Empty &, gz::msgs::Boolean &reply)
  {
    const uint64_t id = this->checkpointSequence.fetch_add(1)+1;
    uint64_t empty = 0;
    const bool accepted = this->pendingCheckpoint.compare_exchange_strong(empty,id);
    reply.set_data(accepted); return true;
  }

  public: void PreUpdate(const gz::sim::UpdateInfo &,
      gz::sim::EntityComponentManager &_ecm) override
  {
    // Retry resolution in case Configure ran before the model/link entities
    // were available. Enabling velocity checks only requests state components.
    this->ResolveLinks(_ecm);
    if (this->auditWorldPoseCommands) this->ObservePoseCommands(_ecm);
  }

  public: void PostUpdate(const gz::sim::UpdateInfo &_info,
      const gz::sim::EntityComponentManager &_ecm) override
  {
    ++this->postUpdateCount;
    if (this->auditWorldPoseCommands) this->ObservePoseCommands(_ecm);
    this->latestSimTime = std::chrono::duration<double>(_info.simTime).count();
    this->latestIteration = _info.iterations;
    this->latestPaused = _info.paused;
    if (!_info.paused)
    { this->lastAdvancingIteration = _info.iterations;
      this->lastAdvancingNs = std::chrono::duration_cast<std::chrono::nanoseconds>(_info.simTime).count(); }
    std::ostringstream json;
    json << std::setprecision(17)
         << "{\"message_kind\":\"observer_health_heartbeat\","
         << "\"plugin_loaded\":true,\"configure_called\":"
         << (this->configureCalled ? "true" : "false")
         << ",\"world_entity_id\":" << this->worldEntity
         << ",\"simulation_time_s\":" << this->latestSimTime
         << ",\"iteration\":" << this->latestIteration
         << ",\"paused\":" << (this->latestPaused ? "true" : "false")
         << ",\"postupdate_count\":" << this->postUpdateCount
         << ",\"publisher_advertised\":"
         << (this->publisher ? "true" : "false")
         << ",\"links\":[";
    bool first = true;
    bool allNativeVelocitiesAvailable = this->links.size() == 3;
    for (const auto &entry : this->links)
    {
      if (!first) json << ',';
      first = false;
      const auto linear = entry.resolved ?
          gz::sim::Link(entry.entity).WorldLinearVelocity(_ecm) : std::nullopt;
      const auto angular = entry.resolved ?
          gz::sim::Link(entry.entity).WorldAngularVelocity(_ecm) : std::nullopt;
      const auto pose = entry.resolved ?
          std::optional<gz::math::Pose3d>(gz::sim::worldPose(entry.entity, _ecm)) : std::nullopt;
      const bool linearAvailable = linear.has_value();
      const bool angularAvailable = angular.has_value();
      allNativeVelocitiesAvailable = allNativeVelocitiesAvailable &&
          entry.resolved && entry.velocityChecksRequested && linearAvailable && angularAvailable;
      json << "{\"expected_scoped_name\":\"" << entry.expectedName
           << "\",\"name\":\"" << entry.expectedName
           << "\",\"resolved\":" << (entry.resolved ? "true" : "false")
           << ",\"lookup_match_count\":" << entry.lookupMatchCount
           << ",\"entity_id\":" << entry.entity
           << ",\"velocity_checks_requested\":"
           << (entry.velocityChecksRequested ? "true" : "false")
           << ",\"world_linear_velocity_available\":"
           << (linearAvailable ? "true" : "false")
           << ",\"world_angular_velocity_available\":"
           << (angularAvailable ? "true" : "false");
      if (pose)
        json << ",\"position_world_m\":[" << pose->Pos().X() << ','
             << pose->Pos().Y() << ',' << pose->Pos().Z()
             << "],\"orientation_world_xyzw\":[" << pose->Rot().X() << ','
             << pose->Rot().Y() << ',' << pose->Rot().Z() << ',' << pose->Rot().W() << ']';
      if (linear)
        json << ",\"linear_velocity_world_m_s\":[" << linear->X() << ','
             << linear->Y() << ',' << linear->Z() << ']';
      if (angular)
        json << ",\"angular_velocity_world_rad_s\":[" << angular->X() << ','
             << angular->Y() << ',' << angular->Z() << ']';
      json << '}';
    }
    json << ']';
    if (this->auditWorldPoseCommands)
      json << ",\"world_pose_command_audit\":{\"enabled\":true,"
           << "\"scope\":\"all entities, PreUpdate and PostUpdate const reads\","
           << "\"active_component_count\":" << this->activePoseCommands
           << ",\"component_observations_total\":" << this->poseCommandObservations
           << ",\"read_callbacks_total\":" << this->poseAuditCallbacks << '}';
    json << ",\"all_link_native_velocities_available\":"
         << (allNativeVelocitiesAvailable ? "true" : "false")
         << ",\"native_velocity_sample_ready\":"
         << (allNativeVelocitiesAvailable ? "true" : "false")
         << ",\"native_velocity_samples_published_prior\":"
         << this->nativeSamplePublishCount
         << ",\"heartbeat_published_prior\":" << this->heartbeatPublishCount
         << ",\"publish_failures_prior\":" << this->publishFailureCount << '}';
    if (!this->publisher) return;
    gz::msgs::StringMsg message;
    message.set_data(json.str());
    if (this->publisher.Publish(message))
    {
      ++this->heartbeatPublishCount;
      if (allNativeVelocitiesAvailable) ++this->nativeSamplePublishCount;
    }
    else ++this->publishFailureCount;
    if (this->checkpointEnabled && _info.paused)
    {
      const auto id = this->pendingCheckpoint.load();
      if (id)
      {
        gz::msgs::StringMsg checkpoint;
        checkpoint.set_data(aero_diagnostic::checkpoint::Serialize(_info,_ecm,json.str(),id,
          this->postUpdateCount,this->worldEntity,this->lastAdvancingIteration,this->lastAdvancingNs));
        this->publisher.Publish(checkpoint);
        this->pendingCheckpoint.store(0);
      }
    }
  }

  private: struct LinkEntry
  {
    std::string expectedName;
    gz::sim::Entity entity{gz::sim::kNullEntity};
    bool resolved{false};
    bool velocityChecksRequested{false};
    size_t lookupMatchCount{0};
  };

  private: void ObservePoseCommands(const gz::sim::EntityComponentManager &_ecm)
  {
    this->activePoseCommands = 0;
    _ecm.Each<gz::sim::components::WorldPoseCmd>(
        [&](const gz::sim::Entity &, const gz::sim::components::WorldPoseCmd *)
        { ++this->activePoseCommands; return true; });
    this->poseCommandObservations += this->activePoseCommands;
    ++this->poseAuditCallbacks;
  }
  private: bool auditWorldPoseCommands{false};
  private: uint64_t activePoseCommands{0}, poseCommandObservations{0}, poseAuditCallbacks{0};
  private: void ResolveLinks(gz::sim::EntityComponentManager &_ecm)
  {
    if (this->links.empty())
      for (const auto *name : {"simple_agent::body", "simple_agent::left_wheel",
                               "simple_agent::right_wheel"})
        this->links.push_back({name});
    for (auto &entry : this->links)
    {
      if (entry.resolved) continue;
      const auto entities = gz::sim::entitiesFromScopedName(entry.expectedName, _ecm);
      entry.lookupMatchCount = entities.size();
      if (entities.size() != 1) continue;
      const auto entity = *entities.begin();
      gz::sim::Link link(entity);
      if (!link.Valid(_ecm)) continue;
      entry.entity = entity;
      entry.resolved = true;
      // This API requests native velocity state components. No link state,
      // command, force, joint, collision or physics parameter is set here.
      link.EnableVelocityChecks(_ecm);
      entry.velocityChecksRequested = true;
    }
  }
  private: bool checkpointEnabled{false};
  private: std::atomic<uint64_t> checkpointSequence{0}, pendingCheckpoint{0};
  private: uint64_t lastAdvancingIteration{0};
  private: int64_t lastAdvancingNs{0};
  private: std::vector<LinkEntry> links;
  private: std::string topic{ "/aero/diagnostic/native_link_velocity" };
  private: gz::transport::Node node;
  private: gz::transport::Node::Publisher publisher;
  private: bool configureCalled{false};
  private: gz::sim::Entity worldEntity{gz::sim::kNullEntity};
  private: uint64_t postUpdateCount{0};
  private: uint64_t nativeSamplePublishCount{0};
  private: uint64_t heartbeatPublishCount{0};
  private: uint64_t publishFailureCount{0};
  private: double latestSimTime{0.0};
  private: uint64_t latestIteration{0};
  private: bool latestPaused{true};
};
}

GZ_ADD_PLUGIN(aero_diagnostic::NativeLinkVelocityObserver,
    gz::sim::System,
    gz::sim::ISystemConfigure,
    gz::sim::ISystemPreUpdate,
    gz::sim::ISystemPostUpdate)
