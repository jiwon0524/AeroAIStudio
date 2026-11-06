# Aero AI Studio V0.7.1 — Capability/ABI V2 handoff

Updated: 2026-11-06T03:10:31.531921+00:00. Worktree `/tmp/AeroAIStudio-dart-internal-trace`. Branch `experiment/dart-internal-trace`, HEAD `25db73b55f758cd34944ced8111fcf580118db02`.

## Goal and current scope

The current request adds development rules authorizing automatic verified checkpoint commit/push at five stage boundaries. docs/DEVELOPMENT_RULES.md is authoritative; AGENTS.md links it. This documentation task does not resume DART investigation/build/runtime. The prior DART Capability/ABI request is complete within the isolated offline scope. The earlier Contact/Constraint cause-tracing prompt was explicitly cancelled and performed reads only. No simulation/campaign followed that cancelled request.

Final verdict: **PARTIALLY_RESOLVED / HOST_BLOCKED_ABI_PARITY_PENDING / NOT_RUNTIME_VERIFIED. Stage B BLOCKED.**

## Instructions and restrictions

Read this worktree's `AGENTS.md`. No Gazebo, World::step, Stage B, production Physics/SDF/system package/library changes, global loader changes, old evidence overwrite, Capture/Clock criteria changes, main edit/push/merge or force push. No account switch or existing process termination. Only verified lightweight experiment-branch commits/push were authorized.

Original main worktree `/home/jiwon/Projects/AeroAIStudio` remains at `46134c6bf5670ed61ba252f394ccdddb7ff2cf6b` with its pre-existing modified8/untracked31 files intact. During the prior DART task its AGENTS.md/handoff.md were not edited. This new explicit rules request updates only its local untracked AGENTS.md to remove the stale blanket commit ban and point to these rules; its code, evidence, older handoff and other dirty files stay unchanged. This experiment worktree is the continuation location for this task.

## Completed work and primary evidence

All relative paths below start at `validation/dart-capability-abi-v2/`.

- `reports/final_report.md`: Korean16-section report and limits. `reports/verdict.json`: machine verdict.
- `reports/dependencies.json` / `reference_modules.json`:11 dependency/tool deb files plus2 same-DART-version optional module reference debs, all apt-index SHA-256 verified. Download/extraction only; installed packages unchanged.
- `reports/build_results.json` / `build_failure_resolution.json`: failed initial include classification preserved; new final Baseline and Trace core/external/IPOPT/NLOPT/ODE targets built with Werror retained.
- `reports/build_profile.json`: HAVE_IPOPT/HAVE_NLOPT/HAVE_ODE now1 in installed/B/C via real detection, not forced macros. Remaining generated config differences are4 source/data path constants.
- `reports/abi_summary.json`, `symbol_differences.json`, `instrumentation_delta.json`, `loader_checks.json`: Core exports5739 match installed; all old module exports retained. External adds19 diagnostic ELF exports, Core12 new recorder imports, External45 new imports. Isolated5-library/plugin relocation checks passed.
- `reports/dwarf_comparison.json`: all10 comparisons completed. Same-profile Baseline→Trace core exit0; optional ODE/IPOPT/NLOPT exit0; external adds17 typed functions (19 ELF symbols). Existing/reference binaries lack type debug corpus, so their exit0 is symbol-only evidence, not full installed type ABI parity.
- `reports/debug_coverage.json`, `installed_debug_paths.json`, `original_debug_buildinfo_probe.json`: original type debug/buildinfo unavailable; exact repository candidates404. Original compiler/full historical flags and dependency versions remain UNVERIFIED.
- `reports/abi_layout.json`, `vtable_sizes.json`:9 size/alignment observations match;403 existing declaration headers unchanged. Optional installed-header arm uses matching distribution source fallback, not original binary layout telemetry.
- `reports/test_summary.json`: final native45+fenced old regression108=153 distinct PASS, fail/error/skip0. The initial new metadata audit failed once because OFF getType expectation was wrong; source Active guard checked and test corrected (OFF identical/ON extra). Initial XML/log remain local; no instrumentation source change or production criterion relaxation.
- `reports/neutrality_static_review.json`, `metadata_call_observation.json`:5 original token sequences preserved; solve/apply order and impulses match limited fixtures. No runtime/timing/FP/clock/Position Integration execution certification.
- `reports/patch_roundtrip.json`: zero-context patch recreates the exact7 tested source files; payload unchanged.
- `reports/integrity.json`:13,281 original files and copied sources preserved; main HEAD/dirty status and package status unchanged. Final post-push main HEAD/status also checked.

