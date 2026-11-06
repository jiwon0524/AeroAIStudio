# Aero AI Studio V0.7.1 — Isolated Runtime Probe Readiness Review V1

## 현재 상태와 기존 증거

**NOT_RUNTIME_VERIFIED / Stage B BLOCKED / Host NEEDS_ADDITIONAL_EVIDENCE 유지.** 실험 worktree의 시작 HEAD는 `83ab0f57a1c85578e8942b00e0f8d9a1707a22fe`, branch는 `experiment/dart-internal-trace`, 시작 Git 상태는 clean이다. 원본 main은 읽기 전용으로 취급했다. AGENTS·개발 규칙·양쪽 handoff·Targeted Evidence final/probe/risk/verdict·V4 Destructor Cleanup 보고서를 읽었다. 하위 validation AGENTS는 발견되지 않았다. 과거 main handoff의 게시 금지는 최신 사용자·실험 개발 규칙의 명시적 실험 브랜치 게시 권한으로 대체되며 main 보존은 유지한다.

기존 Targeted Evidence V1의 22 PASS와 30,823파일 보존은 **과거 보고 결과**이며 이번 테스트 수에 합산하지 않는다. Core/External/Bullet 공식 패키지 일치, 정확한 Build-ID debug 확보 실패, 슬롯18 INFERRED D1 및 TARGETED_EVIDENCE_UNAVAILABLE 판정을 유지한다.

## Probe A~D 준비 상태

|Probe|준비 판정|실행|주요 차단 조건|
|---|---|---|---|
|A Loader Boundary|BLOCKED|SKIP|전체 closure·init/fini·sandbox 미검증|
|B Object Lifetime|BLOCKED|SKIP|owner/deleter·allocator·nested cleanup 미검증|
|C Exception/Unwinding|BLOCKED|SKIP|부분 생성 fault window·unwind/reentrancy 미검증|
|D OFF/ON|BLOCKED|SKIP|비물리 ON entry·owner/quiescent flush·중립성 미검증|

각 Probe의 대상 manifest, 위험, 격리, 제한, 중단·성공 기준, 실패 처리, 결과 보존과 원본 재검사는 `probe_risk_matrix.json`에 기록했다. 기존 계약을 보존해 세부화했으며 READY_FOR_SEPARATE_APPROVAL은 현재 부여하지 않는다.

## ELF 비실행 검토

`elf_review.json`은 실제 파일을 SHA-256 및 readelf -dW/-nW/-SW로 확인한 이번 결과다. 존재하는 9개 고유 ELF의 hash/Build-ID가 이전 기록과 일치한다. B/C External 예상 lib 경로 2개는 실제 누락이다. 임의 대체하거나 파일을 이동하지 않았다. SONAME/NEEDED/RPATH/RUNPATH와 init/fini 태그를 기록했다. B/C RUNPATH의 끝 빈 항목은 작업 디렉터리 검색 위험을 만든다. 같은 Core SONAME과 설치 Bullet 유지 때문에 provider 충돌·잘못된 Core 혼용 방지 및 실제 transitive closure 고정이 필요하다.

초기화 배열이 존재한다는 사실은 함수 부작용을 감사한 결과가 아니다. dlopen은 init/등록/IFUNC/TLS 등을 실행할 수 있고 dlclose와 process exit도 종료 코드를 실행한다. 승인 전 load 순서·handle 소유·역순 종료·스레드 종료를 확정해야 한다. ldd/loader trace/dlopen/dlclose는 이번에 수행하지 않았다. Gazebo plugin은 ELF 데이터로만 읽었다.

## 독립 Fixture와 격리 검증

자체 Python 표준 라이브러리 코드만 별도 `/usr/bin/python3 -I -B` 프로세스로 실행했다. DART/Gazebo 링크·로드 없이 child maps도 확인했다. 새 session, private cwd/HOME/TMPDIR, 환경 allowlist, parent timeout 및 자기 child process group kill/wait를 사용했다. child는 CPU1초/AS128MiB/파일64KiB/NOFILE32/NPROC16/core0 제한을 적용한다.

`fixture_test_results.json`: **14 PASS / 0 FAIL / 0 SKIP**. 정상 종료, exit7, SIGTERM, wall timeout, CPU SIGKILL, MemoryError, 파일 크기 제한, 제한 설정, stdout/stderr, 임시 파일 정리, 중단 후 재실행, 별도 PID, 환경과 대상 미로드를 검증했다. 추가 보고서/계약/JSON 오프라인 unittest **6 PASS**, 총 실행 검사 **20 PASS / 0 FAIL**이며 실제 A~D는 별도 **4 SKIP**이다(`test_summary.json`). 오류·signal·자원 제한 종료는 의도된 fixture 기대값을 검증한 PASS이며 실제 Probe 성공이 아니다. 로그는 임시 디렉터리 삭제 전에 JSON으로 보존했다. 재현: `python3 validation/dart-probe-readiness-v1/scripts/run_fixture.py`.

