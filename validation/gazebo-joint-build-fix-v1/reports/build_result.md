# Probe deployment repair and joint build continuation

2026-11-08 UTC. Starting HEAD e234234edecae3da5e071d0224a878fc069b668e, experiment/dart-internal-trace clean. Required AGENTS, development rules, handoff, original build_result/build_gate/build_commands read; context-handoff used.

**PROBE_FIXED / DART_CONFIGURE_BLOCKED / joint build INCOMPLETE / NOT_RUNTIME_VERIFIED. Stage B BLOCKED; risk acceptance UNDECIDED.**

## Original failure, read-only comparison

`original_comparison.json` preserves both original readelf dynamic/notes output, installation script/log and full byte-difference result. Original size361424, only offset6339 .dynstr changes58 (`:`) to0. DT_RPATH absent in both; DT_RUNPATH loses exactly the trailing colon. SONAME, Build ID and NEEDED unchanged; all other bytes identical. Original hashes remain a18c2eef8fe7014dd51670ff5bf647bb786955827ec69cf2a000f5b1d443b34a (build), ccd88699b6b08d3f54a9b3c0886fb5b0086a74aefe915162c933c34279c87dc1 (prefix).

The generated `cmake_install.cmake:67` explicitly performs OLD_RPATH-with-colon -> NEW_RPATH-without-colon. Thus the extra colon is CMake's install-time rewrite reservation, not an approved empty search directory. This mechanism interpretation is supported by local CMake3.28 Help/prop_tgt/BUILD_RPATH.rst and BUILD_WITH_INSTALL_RPATH.rst plus actual generated link/install commands. No installed CMake source implementation was independently inspected. Build ID equality does not establish byte equality.

## Revised deployment policy and probe result

New phase `validation/gazebo-joint-build-fix-v1`, new build/prefix under `work/config-01`; original input/source/output paths untouched. Original source copies were copied byte-for-byte (3977 files verified). Inputs/scripts copied separately with phase path relocation; dependencies remain at the original approved deps realpath, selected_files allowlist unchanged. No dependency permission expansion. Commands in reports/build_commands.txt retain original component order and environment policy; source helper was not replayed into existing paths.

Toolchain adds `CMAKE_BUILD_WITH_INSTALL_RPATH=ON`, `CMAKE_INSTALL_RPATH_USE_LINK_PATH=OFF`. Receipt's SHA equality contract is unchanged. Probe configure, selection96 external files, two compiles/link, static closure, selected library component install and original receipt algorithm PASS. Generated probe install script contains no RPATH_CHANGE. Build and prefix ELF bytes exactly equal, SHA-256 **3459f37da9645ae24b59376a930796974300352b24ea434e4d7e13c571ab24cd**, Build ID f302c2c1ba1ce10cdfb26d542f6b985425e46983; SONAME libaero-joint-probe.so.1. Metadata in artifacts.json; accepted receipt in work/config-01/manifests/staged.json and result.json.

Both ELFs have no DT_RPATH. Exact DT_RUNPATH entries, in order:

1. /tmp/AeroAIStudio-dart-internal-trace/validation/gazebo-joint-build-fix-v1/work/config-01/prefix/lib
2. /tmp/AeroAIStudio-dart-internal-trace/validation/gazebo-joint-closure-v1/work/deps/usr/lib/x86_64-linux-gnu

These are the approved isolated deployment prefix and dependency root, not temporary compiler/build directories. No empty entry, unapproved directory or build path. Strict new audit rejects empty entries/build paths. Initial new audit falsely rejected deps because it compared a canonical ELF path against an unresolved deps symlink; corrected only the comparison to use the approved canonical root. Original probe.elf.log failure retained, successful recheck separately probe.elf.recheck.log. No receipt bypass/hash mismatch ignored.

Direct NEEDED: libcrypto.so.3, libstdc++.so.6, libgcc_s.so.1, libc.so.6. Transitive libm and ld-linux complete six external files. Each realpath/hash matches original successful allowlist closure, recorded in dependency_comparison.json. This is static resolution, not actual loader mapping. Actual compiler-selected paths are in compile_commands, target-property snapshots, selection log and verbose build log; header launcher passed both compiles.

## First downstream blocker

Fixed order continued to **DART configure**, which exited1. First CMake error is `inputs/export-targets.cmake:10`, get_target_property on non-existent `OpenGL::OpenGL`; additional names include ODE::ODE, Bullet, urdfdom, GLUT targets (full set result.json). Recursive snapshot function queries directory-scoped IMPORTED_TARGETS from an ancestor function invocation; target visibility is the leading explanation, not proven missing installed libraries. No inspector guard was bypassed or imported target promoted. Configure is incomplete: DART selected-path gate NOT_PASSED, compile/link/stage NOT_STARTED. physics/Sim/harness NOT_STARTED. No DART output SHA exists.

Next minimum: separately review directory-scoped target snapshot collection and failed configure evidence, preserving this failure. Do not skip missing snapshots or silently widen dependency approval. This task stops at this first downstream configure failure.

## Evidence, preservation, limits

steps.json records host/PID/start identity, completed exit codes, durations, log paths/hashes, including both audit attempts. All observed commands exited; no job left running from this task. Snapshot only covers same-user project-CWD processes; other namespaces/remote/external-CWD state UNKNOWN. Probe and DART configure traces each contain zero try_run commands. No subject ELF execution/loading, ldd, CTest, physics step, services, markers, sudo, package/system changes. This is command/trace evidence, not syscall tracing.

Original failed ELF hashes and all copied source bytes rechecked. Original main files remain untouched. No original receipt/failure/evidence/marker overwritten. Existing failed config and new artifacts remain local. No existing process terminated/restarted. Raw logs, source/deps/build/binaries and ignored inputs do not transfer through Git and /tmp is not durable. Publish only verified lightweight reports and tested static audit/receipt scripts; generalized prepare/resume runner and unverified downstream inputs remain local.
