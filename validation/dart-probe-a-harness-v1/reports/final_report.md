# Probe A Native Harness Integration V1

## 1. 최종 판정과 실행 범위

**PROBE_A_HARNESS_NEEDS_EVIDENCE / NOT_RUNTIME_VERIFIED / Stage B BLOCKED**.

DART 정적 Allowlist, FD 기반 무결성 검사, 실제 systemd/Bubblewrap Native Fixture 연결, live mapped-file identity 검사, 본문 전 GO gate를 구현했다. 무해한 fixture 재검증은 정상 종료했다. **실제 DART/Gazebo library는 로드하지 않았고 Sandbox에도 노출하지 않았다.** DART 객체·World·step·Probe A~D·Stage B는 미실행이다. simulation open/close 이벤트는 실제 dlopen/dlclose가 아니다.

`map_files` 직접 FD open은 세 파일 모두 EPERM이어서 UNAVAILABLE이다. 별도 `/proc/PID/root` FD 경로에서 maps의 device/inode와 SHA/Build-ID는 일치했다. 이를 **PASS_FILE_IDENTITY**로만 기록하며 직접 map_files 접근이나 resident-page 동일성까지 PASS로 올리지 않는다. 실제 Core용 mount alias와 post-open 동기화 계약도 남아 있으므로 READY가 아니다.

## 2. 시작 상태·인계·소유 범위

`/tmp/AeroAIStudio-dart-internal-trace`, branch `experiment/dart-internal-trace`, 기준 HEAD **9d375b4b58aa6dc9d87afd436a0ddf1ebf671c27**, 작업 시작 clean을 확인했다. 원본 main HEAD46134c6bf5670ed61ba252f394ccdddb7ff2cf6b와 수정8개·미추적31개·staged0을 보존했다.

context-handoff 스킬·AGENTS·DEVELOPMENT_RULES·handoff, Static Audit의 final/dependency/identity/runpath/fixture/plan, Integration V1·Hardening V2와 실제 코드·파일을 대조했다. 이번 소유 변경은 새 `validation/dart-probe-a-harness-v1/`와 실험 handoff뿐이다. 원본 main, 기존 실험 root, production/AI 기능을 수정하지 않았다.

## 3. Allowlist와 FD 무결성

`library_allowlist.json`은 두 profile을 분리한다.

|profile|필수 파일|이번 사용|
|---|---:|---|
|installed_core_future_only|16|읽기 전용 정적 hash/Build-ID 검사만; 미마운트·미로드|
|harmless_fixture_only|3|native_fixture·libc.so.6·ld-linux만 실제 Sandbox에 FD readonly bind|

각 항목은 이름·절대/canonical 경로·symlink 최종 경로·SHA256·Build-ID·SONAME·DT_NEEDED·RPATH/RUNPATH·필수 여부·device/inode를 포함한다. Core source identity는 이전 정적 감사와 실제 file descriptor hash/Build-ID가 같아야 한다. A 설치본만 선택하고 로컬 Baseline/Trace와 ODE/Bullet/Gazebo optional plugin을 제외한다. B/C 예상 External 경로 누락과 후행 빈 RUNPATH는 이전 상태를 유지하며 자동 대체하지 않는다.

Manifest bytes의 SHA pin과 profile 필수 경로 집합, 중복 path·RPATH/RUNPATH 거부를 구현했다. 파일은 canonical absolute path·O_NOFOLLOW로 열고 SHA를 chunk 단위로 계산한다. Build-ID는 같은 FD의 ELF64LE/x86-64 PT_NOTE를 bounded pread로 파싱한다. 라이브러리나 동적 로더를 실행하지 않는다. FD의 size/mtime/ctime/device/inode가 읽기 전후 바뀌면 거부한다. descriptor identity/hash 불일치·파일 누락은 launch callback 전 예외로 중단한다. second profile 실패 때 먼저 연 FD도 닫도록 회귀 테스트했다.

