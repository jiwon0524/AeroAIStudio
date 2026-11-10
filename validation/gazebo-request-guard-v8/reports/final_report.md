# Request guard v8 — FD bridge repair and owner handoff verification

현재 scope: 저장된 v8 후보의 FD bridge 결함 수정, owner bootstrap/receiver 계약 검토,
변경 TU 재빌드·정적/Python 모의 검사, 파일 버전 SHA256 연결과 로컬 기록 완료.
기준/현재 HEAD `0f3eb51319a7a75c18d5930a99280de3455e2bd1`, branch `experiment/dart-internal-trace`.
AGENTS/DEVELOPMENT_RULES/context-handoff/handoff와 저장된 build_receipt/tests를 먼저 읽었다.
현재 사용자의 **commit/push 제외** 지시가 이전 자동 게시 규칙보다 우선한다.

**Stage B BLOCKED / 위험 수용 미결정 / 실제 런타임 미검증.**
**이 범위의 구현·비실행 검증 완료 / 전체 배치 준비·실행 검증 완료 아님.**
실제 launcher와 native candidate main은 서비스·marker 생성 전에 exit78이다.
어떤 C 결과물·bridge·owner·unit anchor·namespace 함수도 실행하지 않았다.

## 저장·검증·게시 상태

|구분|확인 사실|
|---|---|
|로컬 저장|수정 소스, 아래 검증 기록, 이 보고서, progress와 handoff 저장. v8 전체는 여전히 ignored|
|검증 완료 범위|launch TU1개 재컴파일·재링크, 기존10 TU 증명 후 재사용. 정적/Python 모의 1082 PASS|
|staging/commit|이번에 수행하지 않음. HEAD는 기준0f3eb51 그대로이며 v8 commit 없음|
|원격 게시|이번에 시도·조회하지 않음. v8 push 성공을 주장하지 않음. 이전 v7 게시 기록과 구분|

향후 게시 검토의 **정확한54개 파일**은 `reports/publication_files.txt`에 먼저 열거했다.
처음52개에서 이전 build/test 영수증2개를 추가해 이력을 검토할 수 있게 했다.
대상은 handoff, 명시한 v8 source/header/policy/test, 경량 보고서뿐이다.
work/ ELF/object/log/baseline, pycache, 외부 패키지, 기존 main dirty 작업은 목록에서 제외했다.
이번 요청은 게시 권한이 아니므로 파일 목록을 staging 명령으로 실행하지 않았다.

## FD bridge 결함과 수정

원래 `candidate_owner_fds`는 `/dev/null`을 열어 받은 낮은 FD를 그대로 dup2에 사용하고
리디렉션 뒤 그 번호를 close했다. 예를 들어 FD3이 비어 있으면 null이3에 할당되고,
나중에 GO를3에 dup2한 뒤 close(null)이 GO를 닫을 수 있었다. fd0/1/2/4의 빈 슬롯도 같은
번호 충돌/부정확한 CLOEXEC 처리 문제가 있었다.

- `owner_bridge.h`에 작은 실제 C bridge 제어 흐름을 두고 native wrapper가 같은 코드를 호출한다.
  go/observation/diagnostic와 null을 모두 **10 이상 CLOEXEC 사본**으로 확보한다.
- 원래 null FD는 낮은 슬롯일 수 있으므로 사본 생성 후 **리디렉션 전에** 한 번만 닫는다.
  원본 소스 번호와 목적지0..4가 중첩돼도 사본에서 리디렉션하므로 원본을 덮어 읽지 않는다.
- 기존 `check_layout` 기준을 사본과 최종 슬롯에 공유한다. null의 char device1:3, pipe 유형,
  GO 읽기/observation·diagnostic 쓰기 모드, diagnostic1/2 동일 객체, GO/observation/diagnostic
  서로 다른 pipe, 사본 CLOEXEC와 최종 inheritable0..4를 검증한다.
- 최종 배치 확인 후에만 원래 high source FD를 소비한다. 정리는 보유한 임시 사본에만 적용한다.
  redirect/검증/close 실패는78이며 close EINTR 등 불확실 결과를 같은 번호로 재시도하지 않는다.
- 부분 리디렉션 실패 시 이전0..4를 복구했다고 주장하지 않는다. **전용 새 owner는 반환78을
  최종 실패로 처리하고 bootstrap으로 계속 진행하면 안 된다.** 다른 기존 작업의 FD를 정리하는 API가 아니다.
- owner bridge는 rlimit을 설정하지 않는다. target soft/hard CPU10, AS2147483648, FSIZE1048576,
  NOFILE256, CORE0은 기존 child path에만 남아 있고 owner 제안값을 합치지 않았다.

## owner bootstrap과 인계 계약

