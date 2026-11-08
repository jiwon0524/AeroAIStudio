# Harness selection repair and completed static joint build

2026-11-08 UTC. Start HEAD d38acab27c00d18fd68e8b0c8fb024b03c1e5f81, experiment/dart-internal-trace, no staged/tracked changes; only prior root dangling symlink untracked. Required AGENTS, DEVELOPMENT_RULES, handoff, feature-fix report and closure build_gate read. context-handoff used. No duplicate live build visible in project-CWD snapshot; external-CWD/remote/container state UNKNOWN.

**JOINT_BUILD_AND_STATIC_DEPLOYMENT_PASS / NOT_RUNTIME_VERIFIED / NOT_EXECUTION_APPROVED. Stage B BLOCKED; risk acceptance UNDECIDED.**

## Repaired contract

Existing commands_final.json invokes `python3 validation/gazebo-joint-codegen-fix-v1/scripts/check_selection_harness.py harness` in the pinned clean environment. That path was absent; no equivalent harness checker was found. Restored precisely that path and single argument. Required inputs: selected_files/toolchain/tool-ELF locks; staged.json and reused_elfs.json; persistent harness configure trace, File API codemodel/target JSON, compile_commands.json, direct target property snapshot, and Ninja command metadata. Output: JSON stdout, exit0 only on PASS_STATIC_SELECTED_CLOSURE; missing/unreadable/invalid inputs produce BLOCKED/nonzero. No subject loading or running.

Reuses check_selection_broad.py's preexisting external path/hash and installed-stack rejection logic, with harness-only checks: 13 valid predecessor receipts, one RelWithDebInfo executable and one source, direct target gz-sim8::gz-sim8, no extra generated target, evaluated include/link inputs, original compiler launcher/tool, exact RUNPATH and explicit link token resolution. Prefix libraries require receipt SHA/source equality; predecessor probes require exact reused realpath/SHA. Unknown tokens, response files and generator expressions are rejected rather than guessed. Installed subject DART/gz-physics/Sim, /usr/local and the root dangling symlink are rejected. Approved other gz/Qt SDK transitive dependencies remain governed by existing locks; the policy was not broadened to arbitrary Gazebo installations.

Positive actual selection PASS (475 external files checked). Eleven nonexecution negatives PASS_REJECTED: missing input, outside allowlist, installed Sim, /usr/local, root dangling symlink, unresolved -l, target expression, relative library operand, response file, missing link metadata and extra generated target. selection.json/negative_tests.json hold details. The original missing-checker failure log is unchanged.

During checker development, an initial diagnostic treated CMake-deleted TryCompile CMakeLists as persistent required files (selection.first.json preserved locally). These three paths are now explicitly classified only as recorded CMAKE_TRY_COMPILE generated project metadata under this build's exact CMakeScratch/TryCompile-* subtrees. Persistent external scripts, source, locks and generated consumer metadata still must exist. No configure/try_run was rerun. During final inventory implementation, an omitted /usr/lib fallback was corrected to match the existing auditor's search list after libgdal's libarmadillo dependency exposed it; deployment_first_attempt.json records that diagnostic. The existing pinned /usr/lib/libarmadillo.so.12.6.7 SHA passed unchanged lock verification. No new input or library allowlist entry was added.

## Build and deployment observations

- Preflight rehash of all13 predecessor build/prefix receipt pairs PASS; prior feature-fix receipt content equals current receipt. No DART/gz-physics/Sim rebuild or code generation.
- Harness configure information from the prior successful configure was inspected and reused. File API reports only aero-joint-harness; target snapshots confirm direct gz-sim8::gz-sim8. Ninja commands were inspected as metadata, not executed as shell strings.
- Harness build PASS1.91s, compile and link only, using unchanged compile_gate.py and original pinned environment. Actual Ninja dependency metadata contains1 object and543 unique dependency files, all checked with existing policy; zero /usr/local or installed subject headers. actual_headers.json records every dependency SHA. Its installed other gz SDK headers are individually locked and allowed by the original build contract.
- Existing audit_outputs_sim.py harness mode PASS_STATIC_OUTPUT_CLOSURE. This existing variant retains the exact reused-runpath manifest, avoiding the older generic variant's narrower predecessor-path assumption. No loader/ldd used.
- Separate prefix: `validation/gazebo-joint-harness-fix-v1/work/prefix`. Copied executable without stripping/RPATH rewriting to bin/aero-joint-harness; SHA equals original build. New share/aero/world.sdf is the unchanged fixture template with absolute verified plugin paths substituted. Embedded fixture string equals fixture.sdf.in byte-for-byte. The harness uses its embedded world plus plugin arguments; world.sdf is a fixed review artifact, not a new harness input.
- Combined executable + Physics system + dartsim engine recursive DT_NEEDED inventory PASS170 ELF real files, each SHA/Build ID/SONAME/search path/edge recorded in final_manifest.json. Dynamic plugin/mapping selection is not proven by this static inventory. No other plugin discovery is authorized.

