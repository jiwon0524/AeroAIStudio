# Request guard v5 — native paths implemented, deployment BLOCKED

시작 HEAD `43828245cbbe0b9aa4449dc96b1e020e47ab27af`, experiment/dart-internal-trace.
그 이후 작업은 없었다. tracked/index clean, 기존 dangling symlink만 untracked였다.
context-handoff/AGENTS/DEVELOPMENT_RULES/handoff/v4 최종 보고서와 원래 봉인 계약을
대조했다. 과거 증거·source/adapter·manifest는 읽기 전용으로 재사용했다.

**PARTIAL / NOT DEPLOYABLE / 비실행 전체 준비 미완료.**
**Stage B BLOCKED / 위험 수용 UNDECIDED / 실제 런타임 UNVERIFIED.**
실제 launcher와 새 entry main은 서비스·marker·native API 호출 전에78이다.
새 C 함수는 컴파일·링크·정적 검토만 했다. fork/exec/memfd/mount/ptrace/filter/socket
생성·native 실행을 이번에 실제 수행하지 않았다. 후보 배치·기존 계약 재봉인 없음.

## 네 영역의 완료 범위와 최초 차단

|영역|이번 구현·연결|판정과 최초 미해결|
|---|---|---|
|필수 입력|452개 경로/298개 객체의 path·alias·원본 identity·SHA-256을 native compile-time 정책으로 고정. retained copy 생성, seal 후 FD 해시, canonical openat2 동일 객체 검증, broker ADDFD_SEND 및 정책 인덱스 감사 연결|backend API 구현/빌드·모의 PASS. 실제 확인0. 전체 필수468경로 중16경로/5객체가 미준비라 catalog_full_ready가 **fork 전에78**. namespace mount/controller와 새 copy identity의 native/collector 기대값 계약도 미완료|
|pre-exec|전용 bootstrap socket, source credential 검증, listener SCM_RIGHTS 인계/ACK, target FD 제거·확인, execveat 단발 TRACE guard, loader 이전 exec-stop, collector-ready ACK 전 재개 금지|C API 연결·빌드, 실제 kernel 동작 미검증. 현재 전체 catalog gate가 닫혀 호출하더라도 인계 단계에 도달하지 않음. 신뢰 namespace/controller entry는 아직 배치되지 않음|
|스레드·자손|정확한 legacy clone flags·64task 예약, 기존 eventmsg/task/pending 추적, clone syscall-exit 결과, 초기 child stop 선후 보류, root 이후 자손 terminal/ECHILD 수집. read/fstat/전용 write/futex 등 제한된 정상 경로 추가|legacy 및 제한된 clone3 변환 경로 구현/정적·모의만 확인. clone3의 실제 ABI/재검사 동작은 미검증이며 file-backed mmap/실행 mprotect, 경로 metadata emulation은 여전히 거부. 정상 pthread/DART 초기화 완료 아님. 실제 상속 확인0|
|독립 감사|동기 native journal→별도 seqpacket→SCM credential+FD/pidfd→owner/PID/start/ELF 해시 확인→native-prefix 번역→기존 JournalAdapter/AuditGate. collector A/V ACK를 candidate_run에 결합|수신/번역/판정 API 연결·모의 PASS. 실행된 전용 owner/collector 조합은 없음. 원래 collector의 stdout/stderr/cleanup과 새 reader를 구동하는 활성 controller 및 전체 실행 계약은 미완료|

작은 syscall helper나 parser가 있다는 이유로 전체 준비 완료로 판정하지 않는다.

## 452개 필수 경로의 실제 native 전달 코드

`scripts/plan.py`는 v4 검증 reader와 v3 receipt 고정 해시를 재사용한다. 원본594경로/
429객체 = 과거 준비578경로/424객체 + 미준비16경로/5객체 관계는 그대로다.
그중 정적 필수는468경로/303객체이며, 준비된 필수452경로/298객체만 새 native 정책에
넣었다. 나머지126경로의 기존 기록을 삭제하거나 권한을 넓히지 않았다.
allowlist.inc/policy_counts.h/target_env.inc는 봉인 manifest에서 생성한 새 후보 파일이다.

