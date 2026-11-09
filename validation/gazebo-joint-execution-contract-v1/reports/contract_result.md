# Execution input contract sealed; resource closure BLOCKED

Start HEAD `8526df49971fd0e353ee603c04264c54ae95e708`, experiment/dart-internal-trace. HEAD matched the requested checkpoint; tracked/index state was clean, with only the original dangling root plugin symlink untracked. AGENTS, DEVELOPMENT_RULES, handoff, native_result and the original isolation/resource/ACK contracts were read with context-handoff. Old evidence, binaries, markers, main and dirty files remain preserved.

**Input-contract blocker: RESOLVED_STATIC. DART/ODE/auxiliary-resource blocker: BLOCKED. Stage B BLOCKED; risk acceptance UNDECIDED; actual runtime UNVERIFIED.** No harness, harmless program, native loader, Gazebo/DART, physics step, service, marker, sudo, installation or system configuration was executed/changed. No actual execution approval is submitted.

## One input contract

`reports/manifest.json` and `inputs/manifest.sha256` bind 594 individual RO-file mounts, 429 unique backing FDs, 337 ELF namespace aliases, all SONAME dependency edges, 10 required mapping identities, native packet expectations, 21 code/helper files, host tools, source evidence, unchanged limits and proposed new output/one-shot names. Secondary projections (attestation, allowlist and ordered Bubblewrap argv) must match recomputation from this one manifest. Missing/duplicate SONAME edges, stale projections and old changed-component ELF sources fail validation.

Manifest SHA-256: `789737d947f8c0ebd1466300792667fc9c838adba5834168e5c82bc6e4846aae`.

The native observer and sdformat from native-resource-v1, dartsim, DART/ODE/FCL/support DSOs and FD bridge are reused with exact hash/device/inode identities. New Sim/Physics/harness source artifacts are in `work/prefix/lib` and `work/aero-joint-harness`; `deployment_receipt.json` supplies all paths/hashes/Build IDs and scope. The world keeps its original logical Physics/engine paths: only proposed namespace file-FD overlays change their backing sources. No old host ELF is replaced.

`contract.validate` checks regular read-only source FDs, canonical backing paths, stable metadata and complete SHA-256 before any manager, marker or service operation. `stage.inputs` reopens/checks the same inputs, assigns distinct inherited FDs at or above10, and derives the same ordered `--ro-bind-fd` array; it closes FDs on return/failure. It contains no exec. No directory bind, broad filesystem fallback, inherited loader path or native-execution switch was added.

The new attestor uses manifest namespace paths rather than host `realpath`. In particular, the active ODE method provider is expected at the manifest's exact `.../gazebo-joint-physics-fix-v1/work/config-01/prefix/lib/libdart-collision-ode.so.6.13` SONAME alias, backed by the pinned versioned inode; dartsim uses the fixed explicit engine path. Unexpected module path or mapped inode is rejected. Mapping fingerprints, live PID/start, FIFO identities, four namespaces, RO input mounts and cgroup/rlimit checks are retained. Required IDs are not weakened to basename or digest-only checks.

The allowlist covers logical ELF paths with their actual overlay hashes, including valid SONAME aliases. Native expectations are cross-checked against the same mounted schema/config/plugin identities and the generated harness expectation header. The exact world string is reconstructed from fixture and fixed argv for its hash; no mounted-world-file read is claimed. Previous64-file root schema closure is retained, with the129-file/135-edge inventory unchanged.

The external refusal launcher authenticates the manifest and executes contract source bytes read from a verified FD. `source_loader`/common load pinned helper source bytes directly, bypassing .pyc; stale cached app modules are refused. The integration argv helper is copied into the new attestor, avoiding an implicit old integration module import. No old attestor/plan/collector is selected by ambient import search. `collector.session` assembles the existing ACK state machine with the native ledger; actual lifecycle execution remains unavailable while resource closure is blocked.

## Necessary native ordering correction

Static source inspection found that the previous `Physics::JointInit` emitted the first ready_state *before* native resource complete. Its19 hand-built packet cases did not cover that producer call order. This would fail the native ledger, not silently permit a run. The earlier source/ELF/test reports are retained as historical preparation evidence.

In an independent Sim source copy, that early emission is removed. SimulationRunner now seals resources/emits complete, then performs two separate `JointValidate -> JointState(ready_state)` pairs before WaitGo. Keeping separate provider/native validations avoids reusing a single provider snapshot for both ready packets. GO, zero-state/provider equality,100×1ms/freefall, live final mapping, EXIT_ACK, EOF/exit0 and cleanup criteria are unchanged.

Only SimulationRunner.cc and Physics.cc were compiled; Sim core and Physics were relinked and the harness was recompiled/relinked to the new Physics expectation. DART, gz-physics, sdformat, observer and interfaces were not rebuilt. `ready_order.patch`, `build_steps.json` and `harness_commands.json` record this boundary. First-pass candidate bytes remain under `work/first_order_fix`; later snapshot refinement did not overwrite original phase artifacts.

Reused objects are justified by `object_reuse.json`: relinking the original45 Sim objects and1 Physics object with original linker operands reproduces the previous pinned ELF bytes exactly. New compile dependency audit covers1,482 files/headers; inherited SDK/header hashes match native-resource-v1, and copied headers match the original source. Three new ELF hashes/RUNPATHs are in deployment_receipt. No configure/try-run or target execution was needed.

## Bounded DART/ODE/source-path review

`source_paths.json` indexes15 paths, exact file hashes/line sites and237 actual built source/object bindings from the DART header-fix and physics-fix build trees. This corrects reliance on merely similar source copies. Its lexical I/O inventory is a review aid, never an exhaustive call-graph or syscall-absence proof.

