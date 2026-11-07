# Subject/Observer 소멸 통지 — 승인된1회 실행 결과

**SUBJECT_NOTIFICATION_OBSERVATION_PASS / Probe B PARTIAL / Stage B BLOCKED**.
사용자가 준비 commit3c6654b45c78b42a5eaed3a1ba3d988a84552a29의1회 실행을 명시 승인했다. HEAD/branch/clean,27source·manifest pin,fixture/Core16의 해시·FD identity,62dependency edges/29ROmount·저장된 builder argv,동일readonly Core SONAME alias,고정한도·fresh runtime 출력/두marker 부재를 재확인했다. 환경 승인을 받아 read-only manager running/unit collision 검사 후 지정 launch 명령을 정확히1회 실행했다. wrapper exit0,retry0,limit changes0,source changes0. 이전 Probe 재실행 없음.

## 객체 전 식별·GO

unit aero-notification-v1-runtime-cb58e147a9.service; native hostPID231895/start25308986. strict Core16+fixture17개 mapped file identity PASS_FILE_IDENTITY,namespace/cgroup membership/유일한fixture/live resource gate 및 controller during 확인 후만 GO=true. map_files 직접open은 EPERM이고 기존 proc-rootFD fallback으로 SHA/Build-ID/dev/inode를 확인했다. resident pages/COW/loader constructors 부작용 인증은 아니다. 모든 host process identity/host/time은 execution_review.json과 runtime/native_fixture_execution.json에 있다.

## 통지 기준별 판정

|항목|관측|판정|
|---|---|---|
|대상 identity|생존 중 등록한 서로 다른 ShapeNode/BodyNode Subject 주소와 callback 인자 일치; unknown0|PASS|
|횟수|등록2개,release 전0,외부 Shape reset 후0,ShapeNode1/BodyNode1,total2,duplicate/overflow0|PASS|
|owner 해제 구간|두 callback 모두 Skeleton owner.reset window=true 동안|PASS|
|관측 순서|ShapeNode→BodyNode|PASS: notification order만|
|등록 해제|callback 처리 후 Observer subjects_remaining0|PASS|

고정fixture는 내부 검사 통과 후만 registered/notifications_observed를 출력한다. stdout4이벤트 READY WAIT→registered→notifications_observed→lifetime_success를 strict parser로 확인했다. 실제 callback event는 고정2slot/scalar collector에 기록하고 나중에 출력한다. callback에서 logging/할당/등록변경은 없지만 라이브러리 Observer의 set 등록·해제 동작은 계측 무할당을 보장하지 않는다.

**개별 Skeleton/BodyNode/ShapeNode/Joint destructor 호출과 순서는 NOT_OBSERVED**. 이 순서는 Subject notification 전달 순서이며 derived destructor 진입·D0·완료/free의 직접 증거가 아니다. Subject는 destructor 외에서도 통지를 보낼 수 있다. allocator provider/balance/누수는 NOT_MEASURED. weak_ptr 만료나 exit0을 이 항목의 증거로 쓰지 않았다.

## 종료·자원·정리

systemd-run/native 서비스 exit0,stderr code=exited/status=0,result success. service989ms/CPU243ms/swap peak0B. 실제memory.max67108864,swap.max0,pids.max8,cpu.max25000 100000,active RuntimeMax8s/TimeoutStop2s. initial memory.current4603904bytes,last4861952bytes,peak12402688bytes,pids.current3. 수집된memory.events low/high/max/oom/oom_kill/oom_group_kill/sock_throttled 전부0. 마지막 cgroup 표본은 최종 보장없음; 초과 강제효과는 미시험. 수거 후 최종 unit 실행 속성은 미확인이며 exit0은 wait client/stderr 근거다. 수거된 default unit 한도를 실제 실행한도로 해석하지 않는다. signal/timeout event 관측 없음.

cleanup PASS:unit not-found/inactive/dead,cgroup 제거,관측PID-start잔여0,host temp와canary제거. IPv6/UNIX/abstract positive controls 정상, sandbox의 host접속 없음. controller before/after 선택설정 diff0; during 차이는 기존 gate에서 expected. wrapper 완료, own unit/cgroup는 정리됐으며 external-CWD/remote/container 작업은 UNKNOWN.

fresh runtime_integrity.json PASS:changed/missing0,existing-scope additions0,main HEAD/미커밋상태동일. 이전Probe/B1/V2/실패evidence·marker 보존. 새 두marker는 이제 소진됐고 raw stdout/stderr/before snapshot과 함께 local work에 보존한다. marker삭제/재사용/자동retry/limit상향 금지. World/step/Gazebo/sudo/install/system/production/main/Clock/Capture 변경 없음.

## Probe B/C/D 추가·잔여 증거

|항목|이번 추가 증거|남은 요건|
|---|---|---|
|B destroy/notify 하위사례|설치본 BodyNode/ShapeNode notification identity·각1회·owner-reset구간·순서·등록해제|개별derived destructor/D0/provider/allocator balance·누수는 여전히 미관측|
|B Bullet/cast 경계와 비교arm|없음|detector/group/object factory/deleter/cast와 설치/baseline/traceOFF 비교|
|C 부분생성/예외/unwind|없음|정상B 잔여경로 이후 검토된fault window·부분해제/카운트/unwind|
|D trace metadata/OFF·ON|없음|비물리entry,owner/quiescent Configure/GetStatus/Flush,capacity/overflow·출력경계|

Probe B 전체/C/D완료 또는 Gazebo/Host 준비완료로 올리지 않는다. prerequisite_review.md의 항목별 잔여 위험 수용은 이번에 결정하지 않았다. Stage B BLOCKED 유지. 현재1회 승인 범위는 완료했으며 후속runtime을 자동 시작하지 않는다.

증거:execution_review.json,runtime/{mapped_library_validation,native_fixture_execution,runtime_observation,resource_readback,process_cleanup,controller_diff,supervisor_integration}.json,runtime_integrity.json. 준비approval/contract/source/final_report는 변경하지 않은 역사적 준비기록이다. 경량실행결과와handoff만 실험브랜치에 게시한다. /tmp ELF/pin/raw snapshot/log/marker는 local이며 Git만으로 다른기기/계정으로 이전되지 않는다.
