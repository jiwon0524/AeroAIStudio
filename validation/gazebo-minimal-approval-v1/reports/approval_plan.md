# Gazebo 최소 물리 검증 — 선행 단계 승인안

상태: **DRAFT_BLOCKED_NOT_EXECUTABLE / Gazebo NOT_RUNTIME_VERIFIED / Stage B BLOCKED**.
기준: experiment/dart-internal-trace, d35df02bb4be613223e558236c1a92a65dfce49e, 시작 clean.
이번 작업은 읽기 전용 조사와 문서 작성이다. 컴파일/링크, target 실행/로딩, gz help/plugin inspection, World::step, 서비스 시작, 새 marker 소비는 0회다. 아래 명령은 설계 계약이며 실행 승인이 아니다.

## 1. 진입 판단과 근거

- `validation/dart-probe-readiness-v1/reports/next_steps.md`는 제한된 Probe A→B→C→D 뒤 별도 Gazebo 검증 순서를 명시한다. `validation/dart-targeted-evidence-v1/reports/probe_plan.json`의 B는 Skeleton→BodyNode→ShapeNode와 Bullet 소유/해제, C는 정상 B 이후 검토된 예외 경계, D는 별도 trace owner/quiescent 조건을 요구한다. 설치/로컬 baseline/trace 비교 arm도 구분한다.
- `validation/dart-destructor-cleanup-v4/reports/targeted_evidence_plan.md`는 해당 증거 **또는 항목별 잔여 위험의 명시적 수용** 전 Host 승인 준비 완료로 승격하지 못한다고 명시한다. 사용자는 이번에 잔여 위험 수용/단계 생략을 지시하지 않았다.
- V2 `execution_report.md`와 소스 `validation/dart-skeleton-lifetime-v1/fixtures/skeleton.cpp`는 빈 Skeleton 1개의 weak_ptr 만료만 검증한다. 바디/관절0 조건이 있으므로 B 전체, 예외, Bullet factory, trace OFF/ON, Gazebo 물리 실행의 증거가 아니다. 과거 정적 보고서의 NOT_RUN 문구는 그 시점의 역사이며 V2 성공을 취소하지 않는다.
- 따라서 지금 Gazebo 실행을 승인 가능한 상태로 제시하지 않는다. 다음 최소 범위는 **B1: 설치본 Core 정상 비물리 Skeleton→WeldJoint/BodyNode→BoxShape/ShapeNode 소유 체인 1개**다. 이는 B의 첫 하위 사례로, B 전체 완료나 C/D 생략 승인이 아니다. Trace 캠페인이 아닌 설치본 smoke에 한해 C/D를 생략하려면 별도의 항목별 위험 수용이 필요하다. 자동으로 결정하지 않는다.

## 2. 가장 작은 B1 계약

GO 전: host가 namespace/cgroup/PID-start/executable+Core16 mapped file identity와 live resource limits 확인. main 전 constructors가 이미 실행될 수 있다는 V2 한계를 유지한다.
GO 뒤: Skeleton1개, root WeldJoint+BodyNode1개, 공유 BoxShape1개(변0.1m), 일반 ShapeNode1개 생성. collision aspect/group/detector, World/constraint/step, 예외 주입, trace OFF/ON은 포함하지 않는다. 각 포인터 null 여부/개수(1 skeleton,1 joint,1 body,1 shape node), shape 소유 참조와 weak_ptr 유효 확인. fixture의 추가 strong shape 참조를 먼저 해제하고 Skeleton owner를 한 번 reset한다. 종료 뒤 Skeleton/Shape weak_ptr 만료 확인. 해제된 raw BodyNode/Joint/ShapeNode 포인터는 역참조하지 않는다. 예외 발생은 해당 사례 FAIL이며 의도적 fault injection을 하지 않는다.

