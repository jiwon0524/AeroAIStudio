# Subject notification — 별도1회 실행 승인안

**SUBJECT_NOTIFICATION_PREPARED_NOT_EXECUTED / NOT_RUNTIME_VERIFIED / Stage B BLOCKED**.
현재 범위는 source 구현·compile/link·비실행 검사뿐이며 실제 DART/fixture/Gazebo 로딩·실행, World/step, 서비스 시작, runtime marker 소비0회다. B1/V2/Probe A와 실패 증거·marker는 보존한다. 이 문서는 실행 승인이 아니다.

## 실행 명령과 인자

```bash
cd /tmp/AeroAIStudio-dart-internal-trace &&
env -u LD_PRELOAD -u LD_AUDIT -u LD_LIBRARY_PATH \
  PYTHONDONTWRITEBYTECODE=1 \
  python3 validation/dart-subject-notification-v1/scripts/launch.py \
  --execute-approved-notification-once
```

native argv `/fixture/native_fixture --owned-notification-once`; native_fixture는 아래 새 host executable의 readonly FD다. 직접 fixture 호출 금지. launcher 기본 동작은 contract 출력뿐이다. base commit5f5a496dce3acf3f777a816308c1d0d018f30ff3, experiment/dart-internal-trace clean에서 준비했으며 실제 승인에는 이 준비를 게시한 전체 commit/source/ELF identity를 고정해 재대조해야 한다. base ancestry 통과는 실행 승인이 아니다.

## 관측 신호와 정확한 판정

GO 후 Recorder(observer)→Skeleton1/rootWeldJoint+BodyNode1/BoxShape+ShapeNode1을 준비한다. Recorder는 owner보다 먼저 선언해 예외 cleanup에서도 owner보다 오래 산다. borrowed raw node/body/joint를 delete하지 않는다. ShapeNode·BodyNode를 const Subject*로 변환해 서로 다른 identity로 등록한다. protected addSubject의 public wrapper만 사용하며 수동 notification 송신/가상 소멸자 덮어쓰기/allocator override/ptrace/LD_PRELOAD/LD_AUDIT 없음.

등록 대상2·통지0 → fixture Shape strong 참조 reset 후에도 통지0 → recorder.window=true → Skeleton owner.reset → window=false. callback은 대상 ID와 count/order만 stack 고정2slot에 저장한다. body/node각1·총2·window내·ID순서shape_node→body_node·unknown/중복/overflow0·등록잔여0을 모두 확인한다. 해제된 pointer로 객체 접근하지 않는다. expected notification order는 source-derived 가설이고 실패 시 자동 완화/재실행 금지다.

stdout 정확히4이벤트: post_open_ready WAIT → registered(bodies1/shape_nodes1/subjects2/callbacks_before_release0) → notifications_observed(node1/body1/order[node,body]/within_owner_reset=true/subjects_remaining0) → lifetime_success(scope subject_notifications_only/individual_destructors NOT_OBSERVED/allocator_balance NOT_MEASURED). supervisor는 구문·횟수·필드·순서와 count 타입을 검사하고 weak/exit0만 있거나 callback 누락·중복·역순·window외이면 거부한다.

이 신호는 DART Subject/Observer notification 전달 관측이다. Subject가 destructor 외에서도 notification을 보낼 수 있어 **개별 Skeleton/BodyNode/ShapeNode/Joint destructor 진입·호출순서/D0/free는 NOT_OBSERVED**. allocator provider·균형/누수는 NOT_MEASURED. weak_ptr 만료를 사용해 이 판정을 대신하지 않는다. 이 하위사례가 성공해도 Probe B전체/C/D 또는 Gazebo 진입 PASS가 아니다. 요구조건/수용 가능성과 미결정 사항은 prerequisite_review.md에 문서 근거별로 구분했다.

## 고정 파일/ELF

실행파일 Build-ID `5413820f21ad247eeac0a1048667b334aeb1344d`, 86944bytes. manifest.json은 새 binary metadata와 기존 Core16, stat/Build-ID/device/inode를 포함한다. work/manifest.sha256와 runtime_contract.json의 source/manifest/pin 해시로 검증하며 자동 재pin 금지. Core16은 B1/V2와 byte-identical allowlist이고 아래 SHA-256을 열린 readonly FD에서 확인한다.

