# DART duplicate export repair and joint build continuation

2026-11-08 UTC. Starting HEAD `2d5c4f35a426eb75f53bc5a18295e2927a957394`, clean experiment/dart-internal-trace, matches user checkpoint. AGENTS, development rules, handoff, previous build_result and existing build gate/commands read; context-handoff used.

**DART_CONFIGURE_GENERATE_PASS / EXPORT_DUPLICATION_FIXED / DART_SELECTION_BLOCKED / joint build INCOMPLETE / NOT_RUNTIME_VERIFIED. Stage B BLOCKED; risk acceptance UNDECIDED.**

## Exact duplicate rules and downstream contract

`original_export_rules.json` records the preceding phase's actual trace records. Each selected export set contains exactly the following target, with empty namespace:

|Export set|Target|
|---|---|
|dart_component_dart|dart|
|dart_component_external-odelcpsolver|dart-external-odelcpsolver|
|dart_component_collision-ode|dart-collision-ode|
|dart_component_collision-bullet|dart-collision-bullet|
|dart_component_utils|dart-utils|
|dart_component_utils-urdf|dart-utils-urdf|

Source `cmake/Components.cmake:72` performs install(EXPORT): it registers generation/installation of a target metadata file, **not target membership**. Source line168 install(TARGETS ... EXPORT ...) both adds the library to its export set and registers its library/archive installation. Prepared `inputs/install-selected.cmake:10` installs selected library files without EXPORT and therefore does not add export membership. Prepared line13 performs a second install(EXPORT) for each of the6 same sets/file/destination, causing the cross-export ambiguity. Component metadata/config-file install(FILES) rules do not add export membership.

Downstream physics source CMakeLists:75 requests DART CONFIG version>=6.10, components collision-bullet/collision-ode/utils/utils-urdf; DARTConfig appends core dart, recursively visits component dependencies and includes dart_<component>Targets.cmake. The dartsim interface links DART_LIBRARIES, not invented DART:: names. DART6.13.2 exports plain dart/dart-* names with no NAMESPACE. These names and dependency traversal are unchanged. Generated metadata confirms core→external-odelcpsolver; collision adapters→dart plus ODE::ODE/Bullet; utils→dart plus tinyxml2::tinyxml2; utils-urdf→dart-utils plus urdfdom. Core also retains Eigen3::Eigen, ccd, fcl, assimp, fmt::fmt-header-only, spdlog::spdlog_header_only, octomap, dl and approved prefix probe. Complete generated interface references/component scripts in export_validation.json.

## Narrow repair and preserved policy

New phase `validation/gazebo-joint-export-fix-v1`; fresh source/build/prefix under work/config-01. Retain the **upstream sole install(EXPORT)** registration and unchanged install(TARGETS ... EXPORT ...) membership. For exactly the selected6 components, upstream install(EXPORT) receives COMPONENT aero-joint-cmake. Other exports remain Unspecified. Remove only the redundant DART install(EXPORT) from install-selected.cmake; retain library/header/config/Find-module/component metadata installation rules and allowlists.

Simply removing the duplicate without assigning a component would strand the only export install under Unspecified, which the fixed component-only stage deliberately does not invoke. The conditional component assignment keeps the existing narrow stage usable without invoking all-target install or dropping any required target. Both changes are preserved as components.patch and install-selected.patch, with before/after SHA in inputs.json. Only one source file beyond mechanical observer-path relocation changes: cmake/Components.cmake.3977 copied source files were compared; all others retain prior bytes after approved phase relocation. No original source modified.

Directory-local imported-target observation remains unchanged. BUILD_WITH_INSTALL_RPATH=ON, INSTALL_RPATH_USE_LINK_PATH=OFF, strict SHA receipt equality, selected package/header/library allowlist and dependency realpath are unchanged. Search/input/output paths relocate only to the new phase; deps and selected_files are read-only reused references. Exact commands/environment in build_commands.txt; no old source helper replay. Input hashes in inputs.json. Unchanged allowlist was not broadened to pass the new selection errors.

## Actual stages and first downstream blocker

New probe configure/selection(96 pinned external files)/compile2/link/static7-node closure/component install/receipt PASS. Build and prefix bytes identical. SHA-256 **c741f5460c64d7fb9fc426e3acaaffeaffae367b516893a5fe96cf1d836f3fa8**, Build ID **45aee3a9f02c252bc661e4312484428606f1f0c8**, SONAME libaero-joint-probe.so.1. Direct NEEDED libcrypto.so.3, libstdc++.so.6, libgcc_s.so.1, libc.so.6;6 external files including transitive libm/loader match previous allowlist hashes.

