# 빈 Skeleton V2 — SONAME 수정 및 별도 1회 실행 승인안

**STATIC_ALIAS_FIX_PREPARED_NOT_EXECUTED / NOT_RUNTIME_VERIFIED / Stage B BLOCKED**.
시작 branch experiment/dart-internal-trace, HEAD00ac79ea7aa14eb99dc4368a126eb5b998f52963 clean. V1 실패·marker 및 Probe A는 read-only 보존한다. 이번에는 readelf와 Python 비실행 검사만 수행했고 DART/fixture/서비스 실행0, 새 one-shot 소비0이다.

## 수정과 서비스 전 차단

설치 canonical `/usr/lib/x86_64-linux-gnu/libdart.so.6.13.2`의 DT_SONAME은 `libdart.so.6.13`이다. 기존 canonical mount를 유지하면서 `/usr/lib/x86_64-linux-gnu/libdart.so.6.13`에 **같은 검증된 readonly FD**를 추가한다. 이전 계획 대비 추가 target은 이것1개이며 파일 복사·새 provider·시스템 symlink 변경은 없다.

readiness_fixed.py는 기존 helper를 이 작업에 한정해 재사용하고 모든 provider SONAME을 mount/candidate에 포함한다. 기존 Core16 allowlist는 byte-identical이며 executable도 그대로다. 기존 PID/start·파일identity·전체Core membership·객체 전 GO는 동일하고 새 SONAME 경로도 허용된 같은 inode로만 인정한다.

resolution.py의 build_command를 stage와 사전검사가 공유한다. readelf -dW/-lW를 열린 승인 FD에 적용하여 fixture+16ELF의 실제 NEEDED/SONAME/RPATH/RUNPATH와 interpreter를 읽는다. 모든 NEEDED62edges를 실제 ro-bind-fd argv의 승인 file identity에 연결한다. 별칭 부재/충돌/다른 승인파일/미승인FD·metadata 변화·interpreter link 누락은 거부한다. 이 sterile x86-64 layout의 /lib→usr/lib 및 기본 multiarch search 경로를 모델링하며 cache/환경 search path는 제공하지 않는다. symbol version과 실제 kernel loader 동작의 인증은 아니다.

launch: source/manifest/FD identity 검사 -> static resolution -> collection marker exclusive 생성 -> fresh 원본snapshot -> supervisor. supervisor 직접호출도 resolution을 service marker 생성과 systemd-run 이전에 확인한다. stage는 실제 FD argv를 exec 전에 다시 확인한다. 따라서 오류로 새 marker/service를 소비하지 않는다. 사전검사에 subprocess readelf만 쓰고 ldd/target 실행은 없다.

## 정확한 다음 1회 명령 — 별도 승인 전 실행 금지

```bash
cd /tmp/AeroAIStudio-dart-internal-trace
env -u LD_PRELOAD -u LD_AUDIT -u LD_LIBRARY_PATH PYTHONDONTWRITEBYTECODE=1 python3 validation/dart-skeleton-lifetime-v2/scripts/launch.py --execute-approved-skeleton-once
```

native argv `/fixture/native_fixture --owned-skeleton-once`. host launch/supervisor + systemd-run client; service stage→prlimit/bwrap→bwrap reaper→native의 기존 구조다. fixture 직접 실행은 금지한다. dynamic startup constructors는 main 이전이며 native READY 후 host strict identity/namespace/cgroup 검증→GO 이후에만 빈 Skeleton1개 create/null/바디0/관절0/weak_ptr유효/shared_ptr reset/expired 확인한다. 관절/바디/충돌/World 생성·물리 호출·Gazebo는 포함하지 않는다.

## 고정된 파일과 출력

