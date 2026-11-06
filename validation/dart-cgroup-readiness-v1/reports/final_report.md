# Aero AI Studio — Cgroup Delegation Readiness V1

## 판정과 범위

**CGROUP_DELEGATION_PARTIAL / Probe A~D BLOCKED / NOT_RUNTIME_VERIFIED / Stage B BLOCKED.** 사용자 관리자에 cpu·memory·pids가 실제 위임된 경로를 확인했다. 현재 terminal leaf에 cpu가 없다는 사실을 호스트 사용자 전체의 위임 부재로 확대하지 않는다. 다만 transient 생성 권한·실제 task cgroup의 제한 적용·초과·정리는 미실행이므로 READY가 아니다.

사용자 요청5절에 따라 이번 작업은 읽기 전용 조사·비실행 설계·오프라인 검증까지만 수행했다. cgroup mkdir/파일 쓰기/controller 활성화/프로세스 이동/StartTransientUnit 호출/systemd-run 실제 workload를 하지 않았다. sudo·패키지·시스템 설정·AppArmor·기존 unit 정책을 변경하지 않았다. 실제 DART/Gazebo 로드·객체·World::step·OFF/ON·Probe·Stage B도 전부 NOT_RUN이다.

## Git와 인계 대조

승인 worktree `/tmp/AeroAIStudio-dart-internal-trace`, branch `experiment/dart-internal-trace`, 시작 local/remote HEAD `4d727687f03a466a941c296d83e94558cfd0173e` 일치, 실험 Git 상태 clean을 확인했다. main HEAD `46134c6bf5670ed61ba252f394ccdddb7ff2cf6b`의 기존 수정8/미추적31/staged0을 보존한다. AGENTS·DEVELOPMENT_RULES·handoff·Hardening V2 final/verdict·Isolation V1·Readiness V1 보고서를 읽었다. V2 snapshot757f3a1과 현재4d72768은 실제 parent/commit으로 연결했다. 하위 validation AGENTS는 발견되지 않았다. V2의20 PASS/4 SKIP·54,483파일은 역사 결과이며 재실행 결과로 합산하지 않는다.

## 실제 cgroup 환경

`cgroup_capabilities.json`은 동일 일반 UID1000의 승인된 호스트 읽기 전용 관측이다. 도구 sandbox 안의 cgroup ro 마운트와 혼동하지 않는다. 호스트 `/sys/fs/cgroup`는 cgroup2 rw이고 systemd255.4-1ubuntu8.18 사용자 관리자는 running이다. 현재 경로는 사용자 관리자 아래 app.slice/terminal.slice/vte scope다. 전체 정확한 경로·계층·파일 권한은 JSON에 기록했다.

|계층|controllers|subtree_control|의미|
|---|---|---|---|
|terminal task leaf|memory pids|빈 값|memory.max=max, pids.max=34727, cpu.max 없음|
|app.slice|cpu memory pids|memory pids|CPU가 사용 가능한 상위지만 하위 CPU 활성화는 현재 없음|
|user@1000.service|cpu memory pids|cpu memory pids|실제 사용자 관리자 위임 경계|
|user-1000.slice/user.slice|cpu memory pids|cpu memory pids|상위 controller 전달 관측|

`cgroup.procs`는 실제 읽었고 count/현재 검사기 포함 여부만 저장했다. 원시 전체 PID 목록이나 프로세스 명령행·환경은 저장하지 않았다. memory.max/pids.max/cpu.max와 cgroup.type/events, directory 및 파일 owner/mode/W_OK도 계층별로 읽었다. W_OK는 관측 당시 권한이며 실제 mkdir/write나 workload authorization의 증거가 아니다. 사용자 PID 상위값은 공유 제한이며 전용 task limit로 취급하지 않는다.

`systemctl show user@1000.service`의 **Delegate=yes / DelegateControllers=cpu memory pids / DelegateSubgroup=init.scope**와 실제 관리자 cgroup 파일이 일치한다. app.slice의 DisableControllers는 비어 있다. `systemd-run --user` 바이너리와 사용자 bus는 사용 가능하고 StartTransientUnit 메서드가 API에 존재한다. 이 메서드는 호출하지 않았으므로 생성 권한과 resource property 수락은 UNVERIFIED다.

## 실행 방식 비교와 권장 후보

