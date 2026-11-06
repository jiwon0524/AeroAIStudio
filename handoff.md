# Destructor Cleanup V4 — current checkpoint

목표: slot18 D1·Node-subobject D0/complete cleanup·Bullet/Core sized delete/EH를 유한 정적 분석으로 보완하고 다음 검증 방법 결정. **DESTRUCTOR_BOUNDARY_PARTIALLY_VERIFIED / Host NEEDS_TARGETED_EVIDENCE / NOT_RUNTIME_VERIFIED / Stage B BLOCKED**. V4는 Gazebo/World::step/Stage B/실제 DART 객체 생성·삭제/예외 runtime/production·시스템·solver·Clock/Capture 변경 금지. 이번 오프라인 범위 완료이며 새 정적 단계/Runtime을 자동 시작하지 않는다.

직접 관측: 설치 slot18 A0x2f0b70/B0x2f0f60/C0x2f0fd0, AP/offset144, FDE997bytes. A는 **INFERRED D1**이며 symbol 복구나 IDENTIFIED가 아니다. AP역할·complete vptr resets·known base cleanup 순서·D0 직접 call과 제한적 정규화 body 일치로 추론했다. Nested helper semantic proof는 없으며 C 종료조건. A primary D0 0x2f1020이 slot18 call 후 size1664 delete, Node-adjusted ShapeNode D0 0x2f1280이 LEA this−144 후 slot18 call/delete1664. **일반 Node D0→Node D1 가정 없음**. B/C 전용 Node D2 관측, 독립 Node D0/D1/ShapeNode D2 정의 부재를 ABI 누락으로 보지 않는다.

Bullet Object/Group D0의 size48/368과 새 compile-only A-header/B/C sizeof 일치. Object/Group/Detector D0 및 allocator import/version 기록. Factory LSDA4 callsites 중3 cleanup LP, ctor failure0x2024d→0x20353→cold0x12c1c에서 delete48/공유 참조 정리 후보/Unwind_Resume 경계 확인. selected D1/D0 FDE는 LSDA없음; no-throw나 EH 동등성을 의미하지 않는다. 중첩/간접 deleter·lifetime·allocator interposition·full installed layout/compiler·OFF/ON runtime neutrality는 UNKNOWN/HIGH.

이번 **12 new +16 V3 +13 V2 +12 V1 +108 project offline=161 PASS**, final fail/error/skip0. Native45는 World/Skeleton/ShapeNode/Constraint 생성으로 V4 금지에 걸려 **NOT_RUN**; 과거194를 재실행한 것으로 합산하지 않는다. 최초 신규11PASS/1FAIL은 SUB immediate를 예상한 테스트 기대와 실제 LEA−0x90/MOV 차이; 정확한 instruction pair와−144 계약으로 검사 보완, 최초 XML/log 보존. fresh loader12 오류0, import 누락0. 전후 **30673 files 변경0**, main HEAD/status 보존.

증거: `validation/dart-destructor-cleanup-v4/reports/{final_report.md,slot18_analysis.json,destructor_call_graph.json,ownership_contract.json,exception_cleanup.json,consumer_reachability.json,analysis_stop.json,risk_assessment.json,verdict.json,test_summary.json,integrity.json,targeted_evidence_plan.md}`. 새 scripts/tests/경량 reports만 게시, raw work/바이너리/최초 실패/manifests는 로컬 보존·Git제외. 기존 V1~V3/Capability 파일은 읽기 전용. 재현 reports/reproduction.md는 역사 XML/기존 build 의존성을 명시한다.

V3 handoff REVIEW_REQUIRED는 c22f947 snapshot→a7a7b32 게시 HEAD 차이 하나. parent/30files/evidence hash 일치로 검토 완료(`handoff_reconciliation.json`), helper를 초기 MATCH로 보고하지 않았다. 아래 V4 state도 게시 전 snapshot이며 예상 HEAD 전이는 commit parent/scope로 대조한다. 자기 SHA를 넣기 위한 재귀 commit 없음.

