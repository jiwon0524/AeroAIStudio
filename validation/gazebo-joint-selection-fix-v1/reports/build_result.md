# DART selected dependency gate repair

2026-11-08 UTC. Starting HEAD `487d85e0af1e3f612ff29ca5df40f47716f7c9da`, clean experiment/dart-internal-trace, matches requested checkpoint. Required AGENTS/development rules/handoff/previous report/build contract and commands read; context-handoff used. No nested AGENTS found in the current/previous phase.

**FOUR_SELECTION_ITEMS_RESOLVED / DART_SELECTION_PASS / DART_COMPILE_HEADER_BLOCKED / joint build INCOMPLETE / NOT_RUNTIME_VERIFIED. Stage B BLOCKED; risk acceptance UNDECIDED.**

## Four-item evidence and decisions

`four_items.json` records exact paths, SHA-256, package/source versions, declaration and generated compile/link properties. All decisions below are for the selected six targets in RelWithDebInfo; none is an authorization for runtime loading.

|Item|Actual role and selection|Decision|
|---|---|---|
|tinyxml2::tinyxml2|Selected through dart-utils, transitively dart-utils-urdf. Declaration /usr/lib/x86_64-linux-gnu/cmake/tinyxml2/tinyxml2-shared-targets.cmake:72; package libtinyxml2-dev10.0.0+dfsg-2.|Resolved from CMake-generated effective definitions/link fragments, no manual expression assumption.|
|libGLESv2|OpenGL::GLES2/GLES3 IMPORTED_LOCATION exposes /usr/lib/x86_64-linux-gnu/libGLESv2.so → libGLESv2.so.2.1.0. Package libgles2:amd641.7.0-1build1, source libglvnd.|Not in selected target dependency graph, generated compile/link data or selected Ninja commands. Configure-discovered metadata only; not allowlisted.|
|libflann_cpp|flann interface exposes /usr/lib/x86_64-linux-gnu/libflann_cpp.so → libflann_cpp.so.1.9.2. Package libflann1.9:amd641.9.2+dfsg-2build1, source flann.|Used by generated **unselected** dart-planning and test_NearestNeighbor targets, absent from selected closure/commands. Not allowlisted.|
|libgvc6-config-update|Doxygen::dot IMPORTED_LOCATION exposes /usr/bin/dot → /usr/sbin/libgvc6-config-update. Package libgvc62.42.2-9ubuntu0.1, source graphviz.|Imported build-tool metadata only, absent from selected commands; trace execute_process invocation count for both alias/realpath0. No tool launch or allowlist addition.|

Exact raw tinyxml2 INTERFACE_COMPILE_DEFINITIONS:

```
$<$<CONFIG:Debug>:TINYXML2_DEBUG>;$<$<BOOL:yes>:TINYXML2_IMPORT>;_FILE_OFFSET_BITS=64
```

The selected **RelWithDebInfo** File API compile groups for both dart-utils and dart-utils-urdf contain TINYXML2_IMPORT and _FILE_OFFSET_BITS=64, and do not contain TINYXML2_DEBUG. Their generated Ninja compile commands agree. CMake's generated link fragments select `/usr/lib/x86_64-linux-gnu/libtinyxml2.so.10.0.0`, SHA-256 `f9e01d87fb78af744a426af8c992e94abf8cd3810a256e117bcc94cd84d2be6d`, which passes the existing pinned-file policy. This is generation evidence; actual utils compilation was not reached because the first common-source compile failed below. No custom generator-expression evaluator or blanket acceptance of unresolved expressions was added. Unknown raw expressions, mismatched configuration/effective definitions or generated unresolved expressions still reject.

## Checker correction and new layout

The prior checker scanned every BUILDSYSTEM/IMPORTED target snapshot and all compile_commands entries, including unbuilt optional targets, as though each were selected. The earlier snapshot scope fix exposed these names correctly; it did not make them selected dependencies. New work at `validation/gazebo-joint-selection-fix-v1/work/config-01` uses fresh source/build/prefix. Only observer/input/output path relocation changes source bytes:3977 source files verified against previous phase. Source semantics, selected6 library names, empty export namespace, single export registration, directory-local imported-target observation, BUILD_WITH_INSTALL_RPATH=ON, INSTALL_RPATH_USE_LINK_PATH=OFF and strict receipt equality are unchanged.

A `.cmake/api/v1/query/codemodel-v2` query is placed before configure. For DART only, check_selected_dart.py uses the generated codemodel's exact six seed targets and recursive **build** dependency IDs. Generated link fragments already contain evaluated imported/interface transitive references, including tinyxml2; compile groups contain effective definitions/includes. The graph contains exactly dart, dart-external-odelcpsolver, dart-collision-ode, dart-collision-bullet, dart-utils and dart-utils-urdf. A metadata-only `ninja -t commands` query independently captures their actual scheduled compile/link/symlink commands and rejects any unexpected command type. It never executes those commands. Raw snapshot evidence is retained rather than hidden or deleted. Full selected codemodel extract in dart_selected_closure.json; selected command text remains local logs/dart.selected_commands.txt with SHA in the result.

