# Request guard v4 — integrated static/mock checkpoint

최신 HEAD는 공유된 `fb6723e146f8e0b4d4085d7890f28708ab08d38b`와 같았다.
브랜치 experiment/dart-internal-trace, 최초 tracked/index clean 및 기존 dangling symlink만
untracked. AGENTS/DEVELOPMENT_RULES/context-handoff/handoff, 최신 v3 보고서 및 원래
봉인 계약·collector·native identity·mapping 검사를 읽었다. v3 유효 산출물을 재사용했고
그 이후 완료된 별도 작업은 발견하지 못했다.

**PARTIAL / NOT DEPLOYABLE / NONEXEC_PREPARATION_INCOMPLETE.**
**Stage B BLOCKED / 위험 수용 UNDECIDED / 실제 런타임 UNVERIFIED.**
실제 launcher와 새 native/Python entry는 manager/service/marker 전에78이다.
실행 계약 배치·재봉인·기존 판정 완화 없음.

## 통합 판정과 최초 남은 실패 지점

|항목|연결한 구현·정적/모의 근거|최초 남은 실패 및 다음 작업|
|---|---|---|
|정상 입력|ODE ELF+SONAME alias 대표 검사 후 동일 router를424객체/578별칭 전체에 적용. 그중298개 정적 필수 객체/452경로. live FD 검사→canonical alias 객체 대조→독립 description→감사 decision 저장→FD 전달→결과 receipt 순서를 모의로 연결|실제 retained FD catalog factory가 없고 RealFD.namespace_object가 명시 거부한다. 그 다음 원래 native/collector identity와 canonical mapping도 미통합. target 실제 허용0/594, runtime 확인0|
|pre-exec|native control_arm이 실제 초기 wait/SIGSTOP 확인 후 EXITKILL/TRACE*를 설정하고 journal 동기 저장. Python 통합은 private channel→stop→options→filter/listener→exec-stop 순서를 강제|신뢰 child/wait owner가 없고 native filter/listener-before-exec 증거 producer가 없다. 기존 filter는 initial exec도 거부한다. listener handoff·제거·최초 exec 단발 허용과 재exec 요청 시점 차단을 구현해야 한다|
|스레드·자손|native clone/fork/vfork eventmsg와 부모/자식 연결,64task 및 task별 pending notification ID, actual terminal/ECHILD API. 모의로 동시 요청·PID 세대·root 이후 자손 종료를 연결|정상 clone/clone3/futex 등의 syscall 정책은 여전히 default deny. 신뢰 wait dispatcher의 newborn stop 선후 처리·새 task 적용 증명·PID/start 세대 생산이 미통합. 자동 상속을 실제 확인한 자손0|
|독립 감사|기존 v1 sync writer/AuditGate 및 v3 broker 재사용. native callback을 같은 control journal/pending 상태에 연결. bounded private framing+두 sequence 공간+수명 adapter+원래 NativeSession을 모의로 결합|OS 소유권/비상속이 증명된 실제 channel factory와 native numeric journal→run/source-bound framed stream live translator가 없다. parser·boolean·모의 dictionary는 인증이 아니다. 실제 EOF/단절 cleanup owner 연결 필요|

즉 정적·모의 연결은 진전했지만 완전한 비실행 준비가 끝난 상태가 아니다.
미구현 항목을 runtime-only 검증으로 바꾸지 않았고 실행 승인 요청을 제출하지 않았다.

## 입력 관계와 필수성

원래 manifest의594개 논리 경로는429개 원본 device/inode 객체로 묶인다.
v3에서 실제 seal 후 해시를 확인했던424개 객체가578개 별칭을 가진다.
미준비5개 객체는16개 별칭을 가진다. **424+5=429, 578+16=594**다.
이번에는 v3 copy_contract 해시 `0a7b6555…bd9e4c52`를 고정 검증하고 재사용했다.
과거 FD는 닫힌 상태이므로 그 숫자/inode로 실제 live FD를 복원하지 않았다.
새 kernel memfd 준비·mmap·namespace·실행은 하지 않았다.

필수성은 roles/required mappings/payload에서 시작한 SONAME edge 도달성과 native.expected
원본 identity 및 allowlist 입력으로 계산했다.303개 객체가 정적으로 필수이며,
준비된298개가452경로를 가진다. 나머지126개 객체/126경로는 현재 static root에서
필수를 입증하지 못했으나 기존 sealed allowlist 소속이다. 이를 임의 삭제하거나
runtime optional로 확정하지 않았다. 입력별 original identity/hash, aliases, 필수성
witness는 `input_integration.json`에 있다.

준비 한도를 넘은5개는 **모두 필수**다.

|객체|필수 근거|
|---|---|
|codegen dartsim|명시 dartsim role/required mapping|
|codegen DART|명시 dart role + physics SONAME|
|execution-contract Sim core|harness의 libgz-sim8.so.8 SONAME. 여러 과거 논리 alias가 동일 객체|
|header-fix DART|선택된 dart-collision-ode의 libdart.so.6.13 SONAME|
|physics-fix DART|선택된 dartsim의 libdart.so.6.13 SONAME|

