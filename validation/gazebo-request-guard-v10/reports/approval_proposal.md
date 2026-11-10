# v10 작은 무해 종단 검증 — 1회 실행 승인안

**PROPOSED / 아직 실행 승인 없음. 이 문서는 실행 지시가 아니다.**
현재 사용자는 구현·빌드·정적/모의 검사만 승인했고, 실행 전 별도 명시적 승인을 요구했다.
아래 **정확한 계약 해시와 범위 전체에 대한 별도 승인 후에만** 명령을1회 실행한다.
Stage B BLOCKED / 위험 수용 미결정 / 런타임 미검증. 원래 실제 launcher와 v9 entry78 유지.

## 단일 명령과 계약

Ubuntu 호스트의 experiment/dart-internal-trace worktree에서 다음 **한 명령**이다.

```bash
/usr/bin/python3 -I -B /tmp/AeroAIStudio-dart-internal-trace/validation/gazebo-request-guard-v10/scripts/driver.py --execute-once --contract /tmp/AeroAIStudio-dart-internal-trace/validation/gazebo-request-guard-v10/reports/execution_contract.json --approved-contract-sha256 63f630e5e0aee7c19c09b693a8cc9c6d45e54f77b8d022820eb0b6b85c5a7395
```

계약 파일: `reports/execution_contract.json`, SHA256 `63f630e5e0aee7c19c09b693a8cc9c6d45e54f77b8d022820eb0b6b85c5a7395`.
인자는 `--execute-once`, 고정 contract path, `--approved-contract-sha256`뿐이다.
`approved` 인자명은 승인을 부여하지 않으며 이 문서를 준비했다는 사실도 실행 승인으로 해석하지 않는다.
기본 무인자 호출은78. 내부 `--collector-stage`는 위1회 명령이 만든 소유 unit/marker 검증 후에만 동작한다.
재빌드·source/입력 inode/hash 변경·계약 재봉인 시 이전 승인은 사용할 수 없고 새 해시 재검증·승인이 필요하다.

|control/probe 바이너리|bytes|SHA256|
|---|---:|---|
|probe|17192|`a82ea926913bc266bf55a4a010f346fe85a3a3ded86e0d20bc8566bc2cbf02f1`|
|owner|80704|`f1298ce7d2bf4b95902d2aa27c24e51f899987ebd5a10d4ac05c3e348b272685`|
|unit-anchor|16016|`945f6debaf75b0165a582bc1758c5baf5c6bf0f420d5a2c3f67bf294d585fa4d`|

실제 절대 바이너리 경로는 execution_contract의 owner_binary/anchor와 policy.paths[0].source,
build_receipt.outputs에 기록했다. 명령은 source·입력·host tools(Python/systemd-run/systemctl/busctl/git)와
이3개 ELF hash를 먼저 재검사한다. 불일치·누락이면 marker/service 전에 실패한다. ELF는 로컬 ignored이며
Git 게시만으로 다른 기기에 전달되지 않는다. /tmp 원본이 사라지면 이 해시 승인안으로 실행할 수 없다.

## 작은 입력과 포함·제외 범위

- fixed input24 bytes: `AERO_V10_FIXED_INPUT_V1\n`.
  SHA256 `3440488560fd86feb35165c28a58cd8901020579bc5ab109c56e8f92bb636b7a`.
  같은 원본을 `/input/fixed.txt`, `/input/fixed-alias.txt` 두 경로로 RO 전달한다.
- target ELF 집합은 probe17192 bytes, libc2129424 bytes, ld.so236616 bytes이다.
  libc SHA `3a15d66867d83762c7f2f1e37359cb8f6c5743edb369c65285cb0b1c4f7498bf`;
  loader SHA `c20a2dc8917c755f02b94049356320fe1f62ac7d9f8994731f807d9df39302da`.
  policy는 **4원본/5경로**로 고정이며 probe의 DT_NEEDED는 libc.so.6 하나다.
- 전용 owner 진입점은 v9 FD bridge·준비 factory·namespace·listener/단발 exec·task supervisor를
  작은 compile-time 정책으로 연결한다. collector는 초기O, 실제 sealed RO FD C/K, P, 독립 audit/A,
  GO, 종료 직전 live mapping, EXIT_ACK, callback·모든 task death, EOF/exit/정리/V를 처리한다.