Git: experiment/dart-internal-trace, 시작 HEAD/원격 a7a7b32b9aade588a0f134637b46b4211a973cc4 clean. 이번 V4 경량 files와 handoff만 명시적 게시 대상. 게시 직전 기록이며 최종 commit/push/remote 일치 영수증은 새 reports/git_publication.json에 로컬 보존. main dirty/evidence를 staging하지 않는다.

다음 최소 작업: **정적 반복 종료**. exact Build-ID debug/symbol 자료를 확보하거나 targeted_evidence_plan.md의 비물리 객체 수명·allocator/unwind probe 계획을 검토한다. 이 probe도 실제 생성·삭제가 필요해 별도 사용자 승인 전 실행 불가. Host READY 판정 아님. 짧은 subprocess만으로 ABI UB가 통제됐다고 보지 않는다. 별도 승인 전 객체 probe/Host/Gazebo/World::step/Stage B 실행 금지.

알려진 compiler/static/pytest/hash 작업은 모두 완료. snapshot host/PID/start 관측 참조; 외부 CWD/remote/container는 UNKNOWN. 기존 프로세스 종료/재시작/계정 변경 없음. /tmp build·ignored work/raw evidence는 Git push로 다른 기기에 전달되지 않는다. 공통 handoff 스킬 수정 없음.

---
아래는 과거 단계 기록이다. 현재 목표·판정·다음 행동은 위 V4 체크포인트가 우선한다.

# ShapeNode Boundary V3 — current checkpoint

목표: ShapeNode V2 미해석67 슬롯, virtual/RTTI/thunk와 Bullet/Core 생성·소멸·소유권/EH 경계를 정적 ELF·disassembly·compile-only 및 허용 offline 회귀로 보완. **SHAPENODE_BOUNDARY_PARTIALLY_VERIFIED / NOT_RUNTIME_VERIFIED / Stage B BLOCKED / Host NOT_READY**. Gazebo/World::step/Stage B/대상 객체 생성·삭제/throw-catch runtime/production·시스템/solver/Clock/Capture 변경은 하지 않았다. 이번 오프라인 범위 완료이며 자동 Host 단계 없음.

직접 결과: V2의 정확한67 table indices/275 words를 재현, 고유 target49. B/C67 모두 full local symbol로 IDENTIFIED,49 unique 모두 DWARF source 확보. 설치 A는 **IDENTIFIED0 / INFERRED48 / UNRESOLVED19**. 추론 중6은 bounded local callgraph,42는 이름 없는 callee/RIP 정규화 한계. B/C slot58 구현/최적화 차이는 함수 identity/ABI mismatch와 구분한다. A primary D1 slot18은 unresolved. AP21, D1/D0 각각21 slots, nonvirtual thunk12/virtual30 entries(반복 포함). B/C 이름을 설치 A의 직접 확인으로 올리지 않았다.

소비: Gazebo 실제 ShapeFrame call vptr+40은 ShapeNode header AP816의 slot107로67 밖이다. 설치 core NodeDestructor의 jmp *8은 actual ShapeNode인 경우 Node AP552의 slot70 D0로 이어질 수 있어 INDIRECTLY_REACHABLE.67 usage는 direct0/indirect1/not-observed25/unknown41이며 미관측을 불가능으로 보지 않는다. Bullet Object/Group local D0의 sized delete48/368 확인; complete lifetime/allocator/cleanup 계약은 미검증. FDE/LSDA/personality 포인터 복호화, selected49 LSDA는 gcc_except_table. LSDA action/catch semantics 및 runtime unwind는 UNKNOWN.

이번 테스트 **16 new +13 V2 +12 V1 +45 native +108 regression=194 PASS**, final failure/error/skip0. 최초 신규15PASS/1FAIL은 빈 입력이 unsupported EH 전에 truncation으로 거부된 fixture 기대 오류다. 완전8byte 음수 입력으로 목적을 분리했고 별도 truncation/잘못된 offset/relocation 거부 기준은 유지했다. 최초 XML/log 보존. fresh loader12 오류0, Gazebo252/Bullet53 import 누락0. 전후 **30188 files 변경0**, main HEAD/status 유지. 과거 V2 178/30031은 역사 결과로 분리했다.

