# Runtime Sandbox Isolation Verification V1

## 상태와 인수인계

**SANDBOX_ISOLATION_PARTIAL / Probe A~D BLOCKED / NOT_RUNTIME_VERIFIED / Stage B BLOCKED.** 이번 작업은 무해한 자체 Fixture의 제한된 격리 효과를 검증했으며 DART Runtime 검증이 아니다.

실험 경로 `/tmp/AeroAIStudio-dart-internal-trace`, branch `experiment/dart-internal-trace`, 시작 local/remote HEAD `91ee5f7c1627e6d0a7b25b3a9875dc4a065d4ff9` 일치와 clean 상태를 확인했다. main HEAD `46134c6bf5670ed61ba252f394ccdddb7ff2cf6b` 및 기존 dirty 상태를 보존했다. AGENTS/개발 규칙/handoff, Readiness final/verdict/risk/isolation/fixture, Targeted probe_plan을 읽었다. context-handoff 스킬로 증거와 관측을 대조했다. 과거 snapshot의 83ab0f5는 Readiness 게시 전 값이며 실제 후속 commit91ee5f7과 연결된다.

이전 20 PASS, 4 Runtime SKIP, 54,436파일 보존은 과거 결과이며 이번 수에 합산하지 않는다. 이전 work의 manifest·로컬 보고서 생성 스크립트·게시 영수증도 기존 파일로 보존했다. 원본/기존 Evidence는 수정하지 않았다.

## 사용 가능한 기능과 실행 경계

Ubuntu24.04, kernel7.0.0-42-generic, 일반 UID1000에서 검사했다(`sandbox_capabilities.json`). bwrap0.9.0, unshare2.39.3, prlimit/timeout이 설치돼 있다. 일반 도구 sandbox 안은 NoNewPrivs1/Seccomp2/AppArmor bwrap profile로 namespace가 거부됐다. 승인된 호스트 실행은 동일 UID1000/CapEff0이며 기존 AppArmor enabled, 현재 unconfined, NoNewPrivs0/Seccomp0이다. 이 두 환경을 혼동하지 않는다.

호스트 Bubblewrap user/mount/net/pid namespace는 실제 사용 가능하다. `unshare --map-root-user`는 uid_map EPERM으로 BLOCKED다. userns sysctl의 값1은 가용성 전체를 설명하지 못한다. AppArmor·sysctl·패키지·시스템 라이브러리를 변경하지 않았고 sudo/root는 쓰지 않았다. seccomp 신규 필터와 AppArmor 신규 정책은 NOT_TESTED다. 이 결과를 모든 Ubuntu24.04 환경의 가용성으로 일반화하지 않는다.

## 선택한 격리 방식과 Fail-Closed

`prlimit → bwrap --unshare-all --die-with-parent --new-session → /usr/bin/python3 -I -B`의 고정 실행만 제공한다. 범용 command/DART launcher가 아니다. root를 ro-bind하고 기존 mountpoint를 사용해 tests를 `/mnt`, Canary를 `/media`와 `/opt`, 해당 실행의 유일한 호스트 쓰기 출력 디렉터리를 `/run`에 bind한다. private `/tmp` tmpfs, `/dev`, PID namespace용 `/proc`는 별도 가상 쓰기 영역이다. `/etc/resolv.conf`는 자체 로컬 nameserver 설정을 읽기 전용으로 노출한다. 전체 호스트 root 읽기는 허용되므로 비밀 읽기 차단 sandbox라고 주장하지 않는다.

Fixture는 user/mnt/net/pid namespace inode가 호스트와 다른지, root/Canary ro 및 output rw인지 먼저 검사한다. gate 실패 시 case 본문·started marker를 만들지 않는다. invalid bwrap option을 넣은 부정 검사는 nonzero/본문 미진입으로 PASS였다. 처음 namespace/mount/file-path 실패에서도 본문이 실행되지 않았다. 격리 없는 실행으로 fallback하지 않는다.

## 파일 시스템

