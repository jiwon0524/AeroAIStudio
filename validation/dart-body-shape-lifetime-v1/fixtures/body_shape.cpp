// Compile/link preparation only. Run solely through the separately approved sandbox.
#include <dart/dynamics/Skeleton.hpp>
#include <dart/dynamics/BodyNode.hpp>
#include <dart/dynamics/ShapeNode.hpp>
#include <dart/dynamics/WeldJoint.hpp>
#include <dart/dynamics/BoxShape.hpp>
#include <cstdio>
#include <cstring>
#include <memory>
#include <poll.h>
#include <unistd.h>

int main(int argc, char** argv) {
  if (argc != 2 || std::strcmp(argv[1], "--owned-body-shape-once")) return 77;
  // Dynamic startup constructors precede this gate; no test objects before GO.
  std::puts("{\"phase\":\"post_open_ready\",\"result\":\"WAIT\"}");
  if (std::fflush(stdout) != 0) return 24;
  char permission[4] = {};
  pollfd input{STDIN_FILENO, POLLIN, 0};
  if (poll(&input, 1, 3000) != 1 || !(input.revents & POLLIN) ||
      read(STDIN_FILENO, permission, 3) != 3 || std::strcmp(permission, "GO\n")) return 78;
  try {
    auto owner = dart::dynamics::Skeleton::create("AeroBodyShapeLifetime");
    if (!owner) return 20;
    std::weak_ptr<dart::dynamics::Skeleton> skeletonWeak(owner);
    // Returned pointers are borrowed. The Skeleton owns the BodyNode and its joint.
    {
      auto pair = owner->createJointAndBodyNodePair<dart::dynamics::WeldJoint>(nullptr);
      if (!pair.first || !pair.second || owner->getNumBodyNodes() != 1 ||
          owner->getNumJoints() != 1 || owner->getBodyNode(0) != pair.second ||
          pair.second->getParentJoint() != pair.first) return 20;
      auto shape = std::make_shared<dart::dynamics::BoxShape>(Eigen::Vector3d::Constant(0.1));
      std::weak_ptr<dart::dynamics::Shape> shapeWeak(shape);
      auto* node = pair.second->createShapeNode(shape);
      if (!node || pair.second->getNumShapeNodes() != 1 ||
          node->getShape().get() != shape.get() || node->getBodyNodePtr().get() != pair.second ||
          skeletonWeak.expired() || shapeWeak.expired()) return 21;
      std::puts("{\"phase\":\"created\",\"skeletons\":1,\"bodies\":1,\"joints\":1,\"shape_nodes\":1,\"shape_owner_matches\":true}");
      // Drop the fixture's strong reference first. ShapeNode must retain the shape.
      shape.reset();
      if (shapeWeak.expired()) return 22;
      std::puts("{\"phase\":\"external_shape_released\",\"shape_retained\":true}");
      // No manual delete of borrowed pointers; normal owner release only.
      owner.reset();
      // No access through pair/node after reset. These weak observers do not own objects.
      if (!skeletonWeak.expired() || !shapeWeak.expired()) return 22;
      std::puts("{\"phase\":\"owner_release_observed\",\"skeleton_expired\":true,\"shape_expired\":true,\"individual_destructors\":\"NOT_OBSERVED\"}");
    }
    std::puts("{\"phase\":\"lifetime_success\",\"scope\":\"normal_owner_release_only\",\"individual_destructors\":\"NOT_OBSERVED\"}");
    return std::fflush(stdout) == 0 ? 0 : 24;
  } catch (...) {
    std::fputs("{\"phase\":\"exception\",\"result\":\"STOP\"}\n", stderr);
    return 23;
  }
}