`delegation_options.json`에 네 후보를 정리했다.

|후보|aggregate memory/PID/CPU|권한·부작용|선택|
|---|---|---|---|
|systemd 사용자 transient service/scope|설정 가능 후보, 실제 적용 미검증|관리자가 전용 cgroup과 lifecycle 관리; 상위·형제 controller 자동 활성화 가능|**service 우선**, 승인 후 smoke|
|기존 위임 경로에 직접 child 생성|현재 leaf CPU 없음, 직접 작성 미검증|systemd 소유 tree와 충돌·기존 task 이동/부모 활성화 위험|현재 BLOCKED|
|별도 VM/container|호스트/하이퍼바이저 강제 한계가 있어야 함|환경 가용성·권한·controller·정리 모두 별도 확인 필요|UNVERIFIED 대안|
|현재 Bubblewrap+RLIMIT|프로세스별/UID 공유 제한, aggregate 대체 불가|V2 격리 증거를 재사용 가능|보조 수단|

service는 관리자가 새 프로세스를 시작하고 exact unit 정리를 맡길 수 있어 caller가 시작한 프로세스를 묶는 scope보다 이번 경우에 적합하다. payload에 직접 Delegate=yes를 줄 필요는 없다. systemd가 제한을 적용하는 서비스 안에 Bubblewrap을 실행하는 구성을 설계하되 자식·손자가 같은 unit cgroup에 남는지 별도로 확인해야 한다. namespace만 생성한 container나 VM 후보를 자동으로 안전하다고 판단하지 않는다.

설치된 systemd.resource-control/systemd-run/systemd.service 매뉴얼을 읽고 SHA와 해석을 `local_documentation.json`에 기록했다. 매뉴얼에 따르면 자원 속성은 관리자가 상위·형제까지 controller를 활성화할 수 있게 한다. 따라서 CPUQuota 설정이 임시 service 한 개에만 커널 상태 변화를 일으킨다고 약속하지 않는다. 같은 이유로 cleanup 후 ancestor 활성화 baseline이 자동으로 완전히 복구된다고 주장하지 않는다. 수동 controller 비활성화나 사용자 관리자 재시작으로 복구하지 않는다.

## 승인 검토 가능한 첫 실행 계획

실제 실행 명령 배열·한계·사전 검사·증거·정리는 **`approval_plan.json`**에 있다. `scripts/plan.py`는 이 JSON만 출력하며 실행 능력이 없다.

- 새 사용자 service **aero-cgroup-readiness-v1-smoke.service 하나**, payload `/usr/bin/sleep 5`.
- MemoryMax64MiB, swap0, TasksMax8, CPUQuota25%/period100ms, RuntimeMax8초, TimeoutStop2초, KillMode=control-group, OOMPolicy=stop, Delegate=no, 기존 app.slice 사용.
- exact unit의 LoadState=not-found를 먼저 확인한다. 충돌이면 중단하고 다른 unit을 덮어쓰거나 replace하지 않는다.
- 생존 중 manager가 반환한 ControlGroup을 받아 실제 memory.max=67108864, memory.swap.max=0, pids.max=8, cpu.max 비율25%를 읽는다. 추측 경로나 부모 limit만 읽어 PASS하지 않는다.
- sleep 자연 종료, 필요 시 exact 신규 unit만 stop. unit cgroup 빈 상태/제거와 own PID/start 소멸을 확인하고 상태·오류를 보존한다. `--collect`로 unit이 없어지기 전에 필요한 증거를 수집한다.
- 변경 범위는 transient service/cgroup·짧은 journal 메타데이터 및 systemd가 관리하는 controller 활성화다. 영구 unit 파일/수동 cgroup 쓰기/글로벌 설정 변경은 없다. ancestor/sibling의 활성화가 남으면 기록하고 중단하며 자동 수동 복구하지 않는다.

이 smoke도 **사용자 별도 승인 전 실행하지 않는다**. smoke 승인에는 자원 초과·자식 생성·Bubblewrap·DART 실행이 포함되지 않는다. 승인 후에도 환경 실행 권한 요구는 별개다.

## 후속 무해한 Fixture 설계

`resource_test_plan.json`은 미실행 설계다. smoke readback과 정리가 통과한 뒤 별도 승인받아 자체 최소 Fixture를 구현·검토하고 다음을 유한하게 시험한다.