설치 추출 헤더의 Skeleton.hpp: createJointAndBodyNodePair, BodyNode.hpp: createShapeNode API가 존재함을 텍스트 확인했다. WeldJoint/BoxShape 헤더도 존재한다. 기존 V1의 packaged-header+baseline external fallback은 전체 ABI 인증이 아니다. 실제 source/import/deleter 검토, native observer의 bounded nonallocating event collection 검토 및 compile-only 확인은 **미수행**이다. global new/delete override를 도입하지 않는다. weak_ptr 만료는 전체 라이브러리 누수0 또는 allocator callback 수/정확한 D0 경계의 증명이 아니다. 이 미관측 항목을 B 전체 PASS로 표기하지 않는다.

### 제안 명령 — 현재 파일 없음, 실행 금지

호스트 cwd `/tmp/AeroAIStudio-dart-internal-trace`:

```bash
env -u LD_PRELOAD -u LD_AUDIT -u LD_LIBRARY_PATH PYTHONDONTWRITEBYTECODE=1 python3 validation/dart-body-shape-lifetime-v1/scripts/launch.py --execute-approved-body-shape-once
```

격리 내부 payload argv: `/fixture/body_shape_fixture --owned-body-shape-once`.
위 launcher/native는 **NOT_IMPLEMENTED / NOT_BUILT / SHA-256 미확인**. 이번 범위는 문서 작성뿐이므로 임의 구현·컴파일하거나 기존 V2 launcher를 복사해 실행하지 않았다. 다음 별도 준비 작업에서 source·helper·manifest·ELF·FD 마운트 계획을 고정하고 오프라인 gate 검증을 마친 뒤, 실제 commit과 해시가 포함된 최종 실행 승인안을 다시 제시해야 한다. 이 초안만으로 실행 승인을 요청하거나 실행하지 않는다.

B1 입력 Core/의존 ELF: `static_inventory.json`의 `installed_core16_rehashed`에 절대 canonical 경로/SHA-256/기존 Build-ID/device/inode를 기록했다. 16개 모두 V2 승인 manifest의 SHA-256과 재대조했다. Core `/usr/lib/x86_64-linux-gnu/libdart.so.6.13.2` SHA-256 f74f4ec9820aee785ef94fb7bedafa7e4c832f209675a8ca1d35019c72b48e06. 새 executable에 대한 실제 NEEDED closure와 identity는 미확인이다. physics plugin/world는 B1에서 **해당 없음/마운트 금지**다. V2 executable(2bc3e2d18c2360e1d4a2c276226c147f441dbd871cb3b003a054ba695d555292)은 보존 입력일 뿐 B1 실행 대상으로 재사용하지 않는다.

### B1 격리·한도·프로세스

V2와 같은 host launch→supervisor→systemd-run client, own transient user service의 stage→prlimit→bwrap→reaper→native 구조를 제안한다. 단일 arm/단일 사례/한 번, 자동 재시도0. 서비스명 `aero-body-shape-v1-runtime-<unique>.service`; 현재 unit/PID/start/InvocationID 없음. 실행 시 host/PID/start/output을 기록해야 한다.

MemoryMax64MiB(67108864), MemorySwapMax0, TasksMax8, CPUQuota25%/period100ms, RuntimeMax8s, TimeoutStop2s, KillMode=control-group, OOMPolicy=stop, Delegate=no. prlimit CPU2s/AS256MiB/FSIZE64KiB/NOFILE64/CORE0, native GO3s/host READY5s. 제안값은 V2와 동일하다. V2 peak11,812,864bytes/3tasks/897ms는 초기 근거이나 Body/Shape 추가 할당의 충분성을 증명하지 않는다. 이 작고 비물리적인 범위에는 선제 상향 근거가 없어 유지한다. 메모리·시간 부족이면 FAIL 보존, 자동 상향/재시도 금지.

