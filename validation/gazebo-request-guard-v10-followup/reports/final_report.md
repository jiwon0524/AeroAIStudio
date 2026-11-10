# small-02 이후: Bubblewrap 재사용 검토와 차단된 진단 후보

관측 2026-11-10T12:11:45.747002+00:00; 시작 HEAD `cecac03db4c0471b8444bd1a961459fd51f3bbdc`,
branch `experiment/dart-internal-trace`. context-handoff 사용. 현재 요청은 조사·근거 있는 구현·빌드·정적/모의 검사까지다.
**결론: 기존 bwrap 경로를 단순 연결해 모든 신뢰 조건을 유지한다는 근거가 부족하다. Adapter는 구현/활성화하지 않았다.**
대신 별도 followup 경로에서 매핑 I/O 진단과 단일 조회 소유권 관측기를 준비했다.
Python CLI/run_once/collector_stage와 빌드된 native entry는 모두 서비스 시작 전에 무조건78이다.
새 실행 계약·unit·marker·실행 명령은 제공하지 않는다. 이전 PASS는 격리 경로에만 적용한다.

## 실행 당시 증거와 현재 정책

small02 원본 runtime_small_02_report.md, approval_proposal.md, 원본13 runtime 파일·소스·계약을 읽고
hash를 대조했다. native PID377856/start50665745는 userns0 다음 uid-map -1/errno1로 종료했다.
실행 당시 kernel audit(2026-11-10 20:47:03 KST, audit1794311223.360:974/975)에는 같은 PID에
unconfined→unprivileged_userns 전환과 capability21/sys_admin DENIED가 있다.
현재 정책 파일은 bwrap 자체에 userns/capability를 허용하고 payload에는 bwrap//&unpriv_bwrap의
capability 거부를 적용하는 구성을 담고 있다. 현재 host sysctl restrict_userns=1, userns_clone=1,
max_user_namespaces=115757. bwrap mode0755/root 소유, hash는 이전 PASS의 고정값과 같다.
이 정책 파일은 **현재 디스크 관측**이고, 과거 전체 로드 정책 snapshot이 아니다.
로드된 profile 목록 읽기는 권한 거부라 UNKNOWN. 기록/현재 관측은 reports/policy_observation.json.

own_map 기존 구현은 open/write/close를 합쳐 반환하므로 과거 실패 syscall은 확정 불가하다.
AppArmor 거부는 실제 당시 증거이고 mapping write 거부를 강하게 지지하지만, 이번 준비로 과거 호출을
open 또는 write로 소급 확정하지 않는다. UID/GID 매핑, LSM/capability 제한은 우회하지 않았다.

## 호출 순서와 프로세스 배치 대조

기존 통과: systemd user unit512MiB → Python stage(입력 RO FD/hash 확인) → /usr/bin/bwrap
--unshare-all/--cap-drop ALL → namespace/mapping/root 구성 → bwrap PID1 init → fd_bridge/harmless payload.
비특권 bwrap는 자식 namespace 안에서 UID→setgroups deny→GID 매핑을 한다. 부모가 대신 매핑해서
성공했다고 해석하지 않는다. Ubuntu 설치 binary와 당시 hash는 일치하나 mapping syscall trace와 당시
AppArmor label 전체는 없었다. 원본 stdout/stderr/result와 PASS summary hash는 다시 일치 확인했다.
참고 upstream0.9.0: https://github.com/containers/bubblewrap/blob/v0.9.0/bubblewrap.c
(write_uid_gid_map, raw_clone, unprivileged child mapping, PID1 do_init). Ubuntu 패치 전체의 실제 분기 실행 증거와는 구분한다.

small02 요구 배치: owner/collector5GiB unit의 collector → sealed native bootstrap parent →
직접 자식인 동일 sealed ELF PID1 worker. held pidfd+SCM credential/parent PID/start/ELF/cgroup 인증 후 O ACK,
실제4 sealed object C×4/K → held probe P/target512MiB 배치·rlimit/cgroup 검증 → independent audit/A → GO →
EXIT_ACK/callback → all-dead/COMPLETE/ECHILD/EOF → target 정리+원본 무결성+pin 해제 → V → parent wait0 → owner 정리.
현재 native 경로는 userns 직후 self UID mapping에서 이 순서가 중단된다.