`owner_control_fds`가 복사 준비 전에 journal/collector 누락·같은 번호·잘못된 유형을 거부한다.
journal은 owner 소유의 비어 있는 private regular append/write/CLOEXEC 파일이어야 한다.
collector는 연결된 AF_UNIX seqpacket, nonblocking/CLOEXEC, 같은 UID/GID의 private peer여야 한다.
표준·프로토콜 FD 계약과 이 제어 FD 검사가 모두 통과해야 준비 함수에 진입한다.

추가 검토에서 PID namespace init(PID1)에 대한 자기 SIGSTOP 의존과 wait/reap 뒤 숫자 PID로
신호를 보낼 수 있는 오류 경로를 발견했다. 로컬 `pid_namespaces(7)` 문서의 init 신호 규칙을
확인한 뒤 같은 작업에서 수정했다. 실제 namespace/신호 시험으로 확인한 결과는 아니다.

- worker는 SIGCONT handler를 설치하고 SIGCONT를 block한 뒤 private pipe에 R을 쓴다.
- 조상 namespace의 parent가 R을 확인하고 보유 pidfd로 SIGSTOP을 보낸다. PID1의 자기 raise에
  의존하지 않는다. 정지 wait는 WNOHANG와5초 deadline을 사용한다.
- parent는 wait/reap **전** pidfd를 확보한다. 정상 재개와 이후 실패 SIGKILL은 그 pidfd를 사용해,
  PID가 재사용돼도 다른 프로세스에 신호를 보내지 않는다. pidfd 확보 자체가 실패한 경로의
  숫자 SIGKILL은 아직 wait하지 않은 새 direct child에만 한정된다.
- collector의 O가 없거나 poll/recv/프레임이 잘못되면 준비 성공으로 진행하지 않는다.
  worker는 sigsuspend의 원자적 mask 전환으로 SIGCONT 유실 race를 피한다.

`owner.py`는 문법 검사 외에 실제 bind 함수를 OS/transport mock으로 호출했다.
missing/extra/non-pidfd/non-CLOEXEC, 잘못된 PID/UID/GID·ELF·부모 관계·state·cgroup,
유실/조기 EOF/truncation/malformed ancillary, PID 재사용/도메인 이동/조기 재개,
unbounded/0/상한 초과/변경된 한도, close 오류, send 오류·short ACK를 모두 거부한다.
모든 수신 FD를 한 번씩 해제하며 해제 오류는 **O 이전**에 실패한다. ACK 직전에 parent와
worker의 identity/domain 및 cgroup 한도를 다시 확인한다.

CURRENT_OWNER_MAX와 기본 승인 ceiling은536870912이다. 인자로 미적용5GiB 제안값을 넘겨도
현재 후보는 거부하며 자원 설정을 변경하지 않는다. 반환된 Owner의 root는0이다.
**O는 bootstrap identity 확인일 뿐,303 객체/468경로 준비나 전달 완료가 아니다.** 이후의
catalog 검증·K, placement·P, exec/listener/collector·A, 전체 종료 판정·V를 대체하지 않는다.

## 빌드와 검사 범위

원래 v8 C/소스/보고서와 launch.o/candidate는 `work/fd-owner-before-repair/`에 보존했다.
기존 work/candidate, libaero-resource.so, unit-anchor 및 기존 objects를 덮어쓰지 않았다.
새 launch object와 새 supervisor는 build_receipt의 별도 `work/fd-owner-repair/.../` 경로에 있다.

- 원래11-TU 빌드 영수증과3개 output 해시를 먼저 대조했다. 변경하지 않은 객체들과 보존된
  원래 launch.o를 재링크해 원래 supervisor SHA256
  `ec06594d1997e89ec2d0ed05b43d2c78f46d723bd30f0bde2dac69699f433ece`를 정확히 재현했다.
- 변경된 launch1 TU만 Werror/PIC/stack protector로 다시 컴파일하고 RELRO/NOW/PIE로 링크했다.
  native consumer와 unit-anchor 포함 **10 TU는 재사용**했다. 이번에11개를 새로 컴파일했다고
  보고하지 않는다. compiler path/hash, PID/start, argv, dependencies와 object/output SHA는 영수증에 있다.
- **1082개는 이번 전체 suite의 정적/Python 모의 PASS 수**이다. 이전576개에 이 숫자를
  더하지 않는다. 기존 계산/정책·검사를 재사용하고 통합 suite로 재검사했다.
- FD 검사는 실제 작은 C bridge 본문을 제한된 문법으로 해석해 synthetic FD table에서 실행한다.
  native wrapper가 그 본문을 쓰는지도 검사한다.32가지 low-slot 빈 상태와336가지 소스 번호
  순열, copy/open/각 dup2/final-check/각 close 실패를 검사했다. C 바이너리나 kernel FD API를
  실행한 것이 아니므로 ABI·실제 errno 동작의 런타임 증명은 아니다.
