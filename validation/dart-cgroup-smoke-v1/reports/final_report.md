# Aero AI Studio — Cgroup Transient Service Smoke Test V1

## 최종 판정과 범위

**CGROUP_SMOKE_VERIFIED / Probe A~D BLOCKED / NOT_RUNTIME_VERIFIED / Stage B BLOCKED.** 승인된 transient service 한 개에서 `/usr/bin/sleep 5`만 실행했다. MemoryMax64M·TasksMax8·CPUQuota25%의 설정과 실제 cgroup readback, 단일 sleep의 membership, 정상 종료·unit/cgroup 제거를 확인했다. 자원 초과 시 강제 효과, 자식·손자 상속, Bubblewrap 결합은 이번 실행의 검증 대상이 아니다.

## 인계·승인·Git 대조

AGENTS·DEVELOPMENT_RULES·handoff·Readiness final/approval_plan/verdict를 읽고 context-handoff 스킬로 실제 상태를 대조했다. 시작 local/remote HEAD `ce1eb75d785680090ca6930d2390bd491e10b704`, branch `experiment/dart-internal-trace`, 실험 Git clean을 확인했다. main HEAD `46134c6bf5670ed61ba252f394ccdddb7ff2cf6b`의 기존 수정8/미추적31/staged0은 보존했다. 이전 snapshot4d72768은 ce1eb75 게시 전 관측이며 parent/기존 commit 범위와 연결한다.

이번 사용자 메시지가 단일 transient smoke의 명시적 실행 승인이다. 이전 handoff의 승인 대기는 이 제한된 실행에 대해 해소됐고 pressure/자식/Bubblewrap/DART 실행 금지는 유지된다. `plan_reconciliation.json`에 원래 계획 SHA·이번 argv·차이를 기록했다. 고유 unit 이름과 절대 systemd-run 경로, 종료 결과 관찰용 `--wait`만 바꿨다. 부모 observer가 CLI를 비동기로 실행해 service 생존 중 readback하므로 payload와 제한은 늘어나지 않는다. 원래 계획의 swap0/period100ms/runtime8초/stop2초/KillMode/control-group/OOMPolicy/Delegate=no/app.slice는 유지했다.

## 생성·실행·종료

생성 unit: **`aero-cgroup-smoke-v1-20261106T155112-4b7184a3.service`**.

일반 UID1000 호스트에서 사용자 manager running과 cpu/memory/pids 위임, 고유 unit LoadState=not-found 및 candidate cgroup 부재를 먼저 확인했다. systemd-run 호출은 **1회**, service payload는 sleep5 하나였다. work의 one-shot marker로 재실행을 막는다. 기존 사용자 unit에 start/stop/set-property를 하지 않았다.

생존 중 active/running·Transient=yes와 manager가 반환한 정확한 ControlGroup을 읽었다. `/proc`의 host PID **183582**, start identity **17570619**, executable `/usr/bin/sleep`와 cgroup membership을 대조했다. cgroup.procs에는 해당 sleep PID 하나만 있었다. 원시 프로세스 명령행이나 환경은 수집하지 않았다.

`systemd-run --wait`는 exit0, `Finished with result: success`, 실제 main exit0을 반환했다. service runtime은5.011초였다. 이후 exact unit은 LoadState=not-found, 해당 cgroup 디렉터리는 제거됐고 같은 PID/start identity는 남지 않았다. 수동 stop이나 controller 복구 명령은 필요하지 않았다. 47회 관측은3개 상태 전이로 경량화했고 원본은 work/unit_lifecycle_full.json SHA로 연결했다(`unit_lifecycle.json`).

## 설정과 실제 제한

|항목|systemd 설정 readback|실제 cgroup 값|판정|
|---|---|---|---|
|MemoryMax64M|67108864 bytes|memory.max=67108864|PASS|
|MemorySwapMax0|0|memory.swap.max=0|PASS|
|TasksMax8|8|pids.max=8|PASS|
|CPUQuota25% /100ms period|CPUQuotaPerSecUSec=250ms, CPUQuotaPeriodUSec=100ms|cpu.max=25000 100000|PASS|