`catalog_prepare`는 원본 source FD의 dev/inode/size를 검사하고64KiB chunk로 새로운
memfd에 복사한다. 명시 EXEC/NX, WRITE/GROW/SHRINK/SEAL/EXEC 봉인, readonly 재개방,
**최종 봉인 FD의 SHA-256** 확인 뒤에만 보유한다. alias는 같은 원본 그룹의 동일 FD를
공유하고, 서로 다른 원본 그룹을 해시만 같다는 이유로 합치지 않는다. 실패 시 보유
FD를 닫는다. 준비 코드 자체는 이번에 실행하지 않았으며 v3 과거 FD를 되살리지 않았다.

생성자 getrlimit/빈 FD 슬롯/누적 출력 페이지 admission을 넣었다. source size가 사전
계산 뒤 바뀌는 경우도 실제 열린 FD의 크기로 누적 budget을 다시 검사한다. 부모의
rlimit을 올리는 코드는 없다. 현재64MiB 객체 cap과512MiB admission cap을 유지한다.
이 cap은 정확한 실측 peak 보장이 아니며 라이브러리·page cache·kernel overhead와
생성자 cgroup 소유권 확인은 별도 필요하다.

`catalog_open`은 신뢰된 namespace root FD 아래에서 openat2의 IN_ROOT/NO_MAGICLINKS/
NO_SYMLINKS로 승인 canonical 경로를 연다. 그 FD와 보유 사본의 dev/inode/size/접근
모드/exec mode/seal/SHA를 재검사한다. broker는 **이 canonical description**을
ADDFD_FLAG_SEND로 전달한다. target이 검사한 pathname을 다시 여는 CONTINUE는 없다.
경로 교체·잘못된 alias·별도 객체·writable FD는 승인으로 이어지지 않는다.

`INPUT_OBJECT` 정책 인덱스를 요청별 native journal에 먼저 저장한 뒤 PREPARED→실제
응답→DELIVERED를 연결했다. source index와 notification pending ID가 맞아야 하며
collector도 object binding 없는 INPUT_PREPARED/DELIVERED를 거부한다. FD 숫자·과거
receipt·delivery_ready boolean만으로 실제 객체 검증을 대체하지 않는다.

이 코드는 이미 올바르게 copy-FD mount가 만들어진 namespace를 요구한다. old bwrap의
원본 mount를 검사 없이 사본으로 간주하지 않는다. 새 mount/controller 실행 계약,
compiled native identities.hh/plugin 기대값과 collector copy identity projection이
없으므로 기존 원본 inode를 요구하는 실행 계약에는 호환 완료가 아니다. 이 작업에서
원래 native/mapping 검사의 기준이나 original manifest를 수정하지 않았다.

## 미준비 필수5객체의 자원 근거

resources.json에 원본 경로·모든 alias·size·PT_LOAD 크기·계약 한도와 계산식을 기록했다.
아래 값은 **실측 peak가 아니다**. dense memfd 출력 페이지와 새 native copy/hash
동시 buffer128KiB만 합한 알려진 구성분이며 추가 메모리를 포함하지 않는다.

|필수 객체|파일 bytes|페이지 반올림 + native buffers|
|---|---:|---:|
|codegen dartsim|99,090,256|99,221,504|
|codegen DART|543,979,760|544,112,640|
|execution-contract Sim core|74,462,608|74,596,352|
|header-fix DART|543,979,760|544,112,640|
|physics-fix DART|543,979,760|544,112,640|

