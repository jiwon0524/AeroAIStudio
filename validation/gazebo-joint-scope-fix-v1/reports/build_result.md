# DART imported-target scope repair

2026-11-08 UTC. Starting HEAD `53bce23dc3f3ef7b830779777d19a759423e8399`, clean `experiment/dart-internal-trace`, matches user checkpoint. Required AGENTS/development rules/handoff/previous build_result/build_gate/build_commands read; context-handoff used.

**IMPORTED_TARGET_SCOPE_FIXED / DART_GENERATE_BLOCKED / joint build INCOMPLETE / NOT_RUNTIME_VERIFIED. Stage B BLOCKED; risk acceptance UNDECIDED.**

## Root cause and actual package selection

Original failure log: `validation/gazebo-joint-build-fix-v1/logs/dart.configure.log:744`; original trace: that phase's `work/config-01/logs/dart.trace.jsonl`. Call path: DART root CMakeLists:680 → install-selected.cmake:57 → export-targets.cmake:24 recursive aero_export_dir → line10 get_target_property. First failing target is exactly **OpenGL::OpenGL**, not an unexpanded variable or spelling mismatch.

All15 failing names were actually declared before the failed queries. Original trace definition locations and SHA are in `scope_result.json` (full per-property query/observer-insertion list remains local `scope_analysis.json`). Actual providers:

|Exact target names|Selected definition file and original line|
|---|---|
|OpenGL::OpenGL, OpenGL::GLX, OpenGL::GLES2, OpenGL::GLES3, OpenGL::GL, OpenGL::EGL, OpenGL::GLU|/usr/share/cmake-3.28/Modules/FindOpenGL.cmake:556,573,596,630,670,685,702|
|GLUT::Xi, GLUT::Xmu|/usr/share/cmake-3.28/Modules/FindGLUT.cmake:129,135|
|ODE::ODE|preserved DART source cmake/DARTFindODE.cmake:16|
|Bullet|same source cmake/DARTFindBullet.cmake:15|
|flann|same source cmake/DARTFindflann.cmake:18|
|lz4|same source cmake/Findlz4.cmake:46|
|tinyxml2::tinyxml2|/usr/lib/x86_64-linux-gnu/cmake/tinyxml2/tinyxml2-shared-targets.cmake:69|
|urdfdom|same source cmake/DARTFindurdfdom.cmake:24|

The DART source here is the preceding fix phase's `work/config-01/src/dart`, not installed DART. Module/installed config definition SHA values match the existing locked files; source definition bytes match preserved originals. Selected ODE/Bullet/urdfdom dependency paths and imported include/link/location properties are in recovered_targets in scope_result.json. No substitute installation was selected.

**Failure class: visibility.** DIRECTORY IMPORTED_TARGETS can enumerate names declared in a child directory, but get_target_property still resolves names in its current execution directory. Recursing a function with a child-directory string from the root does not switch that directory scope. Non-GLOBAL imported targets remain visible only in their declaring directory and descendants. Declaration order is contradicted by the preceding add_library records; package absence/name mismatch is contradicted by exact declarations and successful local-scope property queries after the fix. Local installed CMake Help/command/add_library.rst (Imported Libraries) and Help/command/cmake_language.rst (Deferring Calls) were consulted alongside execution evidence.

## Minimum observer repair and preserved policy

New phase `validation/gazebo-joint-scope-fix-v1`; new source/build/prefix under `work/config-01`. Two small observer files implement directory-local collection: export-targets.cmake schedules one DEFER callback per directory; snapshot-current.cmake retains the original strict get_target_property/property list/output format and performs it at that directory's end. It does not skip absent targets, catch errors or promote imports GLOBAL. Each source CMakeLists receives one observer include so the callback is scheduled while its directory is active, including return paths. No compilation source/algorithm/package file is changed.

Observer includes were mechanically inserted in267 CMakeLists files across the isolated3 source copies plus inputs. Only84 DART directories actually processed; all84 have scope snapshots, none missing. All15 formerly failing target names now have successful property snapshots. The observer currently collects per-directory end state rather than recursively reading child imports from the root. Input hashes are in input_hashes.json; original/new insertion hashes and exact paths in local scope_analysis.json.3977 copied source files were compared; only CMakeLists observer prefixes differ. Other source bytes and original trees are unchanged.

