# Headless Gazebo first-step gate — 준비 승인안과 차단 결과

**PREPARED_BLOCKED_NOT_EXECUTION_READY / Stage B BLOCKED**. 기준 HEAD `aae135bf487a554b7be678b7ae64c3d03c00d601`, 승인된 실험 브랜치에서 시작 clean을 확인했다. 현재 사용자는 구현·컴파일·링크·모의 입력 검사까지만 허용했다. target 로딩/fixture 실행/물리 step/서비스/marker 소비는 모두0이다. 기존 main·미커밋 변경·evidence·이전 marker는 보존한다.

## 1. 실행 승인 준비 상태

**현재 artifact로 Gazebo 실행 승인을 요청할 수 없다.** 활성 engine/detector 객체와 ELF provider를 신뢰할 수 있게 연결하는 live adapter, iteration0/time0에서 초기화 관측이 가능한 경로, 전체 dynamic resource/dlopen closure, Gazebo 전용 runtime supervisor 연결이 미완성이다. backend/detector/provider 상태는 모두 **UNVERIFIED**다. Bullet 정상수명·개별 destructor·allocator·C 예외 해제 위험도 미수용이다.

launcher는 source/ELF pin·fresh output·branch/ancestry를 읽기 전용으로 검사한 뒤 준비 미완료로 거부하며, 서비스·marker·native를 생성하는 분기가 없다. contract의 모든 capability를 임의로 true로 바꾸더라도 마지막 supervisor 미구현 거부를 통과할 수 없다. C++ driver도 LiveAdapterAvailable=false이면 Server/world 생성 전에78로 종료하도록 작성했다. 이를 실제 실행해서 확인하지는 않았다.

## 2. 정확한 명령 — 현재는 차단되는 준비 인터페이스

```bash
cd /tmp/AeroAIStudio-dart-internal-trace &&
env -u LD_PRELOAD -u LD_AUDIT -u LD_LIBRARY_PATH \
  PYTHONDONTWRITEBYTECODE=1 \
  python3 validation/gazebo-minimal-physics-v1/scripts/launch.py \
  --execute-approved-gazebo-once
```

위 명령은 **현재 실행 불가/서비스·marker 전 거부** 계약이며 승인 후 동작할 완성 명령으로 제시하지 않는다. default는 계약 JSON 출력뿐이다. 미래 payload 후보 argv는 `/fixture/native_fixture --owned-gazebo-gated-once /fixture/minimal.sdf`이고 native_fixture는 새 host `work/gazebo_gate_server`의 readonly FD다. 예전 `gz sim -s -r --iterations100` CLI 대신 직접 `gz::sim::Server` API frontend를 컴파일한 이유는 Run 호출 전 host GO 경계를 코드에 둘 수 있기 때문이다. frontend/ELF가 달라졌으므로 기존 CLI 후보193파일 inventory를 그대로 runtime closure로 쓰지 않는다. 직접 native 호출도 금지다. 완성하려면 source/contract/해시와 준비 commit을 새로 검토해야 한다.

## 3. 고정 입력·경로·SHA-256

최소 world `fixtures/minimal.sdf`: world aero_dart_minimal_v1, gravity(0,0,-9.81), max_step_size0.001s, real_time_factor0, 초기 model z1m/정지, dynamic box0.1m·mass1kg·관성 대각0.001666666666666667, ground/contact pair/mesh/sensor/visual/URI/GUI 없음. Physics system과 자체 gate observer만 명시한다. world SHA-256 `d00ecdde42ee775dc04421e4e46d767811005cde88ae5100d10b2f088940be8e`.

별도 C++ server와 자체 observer를 compile/link했다. 외부 헤더의 실제 파일명은 Pose.hh/LinearVelocity.hh이고 초기 observer 빌드의 WorldPose.hh 이름 오류를 수정했다. 초기 결과·stderr는 reports/build_initial.json 및 work/build_1_initial.stderr에 보존했다. server 빌드는 성공했으므로 다시 덮어쓰지 않고 observer만 별도 빌드했다. 빌드 결과/정확한 compiler argv는 build_result.json과 build_initial.json, 모든 artifact는 미실행이다.

