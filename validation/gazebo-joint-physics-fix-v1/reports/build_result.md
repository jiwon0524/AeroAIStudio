# gz-physics configure repair and joint build continuation

2026-11-08 UTC. Starting HEAD `c699442a14f4764d92f80afd9648e64dc6fc9d86`, experiment/dart-internal-trace; tracked tree clean, pre-existing untracked dangling libgz-physics-dartsim-plugin.so preserved. Required instructions, handoff, preceding build_result/elf_summary and build gate/commands read; context-handoff used.

**DART_REUSED_WITH_MATCHING_GENERATED_HEADER / PHYSICS_BUILT_STAGED_RECEIPT_PASS / SIM_CONFIGURE_GENERATE_PASS / SIM_CODEGEN_INPUT_BLOCKED / joint build INCOMPLETE / NOT_RUNTIME_VERIFIED. Stage B BLOCKED; risk acceptance UNDECIDED.**

## Missing generated DART header

Original source dart/CMakeLists.txt:92-98 configures dart/config.hpp.in into the previous successful build's `build/dart/dart/config.hpp`, then installs it without a component. The selected headers component therefore omitted it; DART include paths were correct. No host header substitution is needed.

Reused header source:
`validation/gazebo-joint-header-fix-v1/work/config-01/build/dart/dart/config.hpp`
SHA-256 **3e79ca3e9c6fbf904948d7a26ca2b08d71c621a6c7f4f51adb8d5d84548f49de**.

The unchanged generated settings include DART6.13.2, RelWithDebInfo1, HAVE_BULLET/HAVE_ODE/HAVE_FLANN/HAVE_OCTOMAP1, NLOPT/IPOPT/PAGMO/SNOPT0, SIMD0 and the original source/data path constants. Full header/settings and lineage are in dart_reuse.json. The old successful DART actual dependency record references this generated header161 times. Existing7 ELF receipt entries (probe +6 DART libraries), both build and prefix files, were rehashed and byte-compared before reuse. DART was **not rebuilt**.

Fresh `work/config-01/prefix` is a byte-preserving copy of the preceding400 regular prefix files (symlinks preserved separately). The guarded inputs/stage-generated-header.cmake installs **only** the matching generated config.hpp from that same DART build to new prefix/include/dart/config.hpp, checking source SHA before install and equality after. It is an explicit corrected staging rule, not Unspecified/all-target installation. No generated macro value or original file was edited. dart_reuse.json binds every reused ELF/copy/build source and header identity.

Fresh physics CHECK_INCLUDE_FILE_CXX(ContactSurface.hpp) now succeeds. After physics compilation, actual Ninja dependencies confirm new prefix/include/dart/config.hpp with the same3e79… SHA:25 object records,1572 unique dependency paths, zero /usr/local headers. actual_header_selection.json and local raw physics.actual_deps.txt are the evidence. The original compiler launcher remains unchanged and rejects unpinned realpath/hash inputs. Approved spdlog/fmt overlay, ABI flags, selected SDK allowlist, BUILD_WITH_INSTALL_RPATH=ON and INSTALL_RPATH_USE_LINK_PATH=OFF remain unchanged.

## Duplicate export: same cause as DART, narrow ownership fix

Original physics_blockers from preceding phase records six duplicated sets: gz-physics7, gz-physics7-sdf, gz-physics7-heightmap, gz-physics7-mesh, gz-physics7-dartsim, gz-physics7-dartsim-plugin. /usr/share/cmake/gz-cmake3/cmake3/GzPackaging.cmake:373 and the prepared install-selected.cmake:41 both register install(EXPORT) for identical files/destinations with namespace **gz-physics7::**. Upstream install(TARGETS ... EXPORT ...) owns target membership; the duplicate install(EXPORT) rules own file deployment, not new target membership. This is the same cross-export ambiguity as the earlier DART failure.