fresh root16MiB RO, private tmp/run 각4MiB/shm1MiB, 승인 ELF readonly FD bind와 동일 Core SONAME alias, private user/mnt/pid/net namespace/cap-drop ALL/die-with-parent/sterile env. 원본 main/기존 evidence/패키지/시스템은 쓰기 노출하지 않는다. 쓰기는 새 own output으로만 host 수집; native는 bounded stdout/stderr 사용. 상속된 환경/credential/GZ/ROS/DISPLAY/사용자 home·socket·장치 노출 금지. IPv6/UNIX positive-control와 sandbox 연결 부재, canary/temp, controller before/during/after 검증은 기존 정책을 유지하되 새 구현도 검토해야 한다.

새 B1 출력: `validation/dart-body-shape-lifetime-v1/reports/runtime/`, `reports/runtime_integrity.json`; 새 one-shot: `work/runtime_collection_attempt.json`, `work/runtime_attempt.json`; raw stdout/stderr와 before snapshot은 같은 새 work/. 모두 현재 부재이며 이번에는 만들지 않는다. lexists로 dangling symlink까지 충돌 판정한다. 사전검사·manager 상태·unique unit 충돌 확인은 marker/service 이전에 완료한다. 이후 marker exclusive 생성; 부분 실패도 marker 보존, 재사용 금지.

성공: 모든 preflight PASS, strict identity PASS→GO, 예상 개수/수명 이벤트 완전, exit0, 메모리 이벤트/리소스 수집, own unit/cgroup/관측 PID-start/temp/canary 정리 PASS, controller 선택 설정 전후 diff0, 원본 무결성 PASS. 필수 관측 누락은 UNKNOWN/INCOMPLETE이지 PASS가 아니다. OOM/signal/timeout/nonzero/identity mismatch/예상 외 프로세스·쓰기·network·plugin이면 FAIL. GO 전 불일치는 stdin 닫고 GO 미전송. 서비스 deadline+2s grace 동안 wait/reap; 불가 시 저장된 InvocationID와 일치하는 exact own unit만 stop하고 cgroup 정리 확인. 전역 pkill/기존 작업 종료 금지. 실패 증거/marker를 보존하고 멈춘다.

## 3. Gazebo 후속 설계 메모 — 현재 실행 대상 아님

아래는 중간 증거/위험 수용 이후의 별도 승인안을 위한 명세다. 지금 Gazebo 진입 허용으로 해석하지 않는다.

기존 `tools/diagnose_v07_gazebo_runtime_physics_backend.py`는 world 복사/observer 빌드 후 3 iteration을 실행하고 inventory에서 `gz plugin --info`로 plugin을 로드할 수 있다. 출력 unlink/상속 환경/45초 timeout도 있으므로 이번에 호출하지 않았고 새 one-shot launcher로 그대로 사용해서는 안 된다. `tools/gazebo_runtime_physics_backend_observer.cc`는 const ECM의 active world PhysicsEnginePlugin, iteration/time을 기록하지만 물체 상태/파일 해시/실제 선택된 engine 객체 provenance를 단독으로 인증하지 않는다. 파일 이름에 dartsim이 있다는 판정만으로 실제 백엔드 확인 PASS를 내지 않는다.

향후 새 최소 world: world `aero_dart_minimal_v1`, gravity(0,0,-9.81), fixed max_step_size0.001s, real_time_factor0, link1개 질량1kg/대각 관성0.001666666666666667, dynamic model1개 초기 z1m/속도0, Box0.1m. plane/contact/mesh/sensor/light/GUI/transport control/사용자 모델 URI 없음. collision geometry는 box1개만, 접촉 대상 없음. Physics system과 bounded read-only diagnostic observer만 명시, UserCommands/SceneBroadcaster/Sensors 미사용. 새 SDF/observer binary/source/launcher는 아직 없음: **경로는 아래 제안, SHA-256 모두 미확인**. production SDF는 수정하지 않는다.