|Path/lifetime|Bounded classification and code basis|
|---|---|
|Schema/conversion/config/world, before GO|Fixed inputs only. Existing native FD/hash/parse/include failure latch; exact manifest identities.|
|Sim pending/system/engine loading|Fixed inputs before seal; deny before lookup/open/LoadLib after seal. Native fatal makes the entire attempt fail.|
|World assets|Nominal fixed box dispatch goes to ConstructBox. No include/URI/mesh/heightmap/visual/texture is present; mesh/Assimp/LocalResource path is excluded for these fixed input branches.|
|Detector factory and IKFast loader|Chosen world construction directly creates default FCL then GzOde; the factory is an in-memory creator map. SharedLibrary::create's selected-source external caller is IKFast, which the fixed free-body forward-dynamics chain does not construct/invoke. This bounded finding does not certify arbitrary external callbacks or whole-library reachability.|
|100 steps|WorldForwardStep -> World::step -> forward dynamics/integration -> ConstraintSolver::solve/updateConstraints -> collision -> integration. Known numeric chain; external collision callbacks remain unresolved.|
|DART's vendored ODE LCP|DantzigBoxedLcpSolver -> external::ode::dSolveLCP is a separate source-bound numeric implementation from the external ODE collision library. It is not a reason to waive collision-provider coverage.|
|External ODE initialization/box/collision/exit|**BLOCKED.** OdeCollisionDetector enters dInitODE2 and related creation, dSpaceCollide/dCollide, dSpaceDestroy/dCloseODE. The matching full libode implementation/build receipt and indirect/TLS callback resource closure are absent; no global native before-access guard was installed. Lack of open imports does not prove absence of internal syscalls/indirect access.|
|Default FCL and auxiliary lifetime|**BLOCKED.** World/ConstraintSolver creates FCL before ODE replacement. External FCL/allocator/support callbacks and cleanup are not source-complete. Active ODE does not erase this initialization.|
|Crypto|**BLOCKED.** VerifyAnchor's EVP_DigestInit_ex/EVP_sha256 and native SHA256 enter libcrypto. Internal provider/configuration access is not source-bound or observed. No assertion is made that a config file was actually opened.|
|Transport/logging and teardown|**BLOCKED.** Sim support/background callbacks and external-library/plugin destructors are not proven free of fallback/resource access. Empty namespaces/no peers and the historical harmless pass cannot supply that proof.|

Seven report rows carry unresolved technical obligations (several share the ODE/teardown boundary). To close them, provide a matching source/binary/build closure proving resource-call reachability for initialization, permitted lifetime and destruction, or install reviewed before-access guards in the exact affected DART/ODE/crypto/auxiliary components and identify their necessary ABI consumers before rebuilding. No speculative DART/ODE or global libc interposition was added. The Sim guard is not misrepresented as a DART/ODE syscall guard.

## Verification and preserved conditions

31 new static/mock cases PASS (`tests.json`, `logs/tests.complete.log`). They reject stale attestor entry/source/cached module, changed provider inode/path, missing mounts/SONAME edges/required mappings, modified allowlist, old ELF/native expectation mixture, argv/FD changes, auxiliary fallback packet and post-GO load/request. They also check a real read-only FD layout without exec, source-only helper imports, and the corrected two independent ready call sites.

A fully synthetic actual-protocol trace passes the reused Gate/AckSession through distinct provider snapshots, GO,100 freefall-valued packets, final live-mapping callback, EXIT_ACK, both EOF, exit0 and cleanup. These are generated packet values and callbacks, not native or physical observations. Mock auxiliary rejection demonstrates policy behavior; it does **not** implement or prove before-access interception in unguarded DART/external DSOs. That is why the resource blocker remains.

Earlier22 resource and19 native static/mock results are reused by exact report hashes, not rerun. Fresh reuse checks preserve170 original ELFs,13 receipt pairs,575 old mounts/428 backing files,129 schema/conversion inputs/135 includes, old ACK/world, original main/dirty evidence and the dangling link. All6 prior native ELF files remain unchanged. Actual old output/one-shot paths remain absent; historical consumed harmless markers remain untouched.

The copied protocol.py is byte-identical to resolution-v1. Existing EOF/exit/ACK/cleanup rejection rules and owned InvocationID/PID-start cleanup helpers remain. Limits are unchanged:512MiB memory/swap0/tasks64/CPU100%; service30s/stop2s/host40s; native CPU10s/AS2GiB/FSIZE1MiB/NOFILE256/CORE0; collection25s/ACK5s; stdout65536/pending16384 and stderr1048576/pending65536 bytes.

## Decision and next minimum

The one static input contract is sealed and the necessary producer-order correction is built. Resource-call closure remains technically BLOCKED. `scripts/launcher.py` is refusal-only, with exit78 before manager/service/marker; proposed new outputs/one-shot paths in the manifest were checked absent, never created or reserved. No executable one-shot launcher command/release option or approval-ready run review is submitted.

Runtime-only evidence would still include actual mount/isolation/cgroup/readback, loader/provider and native outcomes, same PID/start/maps before GO and EXIT_ACK, resource-fit/real-time limits, physical/freefall observations, EOF/exit and owned cleanup/integrity. These cannot be inferred from this build or mocks.

User risk decisions remain separate: Bullet normal lifetime/individual destructors, allocator balance and C-exception cleanup are UNDECIDED. Accepting risk would not repair absent technical access coverage. Stage B stays BLOCKED.

Next minimum: resolve the enumerated external implementation/callback access obligations and only then reconsider runtime release under separate explicit scope/approval. Stop here. Ignored source/build/object/ELF/proof binaries/raw logs and old evidence/markers remain host-local under /tmp, not durable or transferred by Git; device/inode contracts intentionally fail on another machine until reviewed/resealed. Common context-handoff skill was read and not changed.
