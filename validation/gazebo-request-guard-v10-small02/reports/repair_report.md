# v10 small-01 실패 분석 및 small-02 비실행 수정 보고서

관측: 2026-11-10T11:42:44.378119+00:00; host jiwon-System-Product-Name. 시작/현재 작업 기준 HEAD
`5c6710d69cb1191b9d4a0e4cdba9d78dd7596129`, branch `experiment/dart-internal-trace`.
초기 tracked clean, 기존 untracked `libgz-physics-dartsim-plugin.so` 보존. 이번 작업은 별도
`validation/gazebo-request-guard-v10-small02/`와 handoff만 변경한다. 기존 v10 파일은 수정하지 않았다.

## 관측과 최초 단절 위치의 범위

- 원본 `../gazebo-request-guard-v10/work/runtime-small-01/`의 host/collector/target 영수증,
  host.stderr, 감사·journal·raw 파일을 읽고 기존 verification의 해시와 대조했다.
- 기존 user journal을 해당 두 unit·20:24~20:27 KST로 한정해 조회했다. service start20:25:51.585983,
  target anchor start51.694246, target stop51.748159, collector main exit78 at51.806779.
  전사 경로 `work/existing-unit-journal.txt`, SHA256 `f06981455b416628869972446a48acc72b13cb9c09a758245c82bcf63e851a13`.
  이는 기존 실행의 manager lifecycle 기록이며 native 단계의 성공 증거가 아니다.
- collector의 Popen은 native parent를 만들었고 최종 wait returncode78을 기록했다. loader/main
  진입 성공 여부·PID·개별 syscall 진단은 보존되지 않았다. service 자체 미시작 가설은 반증되나
  native main의 어느 검사가 성공했는지는 확정 불가다.
- `collector.py:receive()`는 O/C/P/audit 수신에 같은 `owner handoff disconnect`를 쓴다.
  그러므로 이 문자열만으로 최초 O 이전 실패라고 단정할 수 없다.
- 다만 CATALOG_OBJECT는 첫 FD 검증 직후, C ACK 이전에 collector-audit.jsonl에 동기 기록된다.
  해당 파일이0바이트이므로 **최초 durable CATALOG_OBJECT 이전**으로 범위를 좁힐 수 있다.
  O 자체는 그 파일에 기록되지 않아 O 성공/실패는 미확정이다. 완전 K, P, control_arm, 독립 audit
  initialization/ACK, GO에 도달했다는 주장은 근거가 없으며 기존 순서상 정상 완료는 배제된다.

|소스 순서|실패 가능성과 확인 수준|
|---|---|
|native entry: argv/FD 검사 → control CLOEXEC 복구 → FD bridge|가능, 미확정. 원래 native stderr는 DEVNULL, entry 실패는 journal을 쓰지 않는다.|
|preparation domain → control FD/layout → catalog prepare|가능, 미확정. 최초 O 전 사전 검사들; 개별 결과/errno 증거 없음.|
|userns/maps → namespace/mount-private → fork/ready/SIGSTOP → O send/ACK/resume|가능, 미확정. 5초 timeout보다 짧은 전체 service220ms는 deadline 원인의 근거가 되지 않는다. 즉시 실패는 가능.|
|PID1 resume → proc/tmp/private root/catalog mounts → 첫 C|가능, 미확정. O가 성공했어도 이 구간에서 끊기면 같은 빈 audit/HUP가 남는다.|
|C×4/K → held placement P → control_arm/PREEXEC journal → audit handoff/A → GO|정상 통과 증거 없음. 첫 durable C도 없으므로 이 후반 구간을 최초 정상 진행 구간으로 주장할 수 없다.|

FD source copy/dup2/close 순서와 parent/worker 종료도 읽었다. bridge는 source를 high slot에
복제한 뒤0..4를 교체하며 원본 high source와 temporary만 닫는다. 성공한 bootstrap parent는
O ACK 뒤 collector/journal과0..4를 닫지만 worker는 fork 상속 복사본을 보유한다.
현재 증거로 잘못된 close 또는 FD 재사용을 확정할 수 없어 bridge/ACK/namespace 허용 정책은 수정하지 않았다.
POLLHUP 시 queued frame을 배수하지 않는 기존 fail-closed 동작도 그대로다.

