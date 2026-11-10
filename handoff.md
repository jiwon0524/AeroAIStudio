# Aero AI Studio — small02 single approved runtime checkpoint

## Goal, authorization and stop condition

User explicitly approved exact65d1a64 small02 contract once. It was executed once: exit78 / FAIL.
Approval is consumed. STOP; no retry, cap increase, rebuild, new diagnostic experiment or repair authorized.
Contract SHA256 ab2a778dbcd1e5f6a8923e6ff8270070c7ee5c944caf0017dd9d43043621ef95.
Stage B BLOCKED / risk UNDECIDED / Gazebo runtime UNVERIFIED / original actual launcher exit78 unchanged.
No small01 rerun, large5/303/468 preparation, actual DART/Gazebo/harness, physics, sudo/install/system changes.

## Directly observed runtime result

Current report: validation/gazebo-request-guard-v10-small02/reports/runtime_small_02_report.md.
Evidence hash/mode/process/cleanup/integrity verification: same reports/runtime_small_02_verification.json.
Raw evidence: same work/runtime-small-02/. Consumed marker work/harmless-small-02.once preserved.
Native parent on jiwon-System-Product-Name PID377856/start50665745: last success userns0;
first native failure uid-map -1 with errno1 EPERM, before PID1 worker/O. Which helper subcall or denying policy is UNKNOWN.
Initial owner O and first CATALOG_OBJECT not reached. No successful FD delivery, thread/descendant trace or independent audit.
Collector last wait stage owner-bind-begin, then owner handoff disconnect; native parent final wait78.
Host first failure unit ownership not proven is separate; exact cross-process event ordering unproven.
All13 new runtime files0600, output0700, marker0600. Terminal diagnostic/audit requirements missing: diagnostic_complete false.
Both owned units not-found/MainPID0/empty ControlGroup; both cgroups absent; matching residual process scan0;
native parent identity absent. No cleanup errors. No old tasks stopped/restarted; external/remote tasks UNKNOWN.
119 contract files/202 old v10 content+modes/303 main nonignored paths/1617 baseline files(handoff excluded) match.
Main ignored evidence not re-inventoried; no writes to main. Old small01 marker/log0664 and original dirty files preserved.

## Changes, verification and publication

Only this handoff, small02/progress.md, and two new runtime reports belong to this stage.
No source/tests/build artifact change. Preparation2194 static/mock PASS is historical and not rerun.
Post-run evidence/modes/hashes/proc/cgroup and unit readbacks performed, no runtime replay.
AGENTS/DEVELOPMENT_RULES requires verified lightweight checkpoint commit/push on experiment branch only.
Publication requires actual push+remote match; receipt will be small02/work/runtime-small-02-publication.json.
Raw logs/markers/binaries remain local ignored /tmp artifacts, not durable or automatically portable by Git.
Existing untracked libgz-physics-dartsim-plugin.so stays outside publication.

## Historical preparation

Prepared at65d1a64: same small02 reports/repair_report.md and approval_proposal.md, source_manifest.json,
build_receipt.json, tests.json. Those original documents are preserved as historical pre-runtime evidence.
small01 failed once at05721b8, report published5c6710d under validation/gazebo-request-guard-v10/reports/.
small02 proves the uid-map failure in this attempt; it does not retroactively prove small01's unknown native failure.
Next minimum action: wait for separately scoped user instructions; never reuse consumed small01/small02 markers.

```context-handoff-state
{
  "schema_version": 1,
  "updated_at": "2026-11-10T11:48:02.103309+00:00",
  "project_root_hint": "/tmp/AeroAIStudio-dart-internal-trace",
  "host": "jiwon-System-Product-Name",
  "git": {
    "head": "65d1a6487d732eb598b55f87d25110d085921543",
    "branch": "experiment/dart-internal-trace",
    "status": [
      {
        "status": " M",
        "path": "validation/gazebo-request-guard-v10-small02/progress.md"
      },
      {
        "status": "??",
        "path": "libgz-physics-dartsim-plugin.so"
      }
    ],
    "snapshot_note": "Runtime executed at this approved HEAD. Intended handoff/progress and two runtime reports are task-owned checkpoint edits; remote publication receipt records resulting commit."
  },
  "evidence": [
    {
      "path": "validation/gazebo-request-guard-v10-small02/reports/runtime_small_02_report.md",
      "sha256": "677ebcd84e0d7a4a15f9235aae0c224a1e6f9b685521a6135676768b8b5db10b"
    },
    {
      "path": "validation/gazebo-request-guard-v10-small02/reports/runtime_small_02_verification.json",
      "sha256": "5239d2818434371e67ee91f6476765314897951c76e0410c3f51abbdf69cb35e"
    },
    {
      "path": "validation/gazebo-request-guard-v10-small02/reports/execution_contract.json",
      "sha256": "ab2a778dbcd1e5f6a8923e6ff8270070c7ee5c944caf0017dd9d43043621ef95"
    }
  ],
  "processes": {
    "visibility": "VISIBLE_SCOPE",
    "scope": "same-user project-CWD snapshot 2026-11-10T11:48:02Z no tasks; both owned cgroups absent and matching process scan0; remote/external-CWD UNKNOWN; no arguments/environment recorded",
    "tasks": [],
    "unreadable_same_user_processes": 0
  }
}
```
