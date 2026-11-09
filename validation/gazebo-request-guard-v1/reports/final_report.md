# 요청 시점 차단·독립 감사 후보 구현 — PARTIAL / BLOCKED

시작 HEAD `47097ee5cfb61203190e5267c0503fa2f22e539c`, 브랜치 `experiment/dart-internal-trace`. tracked/index clean, 기존 dangling plugin symlink만 untracked였다. context-handoff, AGENTS, DEVELOPMENT_RULES, 최신 handoff, boundary 결과와 실행 계약 코드·manifest·seal을 읽었다. 이전 인계 snapshot HEAD는 게시 전 부모 `5f37e63`이며 현재 15파일 commit과 4개 증거 해시로 대조했다.

**전체 요청은 부분 구현이다. 금지 접근 차단과 독립 기록을 정상 DART 실행에 적용했다는 보장은 아직 없다. Stage B BLOCKED / 위험 수용 UNDECIDED / 실제 runtime UNVERIFIED.** 새 launcher와 기존 launcher 모두 service/marker/manager 전 exit78 유지. 후보 배치·원본 manifest 재봉인 없음.

## 구현한 후보 경계

`inputs/guard.c`는 Linux x86-64 ptrace supervisor 후보다. 단일 tracee가 최초 `PTRACE_EVENT_EXEC`에서 멈춘 상태를 전제로 하며, 대상 ELF loader의 첫 명령 이전 정지점에서 시작하도록 설계했다. 기존 namespace·RO input mounts·rlimit·FD bridge를 대체하지 않는다. 대상 syscall 진입마다 `PTRACE_GET_SYSCALL_INFO`로 architecture와 entry를 확인한다. 허용 목록 밖 요청은 supervisor journal에 먼저 write/fdatasync하고 `orig_rax=-1`로 바꿔 요청한 syscall을 실행하지 않게 하며, exit stop에서 반환값을 `-EPERM`으로 설정한다. 레지스터 조작이나 journal 저장 실패 시 대상은 재개하지 않고 78을 반환한다. 이 동작은 **코드·컴파일·정적 검토만** 확인했다.

현재 허용은 0/3 read, 1/2/4 write, 제한된 scalar/memory syscall뿐이다. 경로 open/stat/access, 소켓·네트워크, clone/fork/vfork, 재exec, FD alias/변경, ioctl/io_uring/ptrace/process_vm, 파일 기반 mmap과 executable mprotect 등은 default deny다. 다른 syscall ABI는 거부하고 알 수 없는 stop/event도 재개하지 않는다. 경로 포인터를 검사한 후 원래 syscall을 CONTINUE하는 TOCTOU 경로는 추가하지 않았다.

journal은 target stdout/stderr와 다른 supervisor FD다. O_WRONLY|O_APPEND, 빈 regular file, 단일 link, owner 및 group/other 권한 없음 확인을 요구한다. 각 record는 동기화 완료 후에만 받아들인다. short write, 공간 부족, sync 실패는 실패한다. sequence·DENY 개수·실제 terminal wait·ECHILD·COMPLETE를 기록한다. `PTRACE_EVENT_EXIT`를 실제 종료로 간주하지 않는다. EXIT_ACK를 감시 종료 신호로 사용하지 않는다. 거부가 있으면 target exit0이어도 반환78이다.

이 후보는 clone 자체를 거부하므로 정상 thread/자손 생성 지원이 없다. trace options에는 fork/vfork/clone stop도 요청하지만 예상 밖 event를 받아들이는 다중 task loop는 아니다. ECHILD 증거도 **이 제한된 no-clone 후보의 조건부 증거**다. 정상 thread가 있는 DART 전체 수명 추적을 구현했다고 주장하지 않는다.

## 독립 감사가 빠지면 통과하지 않는 판정

`scripts/audit_gate.py`는 기존 NativeSession/AckSession을 감싸는 별도 **offline adapter**다. 인증된 supervisor event를 받는 미래 transport가 run/policy/source/PID/start binding을 제공해야 한다. target packet으로 audit event를 대체할 수 없도록 entry API를 분리했다. 단, `authenticated=True`라는 Python 인자는 인증 구현이 아니며 실제 transport는 아직 없다.

시작 적용 증거(pre-loader·FD·policy·private journal·lifetime)가 모두 없으면 GO를 거부한다. sequence gap/replay, 잘못된 binding, unknown/loss/overflow record, persistence 실패, 조기/중복 EOF, 최종 live task0/ECHILD·pending0/lost0·완료/채널종료 누락은 실패다. 빈 로그는 시작 증거도 종료 증거도 아니다. 거부는 실패를 latch하지만 **독립 audit event 수집은 계속 허용**하여 초기화 실패나 EXIT_ACK 이후 위반에서도 all_dead/complete/EOF까지 처리할 수 있다. 기존 session의 GO·100 sample·마지막 live mapping·EXIT_ACK·양쪽 EOF·exit·cleanup/integrity 판정은 그대로 호출한다.

## 빌드와 비실행 검사

새 구성요소 C translation unit 하나만 compile/link했다. DART/Sim/Physics/harness/ODE/기존 bridge는 다시 빌드하지 않았다. warning-as-error, PIE, RELRO/NOW, stack protector 적용. ELF 동적 의존은 libc뿐이며 readelf/objdump로 검사했다. build_receipt.json에 컴파일러·source·모든 dependency header·ELF SHA-256, Build ID/인터프리터/동적 metadata, compile argv와 compiler PID/start identity를 남겼다. 새 ELF는 한 번도 실행·dlopen하지 않았다. ELF main도 무조건78이며 guard_monitor를 호출하지 않는다.

