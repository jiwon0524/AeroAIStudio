# Aero AI Studio — blocked small02 followup checkpoint

## Current authorization and boundary

User authorized post-cecac03 bwrap trust analysis and only evidence-supported connections/build/static/mock tests.
No new service, consumed trial rerun, marker, Gazebo/DART/harness, physics, sudo/privilege/system/AppArmor change.
Stage B BLOCKED / risk acceptance UNDECIDED / Gazebo runtime UNVERIFIED; actual launcher exit78 retained.
context-handoff used. Verified lightweight checkpoint auto commit/push follows AGENTS/DEVELOPMENT_RULES.
Main and old evidence/markers/dirty files preserved. Current task only adds validation/gazebo-request-guard-v10-followup/ and this handoff.

## Outcome: BLOCKED, diagnostics prepared

Base HEADcecac03db4c0471b8444bd1a961459fd51f3bbdc on experiment/dart-internal-trace.
Current final: validation/gazebo-request-guard-v10-followup/reports/final_report.md.
Trust matrix: same reports/trust_conditions.json. Current status: reports/candidate_status.json.
Direct bwrap substitution cannot prove old PID1/direct-parent/same sealed ELF/pidfd chain;
old single512MiB fixture does not prove new owner5GiB/target512MiB C/K/P/A/audit/cleanup chain.
Current payload capability policy also does not permit assuming old native namespace/mount bootstrap works.
No bwrap adapter or relaxed attestation implemented. No runtime-ready contract, unit, marker or one-run proposal.
Both Python candidate API and built native entry unconditionally return78 before any service/marker operation.

Prepared retained mapping diagnostics: inputs/map_io.h + launch.c adapter records open FD/result, requested/actual
write and close returns with immediate errno before reporting/cleanup. Earlier map error survives close/logger faults.
The32-record/192byte limits remain. This improves observability, not the host UID-map permission itself.
Prepared ownership.inspect_bound single-read observer logs the same row it classifies, rejects incomplete/changed
identity or failed persistence without retry/action. It is not connected to a live launcher.
Failures ledger keeps first failure per source and secondary/cleanup events separately.

## Evidence and validation

reports/build_receipt.json: compile2 changed owner TUs (launch + inert entry), hash-reuse8 objects;
owner ELF not executed. Separate shared-header callback-only mock binary built, no real mapping/namespace calls.
reports/tests.json: final84 Python/static/protocol/mock checks +14 C callback-only cases PASS.
Existing real Owner.bind rejects bwrap PID2/parent ELF/interposed parent/worker ELF/domain faults before O.
Existing coordinator mocked O/Cx4/K/P/A/GO/ACK/V and negative FD/audit/cleanup paths checked; not runtime proof.
Callback C mock invoked3times during test/report additions;14 distinct final cases. Owner/bwrap/service/marker0.
Older2194 static/mock report and historical PASS were read/hash checked, not rerun or added to current count.
reports/unit_ownership_analysis.json: old logged snapshot and owned() fresh lookup can differ; replay confirms it.
Actual failed fresh snapshot fields and global host/native ordering remain unrecorded. No missing ownership accepted.

reports/policy_observation.json: execution-time kernel audit for PID377856 has unconfined→unprivileged_userns
then CAP_SYS_ADMIN DENIED. Current policy files/sysctl/bwrap hash are separately dated; loaded profile list UNKNOWN
due read permission. Historical exact open/write/close syscall still unproven; current diagnostic is only prepared.
reports/preservation.json:377 old v10/small02/PASS files content+modes,303 main nonignored paths,
119 small02 contract hashes and1617 old baseline files(handoff excluded) unchanged. Main ignored evidence not re-inventoried;
no writes to main. Consumed small01/small02 markers, original logs and plugin symlink preserved.
Both old small02 units observed not-found/MainPID0/empty cgroup; no original process stopped/restarted.

## Remaining technical blockers and next minimum action

Need a separately reviewed namespace-factory/owner trust design preserving PID1/parent/ELF authentication,
sealed C/K same-object FD/mounts, sibling owner/target resource domains, pre-GO independent audit and terminal cleanup.
Do not infer that simply wrapping the existing owner in bwrap or weakening receiver checks preserves those conditions.
Actual namespace/capability/LSM/ptrace/SCM/mount/target placement/task audit/EOF/cgroup cleanup would require
separate valid runtime contract and explicit approval, currently unavailable. UID-map behavior remains policy-blocked.
STOP here. Do not run previous or new compiled owner, bwrap, probe, service or marker as a follow-on action.

## Files, publication and portability

Only new followup sources/tests/lightweight reports/progress and this handoff are publication candidates;
exact list: validation/gazebo-request-guard-v10-followup/reports/publication_files.txt.
Preexisting untracked libgz-physics-dartsim-plugin.so remains outside staging. No main/force push/merge.
Actual push+remote match required; local receipt will be followup/work/publication-result.json.
/tmp ignored compiler output/binaries/raw evidence/old markers are not durable or automatically transferred by Git.
Historical small02 failure: validation/gazebo-request-guard-v10-small02/reports/runtime_small_02_report.md,
reported once at65d1a64 and publishedcecac03. Earlier bwrap PASS: validation/gazebo-joint-resolution-v1/reports/harmless_summary.json.

```context-handoff-state
{
  "schema_version": 1,
  "updated_at": "2026-11-10T12:13:24.361196+00:00",
  "project_root_hint": "/tmp/AeroAIStudio-dart-internal-trace",
  "host": "jiwon-System-Product-Name",
  "git": {
    "head": "cecac03db4c0471b8444bd1a961459fd51f3bbdc",
    "branch": "experiment/dart-internal-trace",
    "status": [
      {
        "status": "??",
        "path": "libgz-physics-dartsim-plugin.so"
      }
    ],
    "snapshot_note": "Prepublication tracked clean. Intended new followup files and this handoff are task-owned changes; resulting commit in local publication receipt."
  },
  "evidence": [
    {
      "path": "validation/gazebo-request-guard-v10-followup/reports/final_report.md",
      "sha256": "0e7161eeecbf726ba8aadac018ea69f6632e1f03caf345865e521e64c80c6605"
    },
    {
      "path": "validation/gazebo-request-guard-v10-followup/reports/tests.json",
      "sha256": "9ae1255eb5a326f8b81cdda3a092f26ce57d915acfce31a74ce3c163cef08bab"
    },
    {
      "path": "validation/gazebo-request-guard-v10-followup/reports/candidate_status.json",
      "sha256": "7c368bb38d8f500907cd938903aaf8a9422ed6f068bf9c304df25dd907c270f1"
    },
    {
      "path": "validation/gazebo-request-guard-v10-followup/reports/preservation.json",
      "sha256": "356f5354612d64805983674af1a61deb785007609dff8931cddae1a506f6cdad"
    }
  ],
  "processes": {
    "visibility": "VISIBLE_SCOPE",
    "scope": "same-user project-CWD snapshot2026-11-10T12:07:45Z tasks empty; issued compiler/link/callback mock processes reaped by tools; external-CWD/remote tasks UNKNOWN; no arguments/environment recorded",
    "tasks": [],
    "unreadable_same_user_processes": 0
  }
}
```
