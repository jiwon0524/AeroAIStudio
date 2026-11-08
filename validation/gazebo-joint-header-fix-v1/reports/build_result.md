# DART spdlog header precedence repair

2026-11-08 UTC. Starting HEAD `a3e2e77b81d606df7068da0a555162c6a9a9de72`, clean experiment/dart-internal-trace, matches requested checkpoint. Required AGENTS/development rules/handoff/previous report/build gate and commands read; context-handoff used.

**SPDLOG_HEADER_SELECTION_FIXED / DART_SIX_LIBRARIES_BUILT_AND_BYTE_IDENTICALLY_STAGED / PHYSICS_CONFIGURE_BLOCKED / joint build INCOMPLETE / NOT_RUNTIME_VERIFIED. Stage B BLOCKED; risk acceptance UNDECIDED.**

## Root cause: compiler defaults, not explicit/transitive local input

Previous actual failed commands are in previous_compile_analysis.json and original `validation/gazebo-joint-selection-fix-v1/logs/dart.build.log`. They explicitly select the new source/build/input directories, /usr/include/eigen3 and fixed deps/usr/include. No -I/-isystem /usr/local appears. CMake chooses spdlog_DIR=/usr/lib/x86_64-linux-gnu/cmake/spdlog and its target's include is /usr/include. That default system directory is omitted from effective CMake compiler include arguments; it does not override GCC's implicit search order. The prepared environment clears CPATH/CPLUS_INCLUDE_PATH/C_INCLUDE_PATH and other variable search roots. No raw host environment was saved.

A compiler-only empty-input `-E -x c++ -v -` query under the same sanitized environment confirms:

```
/usr/include/c++/13
/usr/include/x86_64-linux-gnu/c++/13
/usr/include/c++/13/backward
/usr/lib/gcc/x86_64-linux-gnu/13/include
/usr/local/include
/usr/include/x86_64-linux-gnu
/usr/include
```

Thus /usr/local/include precedes the intended /usr/include. The installed local spdlog version macros report1.9.2, while the contract pins1.12.0. The original compiler guard directly observed and rejected `/usr/local/include/spdlog/spdlog.h`.

Original failed .d files and usable Ninja dependencies were not retained: metadata-only `ninja -t deps` returns missing deps. We did not claim to recover historical depfiles. Instead, the exact two commands were replayed as **preprocessing/dependency generation only**, replacing -c/output/dependency destinations with -M/-MF into this new phase; no object was rebuilt or previous file overwritten. Both reconstructions identify33 local headers, all under /usr/local/include/spdlog (no other local header family). Their exact names/hashes, original commands and reconstructed depfile hashes are in previous_compile_analysis.json; raw new depfiles/default search logs remain local. This reconstruction is current reproducibility evidence, distinguished from the original observed rejection.

## Fixed inputs, compatibility and minimal repair

header_inputs.json verifies107 already-pinned spdlog/fmt header/config files against the unchanged selected_files lock. libspdlog-dev version1:1.12.0+ds-2build1 provides /usr/include/spdlog and /usr/lib/x86_64-linux-gnu/cmake/spdlog; libfmt-dev9.1.0+ds1-2 provides /usr/include/fmt and fmt configuration. Macro versions are SPDLOG1.12.0 and FMT_VERSION90100. Exact config/header/library SHA values are recorded, including spdlog.h/version.h/fmt/core.h and libfmt.so.9.1.0.

New phase `validation/gazebo-joint-header-fix-v1` has separate source/build/prefix. Its inputs/pinned-include contains **99 per-file symlinks**, only to the already-approved /usr/include/spdlog and /usr/include/fmt files. Each source hash is checked; header_overlay.json fixes every link/source/hash. The sole semantic toolchain change appends `-I${CMAKE_CURRENT_LIST_DIR}/pinned-include` to CMAKE_CXX_FLAGS_INIT. The unique include root is retained by CMake and appears before GCC defaults. It contains neither general system headers nor a fallback for other /usr/local files. No package/system/global compiler change, new input approval or lock expansion. toolchain.patch and patch_validation.json prove exact patch replay on a disposable input.

The original compile_gate.py is byte-identical (previous/current SHA in header_inputs/preservation), as are its realpath/hash checks. The overlay's symlinks resolve back to pinned /usr headers. Other actual unapproved headers would still reject. Existing6 targets, empty export namespace, single upstream export registration, directory-local imported-target observation and BUILD_WITH_INSTALL_RPATH=ON/INSTALL_RPATH_USE_LINK_PATH=OFF remain unchanged.3977 source files are byte-identical after observer-path relocation; no C++ source algorithm patch is made.

Generated targets retain spdlog::spdlog_header_only and SPDLOG_FMT_EXTERNAL. Core definitions include FMT_HEADER_ONLY=1 with the existing FMT_SHARED dependency definition. spdlog's config requires external fmt; the actual generated link command selects pinned `/usr/lib/x86_64-linux-gnu/libfmt.so.9.1.0`. All actual logging/format headers are the same approved spdlog1.12/fmt9.1 set, not bundled or local fmt. Final DART DSOs do **not** retain a libspdlog/libfmt DT_NEEDED entry; generated target/link references alone are not claimed as loaded libraries. All retained ELF dependencies were separately checked. This is static build compatibility evidence, not runtime ABI certification.

## Failed units first, then complete DART

Fresh probe configure/selection/build/ELF/component stage/receipt PASS. Fresh DART configure/generate/selected-closure/export checks PASS. Before the full build, first_units.py builds **CAllocator.cpp.o first, then Aspect.cpp.o**, using unchanged compiler launcher and prepared sanitized environment. Both compile PASS; actual Ninja metadata records392 and538 dependencies respectively. Both have zero /usr/local headers, and all observed spdlog/fmt realpaths/hashes match the lock. Object and actual dependency metadata hashes are in first_units.json.

