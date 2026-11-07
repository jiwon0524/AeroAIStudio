// Compile-only public ECM observer + emergency pre-update rejection.
#include <gz/plugin/Register.hh>
#include <gz/sim/System.hh>
#include <gz/sim/components/Name.hh>
#include <gz/sim/components/PhysicsEnginePlugin.hh>
#include <gz/sim/components/Pose.hh>
#include <gz/sim/components/LinearVelocity.hh>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstdint>
#include <limits>
#include <memory>
namespace aero_gate {
class Observer final : public gz::sim::System,
    public gz::sim::ISystemConfigure, public gz::sim::ISystemConfigurePriority,
    public gz::sim::ISystemPreUpdate, public gz::sim::ISystemPostUpdate {
 public:
  gz::sim::System::PriorityType ConfigurePriority() override {
    return std::numeric_limits<gz::sim::System::PriorityType>::min();
  }
  void Configure(const gz::sim::Entity& entity,
      const std::shared_ptr<const sdf::Element>&,
      gz::sim::EntityComponentManager&, gz::sim::EventManager&) override {
    world = entity;
  }
  void PreUpdate(const gz::sim::UpdateInfo& info,
      gz::sim::EntityComponentManager& ecm) override {
    const auto* selection = ecm.Component<gz::sim::components::PhysicsEnginePlugin>(world);
    // A selection component is NOT an active instance/provider attestation.
    const auto ns = std::chrono::duration_cast<std::chrono::nanoseconds>(info.simTime).count();
    std::fprintf(stderr,
      "{\"phase\":\"pre_step_rejected\",\"iteration\":%llu,\"sim_time_ns\":%lld,\"selection_present\":%s,\"active_detector\":\"UNVERIFIED\"}\n",
      static_cast<unsigned long long>(info.iterations), static_cast<long long>(ns),
      selection ? "true" : "false");
    std::fflush(stderr);
    // Never return into Physics Update in this unverified candidate.
    // Scheduler ordering and pre-main initialization remain unverified.
    std::_Exit(78);
  }
  void PostUpdate(const gz::sim::UpdateInfo& info,
      const gz::sim::EntityComponentManager& ecm) override {
    // Incomplete telemetry candidate, not a running or trusted gate adapter.
    if (rows++ >= 100) std::_Exit(83);
    bool found = false;
    ecm.Each<gz::sim::components::Name, gz::sim::components::WorldPose,
             gz::sim::components::WorldLinearVelocity>(
      [&](const gz::sim::Entity&, const gz::sim::components::Name* name,
          const gz::sim::components::WorldPose* pose,
          const gz::sim::components::WorldLinearVelocity* velocity) {
        if (name->Data() != "body") return true;
        const auto p = pose->Data().Pos(); const auto v = velocity->Data();
        std::fprintf(stdout,
          "{\"phase\":\"state_candidate\",\"iteration\":%llu,\"sim_time_ns\":%lld,\"x\":%.17g,\"y\":%.17g,\"z\":%.17g,\"vx\":%.17g,\"vy\":%.17g,\"vz\":%.17g}\n",
          static_cast<unsigned long long>(info.iterations),
          static_cast<long long>(std::chrono::duration_cast<std::chrono::nanoseconds>(info.simTime).count()),
          p.X(), p.Y(), p.Z(), v.X(), v.Y(), v.Z());
        found = true; return false;
      });
    if (!found) std::fputs("{\"phase\":\"state_missing\"}\n", stderr);
  }
 private:
  gz::sim::Entity world{gz::sim::kNullEntity};
  std::uint64_t rows{0};
};
}
GZ_ADD_PLUGIN(aero_gate::Observer, gz::sim::System, gz::sim::ISystemConfigure,
  gz::sim::ISystemConfigurePriority, gz::sim::ISystemPreUpdate, gz::sim::ISystemPostUpdate)
