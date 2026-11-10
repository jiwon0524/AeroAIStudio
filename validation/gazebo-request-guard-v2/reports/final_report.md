# Request guard v2 — PARTIAL / NOT DEPLOYABLE

시작 HEAD `10de7c47151601e32704d005b8b2d0887a3c452c`, 브랜치
`experiment/dart-internal-trace`. 구현·분리 빌드·정적/Python 모의 검사만 수행했다.
**Stage B BLOCKED / 위험 수용 UNDECIDED / 실제 런타임 UNVERIFIED.**
정상 DART 초기화를 지원하는 차단 경계는 아직 완성되지 않았다.

## 구성요소별 상태

|구성요소|이번 구현과 확인|남은 차단 조건|
|---|---|---|
|정상 입력 broker|봉인 계약의 594 경로/429 원본을 device/inode/SHA-256/ELF 여부와 연결. 동일 FD 검증, 원본 inode 불변성 요구, open/openat 복사 인자에 대한 읽기 전용 ADDFD+SEND 후보 compile/link|현재 594 경로 모두 불변성 증명 불가로 거부. 실제 안전한 정상 입력 제공은 0. 기존 계약 inode를 바꾸는 memfd 복사는 허용하지 않음|
|스레드·자손|v1 supervisor/journal 재사용. 최대64 task, clone/fork/vfork eventmsg 연결, newborn stop 선후 역전 보류, `__WALL` terminal wait/ECHILD, root 종료 후 자손 수집, 30초 제한 후보 compile/link|필터는 clone/fork/vfork를 계속 거부. 일반 pthread syscall/파일 매핑 지원과 task/filter 적용 증명 없음. 정상 thread 지원 완료 아님|
|로더 이전 적용|NO_NEW_PRIVS+NEW_LISTENER filter 설치 함수, native/x32 ABI 분기, exec-event에서 시작하는 기존 전제 유지|신뢰 launch stub, listener 외부 전달·대상 FD 제거·최초 exec 허용과 preexec EXITKILL 설정/증명이 연결되지 않음. 현재 필터는 exec도 거부하므로 설치 함수를 실행 계약에 연결하면 부트스트랩 불가|
|신뢰 감사 통합|C tree/broker가 v1 동기 journal writer 공유. numeric journal→기존 AuditGate 변환, 요청/task 상태와 카운터·EOF 검증, 원래 NativeSession 모의 프로토콜 연결|실제 격리된 supervisor/collector FD 소유권 증명 및 live drain/최종 수집 transport 미구현. Python proof 사전/`authenticated=True`는 인증 아님|

위 차단은 모두 **남은 구현·통합 조건**이다. 단순 실행 재확인만 하면 해결된다고
분류하지 않는다. 어떤 새 후보도 배치·재봉인하지 않았다. 기존 manifest와 launch
경로 그대로이며 새 Python/native entry도 서비스·marker 생성 전에 무조건78이다.

## 입력·인자 변경과 파일 제공

`scripts/catalog.py`는 manifest canonical SHA-256와 validator source를 먼저 확인하고
원래 `contract.validate`를 읽기 전용으로 호출한다. `input_mapping.json`에 원래
mount alias와 원본 identity/hash를 기록했다. fd pin은 O_RDONLY/CLOEXEC/NOFOLLOW,
regular file, 원본 device/inode/hash와 **해시 읽기 전후 fs-verity** 증명을 요구한다.
권한·RO mount·RO FD·해시 snapshot만으로 내용 불변성을 주장하지 않는다. 이 호스트의
429 원본에서 이 증명을 얻지 못해 594 alias 전부 거부했다. fs-verity를 켜거나 파일,
패키지, 시스템 설정을 변경하지 않았다. 이는 가능한 모든 안전한 구현 방식이
불가능하다는 결론이 아니라, **이 후보가 요구한 충분조건이 현재 충족되지 않음**이다.