|신뢰 조건|기존 bwrap 단순 연결의 판정|
|---|---|
|owner PID/start·pidfd·직접 부모·봉인 ELF|**차단**. 기본 payload는 PID1이 아니며 bwrap init/monitor가 끼어든다. --as-pid-1도 bootstrap parent가 동일 native ELF라는 증거를 만들지 않는다. 실제 기존 Owner.bind를 mock한 검사에서 PID2/부모 ELF/ppid/worker ELF/domain mismatch는 모두 O 이전 거부했다.|
|sealed RO FD C/K와 동일 객체 mount|**미입증**. 이전 ro-bind-fd는 hash-pinned source FD mount였다. 같은 sealed memfd/seals/hash/dev+ino, collector retained pin, SCM identity, canonical mount 검증·K를 새 배치에서도 보존해야 한다. 이전 PASS가 이 전달을 증명하지 않는다.|
|owner/collector5GiB와 target512MiB|**미입증**. 이전 단일512MiB unit 그대로는 불충분. 기존 anchor invocation receipt→held P/attach→target readback→cleanup 경계를 새 배치로 증명해야 한다. 한도를 합치거나 올리지 않았다.|
|independent audit 전 GO 차단|**요구 유지, adapter 미입증**. stdout fixture_ready나 bwrap 시작만으로 O/C/K/P/A를 대신하지 않는다. 기존 실제 Python coordinator mock 회귀에서 순서와 input-audit catch-up을 검사했다.|
|종료까지 감사·정리|**요구 유지, adapter 미입증**. bwrap init의 wait만으로 native task/descendant tracking, COMPLETE/EOF/ECHILD/V·pin 해제를 증명하지 못한다. 누락 회귀는 계속 실패한다.|
|native namespace/mount bootstrap|**현재 직접 연결 차단**. cap-drop ALL과 현재 payload capability 거부 아래서 기존 중첩 userns/mount API를 그대로 계속할 근거가 없다. bwrap 자체의 setup 허용을 payload의 권한으로 오인하지 않는다.|

따라서 bwrap를 앞에 붙이고 PID1/ELF 검사나 audit gate를 완화하는 연결을 만들지 않았다.
향후 별도의 factory/ownership ABI 설계가 필요할 수 있지만, 여기서는 그 동등성/실제 kernel 권한 증거가 없다.
기존 작은 bwrap mount 목록에는 새 native control ELF/libcrypto closure도 없어 단순 payload 교체로 실행 가능하다고 주장하지 않는다.
상세 기계 판정: reports/trust_conditions.json. 이는 모든 가능한 재설계의 불가능성 증명이 아니라 **현재 경로의 직접 재사용 차단**이다.

## 해결한 준비 항목

1. **즉시 errno가 분리된 mapping I/O**: 새 inputs/map_io.h를 실제 launch.c의 own_map adapter에 연결했다.
   uid-map/setgroups/gid-map 각각 open의 FD/errno, write의 실제 return·requested length/errno,
   close의 return/errno를 V10IO로 기록한다. 각 errno는 logging/close 전에 저장하며 각 호출 전 errno0을 설정한다.
   open evidence 저장 실패이면 write하지 않고 FD를 한 번 정리하고 실패한다. write 실패 뒤 close/log 실패가
   나도 write errno를 반환한다. short write는 EIO, 단독 close 실패는 해당 errno, diagnostic 누락은 실패다.
   기존 journal과 분리,192byte 미만 frame, process당32레코드 cap은 유지한다. 정책 거부 자체를 해결한 것은 아니다.
2. **unit ownership 별도 조사**: host 원본에는 incomplete-before → 유효 invocation/cgroup →
   incomplete-after가 있다. cleanup_errors[]이므로 기존 host reason은 cleanup 덮어쓰기가 아니라 main try에서
   발생한 ownership 실패다. 그러나 로그용 manager.inspect와 owned() 내부 재조회가 달라 실제 실패 row는
   보존되지 않았다. mock으로 로그 row≠판정 row를 재현했다. lifecycle teardown 관측으로 설명 가능하나
   실제 fresh row의 어느 필드가 실패했는지는 미확정이며 native uid-map과 global 시간 순서도 확정하지 않는다.
3. **단일 조회 관측기 준비**: ownership.inspect_bound는 정확히 한 번 읽은 row를 저장하고 그 row만 검사한다.
   저장 실패·불완전 identity·invocation/cgroup/cap 변경은 거부한다. starting/teardown을 성공으로 바꾸거나
   대기/재시도/stop을 허가하지 않는다. live driver에 연결하지 않은 순수 관측기다. 이후 실제 action 전에는
   별도 fresh invocation/PID binding이 여전히 필요하다.
4. **최초 실패 보존**: C 모의 검사에서 write EPERM 뒤 close EBADF와 emitter errno 변경을 주입해도
   EPERM을 유지했다. Python Failures는 native/collector/host별 첫 failure, 후속 failure, cleanup을 분리한다.
   서로 다른 프로세스의 첫 event를 가짜 전역 시간 순서로 합치지 않는다.
5. **진입 차단**: 새 Python driver 모든 mode78, native entry.c 무조건78. objdump main은 mov0x4e/ret.
   서비스/marker API가 없는 facade이며, 진단 bootstrap API를 연결한 런타임 entry가 아니다.

## 빌드·정적·모의 결과