Service stage는 검증한 fixture profile의 FD를 `--ro-bind-fd`로 넘기므로 검증 이후 pathname 재탐색으로 다른 inode가 bind되는 위험을 줄였다. read-only descriptor/bind가 host의 같은 inode에 대한 모든 외부 쓰기까지 봉쇄하는 것은 아니다. hash 검사 전후의 짧은 창 및 inode 내용 변경 가능성은 남아 있어 사후 재검사와 검증 시점 한계를 명시한다. 시스템 파일을 바꾸거나 immutable 속성을 설정하지 않았다.

생성·실행 전후 Core16/fixture3 file identity 검사를 통과했다(`allowlist_validation.json`). 실행된 manifest와 초기 manifest/binary를 각각 보존했다. 현행 allowlist/pin은 재검증 후 변경하지 않았다. 향후 필요한 NEEDED alias의 계획은 `future_dependency_alias_plan.json`에 **prospective only**로 분리했다. 절대 Core 경로만으로 전이 의존성 공급자가 고정된다는 주장은 하지 않는다.

## 4. Native Fixture·Supervisor·Sandbox

Static Audit의 `probe_a.c`를 byte 동일하게 `fixtures/base_probe_a.c`로 재사용하고, `harness_fixture.c`에서 loader를0으로 고정했다. 외부 loader macro 활성화는 compile error다. DART/Gazebo header/link는 없고 readelf 검사에서 dlopen/dlclose import도 없다. 기존 simulation workflow를 호출하므로 반환값의 의미를 실제 DART 성공으로 바꾸지 않았다.

기존 Integration V1의 systemd argv·cgroup snapshot/diff·PID/start helper를 재사용했다. 순서는 다음과 같다.

1. Manifest/전체 file identity·memory preflight·unit collision·manager gate.
2. 고유 user transient service에서 isolated Python stage 실행. 이 stage는 파일만 읽고 검증한 FD를 연 뒤 prlimit→Bubblewrap으로 exec한다.
3. fresh root16MiB, user/mnt/net/pid namespace, readonly root/dev, private tmp/run4MiB씩·shm1MiB. 프로젝트 또는 `/usr` 전체를 bind하지 않는다. fixture와 libc/loader, own canary, own cgroup leaf만 FD readonly mount한다. sterile readonly `/cwd`, clearenv, drop capabilities를 사용한다.
4. Native Fixture가 namespace·readonly·cgroup 값·tmpfs 용량·canary EROFS·private file write/delete·IPv4/IPv6/host socket 차단을 확인한다. 하나라도 실패하면 본문 전 거부한다.
5. `harness_ready`에서 최대5초 stdin 대기. Supervisor가 native host PID·cgroup·live maps/file identity·controller 변화를 확인해야 `GO`를 보낸다.
6. GO 뒤에만 `body_entered` 및 harmless simulation workflow. 단 한 번 실행하고 wait/cleanup한다.

Loader 관련 상속 환경이 존재하면 상위 사전검사부터 거부한다. 이번 host 실행에서는 env -u로 이 프로세스의 LD_PRELOAD/LD_AUDIT/LD_LIBRARY_PATH만 제거했고 own unit에 UnsetEnvironment를 설정했다. user manager·시스템 전역 환경을 수정하지 않았고 실제 환경 값은 기록하지 않았다.

## 5. 실제 실행 결과

최종 unit **aero-probe-a-harmless-v1-c95f35522f.service**, native host PID **189868**, start **17933760**, 내부 PID2. bwrap host PID189863/189867과 함께 같은 전용 cgroup이었다. 경로는 `/user.slice/user-1000.slice/user@1000.service/app.slice/<unit>`이다.

- native ready→file identity 검증→GO→본문 순서가 보존됐고 event sequence1~10, loader_compiled=false다.
- systemd-run/main exit0, resultsuccess, service runtime **150ms**, host 관측 전체 **0.194142초**.
- memory.max67108864/swap0/pids.max8/cpu.max25000 100000 일치. pids.current3, readback memory.peak **9469952B**. OOM/max 이벤트0.
- memory preflight는 stream FD 검증 뒤 post-exec VmHWM+8MiB로64MiB 미만을 확인했다. 이 값은 DART 로딩 메모리 측정이나 모든 실행의 peak 보장이 아니다. 제한 상향은 없었다.
- mount/net/user/pid가 host와 다르다는 native gate, readonly root/dev/fixture/input/limits, tmp/run/shm capacity gate가 통과했다. canary의 O_WRONLY open은 EROFS. own tmp/run 파일 쓰기/삭제만 성공했다.
- IPv4/IPv6 문서 주소 connect는 ENETUNREACH, host IPv6/UNIX/abstract socket 접근은 거부됐다. host positive control3개는 성공했고 Sandbox에서 host listener에 전달된 연결0.
- resource 초과 강제 효과나 timeout 강제 종료를 시험하지 않았다. SIGKILL 주입은 없었다.