모두 현재64MiB 객체 준비 한도를 넘는다. streaming은 user buffer만 줄이며 만들어
보유할 memfd의 전체 페이지를 없애지 않는다. DART 하나의 알려진 출력+buffer만으로도
536,870,912-byte MemoryMax를 넘는다. **동일512MiB charged domain에서 기존 dense-copy
방식으로 처리 가능하다고 판정할 수 없다.** 정확한 RSS/cgroup peak는 실행 없이 알 수 없다.

필요한 값은 제안·변경이 아니라 다음 설계의 최소 입력이다.

- 객체 cap은 가장 큰 파일 기준 최소543,979,760 bytes가 필요하다. 현재 cap을 바꾸지 않았다.
- 생성자의 RLIMIT_FSIZE가 target과 같은1,048,576이면 복사 생성이 막힌다. 이 방식의
  생성자 FSIZE는 최소543,979,760이 필요하며 target의 읽기/매핑 FSIZE와는 별개다.
- 전체 필수303객체의 dense 출력 페이지는2,159,001,600 bytes. 새 buffers 포함
  2,159,132,672 bytes에 **추가 overhead**가 필요하다. 이것을 새 MemoryMax로 자동 설정하지 않았다.
- 현재298객체 기준 admission 모델은 준비자 NOFILE308, supervisor311 슬롯 이상을
  예약한다.303객체 전체는 각각313/316이다. ambient/sparse FD/라이브러리 FD 여유는
  별도다. target NOFILE256을 올릴 근거가 아니라 보유자인 별도 owner의 요구다.
- target AS2,147,483,648와 MemoryMax512MiB는 그대로다. ELF 파일의 debug bytes는
  PT_LOAD/실제 resident set과 같지 않으므로 파일 크기만으로 target AS 변경 값을
  계산하지 않았다. 실제 target runtime 요구는 미검증이다.

따라서 기존 한도 안의 준비된 subset은 bounded factory로 구현했으나,5개는 권한·한도
변경 없이 차단했다. 생성자·supervisor·target을 어느 resource domain에서 charge할지
명시하는 계약이 필요하다. 별도 domain을 무제한 우회로로 취급하지 않는다.

## loader 이전 인계와 스레드

새 native API는 별도 신뢰 supervisor가 올바른 namespace와 post-bridge FD0..4 ABI를
갖고 있다는 전제다. exact target argv/env는 기존 계약에서 고정했다. 새 target child는
exec FD5/bootstrap socket6만 따로 복제하고7이상 FD를 닫으며 기존 target rlimit만
적용한다. parent의 준비·보유 FD 한도에 target bridge의256 hard limit을 먼저 씌우면
안 되므로 새 owner/controller 배치 계약은 별도로 작성해야 한다.

parent가 initial stop에서 EXITKILL/TRACE*와 TRACESECCOMP를 설치한다. child는 filter를
설치하고 listener를 private socket으로 전달한다. kernel SCM_CREDENTIALS, 정확히1개
listener FD, MSG_CMSG_CLOEXEC, truncation/type를 확인한다. supervisor ACK가 없으면
initial exec에 도달하지 못한다. bootstrap IPC와 exec는 상태 있는 TRACE guard가
단계별로만 허용하며, kernel exec-stop에서 실제 target FD0..4만 남았는지 확인한다.
target loader는 아직 재개하지 않는다. FD0..4 close/dup/reexec는 거부해 자동 ADDFD 할당이 protocol endpoint를 대체하지 못하게 한다. handoff 실패는 소유한 child만 중단·회수하며
cleanup_pending이나 최종 증거 누락이 남으면78이다. 기존 작업 PID를 attach/kill하지 않는다.

