#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <optional>
#include <string>
#include <unordered_map>

#include <gz/plugin/Register.hh>
#include <gz/sim/EntityComponentManager.hh>
#include <gz/sim/System.hh>
#include <gz/sim/Util.hh>
#include <gz/sim/components/Collision.hh>
#include <gz/sim/components/ContactSensorData.hh>
#include <gz/sim/components/Link.hh>
#include <gz/sim/components/Model.hh>
#include <gz/sim/components/Name.hh>
#include <gz/sim/components/World.hh>
#include <gz/msgs/contacts.pb.h>

namespace aero_diagnostic
{
class ContinuousSupportObserver final : public gz::sim::System,
    public gz::sim::ISystemConfigure, public gz::sim::ISystemReset,
    public gz::sim::ISystemPreUpdate, public gz::sim::ISystemPostUpdate
{
  private: struct Support
  {
    const char *label;
    const char *linkName;
    const char *collisionName;
    gz::sim::Entity model{gz::sim::kNullEntity};
    gz::sim::Entity link{gz::sim::kNullEntity};
    gz::sim::Entity collision{gz::sim::kNullEntity};
    bool requested{false};
    bool availableSeen{false};
    bool availabilityReported{false};
    bool resolutionReported{false};
    std::optional<std::string> previousSerialized;
    std::uint64_t validContacts{0}, validEmpty{0}, unavailable{0}, createFailures{0};
  };

  public: ContinuousSupportObserver() : supports{{
      {"left_wheel", "left_wheel", "left_collision"},
      {"right_wheel", "right_wheel", "right_collision"},
      {"front_caster", "front_caster", "front_collision"},
      {"rear_caster", "rear_caster", "rear_collision"}}} {}

  public: ~ContinuousSupportObserver() override { this->WriteHealth("shutdown"); }

  public: void Configure(const gz::sim::Entity &_entity,
      const std::shared_ptr<const sdf::Element> &_sdf,
      gz::sim::EntityComponentManager &_ecm, gz::sim::EventManager &) override
  {
    this->world = _entity;
    this->configured = true;
    if (_sdf && _sdf->HasElement("output")) this->outputPath = _sdf->Get<std::string>("output");
    if (_sdf && _sdf->HasElement("model_name")) this->modelName = _sdf->Get<std::string>("model_name");
    if (_sdf && _sdf->HasElement("ground_collision")) this->groundName = _sdf->Get<std::string>("ground_collision");
    if (!this->outputPath.empty())
    {
      this->out.open(this->outputPath, std::ios::out | std::ios::trunc);
      this->out << std::setprecision(17);
    }
    if (!this->out)
      std::cerr << "ContinuousSupportObserver: cannot open output file "
                << this->outputPath << '\n';
    this->Resolve(_ecm);
    this->WriteHealth("configured");
  }

  public: void Reset(const gz::sim::UpdateInfo &_info,
      gz::sim::EntityComponentManager &) override
  {
    ++this->epoch;
    this->haveIteration = false;
    this->epochReady = false;
    for (auto &s : this->supports) s.previousSerialized.reset();
    this->WriteBoundary("system_reset", _info);
  }

  public: void PreUpdate(const gz::sim::UpdateInfo &,
      gz::sim::EntityComponentManager &_ecm) override
  {
    ++this->preCount;
    this->Resolve(_ecm);
    for (auto &s : this->supports)
    {
      if (s.collision == gz::sim::kNullEntity) continue;
      auto *component = _ecm.Component<gz::sim::components::ContactSensorData>(s.collision);
      if (!component)
      {
        component = _ecm.CreateComponent(s.collision, gz::sim::components::ContactSensorData());
        if (!component) { ++s.createFailures; continue; }
      }
      s.requested = true;
    }
  }

  public: void PostUpdate(const gz::sim::UpdateInfo &_info,
      const gz::sim::EntityComponentManager &_ecm) override
  {
    ++this->postCount;
    if (_info.paused) { ++this->pausedCount; this->pausedLast = true; return; }
    if (this->pausedLast) { ++this->epoch; this->pausedLast = false;
      this->epochReady = false;
      for (auto &s : this->supports) s.previousSerialized.reset();
      this->WriteBoundary("resume", _info); }
    const auto currentNs = std::chrono::duration_cast<std::chrono::nanoseconds>(_info.simTime).count();
    if (this->haveIteration && (_info.iterations < this->lastIteration || currentNs < this->lastSimTimeNs))
    {
      ++this->epoch;
      this->haveIteration = false;
      this->epochReady = false;
      for (auto &s : this->supports) s.previousSerialized.reset();
      this->WriteBoundary("iteration_or_time_reset", _info);
    }
    if (this->haveIteration && _info.iterations == this->lastIteration)
    { ++this->duplicateCount; return; }
    const bool gap = this->haveIteration && _info.iterations != this->lastIteration + 1;
    this->lastIteration = _info.iterations; this->lastSimTimeNs = currentNs;
    this->haveIteration = true; ++this->sampleCount;
    for (auto &s : this->supports)
    {
      if (s.collision == gz::sim::kNullEntity && !s.resolutionReported)
      {
        s.resolutionReported = true;
        std::cerr << "ContinuousSupportObserver: unresolved required collision "
                  << this->modelName << "::" << s.linkName << "::" << s.collisionName << '\n';
      }
      const auto *component = s.collision == gz::sim::kNullEntity ? nullptr :
          _ecm.Component<gz::sim::components::ContactSensorData>(s.collision);
      if (component && !s.availabilityReported)
      {
        s.availabilityReported = true;
        this->WriteSupportEvent("component_available", s, _info);
      }
    }
    if (this->ground == gz::sim::kNullEntity && !this->groundResolutionReported)
    {
      this->groundResolutionReported = true;
      std::cerr << "ContinuousSupportObserver: unresolved required ground collision "
                << this->groundName << '\n';
    }
    std::unordered_map<gz::sim::Entity, std::string> names;
    _ecm.Each<gz::sim::components::Name>([&](const gz::sim::Entity &e,
        const gz::sim::components::Name *n) { names.emplace(e, gz::sim::scopedName(e, _ecm, "::", false)); return true; });
    bool allComponentsAvailable = true;
    for (const auto &s : this->supports)
      allComponentsAvailable = allComponentsAvailable && s.collision != gz::sim::kNullEntity &&
          _ecm.Component<gz::sim::components::ContactSensorData>(s.collision) != nullptr;
    this->epochReady = this->epochReady || allComponentsAvailable;
    this->out << "{\"kind\":\"support_iteration\",\"epoch\":" << this->epoch
      << ",\"iteration\":" << _info.iterations << ",\"sim_time_ns\":" << currentNs
      << ",\"paused\":false,\"iteration_gap\":" << (gap ? "true" : "false")
      << ",\"all_support_components_available\":" << (allComponentsAvailable ? "true" : "false") << ",\"supports\":{";
    for (std::size_t i = 0; i < this->supports.size(); ++i)
    { if (i) this->out << ','; this->WriteSupport(this->supports[i], _ecm, names); }
    this->out << "}}\n"; this->out.flush();
  }

  private: static std::string Escape(const std::string &v)
  { std::string r; for (char c : v) { if (c == '\\' || c == '"') r += '\\'; if (c == '\n') r += "\\n"; else if (c != '\r') r += c; } return r; }
  private: static std::optional<std::array<double, 3>> Vec(const gz::msgs::Vector3d &v)
  { std::array<double, 3> a{{v.x(), v.y(), v.z()}}; for (double x : a) if (!std::isfinite(x)) return {}; return a; }
  private: void Resolve(gz::sim::EntityComponentManager &_ecm)
  {
    const auto models = gz::sim::entitiesFromScopedName(this->modelName, _ecm, this->world);
    this->modelMatches = models.size(); if (models.size() != 1) return;
    const auto m = *models.begin();
    if (!_ecm.Component<gz::sim::components::Model>(m)) return;
    for (auto &s : this->supports)
    {
      if (s.collision != gz::sim::kNullEntity) continue;
      const auto links = gz::sim::entitiesFromScopedName(s.linkName, _ecm, m);
      if (links.size() != 1 || !_ecm.Component<gz::sim::components::Link>(*links.begin())) continue;
      const auto collisions = gz::sim::entitiesFromScopedName(s.collisionName, _ecm, *links.begin());
      if (collisions.size() != 1 || !_ecm.Component<gz::sim::components::Collision>(*collisions.begin())) continue;
      s.model = m; s.link = *links.begin(); s.collision = *collisions.begin();
      this->WriteResolved(s, _ecm);
    }
    const auto grounds = gz::sim::entitiesFromScopedName(this->groundName, _ecm, this->world);
    if (grounds.size() == 1 && _ecm.Component<gz::sim::components::Collision>(*grounds.begin())) this->ground = *grounds.begin();
  }
  private: void WriteResolved(const Support &s, const gz::sim::EntityComponentManager &_ecm)
  { if (!this->out) return; this->out << "{\"kind\":\"observer_health_event\",\"event\":\"collision_resolved\",\"support\":\"" << s.label << "\",\"model_entity_id\":" << s.model << ",\"model_name\":\"" << Escape(_ecm.Component<gz::sim::components::Name>(s.model)->Data()) << "\",\"link_entity_id\":" << s.link << ",\"link_name\":\"" << Escape(_ecm.Component<gz::sim::components::Name>(s.link)->Data()) << "\",\"collision_entity_id\":" << s.collision << ",\"collision_name\":\"" << Escape(_ecm.Component<gz::sim::components::Name>(s.collision)->Data()) << "\"}\n"; }
  private: void WriteSupport(Support &s, const gz::sim::EntityComponentManager &_ecm,
      const std::unordered_map<gz::sim::Entity, std::string> &names)
  {
    const auto *rawData = s.collision == gz::sim::kNullEntity ? nullptr : _ecm.Component<gz::sim::components::ContactSensorData>(s.collision);
    const bool available = rawData != nullptr;
    const auto *data = this->epochReady ? rawData : nullptr;
    const int count = data ? data->Data().contact_size() : 0;
    const std::string state = !data ? "UNAVAILABLE" : count ? "VALID_CONTACTS" : "VALID_EMPTY_CONTACT_SET";
    if (state == "UNAVAILABLE") ++s.unavailable;
    else if (count) ++s.validContacts;
    else ++s.validEmpty;
    const auto *mn = s.model == gz::sim::kNullEntity ? nullptr : _ecm.Component<gz::sim::components::Name>(s.model);
    const auto *ln = s.link == gz::sim::kNullEntity ? nullptr : _ecm.Component<gz::sim::components::Name>(s.link);
    const auto *cn = s.collision == gz::sim::kNullEntity ? nullptr : _ecm.Component<gz::sim::components::Name>(s.collision);
    std::optional<std::string> current; if (rawData) current = rawData->Data().SerializeAsString();
    const bool changed = current && (!s.previousSerialized || *current != *s.previousSerialized);
    if (current) s.previousSerialized = *current;
    if (available) s.availableSeen = true;
    this->out << '"' << s.label << "\":{\"model\":{\"entity_id\":" << s.model << ",\"name\":\"" << (mn ? Escape(mn->Data()) : "") << "\"},\"link\":{\"entity_id\":" << s.link << ",\"name\":\"" << (ln ? Escape(ln->Data()) : "") << "\"},\"collision\":{\"entity_id\":" << s.collision << ",\"name\":\"" << (cn ? Escape(cn->Data()) : "") << "\"},\"component_requested\":" << (s.requested ? "true" : "false") << ",\"component_available\":" << (available ? "true" : "false") << ",\"component_content_changed_since_previous_iteration\":" << (changed ? "true" : "false") << ",\"component_comparison_note\":\"Physics may retain protobuf values under contactsEql tolerance; every iteration is still emitted\",\"state\":\"" << state << "\",\"contact_count\":";
    if (data) this->out << count; else this->out << "null";
    this->out << ",\"contacts\":[";
    if (data) for (int i = 0; i < count; ++i)
    {
      if (i) this->out << ','; const auto &c = data->Data().contact(i);
      const auto id1 = c.collision1().id(), id2 = c.collision2().id();
      std::string n1 = c.collision1().name(), n2 = c.collision2().name();
      if (n1.empty() && names.count(id1)) n1 = names.at(id1); if (n2.empty() && names.count(id2)) n2 = names.at(id2);
      const bool groundPair = this->ground != gz::sim::kNullEntity && (id1 == this->ground || id2 == this->ground);
      this->out << "{\"contact_index\":" << i << ",\"collision1\":{\"entity_id\":" << id1 << ",\"name\":\"" << Escape(n1) << "\"},\"collision2\":{\"entity_id\":" << id2 << ",\"name\":\"" << Escape(n2) << "\"},\"pair_classification\":\"" << (groundPair ? "SUPPORT_GROUND" : (n1.empty() || n2.empty() ? "UNKNOWN" : "OTHER")) << "\",\"points\":[";
      const int points = std::max({c.position_size(), c.normal_size(), c.depth_size(), c.wrench_size()});
      for (int j = 0; j < points; ++j)
      {
        if (j) this->out << ','; this->out << "{\"point_index\":" << j;
        auto writeVec = [&](const char *key, const std::optional<std::array<double,3>> &v) { this->out << ",\"" << key << "\":"; if (!v) this->out << "null"; else this->out << '[' << (*v)[0] << ',' << (*v)[1] << ',' << (*v)[2] << ']'; };
        if (j < c.position_size()) writeVec("position_world_m", Vec(c.position(j))); else this->out << ",\"position_world_m\":null";
        if (j < c.normal_size()) writeVec("normal_world", Vec(c.normal(j))); else this->out << ",\"normal_world\":null";
        this->out << ",\"depth_m\":";
        if (j < c.depth_size()) this->out << c.depth(j); else this->out << "null";
        if (j < c.wrench_size()) { writeVec("body_1_force_world_n", Vec(c.wrench(j).body_1_wrench().force())); writeVec("body_2_force_world_n", Vec(c.wrench(j).body_2_wrench().force())); }
        else this->out << ",\"body_1_force_world_n\":null,\"body_2_force_world_n\":null";
        this->out << '}';
      }
      this->out << "]}";
    }
    this->out << "]}";
  }
  private: void WriteBoundary(const char *reason, const gz::sim::UpdateInfo &i)
  { if (this->out) this->out << "{\"kind\":\"observer_epoch_boundary\",\"reason\":\"" << reason << "\",\"epoch\":" << this->epoch << ",\"iteration\":" << i.iterations << ",\"sim_time_ns\":" << std::chrono::duration_cast<std::chrono::nanoseconds>(i.simTime).count() << ",\"paused\":" << (i.paused ? "true" : "false") << "}\n"; }
  private: void WriteSupportEvent(const char *event, const Support &s,
      const gz::sim::UpdateInfo &i)
  { if (this->out) this->out << "{\"kind\":\"observer_health_event\",\"event\":\"" << event << "\",\"support\":\"" << s.label << "\",\"epoch\":" << this->epoch << ",\"iteration\":" << i.iterations << "}\n"; }
  private: void WriteHealth(const char *event)
  { if (!this->out) return; this->out << "{\"kind\":\"observer_health\",\"event\":\"" << event << "\",\"plugin_loaded\":true,\"configure_called\":" << (this->configured ? "true" : "false") << ",\"world_entity_id\":" << this->world << ",\"model_resolution_count\":" << this->modelMatches << ",\"ground_collision_entity_id\":" << this->ground << ",\"preupdate_count\":" << this->preCount << ",\"postupdate_count\":" << this->postCount << ",\"advancing_sample_count\":" << this->sampleCount << ",\"paused_heartbeat_count\":" << this->pausedCount << ",\"duplicate_iteration_count\":" << this->duplicateCount << ",\"epoch\":" << this->epoch << ",\"supports\":{"; for (std::size_t i=0;i<this->supports.size();++i) { const auto &s=this->supports[i]; if(i)this->out<<','; this->out<<'"'<<s.label<<"\":{\"model_entity_id\":"<<s.model<<",\"link_entity_id\":"<<s.link<<",\"collision_entity_id\":"<<s.collision<<",\"component_requested\":"<<(s.requested?"true":"false")<<",\"component_available_seen\":"<<(s.availableSeen?"true":"false")<<",\"valid_contacts\":"<<s.validContacts<<",\"valid_empty_contact_set\":"<<s.validEmpty<<",\"unavailable\":"<<s.unavailable<<",\"component_creation_failures\":"<<s.createFailures<<'}'; } this->out << "}}\n"; this->out.flush(); }

  private: std::array<Support,4> supports;
  private: gz::sim::Entity world{gz::sim::kNullEntity}, ground{gz::sim::kNullEntity};
  private: std::string modelName{"simple_agent"}, groundName{"ground::body::collision"}, outputPath;
  private: std::ofstream out; std::size_t modelMatches{0};
  private: std::uint64_t preCount{0}, postCount{0}, sampleCount{0}, pausedCount{0}, duplicateCount{0}, lastIteration{0}, epoch{0};
  private: std::int64_t lastSimTimeNs{0};
  private: bool configured{false}, haveIteration{false}, pausedLast{true}, groundResolutionReported{false}, epochReady{false};
};
}
GZ_ADD_PLUGIN(aero_diagnostic::ContinuousSupportObserver, gz::sim::System,
    gz::sim::ISystemConfigure, gz::sim::ISystemReset,
    gz::sim::ISystemPreUpdate, gz::sim::ISystemPostUpdate)