허용된 `/run/allowed` 쓰기는 성공했다. 전용 Canary 두 경로는 실제 open-for-write에서 **EROFS30**으로 차단됐다. 권한 비트만 검사한 결과가 아니다. Canary hash와 종료 후 임시 디렉터리 정리를 확인했다. 원본 프로젝트나 시스템 파일에는 파괴적 쓰기 시도를 하지 않았다. root ro gate와 기존 파일 전후 hash를 근거로 보존을 확인한다(`filesystem_isolation.json`).

한계: private tmpfs 및 출력의 총용량 상한은 검증하지 않았다. RLIMIT_FSIZE는 개별 파일, RLIMIT_AS는 프로세스 가상 메모리이며 tmpfs 전체·많은 파일의 총량을 제한하지 않는다. 이 때문에 실제 target용 전체 실패 차단 검증은 아직 완료가 아니다.

## 네트워크

호스트와 다른 net namespace inode, 기본/물리 route 없는 테이블 및 실제 연결 결과를 함께 확인했다. 문서용 IPv4주소192.0.2.1 TCP/UDP는 ENETUNREACH였고 외부 서비스에 데이터를 전송하지 않았다. private resolver는127.0.0.1이며 `.invalid` 이름 조회는 EAI_AGAIN이다. 호스트 전용 TCP/UDP 수신기는 loopback에만 열었고 결과는 수신0건이다.

Bubblewrap은 private loopback을 활성화한다. 따라서127.0.0.1 UDP sendto 성공은 private namespace 큐에 전송했다는 의미이며 호스트 접근 성공이 아니다. net inode 분리와 호스트 수신0, TCP refused 및 외부 route 차단을 함께 판단했다. 초기 UDP syscall 실패 기대는 부정확해 실패 기록을 보존하고 이 의미에 맞게 수정했다. DNS 오류 하나만으로 격리 PASS라고 하지 않는다. IPv6·파일 경로 UNIX socket 노출은 별도 검증하지 않았다(`network_isolation.json`).

## 프로세스·자원·정리

CPU2초/AS256MiB/개별 파일64KiB/NOFILE64/core0은 Bubblewrap 생성 전 적용한다. NPROC512는 namespace 생성 뒤 Fixture 본문 전 적용한다. 초기 NPROC32·512를 생성 전에 적용하면 namespace EAGAIN이 발생했고, 이후 적용에서는 해당 오류가 사라졌다. UID 공유 NPROC를 전용 PID/cgroup 제한으로 취급하지 않는다.

정상 종료, exit7, SIGTERM(wrapper143), timeout, CPU kill(wrapper137), MemoryError23, 파일 크기24, 자식 포함 timeout, group kill/wait, 임시 파일 정리와 재실행이 통과했다. 관측한 host PID/start identity4개의 live survivor는0이었다. Z 상태는 non-live로 처리했으므로 완전 zombie reaping의 증거는 아니다. supervisor만 갑자기 죽는 경우를 group kill과 독립적으로 시험하지 않았다. cgroup 전체 CPU/RAM/PID 상한도 미검증이다(`process_isolation.json`).

## 테스트와 실패 보존

현재 최종 실행 **Fixture12 PASS / 0 FAIL / 0 SKIP**, 오프라인 보고서·namespace/limits/Canary/fail-closed/cleanup 검사 **6 PASS**. 추가 안전 항목 **2 SKIP**(독립 supervisor abrupt-death, aggregate cgroup/tmpfs bounds). 최종 합계 **18 PASS / 0 FAIL / 2 SKIP**이며 실제 Probe A~D는 별도 NOT_RUN이다.

이전 실패6회는 삭제하지 않았다:

