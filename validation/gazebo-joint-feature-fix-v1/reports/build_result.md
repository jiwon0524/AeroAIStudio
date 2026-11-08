# RetrieveWorld optional contract repair and stopped joint build

2026-11-08 UTC. Branch experiment/dart-internal-trace. Starting HEAD and live remote both b82792eb0b269f355cebcecfbcaa6fdb4988feef; previous codegen checkpoint had 37 staged files and no commit/push. Required instructions, rules, handoff and previous build report read; context-handoff used.

**PHYSICS_FEATURE_CONTRACT_FIXED / SIM_BUILD_STATIC_STAGE_RECEIPT_PASS / HARNESS_SELECTION_BLOCKED / joint build INCOMPLETE / NOT_RUNTIME_VERIFIED. Stage B BLOCKED; risk acceptance UNDECIDED.**

## Contract evidence and minimum change

The two JointInit/JointValidate casts request exactly `physics::FeatureList<physics::dartsim::RetrieveWorld>`. WorldEntityMap lacked that exact optional list; EntityFeatureMap.hh correctly rejected it at its existing static_assert. The isolated instrumented Sim Physics.cc now adds only that exact list to WorldEntityMap. It is optional, not added to MinimumFeatureList or general engine requirements. Both callers remain confined to the existing joint observer path. Production/main source is untouched. Patch: optional_retrieve_world.patch; old isolated Physics.cc is preserved at ../work/Physics.cc.before with hashes in contract.json.

Provider source chain: dartsim/src/CustomFeatures.hh declares CustomFeatureList<RetrieveWorld> and CustomFeatures : Implements3d<CustomFeatureList>; plugin.cc includes CustomFeatureList in DartsimFeatures, derives Plugin from CustomFeatures and registers GZ_PHYSICS_ADD_PLUGIN(Plugin, FeaturePolicy3d, DartsimFeatures). CustomFeatures.cc's instrumented GetDartsimWorld returns worlds.at(identity). World.hh defines the typed feature interface and WorldPtr return. WorldEntityMap uses EntityFeatureMap3d, which fixes FeaturePolicy3d. Built provider ELF exports CustomFeatures::GetDartsimWorld and virtual thunk (reuse.json). Consumer's actually parsed World.hh is byte-identical to this provider's source (actual_headers.json). No provider feature/policy declaration was changed; provider implementation and registration were already compiled in the reused ELF. Runtime registration availability remains untested.

No static_assert/type check/cast was removed or weakened. Missing proxy still returns false in JointInit and JointValidate; null native world, identity, initial zero-time/frame, solver/detector checks and GO rejection path are unchanged. Failure would stop at compiler/feature boundary. No runtime-negative result is claimed.

## Direct observations and reuse

- Preflight rehashed 10 probe/DART/physics build-prefix receipt pairs, all 22 generated outputs and the prior Sim core. All matched. No DART, physics, codegen or Sim core rebuild was needed.
- Physics.cc.o compiled first through unchanged compile_gate.py and original fixed environment, exit0 (34.83s). Selected command digest equals the previous PASS_STATIC_SELECTED_CLOSURE. Then selected two-target Sim build/link exit0 (0.55s); core reused, Physics system linked.
- Actual Ninja dependencies: 46 object records, 1614 unique dependencies; zero /usr/local inputs. External headers checked against the same selected-file/toolchain locks; RetrieveWorld header SHA d052c92e9d35214fe5f33fd1e82b9c6d4e1f64773b48d51e4ce9f98e9f324030 matches provider.
- Existing audit_outputs_sim.py static recursive ELF closure passed before staging. No loader or ldd used. Narrow library/header/CMake stages all exited0. Existing stage_receipt_sim.py passed. Final rehash confirms 13 unique build/prefix real-file receipt pairs: prior10 plus Sim core and Physics system's two installation locations.
- Harness configure/generate exited0 (4.96s). The exact existing harness.selection command failed exit2: `scripts/check_selection_harness.py` does not exist. First new unmet gate; stopped immediately. No fallback/bypass checker, harness build or later ELF audit was run. logs/harness.selection.log SHA647775910db46e31ff39991d49e17ee3357f3f07f01c96f387729c993b490445. Existing command contract is commands_final.json in the preceding codegen phase. Next minimum: review/implement the missing rejecting harness selection gate, then resume at that boundary with fresh logs; do not replay successful stages.

