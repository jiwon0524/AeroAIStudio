# DART Capability / ABI V2

Only an offline, isolated compatibility investigation. See `reports/final_report.md` and the experiment worktree's `handoff.md` for observed results. No Gazebo, World::step, Stage B, production/system package/library change, main push or merge.

The existing main worktree and prior evidence/builds are read-only inputs. `scripts/common.py` identifies the local input root; adapt that one path on another machine after obtaining access to the original workspace and matching source archives. Existing uncommitted project diagnostics used by the historical regression suite are not included in this branch. This branch does not purport to reproduce those diagnostics from a clean checkout.

- `instrumentation/dart_internal_trace_v1.patch` contains the unchanged, previously tested five-hook/two-recorder source changes. The diff is serialized with zero context for clean Git whitespace checks; patch_roundtrip.json verifies exact source hashes after application. Apply only to the matching distribution-patched DART6.13.2 source in a separate directory; never apply it to production or the original evidence. `reports/neutrality_static_review.json` identifies source hashes.
- `scripts/dependencies.py` verifies apt-index package hashes and extracts only; it does not install. Relocated pkg-config prefixes stay inside the isolated prefix. ODE uses the unchanged installed runtime; IPOPT/NLOPT use downloaded matching dev/runtime pairs. Historical build dependency versions remain unverified.
- `scripts/configure.py` records the initial include-classification failure. `configure_final.py` is the corrected final configuration with a fmt/spdlog-only normal include prefix and SYSTEM third-party headers. Failed initial and successful final artifacts remain separate.
- `scripts/prepare_tests.py` copies reviewed prior fixtures into this new test directory. Tests exercise native Constraint/LCP objects and recorder logic without World::step. Use the explicitly fenced existing regression suite only with its recorded original sources.
- `scripts/analyze_abi.py`, `profile.py`, `abi_layout.py` and `dwarf_compare.py` record ELF/type/loader results. Libabigail comparisons require actual debug info; lack of debug info is a limitation, not PASS.

Source commands, exact packages, checksums and detection conditions are recorded in `reports/`. The primary libabigail interpretation reference is https://sourceware.org/libabigail/manual/abidiff.html . A symbol-only result does not certify complete ABI parity. Runtime neutrality remains unverified even when offline checks pass.

`work/`, `downloads/`, shared libraries, caches, raw build logs, raw full manifests and debug-diff dumps must stay local. Stage only the reviewed explicit lightweight list; do not add pre-existing main edits or untracked files. Publishing is allowed only on `experiment/dart-internal-trace`, without force push or main merge.