실제 승인 파일의 read/pread/fstat/lseek와 FD5 이상의 close, attested FD1/2/4의 write, 일부 signal/
TLS/robust/rseq/futex·익명 비실행 메모리 경로를 제한적으로 연결했다. legacy clone은
VM/FS/FILES/SIGHAND/THREAD/SYSVSEM/TLS/TID의 **정확한** flags만 허용하고 슬롯을
예약한다. CLONE_UNTRACED/namespace 변경/재exec/임의 IPC는 허용하지 않는다.
clone3는 알려진64/80/88-byte 구조를 복사한 뒤 정확한 thread flags·TID/TLS/stack만 허용한다. set_tid/cgroup/pidfd/exit_signal 등 미지원 값은 거부한다. 승인 subset은 고정 scalar clone 레지스터로 재작성해 kernel이 검사했던 mutable 구조체를 다시 읽지 않도록 했다. 실제 glibc trampoline/CET·kernel 재검사·상속은 실행 미검증이며 임의 clone3 변형은 여전히 거부한다. file mmap, executable mprotect,
경로 metadata/probe 등 미구현 경로와 unknown request는 여전히 기록 후 거부한다.
따라서 정상 loader/pthread 전체 지원이나 첫 실제 syscall 순서를 확인한 것은 아니다.

candidate_supervise는 child stop 선후 보류, clone exit 실패, 대기 중 thread death,
거부 후 독립 기록, root 이후 남은 task, actual terminal wait/ECHILD를 연결했다.
EXIT_ACK는 감시 종료 조건이 아니다. 실패 cleanup도 가능한 범위에서 종료를 수집하며,
deadline 내 회수되지 않으면 cleanup_pending을 남기고 COMPLETE 성공을 합성하지 않는다.

## 전용 감사와 기존 최종 판정

기존 v1 fdatasync journal 저장 뒤 별도 nonblocking seqpacket에 같은 record를 전송한다.
전송 실패·short record·overflow는 응답 전에 실패한다. target의7이상 FD는 모두 닫혀
있고 exec-stop FD 검사를 통과해야 한다. collector로 audit FD를 넘긴 뒤 native owner는
그 read-end 사본을 닫아 collector 단절이 가려지지 않도록 했다.

외부 collector와 namespace 내부 PID를 혼동하지 않도록 root pidfd도 전달한다.
수신부는 SCM credentials/정확히2개 FD/owner PID-start/실행 파일 hash/seqpacket peer를
검사한다. pidfd fdinfo의 Pid/NSpid로 observer PID와 source-local root를 연결한다.
native task 번호는 source namespace 내부에서 추적하고 기존 Gate/attestor binding은
외부 observer PID/start를 유지한다. pidfd 매핑이 없거나 재사용되면 거부한다.

NativeJournal은 preexec5 record의 순서와 실제 FD-clean count, raw seq/denial 누적값,
정책 index·task·pending 및 마지막 완료를 확인하고 기존 v2 JournalAdapter/AuditGate로
번역한다. source 저장과 정규화 seq를 분리하되 raw 유실을 검사한다. private endpoint
검증으로 얻는 process-local capability 없이는 raw bytes가 Gate start를 만들 수 없다.
실패 후에도 물리 channel drain을 계속할 수 있으나 verdict failure는 지워지지 않는다.

collector-ready A 전에는 root를 재개하지 않는다. source COMPLETE/실제 audit EOF 뒤에도
기존 GO·100sample·종료 직전 live mapping·EXIT_ACK·양쪽 protocol EOF·실제 exit·cleanup/
integrity의 기존 finalize가 성공해야만 V를 보낸다. candidate_run도 V가 없으면78이다.
실제 driver가 이 API와 원 collector의 모든 stream을 구동한 사례는 없으며, source
COMPLETE나 Python mock 인증이 전체 실행 PASS를 대신하지 않는다.

## 빌드·검사·보존

- 새 catalog/broker/control/launch/refusal entry **5 TU**만 별도 work/에 compile/link.
  Werror/PIE/RELRO/NOW/stack protector. libc+libcrypto.so.3 의존성을 ELF 정적으로 검사.
  libcrypto 실제 파일 hash는 원 계약에 이미 pinned된 입력과 일치했다. runtime 후보를
  로드하지 않았다. compiler PID/start, source/header/object/ELF/library 해시는 build_receipt.json.