All executed configure-file path/hash checks and installed-stack rejection policy are reused unchanged. Actual selected include/link file paths are checked against the **same** selected_files/toolchain/ELF lock; `-l` inputs resolve only through fixed approved prefix/deps/system directories, shared or static library candidates. Original compiler launcher and post-link/staging guards remain unchanged. Non-DART component checks still use the original broad checker. No file is added to the allowlist. Directory candidates do not approve arbitrary headers; compiler depfiles remain a separate rejecting gate for actual header selection.

check_selection.py dispatches only DART to the corrected checker. check_selection_broad.py is byte-identical to the previous original policy; hashes in preservation_current.json. Negative metadata tests use disposable copies and show rejection when an unpinned GLES library is inserted into a selected target, and when tinyxml2's effective import definition is removed. No original generated metadata is modified. negative_tests.json:2 PASS_REJECTED. No subject execution, compilation or loading occurs in these tests.

## Actual stage results and first downstream failure

Fresh probe configure → original selection(96 pinned external files) → compile/link → static ELF closure → selected component install → receipt PASS. Fresh DART configure/generate PASS; generated6 exports remain membership1/registration1/target1, empty namespace (export_validation.json). New DART selection PASS,162 external files checked, errors0; all4 original items resolved within this static selected-build scope.

Then **dart.build exit1** after5.73s. Original compiler launcher rejects actual dependency `/usr/local/include/spdlog/spdlog.h`, SHA-256 `268a03933a066694f5e6b9dbdd30691d351f01197e08eaae581d75ac05bd8da3`. First failed output is dart/CMakeFiles/dart.dir/common/CAllocator.cpp.o; concurrently Aspect.cpp.o fails for the same header. The compiler produced these objects before its depfile audit, but they are **rejected/unverified objects**, not accepted DART outputs. Ninja stopped and no dependent DART link ran. No guard was disabled or retry made.

This is a real compiler-header selection mismatch, distinct from optional metadata. Generated explicit include/link paths passed the static gate, but the compiler's implicit header search reached the unpinned /usr/local spdlog header. Build log and depfiles are the direct evidence. This result demonstrates the retained actual-header guard's role; selection PASS does not claim all headers have already been accessed and verified. The new scope checker did not suppress this finding or approve /usr/local. We did not change compiler search flags, system headers or the build contract to pass it.

Stop at this first new mismatch. DART link/static-ELF/stage/receipt NOT_STARTED; gz-physics/Sim/harness NOT_STARTED. No DART shared library or staged package consumer check exists. No whole-stack build/runtime success claimed. Next minimum: separately review implicit spdlog header selection against the pinned header/toolchain policy in another isolated build; do not automatically approve /usr/local or overwrite this failure.

## New ELF inventory and preservation

Probe build and prefix bytes are identical. SHA-256 **18ea74899c6234c3ee00a8384bff10447dacc5538189b2480f94ec039ae2f5fb**, Build ID **9da7b9320d2066f23ed2e241f1cb0f1f81b50ae0**. SONAME libaero-joint-probe.so.1; DT_NEEDED libcrypto.so.3, libstdc++.so.6, libgcc_s.so.1, libc.so.6. All6 external/transitive ELF files match the previous allowlist closure. DT_RPATH absent; DT_RUNPATH exactly new phase/work/config-01/prefix/lib followed by original gazebo-joint-closure-v1/work/deps/usr/lib/x86_64-linux-gnu. No empty/unapproved/build-directory search entry. Probe install script contains no RPATH_CHANGE.

artifacts.json records13 ELF/helper/object entries with SHA/Build ID/SONAME/DT_NEEDED/RPATH/RUNPATH (empty where not applicable), accepted probe receipt and identity result. This includes the2 rejected DART objects; helpers/compiler-ID/ABI files are inventory only, not subject execution evidence. There is no build/prefix equality claim for those objects or any DART library. build_status.json labels the first rejection and input hashes. Original source/ELF hashes preserved, as checked in preservation_current.json. No previous failure/source/receipt/log/marker overwritten. Original main and its pre-existing dirty work untouched.

Both configure traces have try_run0. No DART/Gazebo subject execution/loading, CTest, ldd, physics step, service/marker/sudo/package install/system change. Compiler and static metadata tools only. Command/trace observation is not a syscall trace. steps.json records observed exited processes with host/PID/start identity, log SHA/path and status. No existing process terminated/restarted. Project-CWD snapshot visibility does not cover external-CWD/remote/container/other namespaces (UNKNOWN).

Publish only checked checker/observer-inspection scripts and lightweight reports. Uncompiled downstream source/input, generalized setup/runner, raw command/trace/build logs, source/deps/build/ELF files remain local/ignored. Git does not transfer these and /tmp is not durable. Stage B remains BLOCKED; risk acceptance remains UNDECIDED.
