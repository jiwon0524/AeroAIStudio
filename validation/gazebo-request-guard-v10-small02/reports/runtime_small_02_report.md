# small-02 승인된 단일 무해 검증 — FAIL

실행 HEAD:65d1a6487d732eb598b55f87d25110d085921543, experiment/dart-internal-trace.
사용자의 명시적1회 승인에 따라 approval_proposal.md의 고정 명령·인자를 정확히1회 실행했다.
계약 SHA256:ab2a778dbcd1e5f6a8923e6ff8270070c7ee5c944caf0017dd9d43043621ef95.
별도 환경 실행 승인 후 실행; 명령 종료코드78. 자동 재시도0, 한도 상향0, 소스 수정/재빌드0.

## 사전 조건

HEAD/branch/게시 영수증 일치, 계약119파일 hash 및5경로 source device/inode/size 일치.
4원본/5경로, 고정 probe/libc/loader/fixed 입력, owner/anchor ELF hash 확인.
전용 work/runtime-small-02 및 work/harmless-small-02.once 부재(dangling link 포함),
두 small02 unit not-found 확인 후 고정 명령을 실행했다. driver도 첫 marker/service 전에 다시 검사했다.
owner5GiB / target512MiB, object543979760/admission2159132672, CPU10/AS2GiB/FSIZE1MiB/NOFILE256/CORE0,
host40s/collection25s/ACK5000ms, target runtime30s/stop2s 등 승인 계약을 변경하지 않았다.

## 마지막 확인 단계와 최초 실패 진단

native parent(jiwon-System-Product-Name, PID377856, start50665745)의 보존 진단:

- seq1 entry0 → seq2 restore-control-cloexec0 → seq3 fd-bridge0 → seq4 domain0 →
  seq5 control-fds0 → seq6 initial-fds0 → seq7 allocate0 → seq8 catalog-prepare0.
- **마지막 native 성공:seq9 userns0**, errno_snapshot2. 성공 시 errno2는 이전 호출의 잔여값일 수 있어 실패로 해석하지 않는다.
- **최초 native 실패:seq10 uid-map -1, errno_snapshot1(EPERM)**.
  소스의 own_map('/proc/self/uid_map', ...) helper가 거부되었다. 이 helper의 open/write/close 중
  어느 세부 호출인지와 거부한 kernel/LSM 정책은 이번 진단만으로 구분할 수 없다.
- 이 실패는 source 순서상 setgroups/gid-map, PID namespace 생성·worker fork/ready 및 O 송신보다 앞이다.
  따라서 초기 owner O 인계와 첫 CATALOG_OBJECT는 도달하지 않았다. catalog-prepare0은 작은 입력 준비
  함수 성공 관측이며 sealed FD가 collector로 실제 전달되었다는 증거는 아니다.

collector startup은 audit 파일 초기화, target 생성, native-spawned까지 성공했고,
마지막 대기 단계는 owner-bind-begin이었다. 최초 collector 실패는 owner handoff disconnect;
collector-final에서 native parent wait78과 target_cleanup true를 기록했다.
독립 native execution audit 두 로그와 owner-journal.raw는0byte다. audit-initialized는 파일 생성만 뜻하며
독립 감사의 실제 trace/인증/연속성에 도달했다는 뜻이 아니다.

host의 최초 실패는 unit ownership not proven이다. startup에는 owner ControlGroup/InvocationID가 비어 있는
초기 readback과, 유효한 invocation/cgroup을 확인한 readback, 이어 ControlGroup이 빈 readback이 남았다.
owned()는 그 뒤 별도 fresh readback으로 판정한다. cross-process 단조 timestamp가 native 진단에 없어
host 실패와 native uid-map 실패의 정확한 전후 관계는 이 기록만으로 확정하지 않는다.
두 실패를 섞어서 kernel 차단 원인이나 host가 native 실패를 유발했다고 단정하지 않았다.

## 필수 증거 판정

|항목|관측/판정|
|---|---|
|초기 owner O 및 최초 CATALOG_OBJECT|둘 다 미도달; owner-bound 없음, collector-audit0byte, native가 O 이전 uid-map에서 실패.|
|실제 sealed RO FD 인계 C/K·5경로 RO mount|미도달/미검증. 준비 함수 rc0만으로 인계 PASS를 주장하지 않는다.|
|스레드·자손·EXIT_ACK callback/join|미도달/미검증.|
|독립 감사·COMPLETE/EOF/V|미도달. startup 진단으로 빈 execution audit를 대체하지 않는다.|
|필수 진단|초기 host/collector/native 기록은 존재하고 읽을 수 있다. terminal success 필수 단계는 누락, diagnostic_complete false이므로 FAIL.|
|로그 권한|새 runtime 파일13개 모두0600, output0700, marker0600. 기존 small01 host 로그0664는 보존.|
|종료|정확한 명령78, owner service main78, owner client78, native parent wait78. PID1 worker/target probe 정상 종료 증거는 없음.|
|정리|collector target_cleanup true, host owner_cleanup true, cleanup_errors[]. 두 unit not-found/MainPID0/ControlGroup empty. 두 기록 cgroup 디렉터리 부재, /proc 매칭 잔여0, 권한 미확인0. Native PID/start의 프로세스 부재.|
|무결성|계약119파일, 이전 v10의202파일 content/mode, main nonignored303경로, 기존1617파일(handoff 제외) 모두 일치. 기존 소스·marker·증거·plugin symlink 보존.|

## 보존 증거와 중단

원본 실행 증거: work/runtime-small-02/의 host-result.json, collector-result.json, target-unit.json,
host-startup.jsonl, collector-startup.jsonl, native-parent.stderr, host.stdout/host.stderr,
collector-audit.jsonl, native-audit.jsonl, owner-journal.raw, stdout.raw, stderr.raw.
각 파일 byte/mode/SHA와 marker hash, process identity, integrity/cleanup 관측은
reports/runtime_small_02_verification.json에 있다. work/harmless-small-02.once는 소진된 상태로 보존했다.

main ignored evidence 전체는 재인벤토리하지 않았으며 main에는 쓰기를 수행하지 않았다.
/tmp ignored raw 증거·marker·ELF는 Git 보고서 게시로 다른 기기에 자동 전달되거나 영구 보관되지 않는다.
같은 사용자 project-CWD snapshot에 남은 작업 없음; remote/external-CWD 작업은 UNKNOWN.
이번 단일 검증 이후 추가 native 실행, 실험·진단 재현·수정·재시작은 수행하지 않는다.

small01 재실행0, 큰 객체/full468 준비·전달0, 실제 DART/Gazebo/harness 로딩0, physics step0,
sudo/install/system 설정 변경0. 원래 actual Gazebo launcher exit78은 원본 hash/source로 유지하며 재실행하지 않았다.
**Stage B BLOCKED / 위험 수용 미결정 / Gazebo 런타임 미검증**.
다음 행동: STOP. 현재1회 승인은 소진되었다. 별도 범위 승인 없이 원인 재현·수정·새 시도를 시작하지 않는다.
