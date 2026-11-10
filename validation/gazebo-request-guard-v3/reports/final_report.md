# Sealed-copy request guard v3 — PARTIAL / NOT DEPLOYABLE

시작 HEAD `b54c3f6dc36bc70a96533f104fe253be8609371e`, 브랜치
`experiment/dart-internal-trace`. 최초 상태는 tracked/index clean 및 기존 dangling
plugin symlink만 untracked였다. context-handoff와 AGENTS/DEVELOPMENT_RULES/handoff,
v2 최종 보고서, 기존 봉인 contract/manifest/attestor/mapped/native identity 검사를 읽었다.

**Stage B BLOCKED / 위험 수용 UNDECIDED / 실제 대상 런타임 UNVERIFIED.**
서비스·marker 이전78 유지. 기존 실행 계약 변경·재봉인·후보 배치 없음.

## 네 구성요소의 판정

|항목|이번에 확인한 사실|판정·남은 일|
|---|---|---|
|입력 사본 계약|429개 원본 객체/594 aliases 중424개 객체/578 aliases의 사본을 생성·seal·읽기 전용 재개방하고 **seal 이후 실제 바이트** SHA-256을 원래 계약과 대조했다. 별칭은 동일 객체 사용. 사본은 검증 후 모두 닫음|제한된 사본 바이트 불변성은 확인. 5객체/16aliases는 준비 메모리 한도로 차단. 기존 identity/경로와 실제 target 전달은 미해결. target 허용0/594|
|정상 로더·스레드 정책|봉인 사본의 PT_INTERP3개와 기존1793 SONAME edge를 정적 대조. thread/task loop는 v2 재사용. 파일·메타데이터·매핑·thread syscall 요청별 차단표 추가|initial exec가 최초 확정 차단점. 실제 로더 첫 syscall UNKNOWN. read/stat/mmap/clone 등 정상 경로는 아직 구현·통합 차단이며 default deny|
|pre-exec 연결|private journal/copy/namespace/FD/EXITKILL/filter/listener/one-shot exec 순서를 명시하고 누락별 모의 거부 검사|설치 함수와 신뢰 launch owner/listener 전달·제거/최초 exec 단발 제어가 연결되지 않음. bool 사전은 증거 아님. 완전한 mock도 실행 승인 불가|
|독립 감사 통합|v1 journal/AuditGate 및 v2 task loop/JournalAdapter 그대로 재사용. 동시 요청·취소·남은 자손·단절·종료 중 위반과 기존 GO/마지막 mapping/ACK/EOF/cleanup 모의 검사|실제 private live channel 소유권, Python→C 고정 FD catalog 전달, 병행 drain/최종 EOF/단절 시 종료 소유권 통합 미구현|

위 미완료는 runtime-only 재확인 항목과 구분되는 **남은 구현·통합 작업**이다.

## 사본 생성과 바이트 보장

`scripts/snapshots.py`는 v2 catalog의 봉인 계약 reader를 재사용한다. 원래 manifest
SHA-256과 validator를 확인하고 기존 `contract.validate`를 읽기 전용 실행한다.
객체 그룹은 원본 device/inode 기준이며 같은 inode에 서로 다른 해시가 지정되면 거부한다.
해시만 같은 별도 원본 inode를 임의로 합치지 않는다. 같은 객체의 ELF alias가 하나라도
있으면 해당 사본에 명시적인 executable intent를 적용한다.

원본 FD를 O_RDONLY/CLOEXEC/NOFOLLOW로 열고 기존 동일-FD device/inode/hash 검사 전후에
유한 길이로 사본을 쓴다. 새로운 memfd에만 mode를 설정하며 원본 권한은 변경하지 않는다.
ELF는 MFD_EXEC, 데이터는 MFD_NOEXEC_SEAL을 명시한다. 기능 미지원 시 기본 memfd로
fallback하지 않는다. WRITE/GROW/SHRINK/SEAL/EXEC seal을 붙인 후 supervisor proc FD를
O_RDONLY로 열고 같은 객체인지 검사하며 writable FD를 닫는다. **최종 sealed FD를
다시 해시**하여 원래 계약 SHA-256과 대조한다. inode·size·mode·seal도 검사한다.
F_SEAL_FUTURE_WRITE만으로 대체하지 않는다. shared writable mapping은 만들지 않았다.

입력 준비에서 실제 수행한 작업은 memfd 생성·복사·seal·stat·read/hash뿐이다.
native 실행·dlopen·실행 가능한 mmap·exec·target 생성·filter 설치는 수행하지 않았다.
MFD_EXEC/seal 성공은 대상 namespace/LSM에서 executable mapping이나 실행이 가능하다는
증거가 아니다. 입력 준비 사실과 대상 runtime 미검증을 혼동하지 않는다.

