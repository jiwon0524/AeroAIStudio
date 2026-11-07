// Compile/link only until a separate one-shot sandbox execution approval.
#include <dart/dynamics/Skeleton.hpp>
#include <dart/dynamics/BodyNode.hpp>
#include <dart/dynamics/ShapeNode.hpp>
#include <dart/dynamics/WeldJoint.hpp>
#include <dart/dynamics/BoxShape.hpp>
#include <dart/common/Observer.hpp>
#include <dart/common/Subject.hpp>
#include <cstdio>
#include <cstring>
#include <memory>
#include <poll.h>
#include <unistd.h>

// The callback stores bounded scalar data only, with no logging/allocation.
// Subject notification is not an individual derived destructor entry signal.
class Recorder final : public dart::common::Observer {
 public:
  const dart::common::Subject* body = nullptr;
  const dart::common::Subject* node = nullptr;
  unsigned count = 0, bodyCount = 0, nodeCount = 0;
  unsigned order[2] = {0, 0};
  bool window = false, invalid = false;
  void watch(const dart::common::Subject* subject) { addSubject(subject); }
  std::size_t registered() const { return mSubjects.size(); }
 protected:
  void handleDestructionNotification(const dart::common::Subject* subject) noexcept override {
    unsigned id = 0;
    if (subject == node) { id = 1; ++nodeCount; }
    else if (subject == body) { id = 2; ++bodyCount; }
    else invalid = true;
    if (!window || count >= 2 || id == 0) invalid = true;
    if (count < 2) order[count] = id;
    ++count;
  }
};

int main(int argc, char** argv) {
  if (argc != 2 || std::strcmp(argv[1], "--owned-notification-once")) return 77;
  std::puts("{\"phase\":\"post_open_ready\",\"result\":\"WAIT\"}");
  if (std::fflush(stdout) != 0) return 24;
  char permission[4] = {};
  pollfd input{STDIN_FILENO, POLLIN, 0};
  if (poll(&input, 1, 3000) != 1 || !(input.revents & POLLIN) ||
      read(STDIN_FILENO, permission, 3) != 3 || std::strcmp(permission, "GO\n")) return 78;
  try {
    Recorder recorder;  // Outlives owner, including exceptional cleanup.
    auto owner = dart::dynamics::Skeleton::create("AeroSubjectNotification");
    if (!owner) return 20;
    auto pair = owner->createJointAndBodyNodePair<dart::dynamics::WeldJoint>(nullptr);
    if (!pair.first || !pair.second || owner->getNumBodyNodes() != 1 || owner->getNumJoints() != 1) return 20;
    auto shape = std::make_shared<dart::dynamics::BoxShape>(Eigen::Vector3d::Constant(0.1));
    auto* node = pair.second->createShapeNode(shape);
    if (!node || pair.second->getNumShapeNodes() != 1 ||
        node->getShape().get() != shape.get() || node->getBodyNodePtr().get() != pair.second) return 21;
    recorder.body = static_cast<const dart::common::Subject*>(pair.second);
    recorder.node = static_cast<const dart::common::Subject*>(node);
    if (recorder.body == recorder.node) return 21;
    recorder.watch(recorder.body); recorder.watch(recorder.node);
    if (recorder.registered() != 2 || recorder.count != 0) return 22;
    std::puts("{\"phase\":\"registered\",\"bodies\":1,\"shape_nodes\":1,\"subjects\":2,\"callbacks_before_release\":0}");
    shape.reset();
    if (recorder.count != 0) return 22;
    recorder.window = true;
    owner.reset();
    recorder.window = false;
    // Never dereference the stored raw subjects/body/node after owner reset.
    if (recorder.invalid || recorder.count != 2 || recorder.nodeCount != 1 ||
        recorder.bodyCount != 1 || recorder.order[0] != 1 || recorder.order[1] != 2 ||
        recorder.registered() != 0) return 22;
    std::puts("{\"phase\":\"notifications_observed\",\"shape_node_callbacks\":1,\"body_node_callbacks\":1,\"order\":[\"shape_node\",\"body_node\"],\"within_owner_reset\":true,\"subjects_remaining\":0}");
    std::puts("{\"phase\":\"lifetime_success\",\"scope\":\"subject_notifications_only\",\"individual_destructors\":\"NOT_OBSERVED\",\"allocator_balance\":\"NOT_MEASURED\"}");
    return std::fflush(stdout) == 0 ? 0 : 24;
  } catch (...) {
    std::fputs("{\"phase\":\"exception\",\"result\":\"STOP\"}\n", stderr);
    return 23;
  }
}