향후 sandbox payload argv 제안(설치 Ruby CLI 소스에서 -s/-r/--iterations/--physics-engine 인자 확인; 실제 호출/--help 없음):

```text
/usr/bin/gz sim -s -r --iterations 100 --physics-engine /usr/lib/x86_64-linux-gnu/gz-physics-7/engine-plugins/libgz-physics7-dartsim-plugin.so.7.8.0 /fixture/minimal.sdf
```

이 argv도 실행용 wrapper가 아니다. `/fixture/minimal.sdf`의 향후 host 경로 `validation/gazebo-minimal-physics-v1/fixtures/minimal.sdf`, observer `work/libaero_minimal_observer.so`, 새 launcher `scripts/launch.py --execute-approved-gazebo-once`는 모두 미구현/미고정이다. 임의 기본world/observer/plugin 대체 금지. GUI를 끄는 -s만 쓰며 rendering/sensors가 없으므로 --headless-rendering도 불필요한 경로로 추가하지 않는다. expected tree는 host supervisor/systemd-run, service stage/prlimit/bwrap/reaper, Ruby gz sim server와 그 transport worker threads; 실제 fork/thread 수는 미확인. GUI/renderer/외부 server가 나타나면 FAIL.

실제 DART 판정은 (1) pinned CLI argv와 SDF로 DART 지정, (2) active world PhysicsEnginePlugin 컴포넌트 값이 approved absolute plugin identity에 대응, (3) service PID/start의 mapping에서 설치 DART plugin/Core/External/필수 의존 ELF의 hash/Build-ID/device/inode 일치와 다른 backend/로컬 trace core 부재, (4) 선택된 engine/plugin class 또는 생성 engine 객체의 provider와 DART 구현 대응 증거를 수집해 교차 확인한다. (4)의 안전한 observer/API 방식은 미확인으로, 설치 사실·단순 loaded mapping·설정 문자열을 active selection 증거로 확대하지 않는다. 불충분하면 BACKEND_UNPROVEN.

물리 판정 제안: 초기 sample iteration0/time0/z1/v0을 별도로 확보하고 advancing PostUpdate100개가 iteration1..100로 누락·중복 없이 연속; dt=1,000,000ns, 마지막 sim_time=100,000,000ns, paused=false. 초기 설정값만 초기 관측으로 가장하지 않는다. 마지막 z는 자유낙하 이론0.95095m에서 |오차|<=0.002m, vz=-0.981m/s에서 |오차|<=0.02m/s, z 감소와 vz<0, x/y 위치·속도 각각 |값|<=1e-6, 회전 변화<=1e-6rad, 모든 값 finite. 수치 적분의 한 스텝 위치 오차(~0.00049m)를 고려한 smoke 허용치이며 solver 정확도 인증이 아니다. ECM이 world pose/velocity를 제공하도록 readback component의 생성/생산 phase를 미리 검토하고, held/default velocity를 실제 측정으로 쓰지 않는다. 이 observer가 없으므로 현 기준은 미검증 명세다. 정상 exit0도 상태/백엔드 자료가 없으면 PASS가 아니다. 기존 Clock/Capture 기준을 수정하거나 이 smoke 기준으로 대체하지 않는다.

Gazebo에는 Skeleton 한도 충분성을 전용할 수 없다: Ruby dispatcher, gz-sim/SDFormat/transport/plugin threads와 193파일의 예비 정적 입력이 추가된다. 제안 상한은 MemoryMax512MiB, swap0, TasksMax64, CPUQuota100%/100ms, service30s/stop2s; prlimit CPU10s/AS2GiB/FSIZE1MiB/NOFILE256/CORE0, host wall40s. 이 값은 계측된 최소 요구량이 아닌 **미검증 최초 승인 상한 제안**이다. 서비스와 전체 자식이 같은 cgroup에 속해야 하며 적용은 별도 명시 승인 후뿐이다. fixed100step와 wall/CPU 제한을 함께 적용하고 부족하면 증거보존/정지, 자동 상향 금지. GUI 없이도 transport가 network socket을 필요로 할 수 있어 새 net namespace 내부 loopback만 허용 여부를 무해 fixture로 사전 검토; host network/socket 노출 금지. 16MiB root/4MiB tmp 등 V2 mount 용량과 동일한 whitelist를 무조건 복사하지 않고 실제 추가 Ruby/resource closure와 tmpfs 사용량을 사전 고정해야 한다.