- memory: 전용96MiB/swap0 service에서 자식 최대3개·각48MiB 이하의 bounded touch, memory.events OOM 변화와 own unit 처리 확인. 준비 gate 전에는 할당하지 않는다.
- PID: TasksMax12, 최대16회 생성 시도, child/grandchild/threads 포함 pids.current와 max event/EAGAIN 확인.
- CPU:25%/100ms, 최대2 busy child·2초 wall, cpu.max와 cpu.stat throttling을 확인한다. CPU quota는 강제 종료 대신 throttling이라는 점을 구분한다.
- own descendants의 cgroup membership·PID/start와 stop/timeout 이후 populated0·identity 소멸 확인.
- V2 Bubblewrap 격리와 결합하고 실제 group limit·namespace 조건을 모두 만족한 뒤 본문 진입. wrapper overhead 때문에 TasksMax가 부족해도 자동 상향하지 않는다.
- absent controller·잘못된 limit·unit collision·wrong cgroup·property 거부는 Fail-Closed로 기록하며 RLIMIT fallback이나 무제한 실행을 하지 않는다.

필수 controller나 권한이 부족하면 생성·설정·압력 시험을 하지 않는다. parent 정책·controller 활성화·권한 변경은 이번 범위가 아니며 필요해지면 다시 구체적 승인 대상으로 분리한다.

## 위험 재평가와 검사 결과

`probe_a_blockers.json`에 VERIFIED/PARTIALLY_VERIFIED/UNVERIFIED/BLOCKED를 구분했다. 전체 memory/PID/CPU 제한과 실제 kernel namespace 실패 주입은 UNVERIFIED다. DART dependency identity는 기존 제한 정적 증거만 있어 PARTIALLY_VERIFIED, RUNPATH 빈 항목은 BLOCKED, init/fini 부작용은 UNVERIFIED, Destructor/Allocator 및 Exception/Unwinding은 selected static 근거만 있어 PARTIALLY_VERIFIED다. 이 분류는 runtime 안전성을 낮은 위험으로 승격하지 않는다. B/C arm 문제를 제외한 설치본 A만을 실행하려면 그 축소 범위도 나중에 명시적으로 검토해야 한다.

현재 읽기 전용 관측 **6 PASS**, 오프라인 **7 PASS**, 실제 service/자원/조합 검증 **8 SKIP**: **13 PASS / 0 FAIL / 8 SKIP**. 최초 busctl member 인자 문법 오류1회는 `cgroup_capabilities_initial.json`에 보존했고 XML introspection으로 수정해 메서드 존재를 확인했다. 최초 실패를 삭제하거나 최종 통과와 합산하지 않는다. 실제 resource test 미실행을 PASS로 기록하지 않는다. `test_summary.json`을 따른다.

## 무결성·Git·다음 단계

`integrity.json`: 전후 기존 **54,502개 파일 변경·누락0 / 기존 범위 신규0 / main HEAD·status 유지 PASS**다. 이전 파일 수와 검사 범위가 다르며 새 task와 실험 handoff는 제외했다. 새 task와 실험 handoff만 변경 허용한다. 기존 코드·Evidence V1~V4/Targeted/Readiness/Sandbox V1/V2·미커밋 파일과 시스템 설정을 보존한다. full manifest/work는 로컬 ignored이며 대용량을 게시하지 않는다.

검증된 신규 경량 scripts/tests/reports와 handoff만 명시 staging/diff 검토/commit/push한다. 실제 SHA·원격 일치 결과는 로컬 `git_publication.json`과 최종 응답에 남기며 자기 SHA를 위한 재귀 commit은 하지 않는다. main/force push/reset/rebase/stash/merge는 하지 않는다. /tmp raw와 main ignored/untracked 원본은 Git push로 다른 기기에 자동 이전되지 않는다.

**다음 최소 작업은 approval_plan.json의 단일 sleep5 smoke service 생성·제한 readback·정리 범위에 대한 사용자 승인**이다. 승인 전에는 실행하지 않는다. 이후 별도 pressure 승인→무해한 aggregate 검증→A closure/init-fini/native fixture 감사→Probe A 별도 승인 준비 재평가 순서다. DART Runtime을 자동 시작하지 않는다.