host의 `unit ownership not proven`은 별도 관측이다. 기존 host는 첫 실패와 cleanup 실패를
같은 reason에 덮어쓰므로 이것이 최초 원인이었는지, unit 소멸 시 관측인지 알 수 없다.
불완전 ownership readback, native early refusal, post-O mount refusal은 모두 가설이다.

## 확인된 결함과 수정

1. **초기 관측 공백**: native parent stdout/stderr DEVNULL, 초기 bootstrap은 감사 전 silent78,
   collector 초기 감사 open 전에 durable stage가 없다. 별도 trusted host/collector startup JSONL과
   private native-parent.stderr를 추가했다. native entry/FD bridge/domain/catalog/userns/ready/O/ACK/
   worker mount/run 및 parent wait를 단계·result·errno_snapshot으로 기록한다. errno_snapshot은
   syscall이 아닌 복합 guard에서 stale일 수 있으며 원인 확정값으로 쓰지 않는다.
2. **host 로그 권한**: Path.open('xb')는 생성 모드0666을 요청했고 실제0664가 관측됐다. 이는 effective mask002와
   일치하지만 당시 정확한 umask/ACL은 보존되지 않아 그 값 자체는 미확정이다.
   새 log는 `os.open(O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600)`으로 처음부터 만든다.
   원본 host stdout/stderr는 여전히0664다. 새 native log는 append-only다.
3. **원인 덮어쓰기**: host/collector 첫 reason과 cleanup_errors를 분리하고 service client 종료코드,
   native parent PID/start/host·최종 returncode를 기록한다. host property 변화도 ownership 검사 전에
   기록해 다음에 transient/readback 실패와 native 자체 실패를 구분한다. ownership 요구는 완화하지 않았다.

startup 진단은 기존 독립 감사의 대체물이 아니다. source/ELF 고정, O/C/K/P/A, sealed FD/mount,
thread/fork, EXIT_ACK/callback, task death/COMPLETE/EOF/cleanup/V 검증은 유지된다.
startup 기록 생성/동기화/누락/순서/권한/프레이밍/종료 기록이 잘못되면 FAIL.
pre-V에는 그 시점까지 필요한 native 진단도 검사하며, parent wait·terminal 진단은 V 이후 확인한다.
각 새 진단 파일 cap16KiB, C 레코드192byte 미만·parent/worker 각각최대32개로 bounded.
진단 FD는 high CLOEXEC이고 target child close_range(7..)/exec에서 제거된다.
기존 빈 native 감사 journal에 진단을 섞지 않아 st_size==0 사전조건을 보존한다.

## 빌드와 비실행 검증

- 새 immutable build 경로의 launch.c와 owner_main.c **2 TU만** cc compile/link; rc0.
- probe/catalog/metadata/control/broker/bound/loader/namespace **8 객체**의 실제 hash와 기존 dependency를
  검사해 재사용했다. 기존 probe ELF와 unit-anchor 재사용. 새 ELF/readelf 결과는 로컬 work에 보존.
- readelf로 probe libc-only 및 Gazebo/DART/sdformat NEEDED 부재 확인. native owner에는 기존 libcrypto/libc가 있다.
- **2194 PASS_STATIC_PYTHON_MOCK_ONLY**: 기존 controller/Owner.bind/Catalog/coordinator 실제 Python 흐름을
  OS/manager/transport mock으로 검사했다. 정상 O/C×4/K/P/A/GO/EXIT_ACK/V, 첫 O 대기 HUP,
  missing startup writer, audit first/second open 실패, startup open/write/sync/close 실패, terminal 진단 누락,
  실패 reason 보존, FD pin 정리, sequence/death/EOF 누락과0600/O_EXCL/NOFOLLOW를 포함한다.
- ordinary temporary diagnostic 파일에서 umask0 하 생성 직후 mode0600·CLOEXEC을 확인했다.
  이는 native/서비스 시험이 아니다. C 진단은 컴파일과 source ordering/bound/static 검증만 받았다.
- 준비 과정 첫 Python -I build/test 호출에서 import path 오류가 있었고 entry import 경로만 수정했다.
  native 실행이나 서비스 실패가 아니다. 이후 최종 compiler2TU/link 및 Python suite는 통과했다.
- 실제 native 실행0 / 서비스 시작0 / marker 소비0 / 준비 객체0 / 전달 경로0 / physics step0.
  커널 userns/SCM/pidfd/ptrace/mount/실제 exit·cleanup 정상 경로는 여전히 미검증이다.