증거: `validation/dart-shapenode-boundary-v3/reports/{final_report.md,shapenode_slots.json,consumer_virtual_calls.json,destructor_contract.json,ownership_boundary.json,rtti_thunks.json,exception_abi.json,risk_assessment.json,verdict.json,test_summary.json,integrity.json}`. scripts와 tests 신규만 작성; work의 raw ELF/disassembly/FDE/초기 실패/manifests는 로컬 보존·게시 제외. 재현 reports/reproduction.md. 기존 V1/V2/Capability 결과는 수정하지 않았다.

시작 인계 REVIEW_REQUIRED는 HEAD 차이 하나였고2edd9e9→c22f947 parent/26files/evidence hash 일치로 검토 완료(`handoff_reconciliation.json`). 이 state도 게시 전 snapshot이며 다음 commit parent와 명시적 파일 목록으로 대조한다. 예상 HEAD 차이만으로 재귀 commit하지 않는다.

Git: experiment/dart-internal-trace, 시작 HEAD/원격 c22f9476d9d2244c244e87272fa1a927e49d6658 clean. 이번 V3 경량 reports/scripts/tests와 handoff만 게시 대상. 게시 직전 기록이며 commit/push/remote 일치 최종 영수증은 새 reports/git_publication.json에 로컬 보존. main dirty/기존 evidence는 staging하지 않는다.

다음 최소 작업: 가장 먼저 primary D1 slot18의 base cleanup/callee 및 Node D0→D1, 이어 Bullet custom-deleter/EH critical edge를 matching debug/symbol map 또는 bounded disassembly로 보완한다. 별도 승인될 비물리 lifetime/cast/unwind 시험 계획을 먼저 검토한다. 짧은 subprocess/physics 실행이 ABI UB를 통제했다고 보지 않는다. Host 시작은 잔여 위험 항목별 수용과 별도 사용자 승인 전 금지.

작업 상태: 알려진 compiler/static/pytest/hash는 모두 완료. snapshot host/PID/start 관측 참조; 외부 CWD/remote/container는 UNKNOWN. 기존 프로세스 종료/재시작·계정 변경 없음. /tmp build와 ignored work/raw evidence는 Git만으로 기기 이동되지 않는다. 공통 context-handoff 스킬 변경 없음.

---
아래는 이전 단계 기록이다. 현재 목표·판정·다음 행동은 위 V3 체크포인트가 우선한다.

# DART Consumer ABI Deep V2 — current checkpoint

현재 목표: 설치 Bullet↔격리 core 객체 계약, Gazebo inline/member 접근 및 virtual/RTTI 위험을 정적·compile-only로 줄이는 명시적 V2 요청. **CONSUMER_ABI_DEEP_PARTIALLY_VERIFIED / NOT_RUNTIME_VERIFIED / Stage B BLOCKED. Host NOT_READY**. Gazebo/World::step/Stage B/production·시스템/solver/Clock/Capture 변경 금지 유지. 이번 오프라인 범위는 완료했으며 후속 물리 작업을 자동 시작하지 않는다.

직접 확인: 10타입 A(extracted matching packaged core headers + source Bullet fallback)/B/C compiler member/base/vtable 배치 일치. 현재 시스템 DART dev headers는 NOT_INSTALLED이며 ‘A-header’를 실제 설치 binary layout으로 부르지 않는다. 선택된 설치 core getter3종 machine-code 일치, Bullet engine pointer+40/new48, Gazebo Contact stride112 및 object1+72/object2+80/force+48/normal+24/depth+88 binary 접근 확인. core table35 records 중34 완전 symbolic match, ShapeNode275 slots 중67 local targets UNKNOWN이며 비교 가능한 slots 차이0. Bullet local destructors와 모든 소비 inline provenance/installed full layout/compiler buildinfo/lifetime/unwind/runtime neutrality는 미확정이다. 헤더403개 B/C 무변경, matching packaged214개 차이0. 실제 설치 whole ABI 인증 아님.

