# Cgroup Inheritance & Bubblewrap Integration V1

## 판정과 범위

현재 fixture 검증 **CGROUP_BWRAP_INTEGRATION_VERIFIED**. Probe A **NEEDS_ADDITIONAL_EVIDENCE**, B~D 기존 BLOCKED. **NOT_RUNTIME_VERIFIED / Stage B BLOCKED**는 실제 DART/Gazebo에 대한 판정이다. 무해 Python fixture 실행 결과를 DART Runtime 인증으로 사용하지 않는다. integrity 및 최종 test 결과는 아래 연결 파일을 따른다.

원본 main을 수정하지 않고 `/tmp/AeroAIStudio-dart-internal-trace`, branch `experiment/dart-internal-trace`, 시작 HEAD `b60d9f9c991579ac4694d108e10e8166f942392e`에서 작업했다. AGENTS·DEVELOPMENT_RULES·handoff, Smoke V1의 final/resource/controller/verdict, Hardening V2 및 Delegation Readiness 보고서를 실제 코드와 대조했다. context-handoff 스킬을 사용했다. 이번 사용자의 명시 승인만큼 무해 부모1/자식1/손자1 및 transient service/Bubblewrap 조합으로 범위를 확장했다. 초과부하·native library·Probe 실행 승인은 없다.

## 부모·자식·손자 및 제한

|조건|부모 host PID|자식 host PID|손자 host PID|총 cgroup tasks|결과|
|---|---:|---:|---:|---:|---|
|일반|184962|184963|184966|3|PASS|
|Bubblewrap|184985|184988|184993|5(추가 bwrap2)|PASS|

일반 unit `aero-cgroup-integration-v1-inheritance-7f636a97af.service`; Bubblewrap unit `aero-cgroup-integration-v1-bubblewrap-9a977f6fbc.service`. 두 cgroup은 각각 `/user.slice/user-1000.slice/user@1000.service/app.slice/<unit>`이다. 프로세스마다 host `/proc/PID/cgroup`, PID/start identity, NSpid를 기록하고 실제 `cgroup.procs`, `cgroup.threads`와 대조했다. Bubblewrap 내부 PID2→3→4, PPid1→2→3를 host PID와 연결했다. 내부 `0::/`는 private cgroup namespace의 상대 경로이며 host cgroup 이탈이 아니다. bwrap host PID184983/184984도 같은 leaf였다.

두 조건 모두 memory.max **67108864**, memory.swap.max **0**, pids.max **8**, cpu.max **25000 100000**을 직접 읽었다. systemd MemoryMax64M/TasksMax8/CPUQuota25%와 일치한다. 실제 readback 시 memory.peak는 일반 **19746816B**, Bubblewrap **20856832B**로 한계 이하였다. CPU quota는 한 CPU25% bandwidth이며 강제 종료나 전체 CPU load 시험 결과가 아니다. memory.events의 max/oom/oom_kill은 모두0. 초과 시 OOM/PID 거부/CPU throttling은 이번에 시험하지 않았다.

사전 메모리 검토는 동일 import의 post-exec `/proc/self/status` VmHWM×3+8MiB 여유로64MiB 미만일 때만 통과한다. 이는 메모리 peak 보장이 아닌 보수적 시작 조건이며 실행 중 실제 memory.peak를 별도 읽었다. 제한 상향은 없었다.

## Bubblewrap 격리와 Fail-Closed

Hardening V2의 fresh tmpfs root, `/usr` readonly, user/mount/PID/network namespace, die-with-parent/new-session, private proc/dev, 환경 clear, prlimit CPU2s/AS256MiB/FSIZE64KiB/NOFILE64/CORE0 구조를 재사용했다. project 전체를 `/project` readonly로 추가하고 fixture와 **own leaf cgroup만** `/fixture`, `/limits` readonly로 연결했다. 임의 host root나 writable host bind는 없다. 내부 readable project는 비밀정보 읽기 방지까지 보장하지 않으며, 실제 native 실행 전 읽기 allowlist 재검토가 필요하다.

각 프로세스는 namespace·readonly·tmpfs 용량·실제 leaf 제한·금지 library 미로드 gate를 검사한 뒤에만 본문에 진입한다. 일반 fixture도 정확한 cgroup/limit gate 후 spawn한다. namespace 또는 membership mismatch의 mock gate는 본문을 거부했다. 실제 kernel namespace 생성 실패 주입은 하지 않았다.

- host와 다른 mount/net/user/PID namespace 확인; 세 Python은 동일 sandbox namespace 사용.
- project canary와 fixture에 O_WRONLY open 시 **EROFS(30)**. 실제 파일 내용 수정은 시도하지 않았다.
- `/tmp`, `/run` 각각4MiB, `/dev/shm`1MiB statvfs 용량 gate; root16MiB readonly. `/tmp`·`/run` own file 쓰기/삭제만 성공. 이번 결합 시험에서 ENOSPC까지 채우지 않았다. Hardening V2의 과거 ENOSPC 증거를 새 실행으로 합산하지 않는다.
- private network의 IPv4/IPv6 문서용 외부 주소 connect **ENETUNREACH(101)**; host IPv6 loopback listener **ECONNREFUSED(111)**.
- host filesystem UNIX socket은 숨겨져 ENOENT(2), abstract UNIX socket은 ECONNREFUSED(111). fixture 전에 host IPv6/UNIX/abstract socket positive control3개 모두 성공했고 sandbox에서 host listener에 전달된 연결0.
- 숨긴 host canary/socket path 부재 gate 확인. 이는 모든 가능한 host socket의 보편적 안전성 증명이 아니라 승인된 canary와 namespace/allowlist 구성 검증이다.

## 정상 종료·정리·controller 비교