`reports/copy_contract.json`에424개 사본의 원본/사본 identity, hash, seal, alias,
명시적 exec intent와 검증 당시 FD link를 기록했다. 이 JSON은 **실행 계약이 아니다**.
준비 과정은 한 객체씩 검증 후 닫았으므로 지금 재사용할 수 있는 객체·FD 번호가 없다.
향후 사용은 같은 preparer의 살아 있는 FD를 소유권 증명과 함께 전달하고 재검증해야 한다.
receipt의 inode나 해시만으로 새 객체를 승인하지 않는다.

전체 원본 크기 합은2,158,870,244 bytes다. 준비 과정은 동시 메모리 증가를 피하기 위해
객체당64MiB의 새 보수적 한도를 사용했다. 5개 초과 객체는 DART3개 원본, dartsim1개,
Sim core1개이며16개 alias다. 이는 kernel 기능 실패가 아니라 **이 준비 도구의
자원 admission 차단**이다. 큰 사본의 생성과 전체 set 유지/외부 supervisor 메모리
accounting은 해결하지 않았다. 기존 MemoryMax/AS/rlimit 등 실행 제한을 늘리지 않았다.

## 대상이 사용할 객체·경로와의 일치

`inputs/broker.c`는 v2의 pointer snapshot→FD 전달 방식을 유지하면서 새 사본의
device/inode, READONLY, WRITE/GROW/SHRINK/SEAL/EXEC 및 실행 mode를 검사한다.
별도 `delivery_ready`가 없으면 해시 검증 사본이어도 거부한다. 현재 이 조건을
실제로 증명하는 producer가 없으며 전달 허용 catalog를 만들지 않았다.
ADDFD_FLAG_SEND, 독립 open description, 취소·불확실 오류 시 실패와 CONTINUE 금지를 유지한다.
검사한 원래 target pathname을 다시 열도록 허용하지 않는다.

바이트와 객체 identity는 분리해야 한다. 현재 사본은 원본과 다른 inode다.
기존 mount attestor, ELF/native.expected, compiled plugin expectation, engine/provider/
detector fingerprint는 원래 identity를 요구한다. 복사 바이트는 같으므로 SHA allowlist와
Build ID 내용은 유지되지만 이 사실로 inode 판정을 통과시키지 않는다.
기존 native resource 코드는 FD hash와 device/inode를 함께 검사하며 일부 expectation은
바이너리에 들어 있다. 단순 JSON 교체만으로 새 identity 계약을 완성할 수 없다.

직접 전달한 memfd의 FD link는 `/memfd:aero-input-… (deleted)`다. 기존 mapped.py는
deleted 이름과 지정되지 않은 canonical pathname을 거부한다. 해당 거부를 모의로
재확인했고 기준을 완화하지 않았다. sealed inode를 기존 namespace의 동일 논리 경로로
bind하고, 대상의 open/stat/maps/map_files/proc-root와 broker가 모두 **그 객체**를
참조하도록 할 수 있는지는 아직 확인되지 않았다. bind mount/namespace를 실행하여
검사하지 않았다. 따라서 현재 원래 계약과 호환된다고 판정한 입력은0개다.

## 로더·thread와 실행 전 경계

sealed ELF FD의 제한된 ELF64 little-endian x86-64 program header만 읽었다.
PT_INTERP는 harness/bridge/libc에서 `/lib64/ld-linux-x86-64.so.2`이며 기존 계약의
명시 symlink를 적용한 `/usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2`가 mount 목록에 있다.
1793 SONAME edge의 provider/mount 연결도 모두 기존 계약에 있다. 이는 정적 closure
근거이며 실제 loader open/probe/metadata syscall trace가 아니다. 캐시·상대경로·디렉터리
검색·ENOENT로 처리할 optional lookup을 임의로 허용하지 않는다.

`scripts/policy.py`는 **offline 계획 검사**다. 검증된 사본+동일 logical path+별도
canonical delivery 증거가 있는 read-only open만 FD 전달 계획으로 분류한다.
현재실행 permit API가 아니다. metadata/newfstatat/statx/access/readlink는 output 구조/
pointer와 관측 객체를 안전하게 emulate하는 코드가 없고, read/pread/lseek/close는 target
FD ledger와 수명 연결이 없다. mmap/mprotect는 실제 객체·권한·경로 증명이 없다.
이 항목은 안전한 정상 요청일 가능성이 있어도 **미구현 차단**으로 남겼다.
쓰기·생성·잘라내기/O_PATH, 알 수 없는 alias/request는 정책상 거부로 구분했다.

clone/clone3/fork/vfork/futex/rseq/robust-list도 정상 pthread 지원이 검증되지 않아 거부한다.
kernel filter 상속은 생성을 안전하게 허용한 경우의 구조적 성질일 뿐, 현재 정상 thread
지원의 증거가 아니다. v2 최대64task/EXITKILL/TRACE*와 root 이후 자손 수집을 재사용했지만
task 추적만 존재한다고 filter 적용·정상 생성 경로 완료를 주장하지 않는다.

