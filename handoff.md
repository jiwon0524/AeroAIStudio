# Request guard v8 — FD bridge and bootstrap checkpoint

Observed HEAD0f3eb51319a7a75c18d5930a99280de3455e2bd1 on experiment/dart-internal-trace.
Worktree `/tmp/AeroAIStudio-dart-internal-trace`. No later HEAD/staging found. Initial v8 was ignored,
with576 prior static/Python mock checks and11-TU compile/link record; read and preserved before edits.
Read context-handoff, AGENTS, DEVELOPMENT_RULES, previous handoff and v8 build/test receipts first.

**Stage B BLOCKED / risk acceptance UNDECIDED / actual runtime UNVERIFIED.**
**This repair scope is saved and statically/mock verified; entire deployment is NOT certified ready.**

## Scope and explicit publication boundary

Current user requested owner FD overlap repair, bootstrap/handoff review, compile/static+Python mocks,
SHA-bound records, final report/handoff. **NO staging/commit/push is authorized in this request.** This
explicit scope overrides earlier automatic-publication guidance. No remote query/push or commit made;
HEAD remains0f3eb51. Original actual launcher and candidate entry remain78 before service/marker work.
No DART/Gazebo/harness/harmless/native artifact execution, service start, marker consumption, sudo,
installation/system settings or resource-limit changes. Preserve main/dirty work/evidence/artifacts/link.
Common skill untouched. No account switches or existing process stops/restarts.

## Completed changes and evidence

Consolidated report: validation/gazebo-request-guard-v8/reports/final_report.md.
Progress: validation/gazebo-request-guard-v8/progress.md.

- candidate_owner_fds now delegates actual control flow to inputs/owner_bridge.h. Snapshot all sources
  and null into>=10 CLOEXEC copies, close raw null BEFORE redirect, validate source/final FD ABI, consume
  high sources only after successful redirect, never retry uncertain close, return78 on any failure.
  Source/destination overlap and all low holes handled; final0..4 inheritable contract unchanged.
  Failed partial redirect is terminal for a new dedicated owner, not a claim of rollback/reusability.
- Added early journal/collector validation before copy preparation: private empty append regular file,
  distinct FD roles, connected AF_UNIX seqpacket, nonblocking/CLOEXEC and same-UID/GID peer. Missing/wrong
  control descriptors cannot yield bootstrap preparation success.
- Bootstrap PID1 review: installed pid_namespaces(7) documents ancestor-only forced SIGSTOP behavior.
  Replaced owner self-SIGSTOP assumption with SIGCONT-handler/block + private R readiness pipe, ancestor
  pidfd STOP, bounded stop wait, O-gated pidfd CONT and pidfd failure KILL. pidfd binds before wait/reap;
  no numeric-PID signaling after reaping. Lost CONT wakeup avoided with sigsuspend mask transition.
  Numeric fallback exists only if pidfd_open fails BEFORE any wait on the newly owned unreaped child.
- owner.py behavioral mocks now cover protocol framing/credential/rights, PID/start/ELF/PPid/state/domain,
  bound memory cap and pre-ACK rechecks, disposal failure before ACK. It closes every received descriptor
  once. O means identity ONLY; Owner.root=0. No full303/468 prepared/delivered claim from this handshake.
  CURRENT_OWNER_MAX remains536870912; proposed5GiB argument is explicitly rejected in current candidate.
- Recompiled launch1 TU only. Reused10 TU objects after relinking original saved launch/object set and
  reproducing recorded baseline supervisor SHAec06594d1997e89ec2d0ed05b43d2c78f46d723bd30f0bde2dac69699f433ece.
  Original work/candidate, consumer DSO, anchor and original objects preserved; new objects/ELF/logs under
  work/fd-owner-repair/<run>/ . Compiler identity/process/dependency/object/artifact hashes in current receipt.
-1082 total CURRENT static/Python mock cases PASS (not576+1082). Actual small C bridge and parent
  readiness/ACK conditions are interpreted with a synthetic FD table or fake poll/read/recv/signal calls;
  no native/kernel bridge code executed. Covers32 hole states,336 source permutations, failures, actual
  owner.bind OS mocks, PID1 gates and existing policy/protocol regression. First interpreter-keyword and
  multiline-condition extraction failures were corrected; original failure records remain in work/.
- reports/source_manifest.json binds42 C/C++/headers/Python/test/policy files and50 reused Python files.
  Manifest digest 4dc8b385e241a69004069a562d2a6fb33face9d4abfdba510562d5bce41e3030.
  Current build/test receipts share that exact digest/source table. Build binds403 C dependencies,
 11 TU object hashes and3 artifacts; tests bind the build receipt SHA and all3 artifact SHA256s.
  Snapshot is checked before and after tests. Python-only edits refreshed metadata after verifying native
  inputs/outputs, without claiming another native compile. No source changed after final PASS.
