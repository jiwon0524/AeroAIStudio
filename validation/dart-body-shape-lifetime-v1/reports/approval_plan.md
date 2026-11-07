# Body/Shape normal ownership B1 — 별도 1회 실행 승인안

**BODY_SHAPE_PREPARED_NOT_EXECUTED / NOT_RUNTIME_VERIFIED / Stage B BLOCKED**.
시작 HEAD `83c9b0c6838f5e1f244811524e45e140cf8657b1`, experiment/dart-internal-trace clean 확인. 현재 사용자 승인은 구현·컴파일·링크·비실행 검사까지다. 실제 fixture/DART loading/service/새 marker 소비0회. 기존 Probe A/V1 실패/V2 결과와 marker는 보존한다. 이 문서의 명령은 별도 명시 승인 전 실행 금지다.

## 정확한 1회 명령

```bash
cd /tmp/AeroAIStudio-dart-internal-trace &&
env -u LD_PRELOAD -u LD_AUDIT -u LD_LIBRARY_PATH \
  PYTHONDONTWRITEBYTECODE=1 \
  python3 validation/dart-body-shape-lifetime-v1/scripts/launch.py \
  --execute-approved-body-shape-once
```

native argv는 `/fixture/native_fixture --owned-body-shape-once`다. host의 body_shape_fixture를 sandbox의 기존 고정 native_fixture 경로에 readonly FD로 노출한다. fixture 직접 호출 금지. 기본 launcher는 계약 JSON만 출력한다. 이 보고서와 후속 publication commit의 source/ELF/manifest가 맞아야 하며 사용자는 실제 승인 시 그 commit을 고정해야 한다. 계약의 base_commit ancestry는 이 준비 commit의 조상 확인용이며 실행 승인 자체가 아니다.

## 객체와 관측 범위

GO 이후 Skeleton1개→root WeldJoint+BodyNode1개→BoxShape1개(0.1m cube)/일반 ShapeNode1개 생성. collision/visual/dynamics aspect 추가, collision detector/group/object, World, solver, step, Gazebo, exception injection, baseline/trace OFF/ON은 없다.

creation 관측: non-null, body/joint/shape node 개수 각1, Skeleton 소속 BodyNode와 parent joint, ShapeNode의 BodyNode/Shape 포인터 동일성. `getBodyNodePtr()`와 `getShape()`의 임시 strong 참조는 이 표현식 끝에 해제된다. 반환된 raw joint/body/node는 borrowed이며 delete하지 않는다. ShapeNode는 BodyNode에 붙고 Shape를 shared ownership으로 보유한다.

release 관측: fixture의 Shape shared_ptr를 먼저 reset→Shape weak_ptr가 아직 유효함 확인→Skeleton owner reset→Skeleton/Shape weak_ptr 만료 확인. reset 뒤 raw 포인터를 역참조하지 않는다. 예외는 catch해서 FAIL(23)이며 fault injection이 아니다. constructor/owner reset 경계에서 bounded 고정 문자열 stdout만 사용하며 new/delete override/소멸자 계측을 넣지 않는다. stdio 초기 버퍼 등 libc 할당까지 없다고 주장하지 않는다.

이벤트 순서 정확히5개: `post_open_ready WAIT`, `created`(개수/owner 동일성), `external_shape_released`(shape_retained true), `owner_release_observed`(두 weak expired true), `lifetime_success`(scope normal_owner_release_only). malformed/중복/순서 오류/필드 누락은 supervisor가 거부한다. substring lifetime_success나 exit0만으로 성공 처리하지 않는다.

**개별 Skeleton/BodyNode/ShapeNode/Joint 소멸자 호출·순서 = NOT_OBSERVED**, allocator balance=NOT_MEASURED. 소스의 destructor 경로는 API 소유권 해석 근거이며 설치 binary의 호출 관측이 아니다. weak_ptr 만료·정상 반환은 유한 정상 owner-release 사례의 결과일 뿐 개별 D0/allocator/누수0/전체 ABI 인증이 아니다. 근거 경로·해시는 static_review.json.

## 파일 고정과 ELF closure

manifest.json에 Core16 및 fixture baseline 프로필을 고정하고 work/manifest.sha256로 pin한다. Core16 allowlist는 V2와 동일하다. runtime_contract.json은 manifest/pin 및 새 source/공유 helper의 SHA-256을 검사한다. ELF들은 열린 RO FD의 SHA-256/Build-ID/device/inode로 확인한다. source/hash mismatch를 자동 재생성하지 않는다. `prepare.py`는 명시적 compile artifact 준비 전용이며 기존 pin이 있으면 재생성을 거부한다.

