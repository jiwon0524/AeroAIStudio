# 빈 Skeleton 수명 시험 — 별도 실행 승인안

**STATIC_PREPARED_NOT_EXECUTED / NOT_RUNTIME_VERIFIED / Stage B BLOCKED**

시작 HEAD f58d45856ddf423d05a5dc52482e9d02f427142f, 실험 Git clean. 기존 Probe A local Runtime JSON과 marker는 보존한다. 동일 unit open/close/exit0 기록은 이전 실행의 보고 결과이며 당시 승인 미확인; 재실행하지 않는다. 이번 준비에서 DART 로딩·객체 실행·서비스 생성은 0회다.

## 승인할 정확한 범위

설치본 DART의 빈 Skeleton 하나를 create하고 null/바디0/관절0을 확인한다. weak_ptr가 초기에는 유효한지 확인하고 유일한 소유 shared_ptr을 reset한 다음 expired를 확인한다. 관절·바디·충돌 객체·World 생성, 메서드 기반 물리 계산, Gazebo/World::step/Probe A 재실행은 포함하지 않는다. weak_ptr expired는 제어 블록의 소유권 소멸이며 전체 메모리 누수 부재 증명이 아니다.

## 정확한 명령 — 이번에 실행 금지

작업 디렉터리 `/tmp/AeroAIStudio-dart-internal-trace`에서 별도 명시 승인 후 단1회:

```bash
env -u LD_PRELOAD -u LD_AUDIT -u LD_LIBRARY_PATH PYTHONDONTWRITEBYTECODE=1 python3 validation/dart-skeleton-lifetime-v1/scripts/launch.py --execute-approved-skeleton-once
```

native argv는 `/fixture/native_fixture --owned-skeleton-once`. 기본/다른 native argv는 exit77이나 기본 실행도 DART startup loading을 일으키므로 직접 실행 금지. launch.py 기본 동작은 JSON 출력만이며 ELF를 실행하지 않는다.

예상 구조: host Python launch/supervisor → systemd-run client; 별도 user transient service의 Python stage가 prlimit/bwrap으로 exec → bwrap reaper → C++ fixture. 최종 서비스 cgroup에서 bwrap2 + native1 예상, setup의 일시적 태스크는 미측정. fixture는 fork/thread를 생성하지 않으며 DART 초기화 내부 thread 여부는 미확정이다.

## 식별 gate와 격리

직접 링크 DT_NEEDED로 Core16이 main 이전 로드된다. 생성자/IFUNC 부작용을 gate 이전에 차단한다는 주장은 하지 않는다. native는 READY를 출력하고 3초간 GO만 대기. host는 PID/start, 실제 cgroup membership/64MiB·swap0·8tasks·25% readback, host와 다른 mnt/net/user/pid namespace, 모든 Core16+실행 파일의 mapping device/inode/SHA/Build-ID를 확인한 후에만 GO를 보낸다. 따라서 객체 생성 전에 live library identity 검사한다. maps 변경/추가/누락/deleted 또는 limit mismatch는 GO 거부. map_files 권한 거부 시 기존 proc-root FD fallback의 파일 identity 수준 한계를 유지한다.

기존 stage의 FD readonly mount와 SONAME aliases, fresh root16MiB RO, /dev RO, /tmp4MiB·/run4MiB·/dev/shm1MiB tmpfs, user/mnt/net/pid namespace, sterile env, cap-drop ALL/die-with-parent 재사용. 프로젝트 전체와 host socket은 sandbox에 mount하지 않는다. host test IPv6/UNIX/abstract socket positive control은 supervisor에서 생성한다. 기존 native의 connect/canary runtime checks는 이번 C++에 포함하지 않았으며, 기존 layout 증거와 host namespace gate를 재사용한다. 새 결합 동작은 정적 검토에 한정한다.

## 자원·종료·판정