원본 v10 **202 파일** content/mode와 main nonignored **303 경로** content/mode·symlink가
이번 시작 snapshot과 일치한다. 별도 기존1617파일 preservation 검사도 통과했다.
기존 v10 계약의116 hash도 계속 일치한다. main ignored evidence 전체는 새로 inventory하지 않았으며
main에는 쓰기를 수행하지 않았다. `reports/preservation.json` 참조.
small01/02 네 unit 모두 not-found/MainPID0/ControlGroup empty. 새 marker/output은 아직 없다.

## 변경 소스 SHA256 (기존 v10 대비)

|경로|SHA256|
|---|---|
|`inputs/launch.c`|`4d899aaefe4bfc5149987dde7d54ad7881113c77c78f9a9a17c1b9878be6a5d3`|
|`inputs/launch.h`|`d63995b053d2253239eb11b44efff1781770e124a7be512bdfd84b33b8b0699d`|
|`inputs/owner_main.c`|`d09a9544017cf591e187e31ebe3ab032480302e477043efd2101e80c394e26f3`|
|`scripts/build.py`|`59f35eb7da0d8e42c452350d34f277b976091ee411f5bd5a7326d0d591fd4de1`|
|`scripts/collector.py`|`55070d18a6f32253ee0d3bcd37d71a8026c50c09f584f2561eeb7a1b9ce4fbcb`|
|`scripts/diagnostics.py`|`658972be8fe37fa5be985788157ce9b30bbfdf6a3f073ec9b5681227394e0d70`|
|`scripts/driver.py`|`9ab3243b1d7b291969f3b852bd72acc8f9bd07206d5a6730f50ef1536c4fbae6`|
|`scripts/seal.py`|`61fc476f42557391553b3dce6bc505b333b89dfc32cfd72cc2dd31368820f3d0`|
|`tests/check.py`|`e53bd6bf972c0b7f419e462e0842fede921da2233892e515329269703f7db5ac`|
|`tests/integration.py`|`9914db4ca1186f76569a30ed23853aedd86aa2160fd93b5bb95d27c5e26f8127`|
|`tests/startup_mocks.py`|`050580a4cb26ae39ecb32db0cb9556352c24d06a2518ee54fda4920e8297dbeb`|

## 실행 관련 ELF SHA256

|절대 경로|bytes|SHA256|
|---|---:|---|
|`/tmp/AeroAIStudio-dart-internal-trace/validation/gazebo-request-guard-v10-small02/work/build-20261110T113607518430Z/owner`|84976|`6d89536cb9a245f4d82fb4341cbbb050db9a29ea52c6aaf727306ff57c127877`|
|`/tmp/AeroAIStudio-dart-internal-trace/validation/gazebo-request-guard-v10/work/build-20261110T094935823777Z/probe`|17192|`a82ea926913bc266bf55a4a010f346fe85a3a3ded86e0d20bc8566bc2cbf02f1`|
|`/tmp/AeroAIStudio-dart-internal-trace/validation/gazebo-request-guard-v8/work/unit-anchor`|16016|`945f6debaf75b0165a582bc1758c5baf5c6bf0f420d5a2c3f67bf294d585fa4d`|

전체 source 고정값: reports/source_manifest.json; compiler/input/object hash와 build argv·PID/start·종료:
reports/build_receipt.json; 개별 검사: reports/tests.json. 위 소스와 산출물은 계약 files로 고정했다.

## 새 승인안과 중단점

reports/approval_proposal.md의 small02 **별도1회 제안**은 아직 승인되지 않았다.
contract SHA256 `ab2a778dbcd1e5f6a8923e6ff8270070c7ee5c944caf0017dd9d43043621ef95`.
큰5개/303객체/468경로 준비·전달, maximum-memory, 실제 DART/Gazebo/harness, physics,
sudo/install/system 변경과 cap 상향은 제외한다. 기존 small01 재시도·marker 재사용 금지.
원래 launcher exit78을 hash/source로 보존했고 재실행하지 않았다.
**Stage B BLOCKED / 위험 수용 미결정 / Gazebo 런타임 미검증**.
다음 최소 행동은 새 계약 해시·게시 commit에 대한 별도 승인 대기다. 이 작업에서는 실행하지 않는다.
로컬 /tmp ignored 바이너리·원본 raw 증거·marker는 Git 게시만으로 다른 기기에 전달되거나 영구 보관되지 않는다.