실행파일 Build-ID `fddd45515eed547e410b246d19754cc562fca603`, size 82560 bytes. 아래는 실행파일+필수 Core16 실제 경로/SHA-256이다. 전체 stat/Build-ID/metadata는 manifest.json 참조.

|경로|SHA-256|
|---|---|
| `/tmp/AeroAIStudio-dart-internal-trace/validation/dart-body-shape-lifetime-v1/work/body_shape_fixture` | `2d0001f80a1f1f1c2f80db5fd68a6018b3bed59fbfda1813934945d3884069f7` |
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

fixture의 실제 NEEDED는 libdart.so.6.13/libstdc++.so.6/libgcc_s.so.1/libc.so.6. source/stage가 공유하는 실제 Bubblewrap argv를 readelf -dW/-lW와 함께 검사해62edges를 승인 provider에 연결했다. 29개 canonical/alias mount에 `/usr/lib/x86_64-linux-gnu/libdart.so.6.13`을 canonical 설치 Core와 **동일 readonly FD**로 포함한다. 누락·충돌·잘못된 provider·미승인 FD·metadata·interpreter link 변경은 marker/service 전에 거부한다. RPATH/RUNPATH 불허. `resolution.json`은 상징 FD 번호를 쓰는 같은 builder의 정확한 mount argv다. stage는 실제 FD argv를 exec 전 다시 확인한다. static search/layout 검사이지 symbol-version/kernel loader 실행 인증은 아니다.

## 실행 전·객체 전 게이트

launch: lexists 기반 runtime output/두 marker/before snapshot/canary/stdout/stderr 충돌 거부→source/manifest/pin/branch/base ancestry→ELF FD identity/실제 resolution→read-only manager running/새 unique own unit collision 확인→collection marker exclusive→fresh 원본 snapshot→supervisor. supervisor는 source/환경·branch/ancestry·resolution·manager/unit을 다시 확인한 뒤 service marker exclusive 생성 후 own service 시작한다. service stage도 source/FD/limits/cgroup/resolution을 재검사한다. 모든 source와 실제 승인 HEAD를 실행 전에 다시 대조해야 한다.

native는 loader 후 READY에서3초 GO 대기한다. host가 살아 있는 PID/start, exact own cgroup membership, 별도 mnt/net/user/pid namespace, limits, 유일한 fixture, strict Core16+fixture mapped-file identity를 확인하고 controller during 차이를 검토한 후만 GO를 보낸다. main 전 DT_NEEDED constructors는 이미 실행될 수 있다. map_files open EPERM의 기존 proc-root FD fallback은 file identity만 보장하고 resident COW/constructor 부작용을 인증하지 않는다. PID가 sampling 전에 끝나면 확인 누락이며 PASS가 아니다.

## 격리·한도·프로세스

V2 stage/layout/strict mapping/정리 helper를 재사용하고 새 task별 source로 고정했다. generic supervisor import가 공유 helper 경로에 가려진 테스트 오류는 `body_shape_supervisor.py` 고유 이름으로 해소했다. 원래 공유 helper/기존 V2 파일은 수정하지 않았다.

host launch→body_shape_supervisor→systemd-run client; service stage→prlimit/bwrap→bwrap reaper→native. 단1회/단 arm. own unit `aero-body-shape-v1-runtime-<unique>.service`; 실제 unit/PID/start/InvocationID는 아직 없음(미실행). 실행 시 host/PID/start와 output을 기록한다. systemd user manager 접근에 환경 승인이 필요할 수 있으나 우회하지 않는다.

MemoryMax64MiB(67108864), MemorySwapMax0, TasksMax8, CPUQuota25%/100ms, RuntimeMax8s, TimeoutStop2s, KillMode control-group, OOMPolicy stop, Delegate no. prlimit CPU2s/AS256MiB/FSIZE64KiB/NOFILE64/CORE0, host READY5s/native GO3s. 제한 변경0. V2 peak11,812,864bytes/3tasks/897ms를 참고해 추가 단1개 body/shape에 선제 상향 근거는 없다고 판단했다. 새 코드의 실제 메모리/CPU/시작시간 충분성은 **미검증**이며 실패 후 자동 상향/재시도 금지다.

fresh root16MiB remount-RO, dev RO, private tmp4MiB/run4MiB/shm1MiB, readonly FD allowlist, unshare-all/user-net-mnt-pid/cap-drop ALL/sterile env/die-with-parent. main/기존 evidence/host HOME·network socket·credential는 native에 노출하지 않는다. service stage의 Python/시스템 도구는 host context에서 실행되며 Bubblewrap 제약은 native subtree에 적용된다. host supervisor는 새 own 증거를 수집하고 기존 원본을 읽는다. IPv6/UNIX/abstract socket positive controls 및 sandbox에서 host 접속 부재 확인, canary/temp/controller 선택 설정 검사를 유지한다. 새 코드 결합의 실제 격리·강제 한계는 이번에 재실행하지 않았다.