The installed module is unchanged. A separately hash-verified local copy of its definitions changes only COMPONENT for these exact six sole upstream registrations to aero-joint-cmake; all other exports stay Unspecified. A single include in the fresh physics root activates the local definitions before packaging. The redundant physics install(EXPORT) in the staging layer is removed; selected library/header/config/pc/plugin-directory rules stay. Namespace, public target names and transitive dependencies are unchanged. physics_exports.json verifies one registration and one generated export target for each6 set. Patches and source/local SHA in packaging_origin.json/GzPackaging.patch record the boundary. The unused physics BUILD_EXAMPLES argument was removed because source/trace showed no option or effect.

Sim's first configure consumes the new physics package successfully but encounters the same duplicate-registration pattern for its own gz-sim8/gz-sim8-physics-system sets. The failed source/build/log are preserved. A separate src/sim-02 and build/sim-02 repeat the same narrow fix using a distinct local GzPackaging-sim.cmake and install-selected-sim.cmake; earlier physics inputs remain frozen. Only2 selected Sim export registrations receive the metadata component, namespace **gz-sim8::** and target membership/transitive refs unchanged. Sim attempt2 configure/generate PASS; sim_exports.json verifies both sole exports. No broad install or extra system target was introduced.5 patch replay tests PASS on disposable files (patch_tests.json); upstream/full package copies are local inputs, not published external packages.

## Reuse is path-bound, not an ELF relocation

Reused DART/probe ELF bytes retain their approved original RUNPATH pointing to previous prefix/lib and the fixed deps directory. DART export metadata also retains an absolute link reference to the original probe. New prefix copies are identical, but this does not make old artifacts independently relocatable. Both old and new prefix file identities are retained explicitly; the original prefix must remain available for any future separately authorized loader validation. No RPATH or compiled prefix constant was rewritten.

The first physics selection attempt conservatively rejected the old absolute probe path because the checker had not connected it to the already-authorized reuse manifest. Original failure log is preserved. After recorded review, the checker accepts **only exact reused realpath+SHA pairs**, not the old prefix directory generally, and verifies their actual hash again. Recheck PASS; source/phase/argv unchanged. review metadata and both attempts are in reuse_binding_review.json/steps.json. Existing SDK allowlist and installed-stack rejection are unchanged.

Post-link ELF audit recognizes these exact staged predecessors, including old-prefix dependencies discovered by their real RUNPATH, and verifies hashes. It permits the old RUNPATH only on the original/reused ELF identities, not on newly built physics outputs. New physics RUNPATH is exactly new prefix/lib + the existing deps lib directory. This is honest static path resolution, not assumed loader equivalence or runtime certification.

## Completed stages and actual package consumption

- DART/probe: reused, not rebuilt;7 receipt entries and all400 prefix regular-file contents verified unchanged. Matching generated config header newly staged.
- physics configure/generate PASS; ContactSurface test1; selected2-target File API/Ninja build closure PASS. Generation-time imported-target scope fix retained.
- physics build PASS98.28s,25 actual compiled objects; no /usr/local headers; actual config path/hash verified.
- physics ELF closure PASS; selected library, headers and metadata component stage commands PASS; receipt PASS. New physics core and dartsim plugin plus its second engine-plugin copy are byte-identical to build outputs.
- Sim reads new prefix's gz-physics7 base and dartsim/heightmap/mesh/sdf package configs (all version7.8.0). All five DIR cache entries are in this prefix; sim_consumer.json records real configure consumption. No installed physics fallback. After the separate duplicate-export fix, Sim configure/generate PASS.
- Sim selected-build inspection remains BLOCKED; no Sim code generation/compile/link/stage and no harness configure/build/execution.

For physics, the original checker pattern of scanning every imported optional target was narrowed consistently with the already-validated DART gate: CMake File API generated2-target build closure supplies effective compile/link inputs; Ninja -t commands independently records actual selected build commands without executing them. All executed configure file hashes are still checked. Raw optional property snapshots remain intact. Three disposable negative cases PASS_REJECTED: injected unapproved selected library, wrong reused ELF hash, missing ContactSurface result. A real contract omission described below is not accepted merely to advance the build.

## First out-of-contract input: Sim protobuf descriptor