These are directly observed this task. Prior implementation144 and parity-v1 44 PASS remain historical and are not added to current153. Full raw logs/manifests and large build outputs remain in this worktree, not Git.

## Changes and version control

Commit `25db73b55f758cd34944ced8111fcf580118db02` was pushed without force to `https://github.com/jiwon0524/AeroAIStudio`, branch `experiment/dart-internal-trace`. Remote experiment commit verified; remote main remains46134c6. No main merge/push/edit.

Explicitly selected68 files, ~0.77MB: new AGENTS, minimal configuration/docs, same instrumentation patch, ABI scripts, reviewed fixtures/tests and lightweight result reports. Staged filename list/whitespace/secret scan passed. No original dirty diagnostic file, downloaded package, shared library, large build/cache/virtualenv or raw full manifest included. `reports/git_publication.json` holds local commit/push details and is intentionally not recursively committed. That scientific commit kept handoff.md local. The current rules checkpoint also versions handoff.md on the experiment branch; raw logs, packages and local publication receipts stay local.

## Current automatic publishing policy checkpoint

- Current authorized target: origin AeroAIStudio, experiment/dart-internal-trace only. main merge/push and force push remain prohibited.
- Automatically publish after implementation/tests, a research phase, a confirmed failure/blocker, before account/device change, and at final milestone completion. Confirm evidence and explicitly select files; do not wait for a separate publish prompt when conditions hold.
- Confirmed failure documents may be published without pretending the code passes. Unverified code, other people's dirty/staged files, large raw artifacts and credentials are excluded. On authentication/divergence/verification problems, preserve work and report the blocker without automatic login/reset/rebase/merge.
- This is agent workflow automation, not a daemon/hook. Common skill repository is unchanged. Existing physical execution restrictions remain.
- Verification for this docs-only request: rule coverage/content/link review, Git diff/whitespace review, original dirty-file preservation excluding the intentionally updated local AGENTS. No DART tests/builds were rerun.
- This machine checkpoint is a PRE-PUBLISH observation. A following commit limited to these three policy/handoff files is expected to change HEAD; reconcile its parent and file list rather than assuming equivalence. Local publication receipt is validation/checkpoint-policy-setup/publication.json (not committed). Do not recursively commit a file just to put its own commit hash inside it.

## Running work

Observation time/host and process visibility are in the state block. All known build, test and abidiff commands have completed; no analysis session needs restarting. The CWD-based same-user scan reports 0 visible tasks, visibility `VISIBLE_SCOPE`. Remote/container/external-CWD jobs remain outside scan coverage. Do not infer global absence or terminate other work.

## Open issues and next minimum action

Capability3 is resolved. Whole installed ABI/build parity and runtime neutrality are not certified. For a future separately requested DART phase, the candidate next action is original debug symbols/buildinfo acquisition or a bounded consumer/type ABI scope. For the current rules task, validate and publish only AGENTS.md, docs/DEVELOPMENT_RULES.md and this handoff checkpoint, then observe these rules at later stage boundaries. This is a prospective next task, not permission for Host, new campaign, model/solver changes or main merge.

## Portability and account changes

