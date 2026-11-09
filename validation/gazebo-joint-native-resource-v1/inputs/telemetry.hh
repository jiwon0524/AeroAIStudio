#pragma once
#include <gz/sim/EntityComponentManager.hh>
#include <gz/sim/Types.hh>
#include <gz/sim/Util.hh>
#include <gz/sim/components/LinearVelocity.hh>
#include <cstdio>
#include <chrono>
#include <stdexcept>
namespace aero_joint {
inline void State(const char *kind, const gz::sim::UpdateInfo &info,
    gz::sim::Entity body, const gz::sim::EntityComponentManager &ecm, int nativeFrame, double nativeTime, unsigned initCount) {
  const auto *velocity=ecm.Component<gz::sim::components::WorldLinearVelocity>(body);
  if (!velocity) throw std::runtime_error("missing measured velocity component");
  const auto pose=gz::sim::worldPose(body,ecm);
  const auto p=pose.Pos(), v=velocity->Data(), e=pose.Rot().Euler();
  const auto t=std::chrono::duration_cast<std::chrono::nanoseconds>(info.simTime).count();
  const auto dt=std::chrono::duration_cast<std::chrono::nanoseconds>(info.dt).count();
  if (dprintf(4,"{\"kind\":\"%s\",\"iteration\":%llu,\"sim_time_ns\":%lld,\"dt_ns\":%lld,\"paused\":%s,\"native_frame\":%d,\"native_time\":%.17g,\"init_count\":%u,\"state_source\":\"measured_live_components\",\"state\":{\"x\":%.17g,\"y\":%.17g,\"z\":%.17g,\"vx\":%.17g,\"vy\":%.17g,\"vz\":%.17g,\"roll\":%.17g,\"pitch\":%.17g,\"yaw\":%.17g}}\n",
    kind,static_cast<unsigned long long>(info.iterations),static_cast<long long>(t),static_cast<long long>(dt),
    info.paused?"true":"false",nativeFrame,nativeTime,initCount,p.X(),p.Y(),p.Z(),v.X(),v.Y(),v.Z(),e.X(),e.Y(),e.Z())<0)
    throw std::runtime_error("observation pipe closed");
}
}