Only after these checks, full DART build runs and exits0 (609.25s). It completes212 object compiles including those two, plus selected library links/symlinks. `actual_headers.json`:212 actual object records,1712 unique dependency files,36 used pinned spdlog/fmt headers, zero /usr/local headers. Original launcher hash-checks each compile; the aggregate Ninja audit independently confirms no local header selection. Actual full logs/dep metadata remain local with source hashes.

Selected six libraries: dart, dart-external-odelcpsolver, dart-collision-ode, dart-collision-bullet, dart-utils, dart-utils-urdf. DART ELF closure gate PASS; selected library, headers and metadata component commands each exit0; strict receipt PASS for all6 libraries. **Probe +6 DART build/prefix ELF files are byte-identical.** No SHA mismatch ignored or install rewrite accepted. Complete SONAME/SHA/Build ID table in elf_summary.md; every ELF's DT_NEEDED/RPATH/RUNPATH in artifacts.json. All7 staged DSOs have no DT_RPATH, and exact DT_RUNPATH new phase/work/config-01/prefix/lib then original gazebo-joint-closure-v1/work/deps/usr/lib/x86_64-linux-gnu, with no empty/unapproved/build path. Staged header completeness is limited by the next failure, even though all library receipts passed.

## First downstream mismatch: gz-physics configuration

Fixed-order continuation reaches physics.configure, exit1 after17.17s. It selects **this prefix** DART_DIR=prefix/share/dart/cmake, DART_INCLUDE_DIRS=prefix/include; DART_LIBRARIES is dart-collision-bullet;dart-collision-ode;dart-utils;dart-utils-urdf;dart. No installed DART fallback is used (cache/trace and physics_blockers.json).

**First feature/header contract mismatch:** dartsim/CMakeLists.txt:51 CHECK_INCLUDE_FILE_CXX returns false for dart/constraint/ContactSurface.hpp, even though that header exists in both source and prefix. Actual check compilation reaches staged dart/common/Deprecated.hpp:36 and fails with `fatal error: dart/config.hpp: No such file or directory`. The generated config header exists at build/dart/dart/config.hpp, SHA in physics_blockers.json, but is absent from prefix. Source dart/CMakeLists.txt:98 installs it without COMPONENT, hence **Unspecified**, which the narrow stage intentionally never invokes. The headers component exits0 without it. This exposes an incomplete generated-header staging policy; the successful ELF receipt does not certify header completeness.

The same configure command then finishes with additional generate errors: upstream gz-cmake export rules and inputs/install-selected.cmake register the same gz-physics7/core/interface/plugin exports twice. First generate error: gz-physics7-all requires gz-physics7-sdf, exported multiple times.12 producer records for6 duplicated sets are in physics_blockers.json; raw logs/trace preserve all diagnostics. BUILD_EXAMPLES is also reported unused. No further patch/retry/guard bypass was made after this command's failure. Physics selected-path gate/build/stage/receipt NOT_STARTED; Sim/harness NOT_STARTED. Next minimum: separately review missing generated-header component membership and downstream export ownership/unused option, preserving these failures; do not invoke Unspecified/all-target install or broaden installation to make them disappear.

Physics also reveals one `try_run` **command** in GzCheckSSE.cmake:133. Its source deliberately uses #error architecture detection (upstream comments explicitly say it never needs to run); CMakeConfigureLog records compile exit1, diagnostic `#error cmake_ARCH x86_64`, no link or run exit result. Thus no architecture-probe target was executed. Probe/DART traces have try_run0; physics has1, recorded truthfully rather than declaring all-zero. The existing deny emulator exits125 if asked to run any target, but this probe never reached that point. The initial final-inventory assertion expecting zero calls exposed this distinction; it was changed only to record the observed physics count after reviewing source/log, not to approve target execution. No physics subject loading/execution occurred; this remains command/trace evidence, not syscall tracing.

## Artifacts, preservation and publication

artifacts.json inventories240 ELF/helper/object files with SHA-256/Build ID/SONAME/DT_NEEDED/RPATH/RUNPATH (empty where not applicable). This includes unexecuted compiler/configure helper ELFs as inventory only. Seven accepted prefix/build pairs are checked by bytes and receipt hash. Prior phase ELF hashes and all source bytes are rechecked; original main/dirty files, previous input/failure/receipt/logs and markers are preserved. Header overlay links are verified again at completion. Original main and system/package configuration were not changed.

All observed commands have exited; first_units/steps contain host/PID/start identity, output path/hash and exit code. No existing task terminated/restarted. Project-CWD scan covers only visible same-user processes; external-CWD/remote/container/other namespaces UNKNOWN. No DART/Gazebo target execution/loading, CTest, physics step, service, marker consumption, sudo, package install or system setting change. No Stage B or risk acceptance change.

Only verified lightweight patch/manifests/recording scripts/reports/handoff are published. Raw traces/build logs/dependency records,99 local include links, source/deps/build/binaries remain local/ignored; Git does not transfer them and /tmp is not durable. Final result is successful DART library/header-selection repair with **downstream header staging/configuration blocked**, not a completed joint stack or execution-ready artifact.

Configure artifact note: physics dartsim/CMakeLists.txt creates an unversioned symlink via a relative create_symlink command. Because the fixed runner CWD is the experiment root, new `libgz-physics-dartsim-plugin.so` appears there as an untracked dangling link. configure_links.json records target and trace provenance. It is preserved and excluded from publication; no target ELF was built or executed through it.