- native parent의 실제 ACK/readiness 조건도 fake poll/read/recv/pidfd signal로 해석했다.
  R+EOF 처리, 잘못된 R/O, readiness/stop/재개 오류, 보류/종료 결과를 검사했다.
- 첫 추가 검사에서 C 변수 in을 Python 식별자로 그대로 해석해 SyntaxError가 났다.
  해석기 이름만 교정했다. ACK 조건을 한 줄로 찾던 보조 검사도 여러 줄 조건을 읽도록
  고쳤다. 두 실패 설명과 첫 실패 소스는 work/fd-owner-repair에 보존했다.
  최종 suite는 수정 후 전부 PASS이다.

## 정확한 파일 버전 연결

`reports/source_manifest.json`은 현재 C/C++/header/Python/test/policy **42개**와 재사용하는
외부 Python source **50개**를 고정한다. canonical manifest digest:

`4dc8b385e241a69004069a562d2a6fb33face9d4abfdba510562d5bce41e3030`

빌드 영수증은 이 digest와 source hashes,403 native dependency hashes,11개 TU의 object hashes,
3개 artifact hashes를 연결한다. 검사 보고서는 **동일 manifest digest·source hashes**와 실제
build_receipt 파일 SHA256, 검사한3개 artifact SHA256을 저장한다. 검사 시작/종료에 source
snapshot을 재확인해 검사 중 수정된 소스를 PASS로 묶지 않는다.

|기록|SHA256|
|---|---|
|build_receipt.json|`e98a82974ec078aa3dc5b0938563272bbbc0bfcee8fcd3f2240677293ca12e6e`|
|tests.json|`dcca5cdbe2fa8af12ad4133743bf410b45390732439509451b7dbbd397e5f1c5`|

Python/test만 바뀐 경우에는 C input/output hashes를 다시 확인하고 source snapshot만
갱신했다. native 재컴파일을 했다고 기록하지 않았다. 원래 해시 없는576개 보고서는
`reports/history/tests.before_fd_repair.json`, 원래 C 영수증은 같은 history의
`build_receipt.before_fd_repair.json`에 원문 보존했다. 과거 Python 버전이 소급 증명됐다고
주장하지 않는다. 최종 source·문서·인계·보고서 목록과 SHA는 `reports/artifacts.json`이다
(자기 자신은 제외하여 해시 순환을 만들지 않음).

허용된 재현 명령(이 Ubuntu의 보존된 원래 objects/baseline 필요):

```bash
python3 -B validation/gazebo-request-guard-v8/scripts/repair_build.py
python3 -B validation/gazebo-request-guard-v8/tests/check.py
```

work/ baseline와 ELF/objects/log는 ignored·로컬이며 위54개 게시 검토 목록에 포함하지 않았다.
다른 기기에는 자동 전송되지 않는다. 원래 objects가 없으면 이 incremental 재현을 할 수 없다.
/tmp도 영구 저장소가 아니다. source/기록을 저장했다는 사실을 원격 백업으로 표현하지 않는다.

## 남은 정확한 차단

- 객체 cap67108864와 준비 cap536870912를 유지했다. 필수 대형 객체5개와 전체303 보유 비용은
  별도 사용자 결정 차단이다. 제안543979760/2159132672/owner5368709120은 모두 **미적용**이다.
- 정적 policy row는468이다. 실제 준비·mount·loader 전달 검증은0이며, 이 작업에서 factory를
  실행해468개를 준비했다는 기록은 없다. resource admission은 namespace/fork보다 먼저 거부한다.
- 이 결함 수정 범위의 비실행 검증은 끝났지만 전체 실행 계약은 미봉인·미배치이다.
  새 native consumer/allowlist·owner 초기화·namespace·unit·audit 전체 경로를 배치 가능하다고
  인증하지 않았다. 한도 승인만으로 launcher나 Stage B를 열면 안 된다.
- 실제 kernel pidfd/SCM/userns/init 신호·mount/chroot·readonly/seal/loader mapping·LSM,
  정상 pthread/clone3/CET와 정책 상속, 종료 callback/EOF/cleanup, resource peak는 별도 승인된
  런타임에서만 확인 가능하며 현재 모두 미검증이다.

원본 main HEAD/dirty 상태, 기존1767 evidence, 기존 v8 inputs(의도 변경 외), source/artifacts/
marker와 dangling symlink 보존 검사를 통과했다. 기존 작업 종료·재시작·계정 변경 없음.
실제 DART/Gazebo/harness·무해 시험·서비스/marker 소비·sudo/install/system 설정 변경 없음.
이번 최종 기록 후에도 commit/push하지 않는다.