Sim attempt2 selected metadata contains four private protobuf generation commands and a factory generator. The current conservative command classifier rejects these new command forms and cannot yet resolve -lstdc++fs via its short directory list. Read-only review shows both generator scripts, protoc, gz-msgs10_protoc_plugin and GCC13 libstdc++fs.a already match their fixed SDK/toolchain SHA values (codegen_existing_inputs.json); the archive's location was confirmed by the pinned compiler's -print-file-name query. These findings are not a Sim selection PASS and no generator was executed.

However the four selected generation commands require **/usr/share/gz/protos/gz-msgs10.gz_desc** via --dependency-proto-descs. That file is absent from **both** selected_files.json and the toolchain inventory; this is a genuinely unapproved build data input, not an unused imported-target false positive. The generator passes it to protoc as a dependency descriptor. Required file details:

- Package **libgz-msgs10:amd64 10.4.0-1~noble**, source gz-msgs10 same version (local dpkg ownership/version metadata).
- Realpath **/usr/share/gz/protos/gz-msgs10.gz_desc**,83796 bytes.
- SHA-256 **c7e1d435538f1a009d034a1e237d3a9a41233aaf9846e41e02525163b1cc5861**.
- Used by peer_control.proto, peer_info.proto, performer_affinity.proto and simulation_step.proto generation for the selected Sim core. Factory registration generation depends on those outputs.

Stop here as requested: adding this descriptor (and reviewing any further codegen data) requires a build-contract input change. We did not add it to the lock, ignore mismatches, execute generators, use generated files from an installed Sim, install packages or start services. sim_codegen_blocker.json preserves the required-input evidence; strict selector failure and metadata command log remain local. Next minimum: decide explicit descriptor/data input pinning, then review exact already-pinned codegen command classes/compiler library resolution before any Sim build. Do not simply disable the rejecting checks.

## ELF results, limits and preservation

New core SONAME **libgz-physics7.so.7**, SHA-256 **06bdf00cda17153e57e1b00194fc90264bde9d466ab9fc521407ee9152f4194b**, Build ID **3f0ab788985f00cc3965990abd36d327e6773c26**.

New plugin SONAME **libgz-physics7-dartsim-plugin.so.7**, SHA-256 **c652c1af1ccf37d0dcc0b185849045a41f074262ad8a6a7c6f38e75ddecc370c**, Build ID **dfaac182e5227709a5743c64698f9e798053eb80**; both staged plugin locations match build bytes.

artifacts.json records49 ELF/helper/object entries with SHA, Build ID, DT_NEEDED, SONAME, RPATH/RUNPATH and10 accepted prefix/build identity pairs (7 reused + core +2 plugin copies). elf_summary.md is the compact table. New physics outputs have no DT_RPATH, no empty/unapproved/build-directory RUNPATH entry. Reused7 keep original approved RUNPATH unchanged. Static dependency audit verifies exact predecessor hashes and existing external allowlist; no dynamic loading/mapping was performed. Compile/configure helpers are inventory only, not subject execution evidence.

Original main/dirty work, old sources/inputs/evidence/ELFs/receipt and the pre-existing root dangling symlink are preserved. New configure CWD is the corresponding new build directory, so physics's relative symlink stays there instead of overwriting the old root link. Patches/input changes and CWD reason are recorded. Existing processes were not terminated/restarted; all commands launched here have exited, host/PID/start identity/log hashes in steps and sim_retry_steps. Snapshot visibility covers only visible same-user project-CWD tasks; external-CWD/remote/container/other namespaces UNKNOWN.

GzCheckSSE's1 try_run command per physics/Sim configure remains the pinned intentional #error architecture-compiler protocol: compile fails before link/run, run result absent, no target executed. Existing deny emulator remains in place. No DART/Gazebo loading, target execution, CTest, physics step, marker consumption, service, sudo, package install or system setting change. Command/trace evidence is not syscall tracing. Stage B BLOCKED and risk UNDECIDED remain unchanged.

Only verified lightweight patches/guards/metadata tests/recording scripts/reports/handoff are published. Full module/input/source copies, unverified future Sim command-classifier work, old/new ELF libraries, raw logs/trace/dependency/command records and prefixes remain local/ignored. Git does not transfer them; /tmp is not durable and path-bound reused artifacts require their original input locations. No execution readiness or whole joint-build completion is claimed.
