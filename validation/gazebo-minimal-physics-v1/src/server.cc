// Compile/link integration candidate. Do not execute this binary in preparation.
#include "adapter.hh"
#include <gz/sim/Server.hh>
#include <gz/sim/ServerConfig.hh>
#include <cstdio>
#include <cstring>
#include <poll.h>
#include <unistd.h>
int main(int argc, char** argv) {
  if (argc != 3 || std::strcmp(argv[1], "--owned-gazebo-gated-once") ||
      std::strcmp(argv[2], "/fixture/minimal.sdf")) return 77;
  // Never construct a world/server with an unavailable live adapter.
  // No input flag/file can promote this compile-only adapter to VERIFIED.
  if (!aero_gate::LiveAdapterAvailable()) {
    std::fputs("{\"phase\":\"blocked\",\"reason\":\"ACTIVE_INSTANCE_ADAPTER_UNAVAILABLE\"}\n", stderr);
    return 78;
  }
  // Defense in depth: this candidate does not yet collect a trustworthy READY
  // attestation. Therefore it never prints READY, and never enables Run below.
  gz::sim::ServerConfig config;
  config.SetInitialSimTime(0.0);
  config.SetPhysicsEngine("/usr/lib/x86_64-linux-gnu/gz-physics-7/engine-plugins/libgz-physics7-dartsim-plugin.so.7.8.0");
  if (!config.SetSdfFile(argv[2])) return 79;
  gz::sim::Server server(config);
  const auto iteration = server.IterationCount();
  if (!iteration || *iteration != 0) return 80;
  const bool trustedReadyCollected = false;  // No private-pointer guessing.
  if (!trustedReadyCollected) return 78;
  char permission[4] = {};
  pollfd input{STDIN_FILENO, POLLIN, 0};
  if (poll(&input, 1, 3000) != 1 || !(input.revents & POLLIN) ||
      read(STDIN_FILENO, permission, 3) != 3 || std::strcmp(permission, "GO\n")) return 78;
  // Candidate API call only. Currently unreachable without a source change,
  // new source hash/contract, and separate approval. No RunOnce bootstrap.
  if (!server.Run(true, 100, false)) return 81;
  const auto finalIteration = server.IterationCount();
  return finalIteration && *finalIteration == 100 ? 0 : 82;
}