`inputs/broker.c`는 target 문자열을 제한된 길이로 복사하여 카탈로그와 비교한다.
검사 후 원래 open syscall을 CONTINUE하지 않는다. 다른 스레드가 문자열/포인터를
바꾸어도 제공 가능한 것은 복사된 이름에 해당하는 카탈로그 FD뿐이다. open/openat
scalar flags는 notification snapshot에서 취하며 쓰기/생성/잘라내기/O_PATH/openat2,
상대경로, 알 수 없는 이름, 검증 불가 FD는 거부한다. 절대경로의 dirfd는 권한으로
사용하지 않는다. 경로 probing/stat/access, mmap/read/close 등 미구현 요청도 거부하므로
**파일 FD 제공 primitive와 정상 로더 지원을 동일시하지 않는다.**

원본을 대상이 다시 열지 않는다. supervisor의 고정 FD를 `/proc/self/fd/N`으로
독립 open description으로 열어 identity/접근모드/fs-verity를 재검사한다. dup로
동시 open의 offset을 공유하지 않는다. 이 supervisor proc view와 FD table이 신뢰
영역에 있다는 증명은 launch integration 차단 조건이다. ADDFD_FLAG_SEND로 FD 설치와
응답을 묶고 O_CLOEXEC 요청을 유지한다. ADDFD의 ENOENT는 취소로 기록해 실패시킨다.
EINTR 등 결과 불확실 오류에서는 재시도·별도 add/send·CONTINUE로 완화하지 않는다.
실제 kernel의 ADDFD/LSM/FD limit/취소 race 동작은 실행하지 않아 미검증이다.

## 전체 수명과 감사

`inputs/tree.c`는 v1 `guard.c`를 include해 기존 journal와 restrictive monitor를
보존하며 별도 task loop를 추가했다. 정상적인 terminal wait만 TASK_DEAD로 기록한다.
EXIT_STOP이나 root death, EXIT_ACK는 수집 완료가 아니다. task0+root terminal+ECHILD
후에만 ALL_DEAD/COMPLETE를 기록한다. broker 요청은 한 event loop에서 순서대로
처리하고 fdatasync 완료 후에만 응답한다. 대기 중 취소/종료, 비정상 종료와 거부는
최종 실패로 연결된다. 추적 불가 stop, task overflow, channel HUP/error, syscall/저장
실패는 성공 receipt 없이78이다. task 생성 전 옵션 적용과 listener 폐쇄 시
EXITKILL/외부 owner 종료 절차는 아직 통합되지 않았다.

notification 수신의 poll/RECV race, process_vm_readv 권한·PID 재사용, ptrace task stop
순서, supervisor 단절 시 kernel 동작, deadline 중 blocked ioctl, 최종 native journal
EOF와 protocol 양쪽 EOF의 실제 병행 drain은 실행 증거가 없다. 함수 timeout이 kernel
내 blocked ioctl까지 중단한다고 주장하지 않는다. 실행 경계로 배치할 수 없다.

`scripts/journal.py`는 순번·native denial 누적값·task 부모·pending 요청 상태·완료·EOF를
검사해 기존 `AuditGate`로 전달한다. DENY와 CANCELLED는 실패하되 감사 수집은 계속한다.
누락/재전송/잘못된 상태/조기 EOF/overflow/저장 실패/종료 증거 누락은 실패다.
TASK_DEAD에 pending이나 비정상 wait status가 있어도 실패시킨다. private regular
journal FD reader는 **종료 후 offline ingestion 후보**이며, live regular file의
일시적인 끝을 실제 EOF로 인증하는 collector가 아니다. trusted launch proof가 없으면
GO를 거부한다. 현재는 그 proof의 실제 생산자가 없고 release launcher가 항상 거부한다.

## 빌드·정적·모의 증거