|절대경로|SHA-256|
|---|---|
| `/tmp/AeroAIStudio-dart-internal-trace/validation/dart-subject-notification-v1/work/notification_fixture` | `453d44703cbe423976aebe721311d22e959fc2ab5613539d7584381593749e9d` |
| `/usr/lib/x86_64-linux-gnu/libdart.so.6.13.2` | `f74f4ec9820aee785ef94fb7bedafa7e4c832f209675a8ca1d35019c72b48e06` |
| `/usr/lib/x86_64-linux-gnu/libdart-external-odelcpsolver.so.6.13.2` | `b890ed6936ea7cf486303fc5101ee5ff68356fc89596273ebaef83671aa4cb16` |
| `/usr/lib/x86_64-linux-gnu/libfcl.so.0.7.0` | `3436bd79e03ed39efce6f7abfd64ed35429d5574bd76337b90edb1fb85506afb` |
| `/usr/lib/x86_64-linux-gnu/liboctomap.so.1.9.7` | `ec8bfd6cce31e7fd3dced8d5489109f6bca3d066c8ac3035b032940a8eb9ef50` |
| `/usr/lib/x86_64-linux-gnu/liboctomath.so.1.9.7` | `efd1dcfc111d271e13173f02153c0a950bbce9ccd53d1319990a5e6ff56c8dca` |
| `/usr/lib/x86_64-linux-gnu/libassimp.so.5.3.0` | `f5524225032201d129cac2adf305af9c7ffcf612d8662f3c87a2d891d5cd3d18` |
| `/usr/lib/x86_64-linux-gnu/libstdc++.so.6.0.33` | `1fd75fe70354a416d75aef22bcae68c47bd25d20e2d0568c30b1a9838cf62f11` |
| `/usr/lib/x86_64-linux-gnu/libm.so.6` | `fce00b6f25f459cf4ae0b7fae4257909a1a8a86f9149e7c029a5d617baf1ccd0` |
| `/usr/lib/x86_64-linux-gnu/libgcc_s.so.1` | `d93224d2b0dab4247598be683adca02f5cf00586f99c187579cd7e92058fb7cb` |
| `/usr/lib/x86_64-linux-gnu/libc.so.6` | `3a15d66867d83762c7f2f1e37359cb8f6c5743edb369c65285cb0b1c4f7498bf` |
| `/usr/lib/x86_64-linux-gnu/libccd.so.2.0` | `aa285639c8e4fa83f5987357fdc882e6df614949e40a7e85676b640ffb25f4f1` |
| `/usr/lib/x86_64-linux-gnu/libz.so.1.3` | `f61677c7bdb7c2aa2a243ea781bfd16afcb361cede7b4ef76127a9d8eb9a5242` |
| `/usr/lib/x86_64-linux-gnu/libdraco.so.8.0.0` | `b368d354f2778606b2553037fc8a3212719ee76a82711c60f7c72de49818e781` |
| `/usr/lib/x86_64-linux-gnu/libminizip.so.1.0.0` | `7397458805900a67287673a7d469d1ff207525ae7694ed885e8603d0164828bf` |
| `/usr/lib/x86_64-linux-gnu/libpugixml.so.1.14` | `b5493d9c8c6e36e3b72e38564b7e287ad925ab717577ded997465f9ac9da1c9e` |
| `/usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2` | `c20a2dc8917c755f02b94049356320fe1f62ac7d9f8994731f807d9df39302da` |

실제 fixture NEEDED4개(libdart.so.6.13/libstdc++.so.6/libgcc_s.so.1/libc.so.6). `resolution.json`에 stage와 공유하는 actual Bubblewrap builder argv(상징FD100.. 등),62edges/29ROmount를 기록했다. Core SONAME libdart.so.6.13은 같은 canonical installed Core FD에 readonly alias로 노출한다. readelf -dW/-lW로 모든 NEEDED/SONAME/RPATH/RUNPATH/interpreter와 실제 mount argv의 provider를 검사한다. missing/collision/wrong provider/unknown FD/metadata/interpreter link 실패는 marker/service 전 거부. stage에서도 열린 실제 FD argv를 exec 전 재확인한다. static resolution PASS는 kernel loader/symbol-version/runtime 인증이 아니다.

static_review.json에 Observer/Subject 헤더·소스 해시 및 설치 Core/export·fixture import symbol을 기록했다. symbol 존재와 보존 source는 runtime callback stack 인증이 아니다. 컴파일은 보존 packaged DART headers+baseline external fallback+Eigen, fixture Werror 유지/외부 isystem 분류이며 전체 header/binary ABI parity는 미인증이다. init/fini는 main 전 실행될 수 있어 pre-object GO와 pre-loader 차단은 다르다.

## 게이트/출력/one-shot

신규 prefix `validation/dart-subject-notification-v1/`. runtime 출력 `reports/runtime/{mapped_library_validation,native_fixture_execution,runtime_observation,resource_readback,process_cleanup,controller_diff,supervisor_integration}.json`, `reports/runtime_integrity.json`. one-shot `work/runtime_collection_attempt.json`, `work/runtime_attempt.json`. raw stdout/stderr/runtime_integrity_before.json/canary는 새 work만 사용. 위 runtime 경로는 현재 모두 부재. 준비 work/build.*·static_tests.log·preservation_before.json·manifest.sha256·notification_fixture는 marker가 아니다. 기존 작업 출력은 재사용하지 않는다.