파일 쓰기와 네트워크 강제 차단은 **NOT_VALIDATED**다. private cwd는 sandbox가 아니고 NPROC는 UID 공유 제한이다. 무해한 child 내부 limits 적용은 native target loader 초기화 전 제한 적용을 입증하지 않는다. 따라서 실제 DART 격리 준비는 BLOCKED다. 격리의 구체적 한계는 `isolation_review.json`을 따른다.

## Destructor/Allocator·Exception·Instrumentation 위험

V4의 primary 및 Node-adjusted ShapeNode D0→추론 D1→sized delete1664와 Bullet48/368은 선택된 정적 경계다. 일반 Node D0/D1 관계나 전체 lifetime 안전성을 확정하지 않는다. Bullet factory→core custom deleter→derived delete의 cross-module 소유, detector/manager 수명, nested callbacks, allocator interposition, double free/UAF 및 비정상 종료 순서는 HIGH/UNKNOWN이다.

일부 LSDA landing pad와 Unwind_Resume 관측은 실제 예외 처리 안전성 증거가 아니다. 부분 생성·공유 참조 정리·destructor 순서·중복 해제·terminate를 검증하지 않았다. 임의 전역 Nth allocation fault는 금지하고, 승인 전 소유권이 확인된 단일 factory window와 비할당 관측 전략을 검토해야 한다.

OFF/ON 비교는 같은 입력·seed·closure/hash·환경·소유권 시퀀스와 fresh process를 사용해야 한다. allocation count, exception outcome, destructor events, metadata/output bounds, 성능 시간과 로그를 분리 비교한다. 추가 TLS/once/cache/atomic/serialization/flush·allocator 호출은 예상 변화로 명세하고 허용 편차를 사전 고정해야 한다. 비물리 결과는 물리·FP·Clock 중립성의 증명이 아니다. 이번 OFF/ON은 모두 미실행이다.

## 해결한 항목과 미해결 항목

독립 프로세스 실행·유한 자원 제한·오류 수집·정리·재실행의 동작을 실제 확인했다. 라이브러리 식별자를 재확인하고 예상 경로 누락 및 RUNPATH 위험을 명시했다. 남은 것은 강제 파일/네트워크 격리, 실제 closure와 init/fini 감사, target-specific native fixture, allocator/EH/ON entry 계약이다. 이번 독립 fixture는 이를 대체하지 않는다.

## 보존과 Git 게시

`integrity.json`: 이번 전후 **54,436개 기존 파일 변경·누락0 / 신규 기존범위 파일0 / main HEAD·status 유지 PASS**다. 새 작업 경로와 실험 handoff는 검사 제외이며 이전의 30,823과 범위가 다르다. 새 작업 경로와 실험 handoff만 변경 허용하며, 기존 Evidence V1~V4·AI 기능·Gazebo 연동·Export·Clock/Capture·production·시스템 패키지/라이브러리는 변경하지 않는다. 독립 fixture와 정적 읽기만 수행했고 실제 Runtime A~D·객체 생성/삭제·예외·OFF/ON·Gazebo·World::step·Stage B는 **SKIP/NOT_RUN**이다.

검증된 신규 scripts/tests/경량 reports 및 handoff만 명시적으로 staging 후 diff 검토·commit/push한다. 시작 SHA 위 후속 commit의 실제 게시·원격 일치 결과는 로컬 `git_publication.json` 및 최종 응답에 남긴다. 해당 영수증 때문에 자기 SHA 재귀 commit은 만들지 않는다. raw/full manifests/work는 제외한다.

## 로드맵과 다음 최소 작업

`next_steps.md`에 범용 AI 플랫폼 방향과 단계별 로드맵을 기록했다. 기존 GridWorld/Q-Learning/DQN/Curriculum/Safety/Brain Map/Replay/Evaluation/Checkpoint/Resume/Gazebo/Export를 보존한다. A*와 DQN 역할을 구분하며 이번에 경로 알고리즘이나 소방 기능을 구현하지 않는다.

다음은 **DART를 로드하지 않고 무해한 Fixture로 파일 쓰기·네트워크 강제 차단 환경을 검증**하는 단계다. 이어 closure/init-fini 및 A 전용 native fixture를 검토한 뒤 별도 실행 승인 요청 준비 여부를 재판정한다. 이번 단계 종료 후 Runtime은 실행할 수 없다. `/tmp` raw/work와 main ignored/untracked 증거는 Git push로 다른 기기에 전달되지 않는다.