- Old576 report and original11-TU receipt are unmodified in reports/history/*.before_fd_repair.json.
  Original source/report/artifact snapshot in work/fd-owner-before-repair/; intermediate pre-PID1 fix
  records in work/fd-owner-repair/before-pid1-stop-fix/. These local snapshots are not runtime evidence.
- Original main HEAD/dirty status, existing1767 evidence, prior tracked files (this intended handoff
  excepted), original v8 policy/unchanged sources and dangling symlink dev/inode/text preservation passed.

## Local files and prospective publication inventory

Local saved: updated inputs/launch.c, scripts/owner.py, tests/check.py and current build/tests receipts;
new owner_bridge.h, receipts.py, repair_build.py, fd_owner_mocks.py, source_manifest/progress/final report/
artifact index/publication list and historical receipt copies. Other pre-existing v8 implementations and
policy are reused unchanged. Whole v8 still ignored; only this tracked handoff is intentionally dirty.

**Exact54 prospective publication paths:** validation/gazebo-request-guard-v8/reports/publication_files.txt.
Initial52-file list was shown first, then2 historical receipts added for provenance. Nothing was staged.
reports/artifacts.json hashes that inventory except itself (no recursive digest). Exclude work/ ELF,
objects/logs/cache/local baselines and main's pre-existing changes. Future publication needs explicit
new permission; do not turn this inventory into git add/commit/push automatically.

Current state distinctions: LOCAL_SAVED / STATIC_MOCK_VERIFIED / NOT_COMMITTED / NOT_PUSHED.
No v8 publication receipt asserting remote success. v7's prior receipt is historical only.

## Remaining blockers and next minimum action

Caps remain object67108864 and preparation536870912. Required5 large objects remain a USER DECISION
blocker. Suggested543979760 /2159132672 /owner-collector5368709120 are unapplied.468 is only the static
policy row count. No actual full input factory, mount, delivery, loader or namespace run verified (0).
C resource admission still precedes namespace/fork and fails for full303 set under current caps.

Repair/handoff static scope complete. Whole candidate execution contract, owner/unit activation and
end-to-end deployment are not sealed/released. Limit approval alone is not readiness or permission to
change refusal main/Stage B. Kernel userns/PID1 signals/pidfd/SCM/mount/chroot/LSM/proc mapping and real
FD/errno behavior, loader/pthread/clone3/CET inheritance, callbacks/EOF/cleanup and real resource peaks
remain runtime-only and UNVERIFIED. Do not automatically start an actual or harmless probe.

Next authorized work would require a new user scope: review the exact source/record inventory or
complete remaining candidate contract/resource decision. This scope ends without commit/push/runtime.

## Locality and jobs

All issued compiler/link/test commands completed; no native candidate started. Snapshot scope is only
same-user project-CWD jobs. External CWD/remote/container jobs remain UNKNOWN. Preserve existing tasks.
Ignored work/ snapshots, original objects and ELF are LOCAL and not transferred by source publication;
/tmp is not durable. Incremental repair_build.py needs preserved original objects/baseline; another
machine must recover those or arrange a separate clean compiler-only preparation. No automatic restart.

## Machine checkpoint

```context-handoff-state
{
  "schema_version": 1,
  "updated_at": "2026-11-10T08:15:26.016812+00:00",
  "project_root_hint": "/tmp/AeroAIStudio-dart-internal-trace",
  "host": "jiwon-System-Product-Name",
  "git": {
    "head": "0f3eb51319a7a75c18d5930a99280de3455e2bd1",
    "branch": "experiment/dart-internal-trace",
    "status": [
      {
        "status": "??",
        "path": "libgz-physics-dartsim-plugin.so"
      }
    ]
  },
  "evidence": [
    {
      "path": "validation/gazebo-request-guard-v8/reports/final_report.md",
      "sha256": "0c16bd44efabf5a59b376fc1064668155adf7c4db9d0a723fa60410aa78b989f"
    },
    {
      "path": "validation/gazebo-request-guard-v8/reports/tests.json",
      "sha256": "dcca5cdbe2fa8af12ad4133743bf410b45390732439509451b7dbbd397e5f1c5"
    },
    {
      "path": "validation/gazebo-request-guard-v8/reports/source_manifest.json",
      "sha256": "c9e6ec37cf5d063177c61898b63f0f86c2a2fdc03a46e602e01261940caa9991"
    }
  ],
  "processes": {
    "visibility": "VISIBLE_SCOPE",
    "scope": "Same-user Linux processes whose CWD is inside this project; excludes inspector ancestors. No arguments/environment collected. Remote/container jobs and jobs with external CWD need separate inspection.",
    "tasks": [],
    "unreadable_same_user_processes": 0
  }
}
```