Probe DT_RPATH absent; DT_RUNPATH exactly new phase/work/config-01/prefix/lib then original gazebo-joint-closure-v1/work/deps/usr/lib/x86_64-linux-gnu. No empty/unapproved/build-directory entry. Probe install script has no RPATH_CHANGE. artifacts.json contains absolute prefix receipt and metadata for11 ELF/helper/object files; helper/compiler-ID outputs are inventoried only, not executed/runtime-certified.

**DART configure and generate exit0.** Fresh trace has9 upstream export-file registrations total; only6 selected ones use aero-joint-cmake, unselected planning/external-imgui/external-lodepng remain outside that stage. Each selected set has membership1, install(EXPORT) registration1 and generated exported target1, as checked by check_exports.py/export_validation.json. No namespace or required target removed. Generated files reside beneath each defining directory's CMakeFiles/Export, rather than a common root CMakeFiles/Export directory.

**First downstream failure: dart.selection exit1**, after159 external-file checks,234.72s. Original rejecting checker unchanged. selection_result.json preserves all4 reported errors:

- tinyxml2 INTERFACE_COMPILE_DEFINITIONS contains unresolved generator expressions: `$<$<CONFIG:Debug>:TINYXML2_DEBUG>;$<$<BOOL:yes>:TINYXML2_IMPORT>;_FILE_OFFSET_BITS=64`. The checker requires explicit evaluation rather than silently assuming either branch.
- OpenGL::GLES2/GLES3 IMPORTED_LOCATION `/usr/lib/x86_64-linux-gnu/libGLESv2.so` resolves to unpinned libGLESv2.so.2.1.0.
- flann INTERFACE_LINK_LIBRARIES `/usr/lib/x86_64-linux-gnu/libflann_cpp.so` resolves to unpinned libflann_cpp.so.1.9.2.
- Doxygen::dot IMPORTED_LOCATION `/usr/bin/dot` resolves through its existing symlink to unpinned `/usr/sbin/libgvc6-config-update`.

selection_origins.json records each property source, realpath and SHA. These are configure-discovered imported metadata; this is not proof they are linked into a selected DART artifact or loaded. The actual trace contains no execute_process call invoking dot/doxygen/libgvc6-config-update. No such tool was launched by this work. Do not approve these paths merely because configure succeeded or metadata came from an optional package.

Stopped immediately after this rejecting selection result. DART compilation/link/stage/receipt NOT_STARTED. gz-physics/Sim/harness NOT_STARTED. DART installed-package consumer resolution is **NOT_VERIFIED**, because no DART prefix was staged; only generated metadata names/transitive references were statically checked. There is no new DART/physics/Sim/harness ELF hash. No unrelated error/allowlist/generator-expression relaxation or retry was made. Next minimum: separately review selected-vs-optional target observation and exact generator-expression interpretation against the unchanged lock, without hiding paths or broadening dependencies automatically.

## Recording, preservation and execution limits

steps.json contains command host/PID/start identity, exit/status, elapsed time and log SHA/path. Both configure traces have zero try_run calls, as recorded in preservation.json. No subject execution/loading, CTest, ldd, physics step, service, marker consumption, sudo/package install/system change. Compiler/link tools only. Command/trace observation is not syscall tracing. All task command processes exited; project-CWD scan scope excludes external-CWD/remote/container/other namespaces (UNKNOWN). No existing process terminated/restarted.

Two launcher setup attempts initially retained the preceding phase's relative path and were rejected by that phase's prior failure latch before command launch. Its optional Python exception hook imported a copied local inspect.py, which re-emitted3 preceding-phase analysis JSON files with byte-identical contents. Their tracked hashes remain identical to2d5c4f3; timestamps were not preserved. Corrected only the new runner's phase path and disabled optional site-hook imports for the runner; old latch and all build/static gates remained active. No previous build/stage/receipt/failure log was replayed or overwritten. A preliminary export inventory assertion also used an incorrect root-only search directory; read-only corrected query found all6 files in their defining subdirectories, with no build/input change. These observer issues are distinct from the actual dart.selection rejection.

Original source/failure/ELF contents preserved; prior probe/helper ELF hashes rechecked. Original main and its dirty work/markers untouched. Patch, checked metadata/reports and inspection scripts are the lightweight publication scope. Generalized setup/runner, uncompiled downstream source/input, raw logs/trace/source/deps/build/binaries remain local/ignored; Git does not transfer them and /tmp is not durable. Stage B BLOCKED and risk UNDECIDED remain unchanged.