원래64MiB 준비 한도·허용 목록·서비스/rlimit을 늘리지 않았다. 이5개만 입력 준비
차단으로 남기고 나머지 입력 및 pre-exec/감사 작업을 계속했다. 대형 객체와 전체 set의
FD/메모리/accounting 설계가 별도로 필요하다.

## 요청→읽기 전용 FD와 감사 연결

`scripts/inputs.py`의 Catalog.bind는 새로운 살아 있는 readonly FD의 seal/바이트/hash/
inode/exec intent 검사를 재사용하도록 설계했다. 원본과 사본 관계, 같은 inode의 모든
alias를 유지한다. 과거 receipt만으로 bind할 수 없다. RealFD는 v3 validate_object를
호출하지만 canonical namespace attestor와 실제 delivery는 아직 명시 거부한다.

Router는 immutable Request의 task/generation/notification ID/path/flags snapshot을
사용하고 read-only mode와 목록을 검사한다. 사본 FD와 namespace alias가 같은 객체인지
검사한 후 고정 FD에서 별도 description을 만든다. 원래 target pathname을 검사 후
다시 열어 실행시키는 CONTINUE 경로는 없다. native broker의 ADDFD_SEND primitive는
v3 소스를 그대로 재사용했고 delivery_ready 조건을 완화하지 않았다.

대표는 libode.so.8.0.2와 libode.so.8 두 논리 경로다. 모의에서 같은 sealed 객체를
가리키며 open description은 따로 생성됐다. 통과 후 같은 조건을578개 경로 모두에
적용했다. 이 수치는 **MockFD와 합성 namespace/응답**의 연결 수다. 실제 target FD 전달,
canonical bind mount, executable ELF mapping, 원래 native expectation 통과 수가 아니다.
원래 mapped.py의 deleted memfd 거부와 기존 inode/path 기준은 유지했다.

각 요청은 private lifetime의 request→decision persist→response→receipt 순서로 처리된다.
기록 실패/예외면 FD를 전달하지 않는다. 불확실한 FD 응답은 재시도하지 않고 실패를
latch하며 다음 새 입력도 허용하지 않는다. 단일 supervisor dispatcher와 Catalog RLock이
target의 동시 요청을 직렬화한다는 설계이며 실제 Python/target thread stress 실행은 없다.

## pre-exec·task·종료 감사

`inputs/control.c`는 v1 record를 재사용한다. control_arm은 caller가 준 stop status만
신뢰하지 않고 waitpid로 실제 initial SIGSTOP을 소비하며, options 설정 전후를 동기
기록하고 **대상을 재개하지 않는다**. 다음 exec event 및 child event가 올바른 종류인지
확인하고 child는 GETEVENTMSG와 대조한다. 새 코드가 child를 만들거나 exec하는 곳은 없다.
따라서 현재 root/FD/namespace/parent 관계를 만드는 신뢰 launch adapter를 대신하지 않는다.

native broker callback의 REQUEST/DENY/INPUT_PREPARED/DELIVERED/REPLIED_DENY/CANCELLED가
control의 동일 sequence 및 task별 notification ID와 연결된다. decision은 응답 전에
동기 저장하며 delivery receipt는 실제 broker 응답 callback 뒤에 기록한다. 파일1MiB,
sequence overflow,64task, pending ID 불일치는 실패다. terminal status만 task death로
받고 task0+actual wait ECHILD 뒤에만 완료 receipt를 쓴다. 거부·취소·비정상/pending
종료는 exit0과 무관하게 실패다. 일련의 함수 API를 실제 wait owner/정리 loop로 잇는
작업은 남았으며, 실패 반환을 무시해도 안전하다고 주장하지 않는다.

`scripts/lifetime.py`는 사전 적용 순서와 task generation/request ID, journal persistence,
실제 전 task 종료/ECHILD/EOF의 증거 완결성을 검사하고 원래 AuditGate를 호출한다.
root death나 EXIT_ACK는 감사 종료가 아니다. 거부 뒤에도 별도 death/completion 수집은
계속할 수 있다. 구조적/transport 실패 후 새 FD 승인 금지. journal 저장을 더 할 수
없는 overflow/저장 장애에서 성공 종료 증거를 합성하지 않으며 최종 판정은 실패다.

`scripts/channel.py`는1MiB/line4096 한도, 부분 frame, duplicate JSON key/nonfinite 값,
loss/replay/binding/stream 구분, 조기/중복/불완전 EOF를 거부한다. raw lifecycle과 기존
Gate의 sequence 공간은 명시 stream 태그로 나눠 번호 충돌을 피했다. 이 parser는 OS
peer 인증이나 semantic verdict를 대신하지 않는다. native numeric record의 live 번역과
private FD ownership factory가 없으므로 실제 channel을 통합했다고 판정하지 않는다.