|역할별 실제 후보 경로|SHA-256|
|---|---|
| `/tmp/AeroAIStudio-dart-internal-trace/validation/gazebo-minimal-physics-v1/work/gazebo_gate_server` | `f8252d1e130207abe72eda6d44d5ceaaca511a26bc8847454c7d82dd8a2c5612` |
| `/tmp/AeroAIStudio-dart-internal-trace/validation/gazebo-minimal-physics-v1/work/libaero_gate_observer.so` | `d3bba7b32205c0f69c215d598d3fdf4661e6af28bc0c152a3a9c10addb165a7a` |
| `/usr/lib/x86_64-linux-gnu/libgz-sim8-physics-system.so.8.15.0` | `5d8b8d068628ee7af0774f5d9e0ef65e23d4e9f9cab23c1aac318faaa51f9575` |
| `/usr/lib/x86_64-linux-gnu/gz-physics-7/engine-plugins/libgz-physics7-dartsim-plugin.so.7.8.0` | `1ee9350aa09d5a5eb43a5075c9c61d2cdcb85113d2ff1e0f32136847edf1688e` |
| `/usr/lib/x86_64-linux-gnu/libgz-sim8.so.8.15.0` | `6120bd5d25a28ced3238f91b8a432e364958cd07706afe00911743072bfe4651` |
| `/usr/lib/x86_64-linux-gnu/libdart-collision-bullet.so.6.13.2` | `897709e0c988e9e562c662292ed5bc860bce70ee2c64499501f54a6b5ca02201` |
| `/usr/lib/x86_64-linux-gnu/libLinearMath.so.3.24` | `31c7e0d2d17efc3924613bf561a645a4258f2d8df54167c162c490ed7fe84fea` |
| `/usr/lib/x86_64-linux-gnu/libdart-collision-ode.so.6.13.2` | `2940e0bd6b056f186d3596e051a26ec25f1c27add88d870cdfe673785dad4b44` |
| `/usr/lib/x86_64-linux-gnu/libdart.so.6.13.2` | `f74f4ec9820aee785ef94fb7bedafa7e4c832f209675a8ca1d35019c72b48e06` |
| `/usr/lib/x86_64-linux-gnu/libBulletCollision.so.3.24` | `a356d9ef207a31737b91a39c4c75a43b05a49cde51891cfa13b4b1c71c223f0a` |

`reports/elf_manifest.json`: 새 server/observer, installed Sim/Physics system/DART plugin, Bullet/ODE/FCL 관련 installed ELF 및 재귀 NEEDED 총166파일의 canonical path/SHA-256/Build-ID/device/inode/NEEDED/SONAME/search tags. Core16 hash는 기존 승인 manifest와 대조했다. `work/manifest.sha256`와 contract source_sha256으로 pin하며 자동 재생성/repin 금지. 모든 외부 ELF는 /usr/lib canonical로 제한하고 /tmp의 ELF는 새 server/observer2개만 명시 허용한다. local baseline/trace ELF와 상속 LD/GZ search 환경은 거부한다.

readelf+ROFD 검사로738의존 연결과306 canonical/SONAME ELF readonly mount를 확인했다. Core own SONAME libdart.so.6.13은 canonical Core와 **동일 승인 FD**에 연결한다. `mount_plan.json`은 상징 FD를 사용한 실제 ordered builder argv다. world는 별도 FD6002→/fixture/minimal.sdf, canary/limits는 별도 제어 FD로 계획한다. default loader layout/interpreter symlink를 재사용하고 RPATH/RUNPATH·wrong alias/provider/unapproved FD/metadata/interpreter 오류를 거부한다. 같은 ELF의 canonical/SONAME mapping은 inode/hash로 동등 비교하며 alias를 동시에 전부 map하라고 요구하지 않는다.

단, 이것은 **ELF-only candidate plan**이다. `/usr/share/sdformat14/1.10` schema125개는 resource_candidates.json에 해시했지만 실제 SDF/resource 검색·runtime config·dlopen 경로의 완전성/마운트는 미완성이다. 모든 정적 NEEDED가 해소됐다는 사실을 full runtime closure로 확대하지 않는다. 추가 resource/ELF가 필요하면 자동 mount/fallback을 하지 않고 차단해야 한다. 설치 Bullet/ODE library의 존재는 활성 detector 증거가 아니다. contract의 detector별 adapter/provider 후보는 이름별 예시이며 GzBullet wrapper 객체 vtable은 DART plugin에 있을 수 있다. 실제 타입/instance/provider 연결은 UNVERIFIED다.

## 4. 첫 step 차단과 관측의 한계

설치 `Server.hh`는 RunOnce(paused=true)도 iteration을1 증가시키며 Run(...,iterations=0)는 초기화만이 아니라 무한 실행이라고 명시한다. `System.hh`의 UpdateInfo.simTime은 업데이트 후 도달 시간이고 unpaused 첫 콜백에서는dt이다. 따라서 “paused1회 초기화 후 iteration0” 또는 “첫unpaused PreUpdate에서time0”라는 가정을 쓰지 않는다.