현재 install 함수 다음 최초 exec 자체가 USER_NOTIF→거부되므로 이것이 최초 확정 차단이다.
listener를 전달하기 위한 syscall도 필터에 막힐 수 있다. 신뢰 stub에서 channel 준비,
filter 설치 후 external listener 획득, target listener 제거, exec FD 단발 승인과 그 후
재exec 차단을 함께 설계해야 한다. 고정 FD 번호만 허용하면 close/reuse나 이후 exec로
우회될 수 있으므로 그런 완화를 추가하지 않았다. 실제 첫 loader syscall은 UNKNOWN이다.

## 빌드·비실행 검사와 보존

- broker/tree/refusal entry3 TU만 별도 `work/` compile/link. tree는 v2 source, journal과
  restrictive monitor는 v1 source를 include해 재사용했다. libc-only ELF를 readelf/objdump로
  검사했고 PIE/RELRO/NOW/stack protector/Werror를 유지했다. 기존 DART/Sim/Physics/harness
  재빌드·실행 없음. source/header/object/compiler/ELF 해시와 compiler PID/start는
  `build_receipt.json`. 최초 tree wrapper 빌드에서 feature macro 순서 오류가 났고
  `_GNU_SOURCE`를 첫 include 전으로 옮긴 뒤 통과했다. 최초 로그는
  `work/tree.initial-failure.log`로 보존했다.
- 신규 **101개 static/Python mock PASS**, `tests.json`. 변경된 원본(복사 전/중), 잘못 쓴
  사본, seal 누락/기능 미지원, final sealed hash 순서, object/mode 치환, 잘못된 alias,
  같은 inode 충돌, ELF metadata, 정상 loader 요청 계획과 미확인 경로 거부를 검사했다.
  사본 함수 검사는 FakeIO로 수행했으며 실제 입력 준비 결과와 구분했다.
- 기존 AuditGate/JournalAdapter/봉인 NativeSession factory를 그대로 재사용해 동시 요청,
  취소/남은 자손/단절/누락/overflow/종료 중 거부를 검사했다. 합성100sample·GO·마지막
  live mapping·EXIT_ACK·양쪽 EOF·exit·cleanup/integrity 판정 유지. 실제 모의 ACK 이후
  거부는 최종 실패였다. 과거84/70 결과를 재실행하거나101개에 합산하지 않았다.
- `work/preservation.json`의 기존 tracked/main dirty 파일과 main HEAD/status, symlink
  device/inode/target을 확인했다. 이 단계의 의도된 worktree handoff만 최종 비교에서
  제외하고 diff를 검토한다. 기존 seal/manifests/보고서/산출물/marker는 변경하지 않았다.

## 다음 최소 작업과 실행에서만 확인할 사항

다음 구현은 새 immutable object의 canonical 경로·native/collector identity 계약,
큰 입력과 전체 set의 FD/메모리 수명·accounting, 동일 객체를 namespace와 broker 양쪽에
전달하는 bridge다. 이후 metadata/read/mapping/thread 정책과 trusted preexec handoff,
독립 live collector를 연결해야 한다. 기존 실행 계약은 그 전까지 그대로 차단한다.

실제 실행에서만 확인할 항목은 대상 namespace의 memfd execute/LSM/noexec, canonical
bind-mount와 maps 표시, 실 loader syscall 순서와 optional lookup, ADDFD 취소 race,
thread/자손 filter+ptrace 상속, supervisor 단절 시 강제 종료, ioctl timeout과
독립 audit 최종 EOF/cleanup 병행 수집이다. 이번에는 어느 것도 실행하지 않았다.

허용 재현은 이 phase의 `scripts/snapshots.py`(입력 준비만), `scripts/policy.py`,
`scripts/build.py`(컴파일·ELF 정적 검사만), `tests/check.py`(static/Python mocks)다.
native binary 실행·로드 명령은 사용하지 않았다. 원 main/미커밋 변경 보존, 서비스·
물리 step·marker 소비/생성·sudo·설치·시스템 변경·계정/기존 작업 종료·재시작 없음.
원시 build/보존 증거는 ignored work/에 남아 Git으로 전달되지 않으며 `/tmp`는 영구
보관소가 아니다. 사본은 FD 종료로 해제됐고 durable executable bundle을 만들지 않았다.

참조: [kernel memfd executable intent](https://www.kernel.org/doc/html/latest/userspace-api/mfd_noexec.html),
[inode seals](https://man7.org/linux/man-pages/man2/F_GET_SEALS.2const.html),
[seccomp inheritance](https://docs.kernel.org/userspace-api/seccomp_filter.html).