MemoryMax64M=67108864, MemorySwapMax0, TasksMax8, CPUQuota25%/period100ms, RuntimeMaxSec8s, TimeoutStopSec2s, KillMode=control-group, OOMPolicy=stop, Delegate=no. prlimit CPU2s/AS256MiB/FSIZE64KiB/NOFILE64/CORE0. Native GO 대기3초. host READY 수집은 최대5초; GO gate 소요 시간이 native3초를 넘으면 실패하므로 충분성은 미확정이다.64MiB/8tasks/25%에서 빈 Skeleton 성공 가능성은 아직 실측하지 않았다. 한계 상향·자동 재시도 금지.

성공: host gate PASS_FILE_IDENTITY + GO + created(empty=true) + lifetime_success(expired=true) + exit0 + unit/cgroup/PID-start/temp/canary cleanup PASS + controller 전후 선택설정 변화0 + 원본 무결성 PASS 모두 필요. 예외23, null/nonempty20, premature expiration21, reset 후 미소멸22, GO누락/부분입력/timeout78, 출력오류24, OOM/signal/서비스timeout/불완전수집은 중단. native는 C++ 예외만 catch하며 segfault/abort/SIGKILL은 host exit와 stderr로 수집한다.

종료는 정상 wait. 실패 시 GO를 보내지 않고 stdin close 후 service deadline을 기다린다. 여전히 실행 중이면 저장한 InvocationID가 일치하는 정확한 이번 unit만 stop. 기존 서비스 종료·manager 재시작·controller 수동복구 없음. unit/cgroup 제거·관측PID/start 소멸·임시 socket/canary 삭제 확인. cleanup/integrity 실패 또는 UNKNOWN이면 성공으로 판정하지 않는다. 예외 중 보고 수집이 실패하면 수동 증거 검토가 필요하며 자동 재실행하지 않는다.

## 출력과 one-shot

`validation/dart-skeleton-lifetime-v1/reports/runtime/`에 observation/mapped identity/resource/cleanup/controller/native execution JSON. stdout/stderr는 이 작업 work/stdout, work/stderr. reports/runtime_integrity.json과 work/runtime_integrity_before.json으로 원본 main 및 기존 evidence hash/status 비교. work/runtime_collection_attempt.json과 work/runtime_attempt.json은 실행 때만 exclusive create하며 현재 둘 다 부재. 두 marker·기존 출력은 삭제/덮어쓰기 금지. 실패한 사전실행으로 marker가 생겨도 보존하고 중단한다.

## 빌드·정적 근거

g++ C++17/O2/Wall/Wextra/Werror/stack protector/RELRO/NOW로 compile/link 성공. readelf/nm으로 DART Core NEEDED, Core create export/import, PIE/RELRO/NOW, RPATH/RUNPATH 없음 확인. ELF와 테스트는 실행하지 않았다. Python AST 및 source/manifest/file identity/closure 검사15개 PASS. build.sh는 이미 있는 pinned executable을 덮어쓰지 않는다. 최초 compile은 matching package에 누락된 safe_convhull_3d.h 때문에 실패했고 기존 baseline-source include fallback을 추가해 성공; 시스템 헤더 설치·패치 없음. 이것은 정확한 설치 binary와 전체 header ABI 인증이 아니며 inline getNumBodyNodes/getNumJoints와 shared_ptr ABI는 실행 위험으로 남긴다.

실행 ELF SHA-256: `2bc3e2d18c2360e1d4a2c276226c147f441dbd871cb3b003a054ba695d555292`
Build-ID: `a0b31f19797f7cb36f6d5c0e311ac62517004b2b`

Core/의존 ELF 경로와 현재 읽은 SHA-256 (manifest.json에 Build-ID/device/inode 및 SONAME/NEEDED 포함):

