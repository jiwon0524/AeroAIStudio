# Consumer ABI V1 — current checkpoint

현재 사용자 요청: 실제 Gazebo 소비자 기준 정적 ABI/격리 Loader 검증. 기존 docs-only 범위는 종료했고 이 명시적 요청으로 분석만 재개했다. Gazebo/World::step/Stage B/production·시스템 변경 금지는 유지한다. **CONSUMER_ABI_PARTIALLY_VERIFIED / NOT_RUNTIME_VERIFIED / Stage B BLOCKED**. Host 실행 보류.

직접 확인: 소비 ELF 2경로(동일 hash/Build ID) 각각252 import, B/C effective 누락0 및 metadata mismatch0. installed Bullet 보조 소비자53 import를 별도 분석했다. plugin2×A/B/C=6 및 optional modules2×3=6 relocation 검사 오류0. core/external은 지정 빌드, Bullet은 명시적 설치 모듈 유지. 완전 isolated stack 또는 binary type ABI 인증이 아니다. 9 layout을 재실행해 일치, VTable/RTTI ELF metadata 확인; 설치 DWARF 부재로 inline/virtual/return ABI UNKNOWN. OFF 추가 진입/metadata 평가와 ON 추가 virtual 조회 위험 유지.

증거: `validation/dart-consumer-abi-v1/reports/final_report.md`, `verdict.json`, `consumer_inventory.json`, `consumer_symbols.json`, `abi_comparison.json`, `loader_results.json`, `module_loader_results.json`, `risk_assessment.json`, `instrumentation_review.json`. 테스트 이번 실행 consumer12/native45/regression108=165 PASS, failures/errors/skips0 (`test_summary.json`, 로컬 work/*.xml/log). 과거144/44/V2 153은 별도 역사 결과이며 중복 합산하지 않는다. 신규 integrity manifest 전후21091 files 변경0, main status 보존 (`integrity.json`). 최초 main CWD에서 신규 script 작성 시도는 경로 부재로 변경 없이 실패했고 실험 worktree에서 수정했다.

현재 변경 소유: 이 작업의 신규 `validation/dart-consumer-abi-v1/{scripts,tests,reports}` 및 이 handoff만 게시한다. 기존 소스/보고서 변경0. work/raw manifests/log/binary는 제외한다. branch experiment/dart-internal-trace, 시작 clean HEAD b3c3f0f, origin 원격 시작 일치. 게시 직전 상태이며 commit/push 및 원격 일치 영수증은 새 reports/git_publication.json에 로컬 기록한다. receipt 자체로 재귀 commit하지 않는다.

다음 최소 작업: 소비 inline/virtual 접근 타입과 retained Bullet→core 계약의 정적 증거 보완 및 잔여 위험 수용 범위 명시. 별도 실행 승인 전 Host/물리 실험을 시작하지 않는다. 이 요청은 오프라인 범위 완료다.

실행 중 작업: snapshot의 host/PID/start 관측 참조. 알려진 분석/테스트 subprocess는 모두 완료했다. 외부 CWD/원격/container는 UNKNOWN. 기존 작업 종료/계정 변경은 하지 않았다. /tmp worktree 및 ignored evidence는 기기 이동 시 자동 전달되지 않으며 Git은 경량 파일만 전달한다.

---
아래는 이전 단계 기록이며 실행 범위와 다음 행동은 위 현재 체크포인트가 우선한다.

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
  "updated_at": "2026-11-06T05:03:25.072758+00:00",
  "project_root_hint": "/tmp/AeroAIStudio-dart-internal-trace",
  "host": "jiwon-System-Product-Name",
  "git": {
    "head": "b3c3f0f3960786799b38350a8c572955f3e62433",
    "branch": "experiment/dart-internal-trace",
    "status": []
  },
  "evidence": [
    {
      "path": "validation/dart-consumer-abi-v1/reports/verdict.json",
      "sha256": "755d6d9f1ccbb49165a953e16ee1c3a1ae38b853973b489a9a0618e7b6901ed1"
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