## 검사·수정·보존 증거

- `scripts/build.py`: broker/control/refusal entry3개 TU만 새 work/에 compile/link했다.
  기존 DART/Sim/Physics/harness/bridge 재빌드 없음. v1 journal/v3 broker source와 header
  dependency, compiler PID/start/sha, object/ELF hash는 build_receipt.json. Werror/PIE/
  RELRO/NOW/stack protector, libc-only. readelf/objdump만 사용했고 ELF 실행·로드 없음.
- `tests/check.py`: **686 static/Python mock PASS**. 578개 서로 다른 입력 경로의 모의
  open 검사가 포함된다. 그외 bad flags/alias/hash/object/reopen, mandatory budget 거부,
  기록 실패/예외, 불확실 reply, preexec 순서/증거 누락, 동시 요청, PID 세대/재전송,
  64task overflow, root 이후 자손, ECHILD 누락, channel framing/loss/overflow/EOF 검사.
- 같은 작업 중 검토에서 고친 사항: decision/response 기록 분리, C callback의 공유
  journal/pending 연결, journal byte 한도, 두 stream의 sequence 충돌 방지, persistence
  예외 latch, 불확실 응답 후 새 승인 차단, PID 재사용/전역 notification replay 차단.
  수정 후 관련 전체 모의 검사가 통과했다. 수정마다 별도 단계 보고서를 만들지 않았다.
- 기존 봉인 SourceLoader/NativeSession/ACK factory와 실제 모의 protocol을 재사용했다.
  합성100sample, GO, 마지막 live mapping, EXIT_ACK, 양쪽 EOF, exit/cleanup/integrity
  유지. 모의 ACK 뒤 금지 요청·disconnect·missing death 및 기존 최종 조건 실패는 거부.
  전 단계101/70/84개를 재실행하거나686개에 합산하지 않았다.
- work/preservation.json 기준 기존 tracked/main dirty 파일, main HEAD/status, symlink
  device/inode/target 보존. 이 단계의 의도된 experiment handoff만 제외하고 diff 검토.
  기존 산출물/evidence/marker 및 원 main은 변경하지 않았다.

## 필요한 다음 구현과 첫 런타임 검증의 조건

다음 최소 구현은 (1) retained immutable catalog→canonical namespace FD attestor/identity
bridge, (2) 신뢰 preexec wait owner와 listener handoff/단발 exec guard, (3) 정상 loader
metadata/read/mapping/thread 정책, (4) native journal live binding/translation/drain/정리다.
정상 입력5개 한도 문제와 별개인 (2)/(4)의 native API와 모의 state는 이번에 진행했지만
그 producer/dispatcher까지 완성된 것은 아니다.

현재는 비실행 준비 미완료이므로 runtime 승인 대기 단계로 승격하지 않는다.
이 구현 공백이 닫힌 뒤 첫 별도 runtime 승인의 최소 후보는 **대표 ODE 객체1개와
SONAME alias2개만 쓰는 소유권이 확인된 임시 namespace/FD 경계 검사**다. DART/Gazebo,
기존 harness, 서비스, 물리 step, marker는 범위에서 제외하는 별도 제안이어야 한다.
그 검사도 지금 실행하지 않았고 별도 명시 승인 없이는 시작하지 않는다.

첫 검사의 통과 기준은 final sealed bytes=계약 hash, 두 alias/open/stat/FD가 같은
copy inode를 사용함, 독립 offset/readonly/CLOEXEC, 잘못된 alias·write 요청 거부와
동기 감사, 요청 취소/단절/overflow 실패, root/모든 자손 실제 terminal/ECHILD/감사 EOF,
잔여 task/FD/출력/정리 이상 없음이다. executable mmap/실 loader 이전 적용은 이 제한된
검사로 인증되지 않으며 그다음 별도 검증과 승인 범위다. 숫자상 모델 PASS를 근거로
이번 launcher를 열거나 이 미래 검사를 자동 수행하지 않는다.

재현은 이번 scripts/build.py와 tests/check.py만이다(compile/static/Python mocks).
실제 DART/Gazebo 로딩, harness·무해/native supervisor 실행, service, step, marker 생성/
소비, sudo/install/system 설정 변경, 계정 전환·기존 프로세스 종료/재시작 없음.
원시 ELF/build/보존 baseline은 ignored work/에 남고 Git으로 전달되지 않는다.
`/tmp`는 영구 저장소가 아니다. 검증한 경량 source/test/report/handoff만 experiment에 게시한다.

API 참조: [ptrace initial/exec/child stop와 EXITKILL](https://man7.org/linux/man-pages/man2/ptrace.2.html),
[seccomp inherited filter와 ADDFD_SEND](https://docs.kernel.org/userspace-api/seccomp_filter.html).
