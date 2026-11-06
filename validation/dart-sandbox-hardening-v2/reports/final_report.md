# Aero AI Studio — Sandbox Isolation Hardening V2

## 최종 결과

**SANDBOX_ISOLATION_PARTIAL / Probe A BLOCKED / Probe B~D BLOCKED / NOT_RUNTIME_VERIFIED / Stage B BLOCKED.** 제한 tmpfs, 독립 supervisor 강제 종료, IPv6·UNIX socket과 여섯 가지 실패 주입을 검증했다. 전체 프로세스 자원 한계는 현재 환경에서 확립하지 못했으므로 준비 완료로 승격하지 않는다.

실험 worktree `/tmp/AeroAIStudio-dart-internal-trace`, branch `experiment/dart-internal-trace`, 시작 local/remote SHA `757f3a1c043fd12e7683d3244e4ab4466198ac2e` 일치와 clean 상태를 확인했다. main은 `46134c6bf5670ed61ba252f394ccdddb7ff2cf6b`, 기존 수정8/미추적31/staged0을 보존했다. AGENTS·DEVELOPMENT_RULES·handoff·V1 final/test/verdict 및 Probe Readiness final을 읽었다. V1의18 PASS/2 SKIP·54,455파일은 이전 결과이며 이번 합계에 더하지 않는다. V1 snapshot의91ee5f7은 게시 전 값이고757f3a1의 파일 목록과 연결된다.

## 자원 한계와 cgroup

`resource_limits.json`, `cgroup_capabilities.json`에 관측 범위를 구분했다. 승인된 호스트 일반 UID1000의 cgroup v2 경로는 일부 파일/디렉터리가 쓰기 가능하지만 `cgroup.subtree_control`은 비어 있고 controller는 memory/pids만 보이며 `cpu.max`는 없다. 사용할 수 있는 active task leaf와 CPU controller 위임이 확인되지 않았다. 기존 cgroup·controller·권한·정책에는 쓰지 않았다. 단순히 파일 쓰기 권한이 있다는 이유로 aggregate 한계 적용 가능이라고 하지 않는다.

CPU2초/AS256MiB/FSIZE64KiB/NOFILE64/core0은 bwrap 이전, NPROC512는 namespace 이후 본문 이전의 **프로세스별/UID 공유 제한**이다. 실제 READY 기록에서 설정값을 확인했다. V1 CPU/memory/file pressure는 역사 결과이며 이번 재실행으로 합산하지 않는다. 종료 직전 여섯 process의 RSS 합/CPU ticks를 기록했지만 공유 페이지 중복과 순간 관측의 한계가 있다. 이는 전체 사용량 quota가 아니다.

이번 구성은 호스트 root 전체 bind 대신 fresh root tmpfs16MiB에 `/usr`와 자체 Fixture만 읽기 전용 allowlist로 노출한다. setup 후 root와 `/dev`를 읽기 전용으로 바꾼다. private `/tmp`4MiB, `/run` 출력4MiB, `/dev/shm`1MiB를 설정했다. payload의 writable tmpfs 설정 총량은9MiB다. `/tmp`와 `/run`은 여러64KiB 파일을 최대80개까지 쓰는 유한 테스트로 **4MiB에서 실제 ENOSPC**를 확인했다. `/dev/shm`1MiB는 설정만 했고 고갈 시험은 하지 않았다. writable host bind를 없앴으므로 Fixture는 host disk에 임의 출력 파일을 만들 수 없다. 부모의 유한 stdout/stderr 로그는 별도 host 파일이며 디스크 전체 quota를 주장하지 않는다.

**전체 memory/PID/CPU 강제 한계3개는 SKIP**이다. 자식 개수·메모리·CPU를 무제한 증가시키는 시험은 하지 않았다. 용량 초과는 Fixture가 ENOSPC를 포착하고 결과를 기록한 뒤 정상 종료한다. aggregate OOM/PID/CPU 초과 시 동작은 미검증이다.

## Supervisor 종료와 정리

호스트 verifier→자체 supervisor→bwrap/reaper→Fixture→자식→손자의 생성 관계를 host PID/PPid/start identity로 관측했다. 비정상 종료는 supervisor만 SIGUSR1로 통지해 `os._exit(17)`, SIGKILL은 **supervisor PID 하나만** 종료했다. group 전체를 죽여서 parent-death 검증을 대체하지 않았다.

bwrap `--die-with-parent`와 PID namespace, verifier subreaper를 함께 사용했다. 두 독립 종료 case에서 관측6개의 모든 identity가 없어졌고 zombie entry도 남지 않았다. verifier는 자신의 adopted child만 wait/reap했다. 기존 사용자 프로세스나 서비스를 종료하지 않았다. 정상 종료/timeout124/비정상17/SIGKILL−9/임시 host 로그 디렉터리 정리/후속 fresh 정상 재실행이 통과했다(`supervisor_termination.json`).

이 검사는 한정된 무해한 tree와 관측 시간에 대한 결과다. 임의 hostile executable·cgroup aggregate containment로 일반화하지 않는다. Timeout case는 supervisor가 자기 bwrap을 종료하고 기다린다. 독립 abrupt case가 전체 descendant disappearance를 확인하는 주 증거다.

## IPv6·UNIX socket

호스트 전용 IPv6 loopback listener, pathname UNIX socket, abstract UNIX socket을 만들고 **호스트 positive control 세 개 모두 connect/echo 성공**을 확인했다. 외부 서비스는 사용하지 않았다.

Sandbox IPv6 내부 `::1` echo는 성공했고, 호스트 `::1` listener는111/ECONNREFUSED였다. 문서용2001:db8::1 TCP/UDP는101/ENETUNREACH로 외부 전송이 차단됐다. net namespace가 호스트와 다름을 본문 전에 검사했다.