launch의 lexists fresh paths/source·manifest hash/branch·ancestry/FD identity/actual resolution→read-only manager running·unique own unit collision check를 모두 통과한 뒤만 collection marker를 exclusive 생성한다. fresh 원본 snapshot 후 notification_supervisor가 source/환경/one-shot/closure/manager/unit을 다시 검사하고 service marker exclusive→service 실행. stage도 source·limits·cgroup·FD·resolution 검사. 부재 marker를 검사하는 비실행 테스트는 mock 실패 주입이며 실제 marker를 만들지 않았다.

native READY 후 host는 strict Core16+fixture file identity(PID/start/dev/inode/SHA/Build-ID),같은 own cgroup membership,유일한 native,별도 mnt/net/user/pid namespace,live limits와 controller during 검사를 확인한 뒤만 GO. mapping 실패/샘플링 누락이면 객체 허가 미전송. map_files EPERM의 기존 proc-root FD fallback은 file identity만 보장하며 resident COW/초기화 부작용은 미인증.

## 격리·자원·예상 프로세스

B1의 Bubblewrap/systemd/strict GO/cleanup 코드를 새 task-local launcher/notification_supervisor/stage/readiness/resolution에서 재사용했고 기존 파일은 수정하지 않았다. host launch→supervisor→systemd-run client; own transient user service stage→prlimit/bwrap→bwrap reaper→native. unit `aero-notification-v1-runtime-<unique>.service`, PID/start/InvocationID는 미실행으로 미확인. 실제 승인 시 host/PID/start/output을 기록한다.

MemoryMax67108864(64MiB), swap0, TasksMax8, CPUQuota25%/100ms, service RuntimeMax8s/stop2s/KillModecontrol-group/OOMPolicystop/Delegate=no. prlimit CPU2s/AS256MiB/FSIZE64KiB/NOFILE64/CORE0; native GO3s/host READY5s. root tmpfs16MiBRO,devRO,tmp4MiB/run4MiB/shm1MiB,readonly FD allowlist,unshare-all/capdrop ALL/sterile env/die-with-parent. native에는 host main/evidence/home/credential/network socket 노출 없음. Python service stage/host supervisor는 host context이고 native subtree에 bwrap 제약이 적용된다. socket positive controls/host연결 부재,canary/temp/controller 선택설정 전후 검사는 유지한다.

한도 변경0. B1이 같은 구조/Core16에서 peak12763136bytes/tasks3/689ms를 기록했다는 역사적 근거와 추가2개 observer 등록만 있는 범위를 참고해 유지한다. 새 관측기 등록의 std::set 할당·call overhead/64MiB/8s 충분성 및 실제 결합 runtime은 미검증이다. 초과 시 보존·정지, 자동 상향·재시도 금지. 기존 검증을 새 fixture runtime PASS라고 재사용하지 않는다.

## 성공·중단·정리·무결성

필수 성공:preflight/identity/limits PASS→GO→정확한4이벤트·callback count/identity/window/order/unregistration 계약→exit0→own unit/cgroup/관측PID-start/temp/canary 정리 PASS→controller 선택설정 before/after diff0→fresh 원본 무결성 PASS. 통지 성공 뒤에도 개별 destructor/allocator는 미관측으로 유지한다. 오류/UNKNOWN/불완전필수수집은 PASS로 올리지 않는다. native exit77 badargv/78 GO absent-partial-timeout/20 structural/21 association/22 observer contract/23 unexpected exception/24 output failure. signal/timeout/nonzero/비승인 provider/write/network/unexpectedcallback이면 FAIL하고 중단한다.

GO전 실패는 stdin을 닫고 GO를 보내지 않는다. own service deadline 내 wait/reap, 필요 시 현재 exact ownunit InvocationID가 저장된 active 값과 같을 때만 stop; 전역 pkill/기존 작업 종료·restart 금지. unit not-found/cgroup 제거/관측PID-start잔여0/temp·canary제거 확인. 수거 후 unit default 속성을 실행 중 한도로 해석하지 않으며 마지막 cgroup sample은 최종 보장없음, 수집 못한 exit/signal/resource는 UNKNOWN. 실패 로그·marker 삭제/복구/자동 재사용 금지.

원본 integrity는 실행 직전 fresh snapshot으로 main HEAD/status·기존source/ignored evidence/이전 marker/승인ELF를 수집하고 실행 후 비교한다. 새 task와 실험 handoff만 제외;changed/missing0/기존범위추가0/main HEAD·dirty상태동일 필요. 새 runtime snapshot을 과거 B1으로 대체하지 않는다. preparation integrity.json도 같은 원칙으로 검사한다. raw ELF/manifest pin/snapshot/로그/marker는 local /tmp라 Git만으로 다른 기기/계정에 옮겨지지 않는다.

이번 단계는 준비 완료 후 게시·보고에서 종료한다. 위험 수용은 결정하지 않았고 실제 명령은 별도 명시 승인 전 실행 금지다. Stage B BLOCKED 유지.