## 6. Live mapped-library identity

검사 PID의 `/proc/PID/maps`에서 file-backed path·device/inode를 Allowlist와 먼저 비교했다. 삭제된 mapping, 예상하지 못한 path, inode 교체, anonymous executable mapping(허용 kernel vdso/vsyscall 제외), 필수 mapping 누락을 거부한다. PID/start 및 maps 전체를 검사 전후 다시 읽어 바뀌면 실패한다.

직접 `/proc/PID/map_files/range` open을 우선 시도했다. **세 파일 모두 readlink는 가능했으나 open은 EPERM(1)**이었다. 해당 항목은 UNAVAILABLE이며 PASS로 표시하지 않았다. sudo·capability·AppArmor/권한 변경을 하지 않았다.

fallback은 **검사 대상의 `/proc/PID/root/<mapped-path>`를 FD로 열어** fstat device/inode가 maps와 같은지, SHA/Build-ID가 Allowlist와 같은지 검사한다. bare host pathname만 해시하는 방식으로 대체하지 않았다.

|매핑 파일|device|inode|FD identity|
|---|---:|---:|---|
|/fixture/native_fixture|66309|3432003|일치|
|/usr/lib/x86_64-linux-gnu/libc.so.6|66309|8153876|일치|
|/usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2|66309|8153674|일치|

이것은 **관측한 file identity의 일치**다. 직접 map_files FD 접근, private relocated/COW 페이지 내용, 검사 이후의 변화, 초기화 이전 안전성을 증명하지 않는다. 이 제한을 이유로 전체 Probe A를 READY로 올리지 않았다. 실제 DART Core·의존성16개에 대한 Runtime mapping 검증 결과는 없다.

## 7. Fail-Closed·초기 실패·재검증

`fail_closed.json`의9개 offline 조건(manifest mismatch·필수파일 누락·SHA·Build-ID·Sandbox·cgroup 설정·net·readonly·supervisor 오류)에서 launch callback이 호출되지 않았다. 이는 mock/synthetic preflight 증거이며 실제 kernel namespace syscall 실패 주입과 구분한다. 실제 resource readback 실패 시 GO를 보내지 않는 경로도 구현했다.

초기 기록을 삭제하거나 성공으로 재분류하지 않았다.

1. 상속 loader 환경 때문에 사전 거부, unit생성0. `preflight_environment_initial.json`.
2. 최초 unit **aero-probe-a-harmless-v1-564af64de7.service**는 Native gate가 exit78로 거부. GO/body0, unit/cgroup/temp 정리 PASS. 원래 세부 predicate가 기록되지 않았으므로 정확한 과거 거부 지점은 직접 관측하지 못했다. `reports/initial/` 및 initial_evidence_hashes 참조.
3. 코드 검토에서 실행 중인 바이너리 open을 EROFS로만 인정하는 진단 오류를 발견했다. Linux는 이 경우 ETXTBSY를 먼저 반환할 수 있다. 수정 후 **실제 errno26**을 관측했다. binary ST_RDONLY와 Canary EROFS 요구를 유지한 채 두 오류를 구분했고, 상세 gate 사유를 추가했다. 최초 실패도 바로 그 분기였다는 설명은 강하게 지지되지만 원래 subpredicate log 부재는 남긴다. Clock/Capture·physics 기준 변경은 없다.
4. 초기 binary/manifest/pin/source와 관련 결과를 별도 경로·해시로 보존하고, 새 fixture용 manifest를 동버전 설치 reference와 재대조해 생성했다. 원래 attempt marker는 유지하고 별도 명시 revalidation marker를 사용했다. 자동 retry loop가 아니다. 실제 own unit은 초기1+재검증1, 총2개였다.