## 새 출력·one-shot·실패·정리

task prefix `validation/dart-body-shape-lifetime-v1/` 아래:

- reports/runtime/{mapped_library_validation,native_fixture_execution,runtime_observation,resource_readback,process_cleanup,controller_diff,supervisor_integration}.json, reports/runtime_integrity.json
- work/runtime_collection_attempt.json, work/runtime_attempt.json (exclusive, 삭제/재사용 금지)
- work/runtime_integrity_before.json, work/stdout, work/stderr, 임시 canary

현재 위 runtime 경로 모두 부재. work/preservation_before.json·build 로그·static test 로그·ELF·manifest pin은 준비 증거이며 runtime marker가 아니다. 기존 V1/V2/Probe A는 입력/보존 대상이고 출력으로 사용하지 않는다.

성공은 사전검사+strict identity→GO+정확한5이벤트+exit0+unit/cgroup/관측 PID-start/temp/canary 정리+controller 선택 설정 전후 diff0+fresh 원본무결성 PASS를 모두 요구한다. 개별 소멸자는 성공 후에도 NOT_OBSERVED다. null/count/소유권/약참조 기대 위반/예외/nonzero/signal/timeout/미승인 mapping/provider/격리위반/불완전 필수 수집이면 FAIL 또는 INCOMPLETE. native exit77(잘못된 argv),78(GO 미수신),20/21(생성/관계),22(소유 해제 기대 실패),23(예외),24(output flush). service 수거 후 사라진 exit/cgroup 최종 값은 UNKNOWN, 마지막 표본을 최종 표본으로 보장하지 않는다. 초과 강제효과·무사고·전체 ABI를 인증하지 않는다.

GO 전 실패는 stdin을 닫고 GO를 보내지 않는다. own service deadline으로 종료를 기다리고, 최후 stop은 저장된 active InvocationID가 현재 exact own unit과 일치할 때만 수행한다. 다른 작업 pkill/재시작/cleanup 금지. wait/reap 후 unit not-found/cgroup 제거/관측 PID-start 잔여0/temp·canary 제거를 확인한다. 실패 증거와 marker는 보존하며 자동 재실행/상향/원본복구 없음.

원본 integrity는 실행 직전 fresh snapshot과 실행 후 snapshot을 비교한다. main HEAD/dirty status, 기존 소스/ignored evidence/이전 marker/승인ELF를 포함하고 새 task와 실험 handoff만 제외한다. changed/missing0/기존범위추가0/main HEAD·status동일이 필요하다. 전수 비교 raw는 local work에 보존되며 Git 게시만으로 다른 기기에 이동되지 않는다.

## Probe B/C/D 대응

|요구|이 fixture가 별도 실행 후 제공할 수 있는 증거|남은 검증/위험 수용|
|---|---|---|
|B 정상 Skeleton→BodyNode→ShapeNode|설치본 단1개 정상 생성·소유 관계·제한된 owner release 결과|개별 destructor/D0 호출·순서·allocator balance·누수는 미관측|
|B Bullet detector/group/object/cast|없음|별도 factory/deleter/cast 수명·provider 검증 필요|
|B 설치/baseline/trace OFF 비교|설치본 사례만|baseline/trace arm별 준비·실행·동등 계약 비교 필요|
|C 부분 생성 예외/unwind|없음; 예상 밖 예외는 FAIL|정상 B 경로 이후 검토된 fault window·재진입·부분 해제 검증 필요|
|D trace OFF/ON owner/quiescent/capacity/flush|없음|별도 trace 경계/계측 메타데이터 영향 검증 필요|
|Gazebo/Host/Stage B|없음|프로젝트 진입 증거 또는 항목별 잔여 위험 명시 수용 후에도 별도 승인 필요|

현재 결과는 **compile/link + 비실행 준비 PASS**, 위 runtime 증거는 아직0이다. B 전체/C/D 완료나 READY_FOR_HOST로 승격하지 않는다. 남은 경계를 생략하려면 사용자의 항목별 위험 수용이 별도로 필요하며, 이 테스트의 한계를 확인하는 것만으로 자동 수용된 것으로 보지 않는다. Stage B BLOCKED 유지. 이 단계가 끝나면 게시·보고 후 멈추며 별도 승인 전 명령을 실행하지 않는다.