- GO 전 root가 두 별칭을 읽고, GO 후 자손 프로세스가 fixed를 읽어0으로 종료한다. ready가 audit보다 먼저 도착해도 필수 입력 audit를 기다린 후 GO를 보낸다.
  EXIT_ACK 뒤 atexit이 살아 있던 worker thread를 깨우며 그 thread가 alias를 읽고 종료한 뒤 join한다.
  두 non-root task의 서로 다른 실제 INPUT_DELIVERED 기록과 모두의 정상 사망이 필수다.
- Gazebo/DART/plugin 로딩0, physics step0, 실제 harness0, 기존 marker 소비0.
  **필수 대형 객체5개 실제 준비, 303객체/468경로 실제 전달, 최대 메모리 측정은 포함하지 않는다.**
  100개 fixture counter는 합성 protocol이며 물리 스텝이 아니다.

작은 native4객체의 page-rounded 출력 계산은2392064 bytes, +직렬128KiB copy/hash는2523136 bytes이다.
별도 owner/anchor 두 control memfd의 dense pages98304 bytes를 함께 보유하면 native 준비 known분2621440 bytes,
retained six objects+collector1MiB hash buffer known분3538944 bytes이다. source cache/Python/ELF/kernel/IO 등
전체 overhead/peak는 이 계산에 포함되지 않는다. 이1회도 memory.peak 최대부하 시험을 수행하지 않는다.

## unit·출력·marker와 자원·시간

|항목|고정 값|
|---|---|
|owner/collector unit|`aero-guard-v10-owner-small-01.service`|
|target unit|`aero-guard-v10-target-small-01.service`|
|새1회 marker|`/tmp/AeroAIStudio-dart-internal-trace/validation/gazebo-request-guard-v10/work/harmless-small-01.once`|
|새 출력 디렉터리|`/tmp/AeroAIStudio-dart-internal-trace/validation/gazebo-request-guard-v10/work/runtime-small-01`|
|owner MemoryMax|5368709120 bytes; preparer/native parent+PID1 worker+Python collector 공용 별도 domain|
|native object/admission ceiling|543979760 /2159132672 bytes; 작은 정책만 준비; 더 올리지 않음|
|target resources|MemoryMax536870912/Swap0/Tasks64/CPU100%, period100ms, runtime30s/stop2s, KillMode control-group/OOM stop/Delegate no|
|target rlimits soft=hard|CPU10s/AS2147483648/FSIZE1048576/NOFILE256/CORE0|
|host/collector/ACK|host40s, collection 최대25s(남은 host 시간으로 축소), ACK5000ms|
|owner unit safety timer|RuntimeMaxSec40s, TimeoutStopSec2s, KillMode control-group/OOM stop|
|manager 호출|절대 경로 systemctl/busctl, 각 호출 timeout2s|
|stdout|total65536/pending16384 bytes|
|stderr|total1048576/pending65536 bytes|
|independent native journal|1MiB; frame 최대192bytes; durable JSONL logs 각각8MiB cap|

owner 속성은 target의 한도를 대체하지 않는다. 대상에 attach하기 전과 후에 target rlimits/cgroup
readback·namespace·caps0를 확인하고 anchor를 종료시킨다. anchor는 동일 target limits에서 잠시 SIGSTOP하며
실제 probe release 전에 종료한다. host40s는 정상 수집 deadline이다. 실패 뒤 stop/readback/client reap은
별도 정리 단계이며 각 manager call2s, cgroup 제거 poll2s, 소유 client wait2s 후 kill/wait2s 등 유한 작업이다.
정리가40s 안에 끝난다는 실측 보장은 없다. systemd safety timer도 실제 커널 동작은 검증 전이다.
전역 cgroup/시스템 설정·다른 unit은 변경하지 않는다.

marker와 출력이 하나라도 있거나 dangling link면 실행하지 않는다. 두 unit 모두 absent여야 한다.
exclusive marker를 첫 mutation으로 만들고(정확한 run+contract SHA), output0700과 로그0600을 새로 만든다.
실패해도 marker/증거를 삭제·재사용하지 않으며 자동 재시도하지 않는다. 이 새 marker만1회 소비하며 기존 것은 읽어 실행하지 않는다.