CPU quota는 한 CPU의25% bandwidth에 해당한다. 이 숫자 일치는 설정 적용·readback 근거이며 실제 CPU throttling 시험 결과가 아니다. sleep은 부하를 발생시키지 않았고 메모리 고갈·PID 고갈·CPU 과부하를 시도하지 않았다. `resource_readback.json`에 정확한 target 경로·설정·PID 증거가 있다.

## 상위·형제 controller 비교

실행 전후 사용자 manager tree 및 해당 경로의 상위·직접 형제 경로까지 **78개 cgroup**, 다음 **6개 설정 파일**을 비교했다: cgroup.controllers, cgroup.subtree_control, memory.max, memory.swap.max, pids.max, cpu.max. 실행 중에는 own 신규 unit을 포함해79개였다. 사용량 같은 동적 값이나 모든 systemd 정책 전체가 동일하다는 주장은 하지 않는다.

실행 중 기존22개 경로에서43개 필드 변화가 있었다. app.slice의 subtree_control은 `memory pids`→`cpu memory pids`, 형제 cgroup에는 cpu controller와 기본 unlimited `cpu.max=max 100000`이 나타났다. 이는 approval_plan에 사전 고지한 systemd CPU controller 전파와 일치한다. 기존 cgroup의 관측한 memory/pids 제한 변경이나 유한 CPU quota 변경은 없었다.

**종료 후 기존 경로의 비교 필드 변화0건**이고 before/after snapshot SHA도 동일하다. systemd가 자동으로 원래 관측 상태로 돌아왔으며 수동 controller 비활성화·부모 설정 복구·사용자 manager 재시작을 하지 않았다. 원본78경로 snapshot 세 개는 work에 보존하고 SHA와 모든 변경은 `controller_diff.json`에 기록했다. 예상하지 못한 권한 오류·설정 변화는 관측되지 않았다.

## 테스트·보존

실제 smoke와 사전조건 검사 **13 PASS / 0 FAIL / 0 SKIP**, 차이 분류·계획 검증의 독립 오프라인 **6 PASS**다. 보존 검사1 PASS를 포함해 **20 PASS / 0 FAIL / 3 SKIP**이다(`test_summary.json`). memory/PID/CPU 초과 시험3개는 미승인이므로 SKIP으로 구분한다. 실제 DART/Gazebo·Probe A~D는 별도 NOT_RUN이다. 생성 첫 시도가 통과했고 실패 run이나 자동 재시도는 없었다.

`integrity.json`: 기존 **54522개 파일 변경·누락0 / 기존 범위 신규0 / main HEAD·status 유지 PASS**다. 이전 단계 파일 수와 범위가 다르다. 새 task와 실험 handoff만 변경 허용 대상으로 제외했다. 이전 V1~V4/Targeted/Readiness/Sandbox/Cgroup Readiness evidence와 main 기존 미커밋 파일은 보존했다. 시스템 전역 cgroup 설정·AppArmor·패키지·라이브러리·production·Clock/Capture·solver·기존 AI 기능을 변경하지 않았다. 의도된 systemd의 일시 controller 전파는 위에서 별도로 공개했다.

## Git 게시와 다음 최소 작업

검증된 새 경량 scripts/tests/reports 및 handoff만 명시 staging/diff 검토 후 승인된 실험 branch에 commit/push한다. 실제 SHA·원격 일치는 로컬 reports/git_publication.json과 최종 응답에 기록한다. 자기 SHA를 위한 재귀 commit은 만들지 않는다. raw work·전체 manifest·원시 반복 status·controller snapshots는 Git에서 제외한다. /tmp raw/ignored·main untracked 원본은 Git push로 다른 기기에 자동 전달되지 않는다.

다음 권장 최소 작업은 **별도 승인 아래 무해한 자식·손자의 같은 cgroup 상속 및 Bubblewrap 결합을 확인**하는 것이다. 그 뒤에만 별도 승인된 유한 memory/PID/CPU 초과 시험으로 효과·종료·로그 보존을 검증한다. 이번 sleep smoke는 aggregate 압력 검증이나 전체 sandbox 안전성 인증이 아니다. A의 의존성 closure/RUNPATH/init-fini/native fixture·Destructor/Allocator·Exception/Unwinding 위험도 남아 있다. 이번 종료 후 DART Runtime이나 pressure 테스트를 자동 시작하지 않는다.