`PhysicsEnginePlugin`은 library 문자열 컴포넌트다. gz-physics World::GetCollisionDetector()/GetWorldCollisionDetector API는 있지만 installed Sim의 active engine/world/detector 객체에 안전하게 접근하는 public bridge는 확보하지 못했다. 문자열·world 설정·loaded library만으로 활성 detector를 인증하지 않는다. private pointer 추정/cast/interposition은 추가하지 않았다.

compiled adapter.cc는 LiveAdapterAvailable=false. server.cc는 그 결과를 확인한 후만 Server 생성 후보 경로에 들어가며, 별도의 trustedReadyCollected=false 방어로 Run 경로도 열지 않는다. 성공하는 Run100 경로는 현재 binary에서 활성화되지 않았고 새 구현·해시검토가 필요하다. observer.cc는 최소 priority ConfigurePriority를 제안하지만 PreUpdate에서 UNVERIFIED를 보고하고 _Exit78로 즉시 중단한다. 이 emergency reject는 스케줄러/초기화 전 무스텝 보장을 실측한 결과가 아니다. PostUpdate 후보도 orientation/provenance/필요 component materialization이 완성되지 않아 최종 검증 자료로 그대로 쓸 수 없다.

**현재 무스텝 보장의 범위는 launcher가 아예 서비스를 시작하지 않는다는 것**이다. 실제 Gazebo world를 초기화·관측한 채 GO 전 iteration/time0을 유지하는 보장은 UNVERIFIED이며 준비 미완료다. 이 항목을 위험 수용으로 PASS 처리하지 않는다.

## 5. 순수 모형 GO 계약과100스텝 수치 기준

`scripts/gate.py`는 실제 데이터를 수집·인증하지 않는 순수 정책 모형이다. 합성 테스트에서만 capabilities=true로 둔다. 실제 contract는 모두false다. 미래 live collector가 준비되면 다음 신호를 공급해야 한다.

- READY_PAUSED 두 관측에서 iteration0/time0/steps0/paused=true와 초기 상태가 동일. 소스가 실측 component이고 초기z1±1e-9m, 초기속도·x/y·각도는±1e-9. 누락/NaN/환경설정값 대체는 거부.
- backend=DART가 active engine instance/provider로 확인되고 고정 fingerprint 일치. detector는 active world detector instance에서 얻은 type과 실제 구현 ELF fingerprint 일치. 후보name/mapping/world설정만으로 대체 금지.
- 실제 mapped ELF는 허용canonical/alias·SHA/Build-ID/dev/inode와 일치하며 요구된 file identity가 모두 존재. 추가/누락/해시·inode불일치와 localtrace/comparearm은 거부. PID/start 안정·namespace/cgroup/live한도도 실측PASS.
- 위 자료가 완전할 때만1회 GO; 재전송 금지. 모형의 GO 반환값은 stdin에 쓰거나 프로세스를 시작하지 않는다.

GO 후 advancing sample 정확히100개, iteration1..100, 각dt1,000,000ns,simtime=i×1,000,000ns,paused=false. 마지막 iteration100/time100,000,000ns. 모든 state는 finite 실측값이며 orientation도 필수. 최종z0.95095±0.002m, vz-0.981±0.02m/s,z<1,vz<0,x/y/vx/vy/roll/pitch/yaw 각절대값≤1e-6. 자유낙하 analytic 대비 적분오차를 허용한 smoke 기준이지 solver 정밀도/Clock/Capture/physics neutrality 인증이 아니다. 기존 Clock/Capture 기준은 변경하지 않는다. 빠진step/중복/추가/time drift/관측누락/NaN/자유낙하범위위반이면FAIL.

## 6. 격리·자원·정리·새 출력

기존 승인 구조의 readonly FD identity/SONAME alias/Bubblewrap layout, systemd argv builder와 InvocationID/PID-start 정리 불변조건을 재사용해 candidate policy로 연결했다. 실제 Gazebo supervisor/namespace/mapping/telemetry 수집·cleanup 호출 경로는 아직 연결하지 않았다. 기존 native supervisor를64MiB 그대로 호출하거나 통과했다고 주장하지 않는다.