실행파일 `/tmp/AeroAIStudio-dart-internal-trace/validation/dart-skeleton-lifetime-v1/work/skeleton_fixture`
SHA256 `2bc3e2d18c2360e1d4a2c276226c147f441dbd871cb3b003a054ba695d555292` / Build-ID `a0b31f19797f7cb36f6d5c0e311ac62517004b2b`
Core SHA256 `f74f4ec9820aee785ef94fb7bedafa7e4c832f209675a8ca1d35019c72b48e06` / Build-ID `071aa565b343db80e31aae393aadaed33c7adb46`
manifest SHA256 `1a9d227d1f3cbc83c6b9f8de4f2ac3cc93ca5ae390b16d219a86c2e6cd5fa150`
나머지 의존 ELF의 절대경로/SHA256/Build-ID/device/inode는 manifest.json에 기존 승인과 동일하게 고정했다. work/manifest.sha256로 pin하며 mismatch를 자동 재생성하지 않는다. source/runtime helper hashes는 runtime_contract.json에 고정한다.

새 출력: validation/dart-skeleton-lifetime-v2/reports/runtime/ 및 reports/runtime_integrity.json.
새 exclusive one-shot: validation/dart-skeleton-lifetime-v2/work/runtime_collection_attempt.json, work/runtime_attempt.json.
stdout/stderr, canary, runtime_integrity_before.json은 새 work/ 아래에서만 생성한다. 현재 runtime출력/marker 전부 부재다. V1과 Probe A 파일은 삭제·덮어쓰기하지 않는다. 기존 출력/marker 충돌이면 중단하며 자동 재시도하지 않는다. /tmp ELF/pin/raw manifest는 로컬이며 Git만으로 다른 기기에 이전되지 않는다.

## 자원·격리·중단·정리

MemoryMax64MiB(67108864)/MemorySwapMax0/TasksMax8/CPUQuota25%·period100ms/RuntimeMaxSec8s/TimeoutStopSec2s/KillModecontrol-group/OOMPolicystop/Delegate=no. prlimit CPU2s/AS256MiB/FSIZE64KiB/NOFILE64/CORE0, nativeGO3초/hostREADY5초. readonly FD allowlist/fresh root16MiBRO/devRO/private tmp4MiB/run4MiB/shm1MiB/net-user-mnt-pid namespace·capdrop·sterile env·die-with-parent 유지. 새 readonly alias만 추가하며 쓰기권한·네트워크 허용은 추가하지 않는다. 실제 격리·tmpfs/connect 재시험은 이번에 하지 않았다.

성공은 사전/host 식별PASS+GO+created(empty)+lifetime_success(expired)+exit0+unit/cgroup/PID-start/temp/canary정리+controller선택설정전후동일+원본hash/main상태PASS 모두다. 오류·UNKNOWN·불완전수집은 성공으로 올리지 않는다. GO전 불일치면 권한 미전송/stdin닫기, service deadline까지 wait, 필요한 경우 InvocationID 일치 exact ownunit만 stop. 자원충분성/초과강제효과/전체ABI/constructors/finalizers는 미검증; 실패 시 증거보존·중단·상향/재시도금지. host proc-root fallback은 파일identity 수준이며 residentCOW/초기화 부작용 예방을 보장하지 않는다. PID sampling 이전 종료는 전체PID검사PASS로 쓰지 않는다.

## 비실행 검증

readelf 기반 실제 V1 argv는 missing alias libdart.so.6.13로 거부; 수정 argv는62edges PASS. 누락/충돌/잘못된 승인대상/미승인FD/interpreter누락/metadata변조 및 marker서비스 이전 거부 검사 포함10PASS/0FAIL. 최초9PASS/1FAIL은 도구 loader 환경의 사전 거부로, 안전 gate를 바꾸지 않고 승인 명령과 동일하게 LD변수를 제거한 검사에서10PASS. 기준 완화나 fixture 실행은 없다. executable 재컴파일·링크 불필요, 원래 hash유지.

실제 실행은 이번 수정 승인 범위가 아니다. 위 명령의 빈 Skeleton1회는 새 별도 명시 승인 후에만 수행하며 Probe A/Gazebo/World::step/Stage B로 확장하지 않는다.