새 향후 출력 `validation/gazebo-minimal-physics-v1/reports/runtime/`, one-shot `work/runtime_collection_attempt.json`, `work/runtime_attempt.json`; 현재 모두 부재. B1과 마찬가지로 output/marker 충돌·hash/identity 미확인·불완전 마운트/격리·진입 조건 실패는 marker/service 전에 중단한다. pre-load readiness와 world step 전 GO gate 구현이 필요하며 CLI 단독 실행은 이를 제공하지 않는다. plugin constructors/engine init 이전 차단과 step 전 차단은 다르다. 기존 코드로 step 전 GO가 가능한지는 미확인이다. 종료·unit/cgroup/PID-start 정리와 원본 무결성 절차는 B1과 동일하며 추가 threads/child도 관측한다.

## 4. 경로·해시와 불확실성

`static_inventory.json`에는 로컬 설치 `/usr/bin/gz`(Ruby script), Ruby interpreter, `/usr/share/gz/sim8.yaml`, `/usr/lib/ruby/gz/cmdsim8.rb`, libgz-sim8-gz.so.8.15.0, libgz-sim8.so.8.15.0, libgz-sim8-physics-system.so.8.15.0, libgz-physics7-dartsim-plugin.so.7.8.0와 정적 NEEDED 재귀 탐색 총193파일의 절대 real path/SHA-256을 기록했다. readelf만 사용했고 ldd/gz plugin/target 실행은 하지 않았다. 기본 multiarch 디렉토리 탐색의 미해결 NEEDED0은 실제 loader mount closure PASS가 아니다. RPATH/RUNPATH, Ruby require/dlopen, transport config/data, protobuf/resource, observer와 새 executable의 완전 closure·Build-ID/FD identity·SONAME alias pin은 **미확인**이며 현재 inventory를 실행용 manifest로 쓰지 않는다. source/기존 marker/주요 evidence/Core16의 보존 비교는 preservation_review.json을 참조한다.

원본 무결성 실행 전/후 절차: main HEAD+porcelain, 기존 source/ignored evidence/이전 Probe·V1·V2 marker/승인ELF 전수 hash snapshot을 새 work에 저장하고, 새 task와 실험 handoff만 제외하여 비교한다. 변경·누락/기존범위 추가0과 main HEAD/status 동일을 요구한다. 자동 복구/삭제/stash/reset 금지. 최신 실행 때 snapshot을 새로 수집하며 과거 V2 snapshot을 새 검증으로 쓰지 않는다. 현재 조사 보존 비교는 선별 입력 해시 검사이며 전수 재검사라 주장하지 않는다. `/tmp` ELF/ignored 증거는 Git만으로 기기 이동되지 않는다.

## 5. 다음 최소 작업과 이번 종료

다음 별도 요청 후보는 B1의 source/소유 해제 계약/launcher 설계 구현 및 compile-only·비실행 gate 검증이다. 그 후 정확한 새 executable hash와 최종 argv/FD mount/contract/commit이 일치할 때에만 실행 승인안을 완성할 수 있다. 이번 문서는 검토 가능한 초안이며 **실행 승인 준비 완료가 아니다**. B1 실행도 Gazebo 실행도 현재 승인 요청 대상으로 자동 제출하지 않는다. 기존 V2 one-shot은 소진 상태로 보존한다. 이 조사/승인안과 인계만 실험 브랜치에 자동 게시한 뒤 멈춘다.