- `scripts/build.py`: broker/tree/refusal-entry 3개 TU만 별도 `work/`에 compile/link.
  v1 C source를 재사용했으며 기존 바이너리·bridge·DART·Physics·Sim·harness 재빌드 없음.
  Werror/PIE/RELRO/NOW/stack protector. ELF는 libc만 필요. readelf/objdump 검사만 수행.
  새 ELF 실행·dlopen 없음. 소스/헤더/오브젝트/ELF/compiler 해시와 compiler PID/start는
  `build_receipt.json`. 초기 tree 빌드는 ioctl 헤더 누락으로 실패했고 include 수정 뒤
  최종 3개 TU warning-as-error 빌드가 통과했다.
- `tests/check.py`: **70개 static/Python mock PASS**, `tests.json`. 정상 journal,
  interleaved task 요청, root보다 늦은 자손 종료, 취소/pending 종료, ACK 뒤 거부,
  불변성 증명 없는 RO 파일 거부, 경로 교체 후 열린 inode 유지, 잘못된 순번/상태,
  overflow/조기 EOF/저장 실패/최종 종료 증거 누락을 검사했다.
- 원래 봉인 source loader와 packet/setup/ready factory를 그대로 재사용하여
  GO→합성100×1ms→마지막 live mapping→EXIT_ACK→양쪽 EOF/exit/cleanup/integrity에
  journal adapter를 연결했다. ACK 뒤 native journal 거부는 최종 실패다.
  기존 EOF/cleanup/integrity/last mapping 실패 판정도 유지했다. 물리 sample이나
  실제 syscall trace가 아니며 C broker/thread loop를 실행한 검사가 아니다.
- `work/preservation.json` baseline의 기존 tracked/main dirty 파일과 main HEAD/status,
  dangling symlink device/inode/target을 보존 검사했다. 최초 handoff 갱신 전 전체 보존을 확인했고, 최종 재검사는 의도된 worktree handoff만 제외했다.
  이전 v1의84개/이전 단계 결과는 재실행하지 않았고 신규70개에 합산하지 않았다.

허용 재현: `python3 validation/gazebo-request-guard-v2/scripts/catalog.py`, `scripts/build.py`,
`tests/check.py`(각각 같은 phase 경로). 보존 검사는 이 단계의 의도된 worktree handoff만 제외하며 그 diff는 따로 검토한다. native ELF 실행 명령은 제공·실행하지 않았다.

## 다음 최소 작업

1. 원본 inode/해시 판정을 유지하면서 내용 불변성을 입증하는 별도 설계를 정하거나,
   새 입력 identity 계약 변경을 명시 검토해야 한다. 이번에는 원본을 복사·수정·재봉인하지 않았다.
2. trusted preexec launch/listener handoff, inherited FD/namespace/정책 증명과 정상 loader
   read/stat/mmap/close/thread syscall 정책을 구현해야 한다. 현재 mock proof로 대신할 수 없다.
3. 전체 collector에 supervisor private live channel/drain/death/EOF/cleanup을 연결하고
   신뢰 경계를 확인한 뒤 별도 실행 계약 검토가 필요하다. 그 전 GO/후보 배치 금지.

실제 DART/Gazebo 로딩, harness·무해/native guard 실행, 서비스, step, marker 생성·소비,
sudo, 설치·시스템 변경, 원 main 편집, 기존 작업 종료·재시작 없음. 새 경량 코드/검사/
보고서/인계만 실험 브랜치에 게시한다. `work/`의 ELF/로그/보존 baseline과 기존 ignored
증거·marker는 Git으로 전달되지 않고 `/tmp` 원본은 영구 보관이 아니다.

설계 참조: [kernel seccomp](https://docs.kernel.org/userspace-api/seccomp_filter.html),
[notification API와 TOCTOU/ADDFD](https://man7.org/linux/man-pages/man2/seccomp_unotify.2.html),
[ptrace task/exec/exit stop](https://man7.org/linux/man-pages/man2/ptrace.2.html),
[fs-verity](https://www.kernel.org/doc/html/latest/filesystems/fsverity.html).