Read this worktree's handoff first, not the original main's older checkpoint. `/tmp` worktree/build/download artifacts are local and may be removed by OS cleanup; the pushed lightweight reports/patch/scripts are durable, but they do not transfer original ignored evidence or pre-existing uncommitted main diagnostics. Future use of the108 regression suite needs the original preserved workspace; common.py input path needs adapting on another machine.

Common skill source remains outside the project at `/home/jiwon/Projects/my-agent-skills/skills/context-handoff`, installed through `/home/jiwon/.agents/skills/context-handoff`. It was not modified/published by this DART task. No credentials or account data recorded.

## Machine checkpoint

```context-handoff-state
{
  "schema_version": 1,
  "updated_at": "2026-11-06T03:10:31.531921+00:00",
  "project_root_hint": "/tmp/AeroAIStudio-dart-internal-trace",
  "host": "jiwon-System-Product-Name",
  "git": {
    "head": "25db73b55f758cd34944ced8111fcf580118db02",
    "branch": "experiment/dart-internal-trace",
    "status": [
      {
        "status": " M",
        "path": "AGENTS.md"
      },
      {
        "status": "??",
        "path": "docs/DEVELOPMENT_RULES.md"
      }
    ]
  },
  "evidence": [
    {
      "path": "AGENTS.md",
      "sha256": "b2e2a3e8d6492884f646f124f9fa64c669185e025a5f8db228136f4aabc40594"
    },
    {
      "path": "validation/dart-capability-abi-v2/reports/final_report.md",
      "sha256": "54e99c37ca6e5ca561de9d7dbc85cfd8ff1aabc13e7fc41f1e61a6399edbbad5"
    },
    {
      "path": "validation/dart-capability-abi-v2/reports/verdict.json",
      "sha256": "b2782a1390474fdcaf4e53bcda6ae86d3ae6bae02ce6c55a4515fc61159a51a5"
    },
    {
      "path": "validation/dart-capability-abi-v2/reports/test_summary.json",
      "sha256": "fd44f2a2148753d80ffc01a6fb5c137ce2a940151cb5db1e393074dce7248e88"
    },
    {
      "path": "validation/dart-capability-abi-v2/reports/dependencies.json",
      "sha256": "92edbdb90549a727a0e81a6393ef5fc6bf3c30deaede55cbf935829d773044c3"
    },
    {
      "path": "validation/dart-capability-abi-v2/reports/build_results.json",
      "sha256": "ac9f22cdf3268d178ee16e19ff23ed85dcedcc91e6b3d18b08e61e7f3fc6ad16"
    },
    {
      "path": "validation/dart-capability-abi-v2/reports/abi_summary.json",
      "sha256": "d15a8f2b6238554768598b824eab13808476bdc2454b961f5ae7ac4ce883d2e7"
    },
    {
      "path": "validation/dart-capability-abi-v2/reports/dwarf_comparison.json",
      "sha256": "46d734428121d28b745e5ce6531b5bc2f8fc0f6835a948a17cbe964d6f632468"
    },
    {
      "path": "validation/dart-capability-abi-v2/reports/debug_coverage.json",
      "sha256": "aa0e77279d58adf0275146db84967f61b129b3cc490015bb612651bbcda8c7dd"
    },
    {
      "path": "validation/dart-capability-abi-v2/reports/integrity.json",
      "sha256": "156e2b7575bf18b19b9118652bbbfe7bc7ed40f054db6e963f54af995aea2747"
    },
    {
      "path": "validation/dart-capability-abi-v2/reports/patch_roundtrip.json",
      "sha256": "7e2b70b748a4eba1d34fa7eefd2a5090ba0687461b10b1c2766c546fac2efa99"
    },
    {
      "path": "validation/dart-capability-abi-v2/reports/git_publication.json",
      "sha256": "b24e61cf2492a51dce1218fae9e0d621020d0925e0c160d9404004c37fdb3157"
    },
    {
      "path": "docs/DEVELOPMENT_RULES.md",
      "sha256": "907019ccb9343e4155d59847400912ce99bf0c08136f6e6bbf3dbcf9ca585a96"
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