호스트 pathname socket은 호스트에 실제 존재·동작하지만 sandbox에서는 fresh root와 private `/tmp`로 원래 경로를 노출하지 않아 ENOENT다. 따라서 호스트 자체 파일 부재에 따른 실패가 아니라 **mount 구성으로 숨긴 경로**라는 증거가 있다. read-only bind만으로 socket connect가 차단된다고 주장하지 않는다. 동일 abstract 이름도 별도 net namespace에서 ECONNREFUSED였다. sandbox 내부 `/tmp/internal.sock` echo는 성공했다. 호스트 listener의 sandbox 이후 수신은 모두0건이다(`socket_isolation.json`).

## Fail-Closed와 테스트 집계

여섯 주입 case 모두 CASE_ENTERED 없이 nonzero로 종료됐다(`fail_closed.json`).

|조건|실제 확인|판정|
|---|---|---|
|Namespace 설정 오류|bwrap invalid namespace option 거부|PASS — 설정 거부 범위|
|Mount 실패|존재하지 않는 bind source로 setup 중단|PASS|
|Network 격리 누락|의도적 share-net을 inode gate가90으로 거부|PASS|
|자원 제한 불일치|유효한 AS128MiB를 요구256MiB와 비교해91로 거부|PASS|
|Supervisor 초기화 오류|주입된 startup 오류71, bwrap 미실행|PASS|
|임시 디렉터리 준비 실패|regular log file 아래 mkdir ENOTDIR,72, bwrap 미실행|PASS|

실제 kernel namespace 생성 syscall 자체를 실패시키는 주입은 하지 않았다. 설정 거부와 구분해 **1 SKIP**으로 남긴다. 또한 현재 fixture는 한정된 검증용이며 실제 target에 필요한 aggregate 조건이 없는데 target을 실행하는 fallback launcher를 제공하지 않는다.

최종 신규 Fixture **14 PASS / 0 FAIL**, 오프라인 검사 **6 PASS / 0 FAIL**, 추가 **4 SKIP**(aggregate3 + kernel namespace failure1): **20 PASS / 0 FAIL / 4 SKIP**. 최초14 PASS도 `fixture_results_initial.json`에 보존했다. 이후 실제 AS mismatch gate와 RSS/CPU 관측을 추가한 최종14 PASS를 별도로 기록했고 합산하지 않는다. 이번 단계에 관측된 실패 run은 없다. 의도한 차단 nonzero는 계약 검증 PASS이며 실제 작업 성공을 뜻하지 않는다.

재현: 호스트 일반 사용자에서 `python3 -B validation/dart-sandbox-hardening-v2/scripts/verify.py`, 오프라인은 `python3 -B -m unittest discover -s validation/dart-sandbox-hardening-v2/tests -p test_reports.py -v`. host 실행과 도구 sandbox 승인 경계는 별개다.

## 기존 파일·라이브러리와 Probe A

`integrity.json`: 기존 **54,483개 파일 변경·누락0 / 기존 범위 신규0 / main HEAD·미커밋 상태 유지 PASS**. 새 작업 경로와 실험 handoff만 제외했다. 이전 Evidence·미커밋 코드·AI 기능·production·Clock/Capture·시스템 패키지와 설정을 보존했다. 원본 검사 full manifest는 work에만 두며 이전 수와 범위가 다르다.

실제 DART/Gazebo를 링크·로드·실행하지 않았다. dlopen/dlclose/ldd, 객체 생성/삭제, World::step, OFF/ON, Probe A~D 및 Stage B 모두 NOT_RUN이다. 성공한 Fixture의 maps에 대상 library가 없음을 확인했다. 설치 ELF identity는 보존된 V1 근거를 참조하며 이번에 `/usr` DART hash/Build-ID 재검사를 했다고 주장하지 않는다.

**Probe A BLOCKED**: aggregate 제어와 실제 kernel-failure gate 검증 외에도 exact dependency closure/provider, B/C External 예상 경로 누락, RUNPATH 빈 component, init/fini/IFUNC/TLS/thread shutdown 및 A native fixture 검토가 남는다. Destructor/Allocator·Exception/Unwinding은 HIGH/UNKNOWN 유지다. Probe B~D는 별도 검증 전 BLOCKED다. Sandbox 일부 통과를 runtime 안전성·실행 승인으로 취급하지 않는다.

## Git·다음 최소 작업

검증된 신규 경량 scripts/tests/reports와 handoff만 명시적 stage/diff 검토 후 실험 branch에 commit/push하고 원격 SHA를 확인한다. 실제 게시 결과는 로컬 `git_publication.json`과 최종 응답에 남긴다. 자기 SHA를 위한 재귀 commit은 하지 않는다. work/full manifests·바이너리는 게시하지 않는다. `/tmp` ignored/raw·main untracked evidence는 Git push로 다른 기기에 자동 전달되지 않는다.

다음 최소 작업은 **기존 정책을 바꾸지 않고 사용할 수 있는 active memory/pids/cpu controller가 위임된 전용 task 환경 또는 disposable 환경을 확보**하고, aggregate 자원 초과 처리와 실제 kernel namespace 실패 gate를 무해한 Fixture로 검증하는 것이다. 그런 환경을 확인하기 전 같은 RLIMIT 테스트를 반복해 전체 제한을 인증하지 않는다. 이후 A의 exact closure/init-fini/native fixture를 검토하고 별도 실행 승인 준비 여부를 판정한다. 이번 종료 뒤 Runtime을 자동 실행하지 않는다.