- `fixture_results_initial.json`, `fixture_results_nproc512.json`: namespace EAGAIN, 본문 미실행.
- `fixture_results_post_namespace_nproc.json`: root ro 상태의 신규 mountpoint mkdir EROFS, 본문 미실행. 기존 mountpoint로 수정.
- `fixture_results_mountpoints.json`: mountpoint 치환 중 Fixture 파일명 경로 오기, Python 본문 미실행. 고정 경로 수정.
- `fixture_results_udp_expectation.json`: private-loopback UDP 의미에 대한 기대 오류. 파일 차단 실패나 호스트 전달은 관측되지 않음.
- `fixture_results_signal_expectation.json`: wrapper의128+signal 전달을 native negative returncode와 혼동한 기대 오류. raw143을 보존하고 기대 수정.

실패 시 후속 case를 중단했다. 따라서 중간 실패 run에서 목록에 없는 후속 case도 NOT_RUN이며 최종 통과로 과거 실패를 지우지 않는다. final `fixture_results.json`에 ID/목적/Fixture/격리/기대/실제 rc·signal·timeout·시간·오류·로그·정리와 evidence 경로를 기록했다. 재현은 호스트 일반 사용자로 `python3 -B validation/dart-sandbox-isolation-v1/scripts/verify.py`; 도구 sandbox의 외부 실행 승인은 별개다. 실패 시 nonzero를 반환하도록 runner를 보완했다(동일 성공 경로의 보고 결과는 변경하지 않음).

## 무결성 및 실제 라이브러리 비실행

`integrity.json`: 전후 **54,455개 기존 파일 변경·누락0 / 기존 범위 신규0 / main HEAD·status 동일 PASS**. 새 task와 실험 handoff만 허용 변경으로 제외했다. 이전 54,436과 대상 범위가 다르다. raw/full manifest는 work에만 유지한다. SHA/Build-ID와 readelf만 사용한 새 `elf_review.json`에서9개 ELF 동일성을 재확인했다. B/C External 예상 경로2개는 계속 누락이며 RUNPATH 끝 빈 항목도 남아 있다. 파일 이동/수정이나 암묵적 대체는 하지 않았다.

실제 DART Core/External/Bullet/Gazebo plugin을 링크·dlopen·dlclose·ldd하지 않았다. 실제 객체 생성/삭제, 예외 경로, OFF/ON, Gazebo, World::step, Probe A~D, Stage B는 실행하지 않았다. 성공 Fixture의 maps에서 대상 라이브러리가 없음을 확인했다. 기존 AI 기능·Export·Clock/Capture·solver·production·시스템은 변경하지 않았다.

## 판정과 다음 최소 작업

**SANDBOX_ISOLATION_PARTIAL**: 제한된 파일 쓰기·IPv4 네트워크·PID·프로세스별 자원 제한의 강제 효과는 확인됐지만 전체 자원 총량/갑작스러운 supervisor 종료/추가 socket 노출 검증이 남는다. **Probe A BLOCKED, B~D BLOCKED**다. sandbox 성공만으로 init/fini/TLS/IFUNC/thread shutdown·allocator·EH·중립성을 확정하지 않는다. 정확한 전체 closure/provider와 A용 native fixture/source/imports/loader 이전 제한 적용 검토도 별도 필요하다(`probe_a_readiness.json`).

다음 최소 작업: 무해한 Fixture로 **tmpfs·출력 총량과 전체 PID/resource 한계, supervisor 독립 abrupt-death, IPv6/UNIX socket 노출**을 검증하거나 이를 충족하는 별도 disposable 환경을 준비한다. 그 뒤 exact closure/init-fini 및 A native fixture를 검토해 별도 승인 요청 가능 여부를 재판정한다. Runtime을 자동 실행하지 않는다.

## Git와 이동

검증된 신규 scripts/tests/경량 reports와 handoff만 명시적으로 stage/diff 검토/commit/push한다. 실제 SHA·push·원격 일치 결과는 로컬 `git_publication.json`과 최종 응답에 기록한다. 자기 SHA를 위한 재귀 commit은 하지 않는다. `/tmp` raw/work·ignored/untracked 원본은 Git으로 다른 기기에 자동 전달되지 않는다. main/force push/reset/stash/rebase/merge, 계정 변경·기존 프로세스 종료는 하지 않는다.