launch.c와 inert entry.c **2 TU compile/link**, 기존8 객체/probe hash와 dependencies 확인 재사용.
별도 callback-only C mock을 빌드했다. 이 mock은 실제 open/write/close/userns/mount/service를 호출하지 않고
fake callbacks만 사용하는 map_io.h 단위 검사다. 동적 imports에서도 관련 namespace/map 함수 부재를 확인했다.
**최종 Python/static/mock 84 PASS + C callback14 cases PASS**.
기존 Owner.bind, C×4/K/P/A/GO/ACK/V Python coordinator와 cleanup/sequence/audit/FD 실패 회귀도 실제 함수를 mock 경계로 검사했다.
기존 check.py 전체는 실행하지 않아 과거 보고서를 덮어쓰지 않았다. 역사적2194 PASS를 이번 실행 수로 더하지 않았다.
C callback mock은 보고 metadata 보정/단일 조회 검사 추가 과정의 총3회(최종14 distinct cases)이며,
owner ELF/probe/bwrap 실행0, mapping 파일 open0, 서비스0, marker0, physics0이다.
첫 두 mock 결과는 work/tests-initial.json, tests-before-single-read.json에 보존했다.

현재 호스트에서 native UID-map diagnostic가 실제 어느 syscall EPERM을 포착할지, namespace/ptrace/LSM/SCM/mount,
O/C/K/P/A 및 실제 target placement·독립 task audit·EOF·invocation cleanup 정상 경로는 **실제 실행에서만 확인 가능**하다.
이번에는 어느 것도 실행하지 않았다. 무해1회 승인안을 새로 제시할 준비가 된 상태가 아니다.

## 소스·산출물 SHA256

|새 소스/검사 경로|SHA256|
|---|---|
|`inputs/entry.c`|`3bcaf3bb6dc594a340b39eba8b90797855c4d6c70ea7ba2f9dc9d41e67c144ff`|
|`inputs/launch.c`|`90a7b2292bc6293c589f5be59cc5775a37a948ee57c7f8fe9428f3ae97b9cc6d`|
|`inputs/map_io.h`|`33d4f0c87b96cd45f5a20262917c4319a31c9b2bd853f1cb8db4ce206008c1b7`|
|`scripts/build.py`|`9d66df6fc3840f8b4e204581335f5f7cdd5272c6bbd66f41b27e884838019a4e`|
|`scripts/driver.py`|`24996c92c69709ab8223a99aaa30e19139e675106eecaa0d4ed74051f3a6784b`|
|`scripts/map_records.py`|`de744bf9cd5478793b78f15d65dbadddba705a47058e475494c31737971ba315`|
|`scripts/ownership.py`|`4cbe4743b19dcdd63d2165f3680321970ccc433c6577ce432084083df3f6346a`|
|`tests/check.py`|`92914b26e863c62042187f7c4b6f1ccfc79f3e85b328ba293d0477c025a61d19`|
|`tests/map_io_mock.c`|`e82917f5708a643dc789513221dff735c3086874e38bd29ad25468c2c388352d`|

|로컬 ELF 경로|bytes|SHA256|
|---|---:|---|
|`/tmp/AeroAIStudio-dart-internal-trace/validation/gazebo-request-guard-v10-followup/work/build-20261110T120244581950Z/owner-blocked`|85120|`e3a67775d63bcd3229c8652fb94d62b6d07268ecb3443e6e40d93722db03335c`|
|`/tmp/AeroAIStudio-dart-internal-trace/validation/gazebo-request-guard-v10-followup/work/build-20261110T120244581950Z/map-io-mock`|16872|`021006fd61d66a71a087b48b39862b18e23f86195a6f4d459d8e70b5691041db`|

Compiler argv·입력/object hash·PID/start/종료 및 objdump 근거는 reports/build_receipt.json;
개별 검사/모의 프로세스 identity는 reports/tests.json; source hash는 reports/source_manifest.json.

## 보존과 최종 중단

기존 v10/small02/이전 PASS **377 파일** content/mode, main nonignored **303 경로**,
small02 계약119 hash 및 기존1617 tracked baseline(handoff 제외) 모두 일치. 원본 marker/raw 로그/소스는 변경하지 않았다.
main ignored evidence 전체는 새로 inventory하지 않았으며 main에 쓰지 않았다.
현재 small02 unit 둘 not-found/MainPID0/ControlGroup empty; same-user project-CWD snapshot에 작업 없음,
remote/external-CWD UNKNOWN. 원래 dirty plugin symlink도 게시 대상에서 제외한다.
새 파일은 followup/와 handoff뿐이다. raw binaries/compiler logs/ignored /tmp evidence는 Git 게시만으로
영구 보관되거나 다른 기기로 전달되지 않는다.
**서비스 시작 전 exit78 / Stage B BLOCKED / 위험 수용 미결정 / Gazebo 런타임 미검증**.
기술 차단은 유지하며, 승인 없는 새 실행·marker 소비·AppArmor/시스템 정책 변경·권한 상향·sudo를 하지 않는다.
