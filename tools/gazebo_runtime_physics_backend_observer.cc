#include <chrono>
#include <fstream>
#include <iomanip>
#include <memory>
#include <string>

#include <gz/plugin/Register.hh>
#include <gz/sim/System.hh>
#include <gz/sim/components/Name.hh>
#include <gz/sim/components/PhysicsEnginePlugin.hh>

namespace aero_diagnostic
{
class RuntimePhysicsBackendObserver final : public gz::sim::System,
    public gz::sim::ISystemConfigure, public gz::sim::ISystemPostUpdate
{
  public: void Configure(const gz::sim::Entity &_entity,
      const std::shared_ptr<const sdf::Element> &_sdf,
      gz::sim::EntityComponentManager &,
      gz::sim::EventManager &) override
  {
    this->worldEntity = _entity;
    if (_sdf && _sdf->HasElement("output"))
      this->output = _sdf->Get<std::string>("output");
  }

  public: void PostUpdate(const gz::sim::UpdateInfo &_info,
      const gz::sim::EntityComponentManager &_ecm) override
  {
    ++this->postUpdateCount;
    const auto *engine = _ecm.Component<gz::sim::components::PhysicsEnginePlugin>(
        this->worldEntity);
    const auto *worldName = _ecm.Component<gz::sim::components::Name>(
        this->worldEntity);
    if (!engine || !worldName || this->output.empty()) return;

    std::ofstream stream(this->output, std::ios::out | std::ios::trunc);
    if (!stream) return;
    stream << std::setprecision(17)
      << "{\"message_kind\":\"runtime_physics_backend_identity\","
      << "\"evidence_source\":\"gz::sim::components::PhysicsEnginePlugin on active world entity\","
      << "\"world_name\":\"" << Escape(worldName->Data()) << "\","
      << "\"world_entity_id\":" << this->worldEntity << ','
      << "\"simulation_time_s\":"
      << std::chrono::duration<double>(_info.simTime).count() << ','
      << "\"iteration\":" << _info.iterations << ','
      << "\"postupdate_count\":" << this->postUpdateCount << ','
      << "\"physics_engine_plugin_library\":\""
      << Escape(engine->Data()) << "\","
      << "\"runtime_identity_confirmed\":"
      << (!engine->Data().empty() ? "true" : "false") << "}\n";
    stream.flush();
  }

  private: static std::string Escape(const std::string &_value)
  {
    std::string result;
    for (const char ch : _value)
    {
      if (ch == '\\' || ch == '"') result.push_back('\\');
      if (ch == '\n') { result += "\\n"; continue; }
      if (ch == '\r') { result += "\\r"; continue; }
      result.push_back(ch);
    }
    return result;
  }

  private: gz::sim::Entity worldEntity{gz::sim::kNullEntity};
  private: std::string output;
  private: std::uint64_t postUpdateCount{0};
};
}

GZ_ADD_PLUGIN(aero_diagnostic::RuntimePhysicsBackendObserver,
    gz::sim::System,
    gz::sim::ISystemConfigure,
    gz::sim::ISystemPostUpdate)
