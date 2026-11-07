// Prepared only: this executable must never be run outside the approved sandbox.
#include <dart/dynamics/Skeleton.hpp>
#include <cstdio>
#include <cstring>
#include <memory>
#include <poll.h>
#include <unistd.h>
int main(int argc, char** argv) {
  if (argc != 2 || std::strcmp(argv[1], "--owned-skeleton-once")) return 77;
  // Dynamic-loader constructors precede main. No Skeleton before external GO.
  std::puts("{\"phase\":\"post_open_ready\",\"result\":\"WAIT\"}");
  std::fflush(stdout);
  char permission[4] = {};
  // One bounded read; partial input is rejected, never retried.
  pollfd input{STDIN_FILENO, POLLIN, 0};
  if (poll(&input, 1, 3000) != 1 || !(input.revents & POLLIN) ||
      read(STDIN_FILENO, permission, 3) != 3 || std::strcmp(permission, "GO\n")) return 78;
  try {
    auto owner = dart::dynamics::Skeleton::create("AeroEmptyLifetime");
    if (!owner || owner->getNumBodyNodes() != 0 || owner->getNumJoints() != 0) return 20;
    std::weak_ptr<dart::dynamics::Skeleton> observer(owner);
    if (observer.expired()) return 21;
    std::puts("{\"phase\":\"created\",\"empty\":true}");
    owner.reset();
    if (!observer.expired()) return 22;
    std::puts("{\"phase\":\"lifetime_success\",\"expired\":true}");
    return std::fflush(stdout) == 0 ? 0 : 24;
  } catch (...) {
    std::fputs("{\"phase\":\"exception\",\"result\":\"STOP\"}\n", stderr);
    return 23;
  }
}