일반2.418초, Bubblewrap2.633초 내 정상 종료(정확한 stderr runtime은 case JSON 참조), systemd-run exit0/mainexit0/resultsuccess다. RuntimeMax8초/TimeoutStop2초/KillModecontrol-group/Delegate=no를 유지했다. timeout이나 강제 stop/SIGKILL 주입은 없었다. timeout 설정의 강제 효과는 이번 실행에서 검증하지 않았다.

두 최종 unit LoadState=not-found, leaf cgroup 제거, 관측한 host PID/start 잔여0. host socket/temp directory와 project canary 삭제를 확인했다. fixture 자식은 wait로 정리한다. 기존 서비스 종료·controller 수동 복구·systemd manager 재시작은 없었다. 새로운 unique unit과 fresh one-shot 디렉터리로 재실행 가능하도록 설계했지만 같은 attempt의 재실행은 거부한다. 이번 완료 후 추가 실행은 자동 시작하지 않는다.

user manager running·ControlGroup은 전후 동일하다. manager tree+상위·직접형제 **78개 경로/6개 선택 설정**을 비교했다. 각 실행 중 기존22개 경로43개 필드에서 systemd CPU controller 자동 활성화가 발생했다. CPU controller 추가와 기본 unlimited cpu.max만 사전 허용했으며 memory/pids 유한 한계 변화는 없었다. **각 종료 후 및 전체 종료 후 변경0**. 자동 복원됐으며 수동 복구 필요 항목0. 모든 정책·사용량 전체 동일성을 주장하지 않는다.

## 초기 실패와 수정 후 재검증

1. namespace 단위 테스트 최초7PASS/1FAIL: 올바르게 추가한 RLIMIT gate가 먼저 거부했다. namespace 테스트에 정상 RLIMIT를 mock했고 gate는 완화하지 않았다. `offline_tests_initial.log` 보존.
2. host 사전검사: ru_maxrss가 실행 도구 부모의 high-water699104KiB를 물려받아 중단, service생성0. 별도 실제 post-exec VmHWM/VmRSS12772KiB와 불일치를 확인해 VmHWM 측정으로 수정했다. `preflight_initial_failure.json`.
3. 최초 일반 unit은 mainexit0/runtime2.529s였으나 stdout이 journal로 가서 collector가 기록을 못 받았다. unit이 종료된 후 읽은 limit은null이어서 수집 FAIL. journal에서3역할·같은 cgroup·gatePASS를 복구했지만 live cgroup.procs는 없으므로 최초 실행을 완전검증으로 승격하지 않았다. `initial/`, `journal_recovery.json`, `initial_evidence_hashes.json` 보존.
4. --pipe만 추가한 별도 명시 one-shot revalidation에서 일반/Bubblewrap 모두 통과했다. 원래 attempt marker는 유지, 자동 retry loop는 없다. 최초1unit+재검증2unit=총3개 own service를 만들었고 각 계층은 최대3Python이었다.
5. evidence unittest가 진행 중인 hash job보다 먼저 실행되어14PASS/1ERROR(FileNotFound)였다. 테스트 기준 수정 없이 integrity 완료 후 재검증한다. `tests_before_integrity_complete.log` 보존.

## 테스트·무결성·게시

실행 명령은 각 case JSON의 `command`(이번 소유 fixture argv만; 타 프로세스 원시 명령행 수집 안 함)와 scripts에 있다. 단위/증거 테스트: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s validation/dart-cgroup-integration-v1/tests -p 'test_*.py' -v`; 기존 smoke/hardening 각각의 tests 경로에서도 동일 unittest discover를 실행했다. 최종 수치는 `test_summary.json` 및 `tests_final.log`를 따른다. 실행하지 않은 resource 초과3·kernel namespace failure·supervisor SIGKILL은 SKIP이며 과거 통과를 재실행 수로 합산하지 않는다.

보존 범위와 실제 파일 수는 `integrity.json`: main 전체와 실험 기존 파일을 해시하고 새 task·실험 handoff·.git·pycache만 제외했다. 기존 source/보고서/evidence와 main HEAD/status 보존을 확인한다. 실제 package/AppArmor/global loader/system library/production/Clock/Capture 변경 없음. `scripts/preserve.py`와 work의 full manifest로 재현 가능하다. 원본 main의 handoff도 변경하지 않는다.

새 task scripts2개, fixture/tests3개, 경량 reports 및 실험 handoff만 게시 대상이다. work/full manifest/raw logs는 제외한다. `/tmp` 로컬·ignored/untracked 증거는 GitHub push로 자동 이전되지 않는다. 실제 push 및 원격 일치 SHA는 로컬 `git_publication.json`과 최종 응답을 따른다.

## Probe A 재평가·다음 계획

**NEEDS_ADDITIONAL_EVIDENCE**. sandbox/cgroup 결합·제한 설정·상속·정상 종료는 검증됐다. 초과 강제 효과와 실제 kernel namespace 실패 주입은 미검증이다. DART exact transitive dependency closure, RUNPATH 빈 항목, dlopen init/fini, native fixture/allocator/exception 경계는 기존 잔여 위험이다. B~D는 기존 BLOCKED. Python fixture의 `maps` 검사만으로 DART load의 안전성을 주장하지 않는다.

**다음 최소 작업: Runtime 없이 Probe A의 정확한 의존성 경로·RUNPATH·dlopen 초기화/종료 및 전용 native fixture를 정적으로 감사하고, 별도 실행 승인에 필요한 잔여 증거를 좁힌다.** 이번 범위를 마친 뒤 이를 자동 시작하지 않는다. 압력·kernel failure 또는 Probe A 실행은 각각 별도 구체 승인 사항이다. 실제 DART/Gazebo·World::step·Stage B는 실행하지 않았다.