|경로|SHA-256|
|---|---|
|`/usr/lib/x86_64-linux-gnu/libdart.so.6.13.2`|`f74f4ec9820aee785ef94fb7bedafa7e4c832f209675a8ca1d35019c72b48e06`|
|`/usr/lib/x86_64-linux-gnu/libdart-external-odelcpsolver.so.6.13.2`|`b890ed6936ea7cf486303fc5101ee5ff68356fc89596273ebaef83671aa4cb16`|
|`/usr/lib/x86_64-linux-gnu/libfcl.so.0.7.0`|`3436bd79e03ed39efce6f7abfd64ed35429d5574bd76337b90edb1fb85506afb`|
|`/usr/lib/x86_64-linux-gnu/liboctomap.so.1.9.7`|`ec8bfd6cce31e7fd3dced8d5489109f6bca3d066c8ac3035b032940a8eb9ef50`|
|`/usr/lib/x86_64-linux-gnu/liboctomath.so.1.9.7`|`efd1dcfc111d271e13173f02153c0a950bbce9ccd53d1319990a5e6ff56c8dca`|
|`/usr/lib/x86_64-linux-gnu/libassimp.so.5.3.0`|`f5524225032201d129cac2adf305af9c7ffcf612d8662f3c87a2d891d5cd3d18`|
|`/usr/lib/x86_64-linux-gnu/libstdc++.so.6.0.33`|`1fd75fe70354a416d75aef22bcae68c47bd25d20e2d0568c30b1a9838cf62f11`|
|`/usr/lib/x86_64-linux-gnu/libm.so.6`|`fce00b6f25f459cf4ae0b7fae4257909a1a8a86f9149e7c029a5d617baf1ccd0`|
|`/usr/lib/x86_64-linux-gnu/libgcc_s.so.1`|`d93224d2b0dab4247598be683adca02f5cf00586f99c187579cd7e92058fb7cb`|
|`/usr/lib/x86_64-linux-gnu/libc.so.6`|`3a15d66867d83762c7f2f1e37359cb8f6c5743edb369c65285cb0b1c4f7498bf`|
|`/usr/lib/x86_64-linux-gnu/libccd.so.2.0`|`aa285639c8e4fa83f5987357fdc882e6df614949e40a7e85676b640ffb25f4f1`|
|`/usr/lib/x86_64-linux-gnu/libz.so.1.3`|`f61677c7bdb7c2aa2a243ea781bfd16afcb361cede7b4ef76127a9d8eb9a5242`|
|`/usr/lib/x86_64-linux-gnu/libdraco.so.8.0.0`|`b368d354f2778606b2553037fc8a3212719ee76a82711c60f7c72de49818e781`|
|`/usr/lib/x86_64-linux-gnu/libminizip.so.1.0.0`|`7397458805900a67287673a7d469d1ff207525ae7694ed885e8603d0164828bf`|
|`/usr/lib/x86_64-linux-gnu/libpugixml.so.1.14`|`b5493d9c8c6e36e3b72e38564b7e287ad925ab717577ded997465f9ac9da1c9e`|
|`/usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2`|`c20a2dc8917c755f02b94049356320fe1f62ac7d9f8994731f807d9df39302da`|

## 남은 제약과 승인 경계

새 C++ runtime/host 통합은 미실행이며 정적 준비 상태다. 자원 초과 강제효과·실제 kernel namespace 실패·DART destructors/allocator/unwind·global fini 부작용은 미검증. 기존 무해 격리/상속 증거를 반복하지 않는다. 이 한정 fixture에 대해 기존 cgroup+namespace+RLIMIT+deadline과 실패시 중단 조건을 수용하면 별도 1회 실행 승인 검토 가능하다. 성공해도 Gazebo 물리 검증으로 자동 진입하지 않는다.

로컬 ELF/pin/raw manifests/header fallback은 Git에 자동 포함되지 않는다. 다른 기기에서 pin을 무조건 갱신해 재사용하지 않는다. 공통 스킬·production·main·Clock/Capture는 변경하지 않는다.