## Link inputs and ELF deployment

Actual verbose link command and static metadata are in ../logs/sim.build.log, ../logs/selected_link_commands.txt and elf_and_receipt.json. Physics system links build/sim-03/lib/libgz-sim8.so.8.15.0 plus current codegen prefix libdart.so.6.13.2 (SHA42ff81108e013b45ed1b11a1433cea0ea18964d2280d09c61d05d0fbe49b4af4), five selected DART companion libraries and libgz-physics7.so.7.8.0 (SHA06bdf00cda17153e57e1b00194fc90264bde9d466ab9fc521407ee9152f4194b). Explicit transitive probe paths retain approved predecessor prefixes and match SHA9dca4718eda1f970ba0d28e6d2f3233d081b781c2c44438e19b27a87448f43e8. All 61 explicit absolute library operands are recorded with realpath/SHA. The dartsim engine plugin is a separately selected runtime provider, not a direct Physics-system DT_NEEDED entry; it was never loaded.

|ELF|SHA-256|Build ID|
|---|---|---|
|libgz-sim8.so.8.15.0|25b168676e55c1bfb847a92b0648802f916af96bd1730a9344e196632dea9128|2ef698d5755bce23d06410751edb6827b4be233f|
|libgz-sim8-physics-system.so.8.15.0|dfe093dc43a949bc554de3f52223aae3f437759a6378cd5aa22cca5d21423a11|ee1262241b3849de49d3fdfc2c544f00b7b3aeaf|
|reused libgz-physics7-dartsim-plugin.so.7.8.0|c652c1af1ccf37d0dcc0b185849045a41f074262ad8a6a7c6f38e75ddecc370c|previous physics receipt lineage|

Both Sim outputs have no DT_RPATH; DT_RUNPATH is exactly codegen phase work/config-01/prefix/lib plus closure phase work/deps/usr/lib/x86_64-linux-gnu. No empty/build search path. Core is deployed to prefix/lib; Physics system is deployed to prefix/lib and prefix/lib/gz-sim-8/plugins. All bytes equal their source build ELF. Reused ELF path bindings remain unchanged. Static resolution is not actual runtime mapping/ABI certification.

## Preservation and publication

Pre-existing untracked root libgz-physics-dartsim-plugin.so is a 32-byte dangling symlink to relative libgz-physics7-dartsim-plugin.so. Original configure_links.json identifies the 2026-11-08 09:16 UTC relative CMake create_symlink command in physics/dartsim/CMakeLists.txt:73; lstat timestamp matches. No target bytes exist at the resolved root path, so no target ELF hash is available. Preserved untracked, never staged, linked or loaded.

Previous staged evidence preserved byte-for-byte except handoff update; historical reports are not rewritten to claim later success. Isolated Physics.cc original bytes saved before its explicit optional-list edit. Existing raw build/failure/codegen logs and predecessor artifacts retained. Current Sim receipt only adds successful Sim entries. Original main/dirty files, marker contents and policy criteria were not edited or consumed. All launched tasks exited; steps.json records host/PID/start identity/output hashes. Project-CWD process snapshot cannot establish external-CWD/remote/container job state (UNKNOWN).

No DART/Gazebo load or execution, target execution, physics step, service, marker consumption, sudo, package install or system change. Publish reviewed lightweight patch/scripts/reports and prior staged checkpoint only, on experiment branch. Raw logs, original source backup, full source/build/prefix and locks remain local/ignored under /tmp, which is not durable and is not transferred by Git. Stage B BLOCKED and risk acceptance UNDECIDED remain.