제안한도: MemoryMax512MiB(536870912),swap0,TasksMax64,CPUQuota100%/100ms,RuntimeMax30s,TimeoutStop2s,KillModecontrol-group,OOMPolicystop,Delegate=no,hostwall40s. prlimitCPU10s/AS2GiB/FSIZE1MiB/NOFILE256/CORE0. bwrap root64MiBRO,devRO,tmp16MiB/run16MiB/shm1MiB,user/mnt/pid/net namespace·capdropALL·sterileenv·die-with-parent. host HOME/기존main/evidence/credential/socket 쓰기·노출을 허용하지 않는다. namespace 내부 transport 필요성/loopback/proc/dev 요구·실제task수는 미검증이다.

B1의64MiB/8tasks/8s 성공은 Gazebo 초기화/transport/thread/SDF/plugin의 충분성을 증명하지 않는다. 166개 정적 ELF는 RSS 추정치가 아니며 위 값은 기존Gazebo초안에 근거한 최초승인 상한 **제안**이다. 실제startup/RSS/동적resource 충분성/초과강제효과는 UNKNOWN. 한도변경은 기존검증에 적용하지 않았고 새로운실행에 대해 별도 승인해야 한다. 실패시 자동상향/retry없음.

새prefix validation/gazebo-minimal-physics-v1 아래 runtime 출력 reports/runtime/,reports/runtime_integrity.json,raw work/runtime_integrity_before.json,stdout,stderr,canary. exclusive one-shot work/runtime_collection_attempt.json 및 work/runtime_attempt.json. 모두 현재 부재. preparation ELF/manifest pin/빌드·모의검사 로그/preservation_before.json은 runtime marker가 아니다. 기존probe/V1/V2/B1/notification marker·failure증거는 보존.

완성 후 성공요건은 preflight→trustedREADY/GO→100step판정→exit0→unit not-found/cgroup 제거/관측PID-start잔여0/temp·canary제거/controller before-afterdiff0→fresh 원본무결성PASS 전체다. UNKNOWN/자료누락을PASS로 바꾸지 않는다. 실패/timeout/signal/allocator진단/새provider/network·쓰기위반은 중단·증거보존. GO전 실패는stdin닫기/GO미전송;deadline내wait/reap,필요시nonempty saved InvocationID와현재exact ownunit일치때만stop. 전역pkill/다른작업종료/자동rollback 금지. fresh snapshot은main HEAD/status·기존source/ignored evidence/marker/ELF를전후대조하고newtask·handoff만제외한다. raw자료는local/tmp로Git만으로다른기기에전달되지않는다.

## 7. 미수용 위험과 조건부 비적용

Bullet 정상수명/cast/deleter,개별destructor/D0/free,allocator provider·balance,C의부분생성/예외unwind는 **NOT_ACCEPTED**. weak만료·notification·exit0으로대체하지 않는다. 잔여위험의항목별명시수용 대체경로는 V4 targeted_evidence_plan.md 마지막문단이 허용하지만 이번에 결정하지 않았다. actualprovider 식별/무스텝 gate 부재를수용으로메울수는없다.

설치Core/External을그대로고정하고localbaseline/trace의마운트/검색/실제mapping이없으며neutrality/recorder성능주장을하지않는단일설치arm에만 비교arm과 D localtrace OFF/ON·metadata/owner-quiescent/capacity/overflow/flush가 기술적으로조건부비적용이다. 기본next_steps A→B→C→D→Gazebo gate의생략승인은별개이며자동면제하지않는다. localtrace/비교라이브러리·recorderAPI가추가되면재적용. 완성된실행closure가없어이조건의실제충족도아직UNVERIFIED다. 문서근거는 validation/gazebo-entry-review-v2/reports/entry_review.md §3/4, validation/dart-targeted-evidence-v1/reports/probe_plan.json B/C/D, validation/dart-destructor-cleanup-v4/reports/targeted_evidence_plan.md.

## 8. 이번 결과

server/observer compile/link와 XML구문검사,Python AST,42개 비실행 정책·ELF 검사 PASS. 초기observer include 오류와 준비script import 경로 오류는 로컬진단에 보존/설명했고 target 실행·marker소비는 없었다. backend/detector불일치,누락·예상밖mapping,GO전iteration/time변화,관측누락과소스pin거부를모의/정적으로검증했다. 양성mock은 live관측의신뢰성을입증하지않는다.

다음은 신뢰할 수 있는 active-instance adapter/iteration0초기화 경로와 실제 resource/supervisor 연결 방법의 검토, 그리고 별도 위험·범위 결정이다. 이번 artifact는 실행준비미완료 상태로 게시·보고하고 멈춘다. 사용자에게 실행 승인만 받으면 돌릴 수 있는 상태라고 제시하지 않는다. **Stage B BLOCKED 유지**.