## 8. 정상 종료·정리·controller

최종 unit LoadState=not-found, leaf 제거, 관측한 PID/start 잔여0, canary·host socket/temp directory 제거를 확인했다. initial unit도 제거됐다. 초기 PID들을 생존 중 수집하지 못했으므로 해당 목록의 완전성은 주장하지 않으며, cgroup 제거가 확인된 별도 cleanup 근거다. 수동 기존 서비스 종료/manager 재시작/controller 복구는 없다.

현재 user manager tree와 상위·직접형제 **77개 경로/6개 선택 설정**을 비교했다. 실행 중 systemd CPU controller 자동전파에 해당하는43개 필드 변화만 있었고, 종료 후0이었다. manager SystemState/ControlGroup은 전후 같았다. systemd가 자동 복원했으며 수동 복구가 필요한 항목0. 모든 정책·사용량 전체 동일성을 주장하지 않는다.

## 9. 테스트와 무결성

신규 **31 PASS**, 회귀 **76 PASS**(Static27/Integration15/Smoke6/Hardening6/Targeted22), 총 **107 unittest PASS / 0 FAIL / runner SKIP0**. 실제 harmless native 재검증1 PASS는 별도다. 초기 실제 positive 실행1 FAIL과 환경 사전거부를 숨기거나 최종 PASS 수에 더하지 않았다. 직접 map_files·resource 초과3·kernel failure·Supervisor SIGKILL·실제DART Probe의7개 미실행/미확인 활동을 SKIP으로 구분했다.

컴파일은 cc C11/O2/Wall/Wextra/Werror/stack protector/RELRO/NOW, DART 링크0. source 및 command는 fixture_build.json에 있다. 정확한 offline 명령:

```
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s validation/dart-probe-a-harness-v1/tests -p 'test_*.py' -v
```

회귀는 같은 discover로 각 이전 tests 경로에서 실행했다(`regression_*.log`). 값 변조는 own tempfile/모의 manifest에서만 시험했으며 시스템 라이브러리를 변조하지 않았다. source 복사 동일성·FD 누수·동일 inode 내용 변조·device/inode 교체·deleted/unexpected mapping·missing PID도 검사했다.

`integrity.json`: **54,654개 기존파일 변경·누락0/기존범위신규0, main HEAD/status 유지 PASS**. 새 task·실험 handoff·.git·pycache만 제외했다. library_allowlist의 Core16+fixture3는 실행 후에도 FD identity 검사를 통과했다. 초기 증거 해시도 일치했다. production/AI 코드·SDF·패키지·시스템 library/loader·AppArmor·Clock/Capture 기준을 바꾸지 않았다.

## 10. 남은 조건·게시·다음 최소 작업

Probe A는 NEEDS_EVIDENCE, B~D BLOCKED다. 남은 핵심은 (a) 직접 map_files 불가 환경에서 FD fallback의 보장 범위 수용 여부, (b) Core-only NEEDED alias mount의 검토, (c) loader-enabled open 이후 close 전 외부 검증을 위한 동기화 계약, (d) 실제 초기화/종료·64MiB·resource 초과 등 미검증 사항과 별도 사용자 승인이다. 현재 runner는 harmless native만 실행하며 실제 Probe 명령을 제공하지 않는다.

**다음 최소 작업은 실제 DART를 로드하지 않고 Core-only alias·post-open 검증 gate 및 FD fallback 보장 범위를 하나의 실행 계약으로 확정하는 것이다.** 시스템 권한을 올리거나 추가 Runtime을 자동 시작하지 않는다.

경량 source/tests/reports와 실험 handoff만 명시 staging/검토 후 실험 branch에 commit/push한다. binary/work/raw full manifest는 제외한다. 실제 SHA/원격 일치는 로컬 `git_publication.json` 및 최종 응답으로 남긴다. `/tmp` ignored/raw와 main untracked evidence는 push로 다른 기기에 자동 이전되지 않는다. main commit/push, force/reset/rebase/stash/merge는 없다. **NOT_RUNTIME_VERIFIED / Stage B BLOCKED 유지**.