- 신규 **573 static/Python mock PASS**, tests.json.452 native policy rows 및452개 native
  wire 입력 index, FD/alias/source/hash mismatch, private source/credentials/start/ELF 검증,
  잘못된 handoff FD 정리, PID namespace 변환, 손실·재전송·overflow·조기 EOF·실패 후
  drain, 동시 요청/취소/종료 중 거부와 기존 protocol finalize를 검사했다.
- 기존 SourceLoader/NativeSession/ACK factories와 adapter를 재사용했다. 과거686/101개를
  재실행하거나573개에 합산하지 않았다. C API/kernel 동작을 실행한 테스트가 아니다.
- 같은 작업에서 수정한 문제: handoff HUP 선후, decision/응답 exit-stop 구분, clone 슬롯
  예약, source 읽기 FD의 중복 보유, truncated SCM_RIGHTS 누수, 실제 collector V gate,
  PID namespace 혼동, 변동 size의 admission 재검사. C admission 변수 scope 빌드 실패는
  work/catalog.admission-scope-failure.log에 보존하고 수정 후 전체 빌드·검사를 통과했다.
- baseline work/preservation.json의 기존 파일/main HEAD/status 및 symlink identity 보존.
  의도된 experiment handoff만 제외해 최종 대조한다. 원본 코드·evidence·산출물·marker와
  dangling symlink 변경 없음. service/step/marker 생성·소비/sudo/install/system 변경 없음.

## 다음 최소 작업·runtime 경계

첫 차단은 전체 catalog의452≠468이다.5개의 preparation/owner resource 계약을 해결한 뒤,
canonical copy mount/새 native identity 기대값과 namespace/controller 계약을 완성해야 한다.
이어서 정상 경로 metadata/file mapping/negative lookup 정책과 실제 multi-stream
collector driver를 마쳐야 한다. 원래 실행 계약은 그대로 차단 상태다. supervisor가 target unit 내부에서 V를 기다리면 기존 unit 정리 판정과 순환 대기가 생길 수 있으므로, 별도 owner 자원 domain과 target cgroup 배치 순서도 새 계약에 명시해야 한다. 현재 API가 그 service/controller 배치까지 만든 것은 아니다.

따라서 전체 비실행 준비 완료나 runtime 승인 대기 단계로 승격하지 않았다. 이후 첫 별도
runtime 검증은 대표 ODE 객체+SONAME alias만 사용하는 격리 FD/namespace/channel 경계가
최소 후보다. sealed hash·canonical inode 일치, RO/CLOEXEC·독립 offset, handoff 실패 시
loader 미진행, 거부/단절/손실/overflow 실패, 실제 전 task 종료/ECHILD/EOF/정리가 기준이다.
DART/Gazebo/harness/service/step/marker는 그 제안에도 포함하지 않으며 별도 명시 승인 없이
실행하지 않는다. executable mapping/실 loader/thread 상속/자원 peak는 추가 runtime
검증이 필요하다. 이번에는 실제로 확인한 전달 입력·loader·자손이 모두0이다.

재현: scripts/plan.py(읽기/정책 생성), scripts/build.py(컴파일/ELF 정적 검사), tests/check.py
(Python mocks)만. ELF/raw log/보존 baseline은 ignored work/에 있고 Git으로 전달되지 않는다.
`/tmp`는 영구 저장소가 아니다. 검증된 경량 source/test/report/handoff만 experiment에 게시한다.

참조: [ptrace/seccomp TRACE](https://man7.org/linux/man-pages/man2/seccomp.2.html),
[notification API](https://man7.org/linux/man-pages/man2/seccomp_unotify.2.html),
[cgroup memory accounting](https://docs.kernel.org/admin-guide/cgroup-v2.html).