이번 테스트 **13 new +12 V1 +45 native +108 regression=178 PASS**, failure/error/skip0. 새 boundary는 compile/link 분석만 하고 DART/plugin 객체를 생성·실행하지 않았다. 기존 Native synthetic algebra 회귀 범위는 따로 구분했다. fresh loader12 checks 오류0, Gazebo252/Bullet53 imports 각 arm 누락0. 무결성 **30031 files 변경0**, main HEAD/status 보존. 기존 V1 165PASS/21091 보존은 과거 결과로 분리했다.

근거: `validation/dart-consumer-abi-v2/reports/final_report.md`, `bullet_core_contract.json`, `inline_access.json`, `vtable_rtti.json`, `compiler_abi.json`, `boundary_fixture.json`, `instrumentation_abi.json`, `loader_results.json`, `risk_assessment.json`, `test_summary.json`, `integrity.json`, `verdict.json`. 재현은 reports/reproduction.md; 새 scripts/tests만 사용했다. 초기 ET_REL 주소/Compiler ID parser 출력은 work에 보존했으며 실제 ABI mismatch나 pytest 실패가 아니다.

V1 handoff verify REVIEW_REQUIRED는 head 차이 하나였다. recorded b3c3f0f→observed2edd9e9의 parent/23files/evidence hash 일치로 검토 완료했다(`handoff_reconciliation.json`). helper 자체를 MATCH로 표시하지 않았다. 이번 state도 publish 전 HEAD snapshot이며 다음 commit은 그 parent와 파일 scope로 대조한다.

Git: branch experiment/dart-internal-trace, 시작 HEAD/원격2edd9e989e7ab8186a075cf605ddecb6b7dfa386 clean 확인. 이번 V2 scripts/tests/reports와 handoff만 명시적 게시 대상이다. 본 기록은 게시 직전이며 commit/push/remote 일치 영수증은 새 reports/git_publication.json에 로컬 보존한다. receipt만으로 재귀 commit하지 않는다. main dirty 파일·기존 evidence는 게시/수정하지 않았다.

다음 최소 작업: matching Build-ID debug/symbol map 또는 bounded disassembly로 ShapeNode/Bullet local virtual/destructor targets와 남은 critical member 접근을 좁힌다. 이후 별도 승인될 비물리 lifetime/cast/unwind 시험 계획을 먼저 검토한다. subprocess/짧은 tick만으로 ABI UB를 통제했다고 보지 않는다. 실행 계획의 잔여 위험 수용 및 별도 사용자 승인 전 Host 실행 금지.

실행 중 작업: 알려진 compile/static/pytest/hash 분석은 모두 완료했다. snapshot의 host/start/PID 관측 참조; 프로젝트 CWD 외부/remote/container는 UNKNOWN. 프로세스 종료·재시작/계정 변경은 하지 않았다. /tmp build 및 ignored work/raw 로그는 기기 이동 시 자동 전달되지 않으며 Git은 경량 검증 파일만 전달한다. 공통 handoff 스킬은 수정하지 않았다.

---
아래는 이전 단계 기록이다. 현재 범위·판정·다음 행동은 위 V2 체크포인트가 우선한다.

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
  "updated_at": "2026-11-06T05:58:57.270813+00:00",
  "project_root_hint": "/tmp/AeroAIStudio-dart-internal-trace",
  "host": "jiwon-System-Product-Name",
  "git": {
    "head": "a7a7b32b9aade588a0f134637b46b4211a973cc4",
    "branch": "experiment/dart-internal-trace",
    "status": []
  },
  "evidence": [
    {
      "path": "validation/dart-destructor-cleanup-v4/reports/verdict.json",
      "sha256": "deb9933bd7e8252b46d598ac7058fb48447fb5c25fe5bd8db703622e802d156d"
    },
    {
      "path": "validation/dart-destructor-cleanup-v4/reports/integrity.json",
      "sha256": "045e58955abd1f549d3aaf1e51368cb7db9a85329b2acb34b0c3c9a04f4f6e54"
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
