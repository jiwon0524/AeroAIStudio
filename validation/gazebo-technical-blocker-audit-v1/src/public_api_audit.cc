// Compile/link evidence only. This shared object must never be loaded here.
#include <gz/sim/Server.hh>
#include <gz/sim/Types.hh>
#include <gz/sim/SystemPluginPtr.hh>
#include <gz/sim/components/Physics.hh>
#include <gz/sim/components/PhysicsEnginePlugin.hh>
#include <gz/physics/World.hh>
#include <gz/physics/FeatureList.hh>
#include <cstddef>
#include <string>
#include <type_traits>
#include <utility>

template<class T, class = void> struct HasPublicEngineGetter : std::false_type {};
template<class T> struct HasPublicEngineGetter<T,
    std::void_t<decltype(std::declval<T&>().GetPhysicsEngine())>> : std::true_type {};
template<class T, class = void> struct HasPublicDataPtr : std::false_type {};
template<class T> struct HasPublicDataPtr<T,
    std::void_t<decltype(std::declval<T&>().dataPtr)>> : std::true_type {};
using Features = gz::physics::FeatureList<gz::physics::CollisionDetector>;
using DetectorWorldAPI = gz::physics::CollisionDetector::World<gz::physics::FeaturePolicy3d, Features>;
static_assert(std::is_same_v<decltype(std::declval<const DetectorWorldAPI&>().GetCollisionDetector()), const std::string&>);
static_assert(std::is_same_v<decltype(std::declval<const gz::sim::components::PhysicsCollisionDetector&>().Data()), const std::string&>);
static_assert(std::is_same_v<decltype(std::declval<const gz::sim::components::PhysicsEnginePlugin&>().Data()), const std::string&>);
static_assert(!HasPublicEngineGetter<gz::sim::Server>::value);
static_assert(!HasPublicDataPtr<gz::sim::Server>::value);
// These are public UpdateInfo fields, not guesses at PhysicsPrivate layout.
static_assert(std::is_standard_layout_v<gz::sim::UpdateInfo>);
static_assert(offsetof(gz::sim::UpdateInfo, paused) == 0x20);
static_assert(offsetof(gz::sim::UpdateInfo, iterations) == 0x18);
extern "C" bool audit_public_iteration_is_zero(const gz::sim::Server& server) {
  const auto iteration = server.IterationCount(0);
  return iteration && *iteration == 0;
}
// No Server construction, Run, World creation or loader calls in this artifact.