Search change is solely phase relocation for source/input/build/prefix. Existing deps realpath and selected_files allowlist remain unchanged through read-only reuse symlinks. The added observer files are explicit new local observation inputs, hash-recorded. Existing sanitized environment, toolchain ABI/header launcher, BUILD_WITH_INSTALL_RPATH=ON, INSTALL_RPATH_USE_LINK_PATH=OFF and byte-identical receipt contract are retained. No host package/config/header/library allowlist expansion.

## Passed stages and first downstream blocker

New probe configure → selection(96 pinned external files) → compile2/link → static7-node closure → selected-component install → receipt all PASS. Six external ELF paths/hashes match the previous allowlist closure. Probe build and prefix are byte-identical, SHA-256 `6154c4568d53882feea1899bed3f46b6faf21cb760264e1c45b73920e7f31aea`, Build ID `f0abbe763e05f61f2abc577cf1598d8db003a3ec`; SONAME libaero-joint-probe.so.1; DT_NEEDED libcrypto.so.3, libstdc++.so.6, libgcc_s.so.1, libc.so.6. No DT_RPATH. DT_RUNPATH is exactly new phase/work/config-01/prefix/lib followed by original gazebo-joint-closure-v1/work/deps/usr/lib/x86_64-linux-gnu. No empty entry/unapproved directory/build path. Generated probe install script has no RPATH_CHANGE. Complete absolute paths/metadata/receipt in artifacts.json, including11 generated ELF/helper/object entries; helpers are not executed or certified runtime outputs.

DART now reaches `Configuring done`, with no non-existent-target lookup error, but **generate fails, command exit1**. First new error at logs/dart.configure.log:745: exported `dart` requires `dart-external-odelcpsolver`, exported multiple times. Additional selected consumers collision-ode/collision-bullet/utils/utils-urdf show equivalent errors.

Actual duplicate registrations in the new trace:

- Source `src/dart/cmake/Components.cmake:72`: install(EXPORT dart_component_external-odelcpsolver FILE dart_external-odelcpsolverTargets.cmake DESTINATION share/dart/cmake).
- New phase `inputs/install-selected.cmake:13`: the same export/file/destination, additionally COMPONENT aero-joint-cmake.

Likewise dart_component_dart is registered twice. The upstream target dependencies are legitimate; the prepared component-only staging layer adds a second install(EXPORT) registration. CMake rejects cross-export dependencies where their provider is exported multiple times. This is a distinct generation/staging-policy conflict, not a recurrence of the scope failure or evidence of a missing external library. Exact two producer records are retained in scope_result.json; full trace/log remain local.

Stopped on this first downstream failure. DART configure/generate as a complete command is NOT_PASS; actual DART selection gate NOT_RUN/NOT_PASSED, DART compilation/link/stage/receipt NOT_STARTED. gz-physics/Sim/harness NOT_STARTED. No newly built DART/physics/Sim/harness ELF exists. Next minimum: separately review how to assign the selected component to a single upstream export registration without duplicate exports, unbuilt-target staging or skipping path checks. No such further change/retry was made in this task.

## Evidence, preservation and limits

steps.json records observed command exit codes, host/PID/start identity, duration and log SHA/path. Original53bce23 probe ELF hashes rechecked unchanged. Main remains46134c6 with its prior modified/untracked file list untouched; no main/source/evidence/marker write. New scope files/properties, input hashes, exact commands and static inspection reports accompany the fix. Uncompiled generalized preparation/runner and raw logs/trace/source/deps/build/binaries remain local/ignored; Git does not transfer them and /tmp is not durable.

Both configure traces have zero try_run commands. No subject DART/Gazebo execution/loading, CTest, ldd, step, services, marker consumption, sudo/install/system setting change. Command/trace audit is not syscall tracing. All observed commands exited; no process left running by this task. Snapshot covers only same-user project-CWD processes; external-CWD/remote/container visibility UNKNOWN. No existing process terminated/restarted. Stage B BLOCKED and risk UNDECIDED remain unchanged.