예정 출력: host.stdout/host.stderr, host-result.json, stdout.raw/stderr.raw,
owner-journal.raw, collector-audit.jsonl, native-audit.jsonl, target-unit.json, collector-result.json.
원시 출력은 로컬 보존이며 자동 게시 대상이 아니다. target InvocationID/cgroup 영수증은 anchor 관찰 전에
동기 저장한다. 소유권 증거를 얻지 못하면 임의 stop/kill하지 않고 UNKNOWN/FAIL을 남겨 별도 소유 복구를 요구한다.

## 매핑 증거의 작은 시험 전용 판정

기존 harmless 증거에서 map_files FD open은 EPERM으로 UNAVAILABLE였다. 이 권한을 높이지 않는다.
새 small profile은 map_files open을 우선 시도하며 EPERM/EACCES에서만 다음 조합을 명시적으로 사용한다:
살아 있는 retained sealed FD가 inode 재사용을 막고, kernel maps dev/ino가 그 object와 일치하며,
canonical `/proc/PID/root` FD가 그 동일 객체·seals·RO/NOSUID/NODEV/객체별 NOEXEC mount와 일치해야 한다.
5개 모든 canonical 경로를 검사하고 PID/start/maps 전후 안정성도 필수다. pathname label은 권한 근거가 아니다.
ENOENT/EIO/identity mismatch/unknown mapping/W+X/NX 실행에는 fallback이 없다. fallback 사용 기록은 독립
collector audit에 동기 저장한다. **v9 전체 정책의 더 엄격한 validator를 변경하거나 통과했다고 주장하지 않는다.**

## 통과·중단·정리 기준

통과에는 모두 필요하다:

1. 파일/계약 hash·source identity 일치, 새 run/marker/unit 소유권, 정확한 owner5GiB와 독립 target512MiB readback.
2. 실제 held PID1 owner O와4개 최종 sealed RO hash/identity FD 인계,5경로 정책·별칭·RO mount 확인 후 K.
3. target placement P·initial maps/FDs/listener ACK·one-shot exec·독립 감사 A가 끝나기 전 GO 없음.
4. 고정 입력 승인 전달과100 fixture sequence, 정상 thread/fork task trace, GO 전/EXIT_ACK 전 동일 sealed mapping.
5. EXIT_ACK 이후 worker의 alias 전달·callback join, 모든 task 정상 사망·ECHILD·COMPLETE·독립 audit EOF,
   stdout/stderr EOF, target exit·target unit/cgroup 제거·integrity, collector pins release가 끝난 뒤 V.
6. native worker와 그 parent의 실제 wait exit0, collector exit0, owner unit/cgroup 제거, residual0,
   host/collector 두 결과 모두 PASS_SMALL_HARMLESS_PATH_ONLY.

누락·부정 FD/hash/별칭·권한/namespace/cgroup 실패·거부1건·sequence loss·동시 mutation 충돌·로그 쓰기 실패·
단절·overflow·deadline/OOM·종료/callback/EOF/exit/정리 증거 누락은 FAIL이다. 실패 뒤 GO/ACK/V를 새로 보내지 않는다.
단절 후에도 원래 감사·stream 수집 실패가 성공으로 바뀌지 않는다. 필요 시 소유 invocation이 확인된 unit만 stop하고
직접 생성한 unreaped client/native parent만 bounded wait/terminate/kill한다. 다른 unit·기존 PID를 건드리지 않는다.
영수증 누락·invocation 변경이면 cleanup UNKNOWN/FAIL이며 자동 복구·재시도·한도 상향은 없다.

## 후속 검증 분리

이1회가 통과해도 v9의 큰5개/303객체/468경로 실제 봉인·RO 전달과 cold-cache/최대 peak,
실제 Gazebo/DART 초기화·정상 loader/pthread 전체 정책·물리 동작은 증명하지 않는다.
이들은 각각 별도 계약·승인·시험이다. Stage B나 실제 launcher는 이 시험 결과로 열지 않는다.
현재 승인 대기이며 실제 userns/pidfd/SCM/ptrace/mount/AttachProcessesToUnit/LSM/EOF·cleanup 동작은 모두 미검증이다.