## Final artifacts

Paths below are relative to this experiment worktree. Whole exact paths/hashes are in final_manifest.json.

|Artifact|Path|SHA-256|
|---|---|---|
|Harness|validation/gazebo-joint-harness-fix-v1/work/prefix/bin/aero-joint-harness|bd7ce6480b15debab915a69cd9e9a429b92c066063cd31882666617c0a0b3d5a|
|World|validation/gazebo-joint-harness-fix-v1/work/prefix/share/aero/world.sdf|534b09dddb318e5db1f9ccb2267fb7c7744c552d8bc4034008d547514c37ba69|
|Sim core|validation/gazebo-joint-codegen-fix-v1/work/config-01/prefix/lib/libgz-sim8.so.8.15.0|25b168676e55c1bfb847a92b0648802f916af96bd1730a9344e196632dea9128|
|Physics system|validation/gazebo-joint-codegen-fix-v1/work/config-01/prefix/lib/gz-sim-8/plugins/libgz-sim8-physics-system.so.8.15.0|dfe093dc43a949bc554de3f52223aae3f437759a6378cd5aa22cca5d21423a11|
|dartsim engine|validation/gazebo-joint-codegen-fix-v1/work/config-01/prefix/lib/gz-physics-7/engine-plugins/libgz-physics7-dartsim-plugin.so.7.8.0|c652c1af1ccf37d0dcc0b185849045a41f074262ad8a6a7c6f38e75ddecc370c|

Harness Build ID82c1f5a064a9d7c044c31cb9cdc7c8d3cc5fbe02; ELF DYN/PIE; no SONAME (executable), no DT_RPATH. DT_RUNPATH exactly codegen-fix work/config-01/prefix/lib plus closure-v1 work/deps/usr/lib/x86_64-linux-gnu; no empty or build-directory entry. DT_NEEDED: libgz-sim8.so.8, libsdformat14.so.14, libstdc++.so.6, libgcc_s.so.1, libc.so.6. Full verbose link operands, including pinned transitive inputs removed by linker as-needed, are in logs/harness.build.log and selection.json. Harness build path remains codegen-fix work/config-01/build/harness/aero-joint-harness; deployed bytes are identical.

The compiled AERO_JOINT_PREFIX and RUNPATH intentionally retain the successful stack prefix. Separate executable deployment is not a relocatable complete stack; predecessor prefixes/deps recorded in final_manifest.json must remain available. This is static build completion, not runtime ABI/mapping or no-step initialization certification.

## Preservation and next boundary

preservation.json directly rechecks9 fixed input/log hashes, all13 receipt pairs, original main HEAD/status/dirty regular-file hashes, and root symlink inode/target/mtime. Original main and existing sources/ELFs/receipts/failed logs remain unchanged. Root libgz-physics-dartsim-plugin.so remains the original dangling relative link, excluded from all actual inputs. No marker path was opened/written/consumed; no marker-content revalidation is claimed. No existing process terminated/restarted. All launched task processes exited; steps.json/deployment_step.json carry host/PID/start identity/output hashes. New raw logs/build/deployment remain local/ignored and are not transferred by Git; /tmp is not durable.

Separate execution proposal and unmet conditions are in execution_proposal.md. No DART/Gazebo loading, harness run, physics step, service, marker consumption, sudo, package install or system setting change was performed. Stage B BLOCKED, risk acceptance UNDECIDED and runtime UNVERIFIED remain. Publish only restored checker, verified lightweight scripts/results and handoff on experiment branch; no main/merge/force push.
