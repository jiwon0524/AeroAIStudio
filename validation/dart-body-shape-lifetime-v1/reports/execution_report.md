# 설치본 DART B1 정상 소유자 해제 — 1회 실행 결과

**NORMAL_OWNER_RELEASE_B1_PASS / Probe B PARTIAL / Stage B BLOCKED**.
사용자가 준비 commit `89a8676fe0dba854a4b01fb7f3696d10599b9ddd`의 고정 명령을 1회 명시 승인했다. 전체 HEAD/branch/clean 상태와27개 source·manifest pin, 실행파일/Core16 해시·FDidentity,62개 의존 연결,29개 mount와 저장된 실제 builder argv,같은 readonly Core SONAME alias,live 서비스 한도 계약,새 runtime 출력·marker 부재를 직접 확인했다. 환경 승인을 받아 read-only manager running/unit collision 검사 뒤 지정 launch를 정확히1회 호출했다. wrapper exit0, retry0, limit changes0, source changes0.

## 객체 전 식별과 관측 결과

unit `aero-body-shape-v1-runtime-c1bb91795b.service`. strict Core16+fixture17개 mapped file identity PASS_FILE_IDENTITY와 namespace/cgroup/실제limit/PID-start 검사 후만 GO=true. native host PID230417/start25213034. 상세 host process identity는 execution_review.json과 runtime/native_fixture_execution.json 참조. map_files direct open EPERM으로 기존 proc-root FD fallback을 사용했으며 resident COW/pages/constructor 부작용은 미인증이다.

정확한 이벤트5개 관측: READY WAIT → created(skeleton/body/joint/shape_node각1,shape_owner_matches=true) → external_shape_released(shape_retained=true) → owner_release_observed(skeleton_expired=true,shape_expired=true) → lifetime_success(normal_owner_release_only). 고정 소스의 포인터/소속/count 검사를 통과한 뒤 created를 출력하며 raw borrowed 포인터를 직접 delete하지 않는다. fixture 외부 Shape strong 참조를 먼저 없애고 Skeleton owner를 해제했다. **개별 Skeleton/BodyNode/ShapeNode/Joint 소멸자 호출과 순서는 NOT_OBSERVED**, allocator balance는 NOT_MEASURED다. weak 만료와 정상 종료를 개별 destructor/D0/누수0/전체 ABI 증명으로 승격하지 않는다.

## 종료·자원·정리

systemd-run/native 서비스 exit0, stderr code=exited/status=0 및 result success. service689ms, CPU184ms, swap peak0B. live readback memory.max67108864, memory.swap.max0, pids.max8, cpu.max25000 100000. active RuntimeMax8s/TimeoutStop2s 확인. 관측 memory.current4198400bytes, memory.peak12763136bytes, pids.current3; memory.events의 수집된 low/high/max/oom/oom_kill/oom_group_kill/sock_throttled 모두0. 마지막 표본도 동일하나 최종 표본 보장은 없다. 제한 초과 강제효과를 시험하지 않았다.

cleanup PASS: own unit not-found/inactive/dead, cgroup 제거, 관측PID-start잔여0, host temp/canary 제거. host socket 연결 없음. controller 선택 설정의 before/after diff0; during의 systemd CPU activation 차이는 기존 gate에서 expected 판정했다. 수거 후 unit의 기본 Timeout/MemoryMax 등을 실행 중 한도로 해석하지 않는다. 최종 unit execution 속성은 수거 후 미확인이고 exit0은 wait client/stderr 증거에 근거한다. timeout/signal 이벤트는 관측되지 않았다.

fresh runtime_integrity.json PASS: 기존 changed/missing0, 기존범위추가0, main HEAD/미커밋 상태 동일. 기존 Probe A/V1실패/V2 증거·marker 보존. 새 두 one-shot marker는 이제 소진됐으며 raw stdout/stderr/before snapshot과 함께 보존한다. 재사용/삭제/자동 retry 금지. World/step/Gazebo/sudo/install/system/production/main/Clock/Capture 변경 없음.

## Probe B/C/D와 남은 요건

|항목|이번 증거|남은 요건|
|---|---|---|
|B 설치본 정상 Skeleton→BodyNode→ShapeNode|각1개 생성 관계와 owner-release 약참조 기대를 제한된 사례에서 관측|개별 destructor/D0/provider/순서/allocator balance·누수 미검증|
|B Bullet/cast 경계|없음|detector/group/object factory/deleter/cast 별도 검증|
|B 비교 arm|설치본1개만|baseline 및 trace OFF 비교 미실행|
|C 부분 생성/예외/unwind|없음|정상 B의 나머지 경로와 검토된 fault window·부분 해제 필요|
|D trace metadata/OFF·ON|없음|owner/quiescent Configure/GetStatus/Flush·capacity/overflow·출력 경계 필요|

Probe B 전체/C/D 완료가 아니며 기존 진입 조건을 생략하려면 항목별 사용자 위험 수용이 별도로 필요하다. Gazebo/Host/Stage B 실행 승인이 아니다. Stage B BLOCKED 유지. 현재 승인 범위는 완료했으며 더 실행하지 않는다.

증거: execution_review.json, runtime/{mapped_library_validation,native_fixture_execution,runtime_observation,resource_readback,process_cleanup,controller_diff,supervisor_integration}.json 및 runtime_integrity.json. 기존 preparation final_report/approval_plan/contract는 역사적 준비 결과로 보존했다. 경량 결과와 handoff만 실험 브랜치에 게시한다. /tmp ELF/work pin/raw snapshot/log/marker는 로컬이고 Git 게시만으로 기기이동되지 않는다. wrapper/own service 완료; 외부CWD/remote/container 작업 상태 UNKNOWN.
