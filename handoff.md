# Aero AI Studio — v10 harmless-only driver checkpoint

## Scope and current state

Observed base HEAD e37a69229a1a1a77937f0c22335a78a2858f86a0 on experiment/dart-internal-trace.
Current request: prepare separate small harmless driver, build/static/Python mocks and exact one-run approval proposal.
No harmless driver/probe/owner/anchor/native execution, Gazebo/DART/harness loading, service, step, marker consumption,
new cap increases, sudo/install/system changes. Original main/code/evidence/dirty/artifacts/markers preserved.
Original actual launcher and v9 entry78; Stage B BLOCKED / risk UNDECIDED / runtime UNVERIFIED.
context-handoff used. AGENTS/DEVELOPMENT_RULES automatic verified lightweight checkpoint commit/push still applies;
publication is NOT runtime approval. Wait for a new explicit approval of the exact one-run contract before execution.

## Completed / evidence

Current final: validation/gazebo-request-guard-v10/reports/final_report.md.
Single approval proposal: validation/gazebo-request-guard-v10/reports/approval_proposal.md.
Exact execution contract: validation/gazebo-request-guard-v10/reports/execution_contract.json.
Contract SHA256 63f630e5e0aee7c19c09b693a8cc9c6d45e54f77b8d022820eb0b6b85c5a7395.
Source/build/tests: reports/source_manifest.json, build_receipt.json, tests.json;2119 static/Python mock PASS.
Counts:1617 tracked-file preservation,376 source/dependency/artifact hashes,126 policy/behavior/source assertions.
Earlier v9 1638 and historical harmless PASS evidence reused by hash, not rerun/added to current count.
6 new/profile-affected TU compile/link;4 v9 objects+anchor hash-verified reused. No C binary/DSO was run.

Separate native owner main calls unchanged v9 FD bridge and bootstrap with small compile-time4-original/5-path policy.
Probe17192bytes+libc+ld+fixed24bytes; two fixed aliases share one original. Control owner80704bytes and reused
anchor16016bytes separately sealed only in future runtime. Fixed input SHA and all ELF/host-tool hashes are in contract.
Initial owner O,4FD C/K, target placement P, audit/A, GO/100 fixture/EXIT_ACK, cross-channel ready/audit catch-up before GO, post-ACK callback thread read/join,
process-child approved read+exit, independent task death/COMPLETE/EOF, invocation-bound cleanup and pin release/V linked.
Small-only fork/read-only self-prlimit and normal probe calls added; full v9 files/policy unchanged.
Historical map_files EPERM handled explicitly in small profile by retained sealed pin + kernel dev/inode + all5 canonical
RO FD/mount identity with PID/start/maps stability; no fallback on mismatches/disappearance. Full v9 strict policy unchanged.
pass_fds CLOEXEC loss fixed in new owner entry; failed restore refuses before bootstrap. Target invocation receipt
persisted before anchor observation; missing/reused ownership makes cleanup UNKNOWN/FAIL, never arbitrary stop.
Mocks exercised actual Owner.bind/Catalog/coordinator and reused controller/protocol, plus host lifecycle faults.
Actual preparation0/delivered0/units0/markers0. Existing output/marker are absent as last stat observation, not consumed.

## Exact next action and remaining separation

Nonexecution preparation complete. No known unresolved static blocker. DO NOT run the proposal automatically.
Obtain separate explicit approval for the exact command/hash/scope in approval_proposal.md, then at most1 execution.
Proposal uses new units aero-guard-v10-owner-small-01.service and aero-guard-v10-target-small-01.service,
new work/harmless-small-01.once and work/runtime-small-01 only. Exclusive/no-retry; keep marker/evidence on failure.
Approved candidate caps543979760/2159132672 and owner5368709120 unchanged; target512MiB/AS2GiB/FSIZE1MiB/NOFILE256.
Before mutation check exact source/contract/ELF/input hashes, branch, output/marker absence and both unit absence.
Future first runtime gate may fail there, then owner domain/userns/SCM/ptrace/mount/cgroup/LSM/mapping/thread/exit/cleanup.
All real kernel behavior is unverified. Owner/target safety deadlines and no-success-on-missing-audit are mock checked only.
Missing authenticated invocation means cleanup UNKNOWN/FAIL and may require separately owned recovery, no unsafe stop.
This small trial excludes actual large5/303objects/468paths preparation and maximum memory measurement;
small PASS cannot prove full v9 delivery, Gazebo/DART behavior, physics or open Stage B. Those need separate contracts/approval.

## Preservation / publication / processes

Only new ignored v10 and intended handoff edit belong to this task. Existing tracked v9/old artifacts/main dirty/dangling
symlink checks pass; native inputs/objects only read/hash except newly generated v10 outputs. No old work stopped/restarted.
Issued compiler/link/test commands observed exited; same-user project-CWD snapshot showed no other tasks; remote/external-CWD tasks UNKNOWN.
Local work contains immutable-versioned compiler outputs/logs and baseline/receipts; binaries/raw logs excluded from Git publication.
Exact lightweight files: reports/publication_files.txt. /tmp and ignored work are not durable or automatically portable.
Another host needs exact local binaries/backings or a fresh compiler-only build+new contract+tests+approval.
This handoff precedes checkpoint commit; publication success requires actual push+remote match in work/publication-result.json.
No main/force push/merge or unrelated staging. Do not execute anything in response to publishing or account change alone.

## Historical context

v9 final/candidate: validation/gazebo-request-guard-v9/reports/ (published e37a692).
Historical harmless: validation/gazebo-joint-resolution-v1/reports/harmless_summary.json and harmless_runtime/ (not rerun).
Original sealed contract: validation/gazebo-joint-execution-contract-v1/reports/manifest.json; unchanged, not new runtime authorization.

```context-handoff-state
{
  "schema_version": 1,
  "updated_at": "2026-11-10T10:12:38.589071+00:00",
  "project_root_hint": "/tmp/AeroAIStudio-dart-internal-trace",
  "host": "jiwon-System-Product-Name",
  "git": {
    "head": "e37a69229a1a1a77937f0c22335a78a2858f86a0",
    "branch": "experiment/dart-internal-trace",
    "status": [
      {
        "status": "??",
        "path": "libgz-physics-dartsim-plugin.so"
      }
    ],
    "snapshot_note": "Base HEAD and original clean tracked-state observation; intended55-file v10 checkpoint is staged separately; exact list publication_files.txt."
  },
  "evidence": [
    {
      "path": "validation/gazebo-request-guard-v10/reports/final_report.md",
      "sha256": "7ce8ed3d45ca233efde78ef4834e6a2f071d0e44ca02a0a645c717f94c16b49f"
    },
    {
      "path": "validation/gazebo-request-guard-v10/reports/tests.json",
      "sha256": "f333b198db045193ae12d8b83da0cc697988bf77ee8b585bd4494f843e8eeab7"
    },
    {
      "path": "validation/gazebo-request-guard-v10/reports/execution_contract.json",
      "sha256": "63f630e5e0aee7c19c09b693a8cc9c6d45e54f77b8d022820eb0b6b85c5a7395"
    }
  ],
  "processes": {
    "visibility": "VISIBLE_SCOPE",
    "scope": "same-user project-CWD helper snapshot 2026-11-10T09:58:40Z; remote/external-CWD UNKNOWN; no arguments/environment recorded",
    "tasks": [],
    "unreadable_same_user_processes": 0
  }
}
```