신규 **84개 static/mock 검사 PASS** (`tests.json`). 기존 boundary90/contract31 결과는 보고서 hash로 재사용하며 신규 수에 합산하지 않았다. 원래 sealed source loader와 원래 test의 packet/setup/ready factory만 가져와 기존 실제 프로토콜 모의 정상 trace(GO→100×1ms→마지막 live mapping→EXIT_ACK→EOF/exit/cleanup)를 새 감사 adapter와 조합했다. 초기화 거부, ACK 뒤 destructor 거부, journal 저장 실패, sequence 유실, overflow, 조기 단절, 완료 누락, 남은 자손, source/run/policy/PID binding 불일치와 기존 cleanup/EOF/integrity/mapping 실패를 거부했다. 모두 합성 값이며 실제 물리 sample·syscall 차단 관측이 아니다.

기존 manifest 전체를 read-only 재검증했다. 1,442개 기존 tracked/main dirty 일반 파일 hash, main HEAD/status, dangling symlink device/inode/target을 보존했다. 완료 보고서 작성 뒤 handoff 갱신은 의도한 신규 변경이며 기존 단계 evidence는 수정하지 않았다. 보존 baseline은 ignored work/preservation_before.json, 요약은 tests.json에 있다.

## 아직 보장할 수 없는 경계 / 다음 최소 작업

1. **정상 승인 입력 접근 미구현.** 후보는 loader의 필수 open과 executable file mapping도 거부한다. pinned FD를 안전하게 주입하고 읽기/매핑 권한을 이어가는 broker가 없다. 단순 pathname 검사+재개로 풀지 않았다. 현재 후보를 정상 경로 지원으로 배치하면 안 된다.
2. **시작 adapter 미구현.** namespace 내부의 신뢰된 single-child 생성, 최초 exec 전 EXITKILL 설정, target/loader identity와 FD0..4 attestation, journal FD 비상속/접근불가를 한 계약에 묶는 코드가 없다. guard_monitor 함수의 전제조건을 target의 자기보고로 충족했다고 간주하지 않는다. tracer 자체 로더는 신뢰 영역이며 대상 로더와 다르다.
3. **정상 thread/자손 수명 미구현.** clone은 현재 거부된다. 기존 정상 초기화와 양립할 thread 정책·모든 task 추적·완전 종료 증거가 필요하다. 외부 전체 프로세스/자손 보장은 미해결이다.
4. **native journal→collector 연결 미구현.** C journal의 numeric sequence/records를 policy/run/source binding 및 시작 적용 증거와 함께 인증하는 transport/번역기·collector factory 연결이 없다. 외부 supervisor를 target이 조작할 수 없다는 namespace/FD/권한 근거와 신뢰된 최종 수집 증거가 필요하다. Python 모의 API의 인증 boolean, journal mode나 hash만으로 이를 대신하지 않는다. 여러 채널의 drain 순서와 EOF 결합도 실제 lifecycle adapter 검토 대상이다.
5. **동적 로딩 의미 경계.** open/file-backed mmap/executable mprotect 요청은 restrictive 후보에서 거부되지만 syscall 없는 cached dlopen/기존 mapping 조작까지 API 차원에서 차단·기록하지 않는다. native semantic guard와 일치시킬 범위가 남는다.

이 1~5는 단순 runtime-only 검증이 아니라 **남은 구현·통합 작업**이다. 현재는 승인 입력/통신만 허용하는 정상 실행 경계를 완성하지 못했으며 실제 차단+감사 보장 판정을 내리지 않는다. 다음 최소 작업은 read-only pinned input broker 및 thread 정책을 먼저 구현·검토하고, pre-exec adapter/신뢰 transport/전체 collector와 함께 별도 contract에 봉인하는 것이다. 현재 ODE/bridge 후보도 배치하지 않는다.

그 이후에도 별도 명시 실행 승인이 있어야 ptrace kernel/architecture/Yama/namespace 동작, 최초 loader 이전 stop, FD/journal 접근 격리, 실제 constructor/destructor 거부·실패 latch, 모든 자손 종료·journal 유실/시간 한도·성능과 기존 runtime/물리 판정을 확인할 수 있다. 이번에는 해당 실행을 하지 않았다.

## 보존·게시·재현

Gazebo/DART 로딩, harness/무해/native supervisor 실행, step, service, marker 생성/소비, sudo/설치/시스템 변경, 기존 프로세스 종료·재시작/계정 전환 모두 없음. Stage B BLOCKED·위험 UNDECIDED·runtime UNVERIFIED 유지. 원 main과 원본 sealed code/manifest/mounts/SONAME/provider/allowlist/marker는 그대로다.

재현 가능한 허용 검증은 이 단계의 `scripts/build.py`(compile/link/static inspection만)와 `tests/check_guard.py`(Python static/mock만)다. 원시 로그·ELF·보존 manifest는 ignored work/에 남으며 Git으로 다른 기기에 전달되지 않는다. `/tmp` 원본은 영구 저장이 아니다. 경량 source/tests/policy/receipt/report/handoff만 승인 실험 브랜치에 명시 선택해 게시한다. 실제 push/원격 일치 결과는 local reports/publication.json에 기록한다.

설계 참조: [Linux ptrace API](https://man7.org/linux/man-pages/man2/ptrace.2.html)의 syscall stop/exec/EXITKILL/exit event 구분. [kernel seccomp 문서](https://www.kernel.org/doc/html/latest/userspace-api/seccomp_filter.html) 및 [user notification API](https://man7.org/linux/man-pages/man2/seccomp_unotify.2.html)도 검토했으나 notification 설치나 보안 보장을 구현했다고 주장하지 않는다.
