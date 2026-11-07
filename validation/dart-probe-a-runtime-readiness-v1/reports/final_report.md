# DART Probe A Runtime Readiness V1

**PROBE_A_NEEDS_EVIDENCE / NOT_RUNTIME_VERIFIED / Stage B BLOCKED**.

실제 DART/Gazebo 로드·실행, World::step, Stage B는 수행하지 않았다. 원본 main과 기존 실험 자료는 보존했다. 기준 HEAD e135cc5227ac584466c857e03f574e90b5c37ea7에서 시작했다.

## 구현과 검증

기존 Harness의 ETXTBSY 진단 수정·재검증과 systemd/Bubblewrap 격리·정리 증거를 재사용했다. 새로운 대량 정적 ELF 감사는 하지 않았다. Core16의 기존 manifest pin을 확인하고 현재 FD의 SHA-256·Build-ID·device/inode를 다시 검증했다. 기존 SONAME/DT_NEEDED를 바탕으로 58개 의존성 edge와 alias를 연결했다. 검증한 FD만 canonical/SONAME 경로에 readonly bind하는 인자를 생성한다. 로더 실행을 통한 새 ELF 감사는 없다.

Alias namespace에서 DART 파일을 읽기 전용 노출하고 libc만 사용하는 무해 C fixture를 실행했다. exit0, DART 로드0. 최초 namespace 생성 거부 기록은 alias_namespace_initial.json에 보존했으며 환경 승인 후 밖에서 수행한 검증은 PASS다. 이 검증은 Core의 실제 dynamic resolution이나 systemd 결합 검증이 아니다.

Post-open host gate는 기존 maps 검사기를 재사용해 예상하지 못한/deleted mapping, device/inode, SHA/Build-ID, PID/start 및 maps 전후 안정성과 Core 전체 inode 출현을 검사한다. Core baseline의 libc/loader 공유를 허용하되 identity 충돌을 거부한다. 실패 시 CLOSE를 보내지 않는다. Native 검토본은 open 후 5초 WAIT 및 exact CLOSE만 허용하며 거부 시 _exit(78)한다. loader-enabled 검토본은 REL object로만 컴파일했고 링크/실행하지 않았다. 무해 protocol fixture는 허용·잘못된 입력·EOF·timeout을 실제 검증했다.

신규15 PASS + 기존 Harness 회귀31 PASS =46 tests, FAIL0. 기존 observed 테스트는 과거 증거를 확인하며 service를 재실행하지 않는다. 별도 alias namespace1 PASS. 초기 환경거부1 FAIL을 최종 성공과 분리한다. 실제 DART, resource 초과 강제 효과, 새 통합 service 계약은 SKIP/미검증이다.

## 한계와 다음 단계

map_files EPERM은 이전 관측이며 이번에 권한을 우회하지 않았다. proc-root FD fallback은 maps inode와 일치하는 파일의 identity만 보장한다. resident COW 페이지, 검사 이후 변화, constructor 이전 안전성을 보장하지 않는다. post-open gate 이전에 constructors/IFUNC가 이미 실행된다는 위험은 남는다.

MemoryMax64M/TasksMax8/CPUQuota25%를 유지했다. 기존 harmless peak9,469,952B는 DART 메모리 예측 근거가 아니다. ELF 크기와 RSS/cgroup charge는 다르다. 128MiB는 추후 검토 후보일 뿐 변경·필요성 인증을 하지 않았다. 초과 강제 효과·강제 supervisor 종료는 미검증이다.

**실제 Probe A를 지금 실행할 수 없다.** 검토본 /audit Core 경로와 canonical mount 경로를 통일하고, binary/manifest를 pin한 뒤 post_open_ready를 Supervisor callback과 연결하는 작업이 남는다. 기존 stage는 harmless-only다. 새 결합 경로를 무해 service fixture로 검증한 후 별도 Runtime 승인을 받아야 한다. 따라서 실행 명령은 제공하지 않으며 runtime_execution_plan.json에 순서·위험·선행조건을 기록했다. 후속 DART 실행은 자동 시작하지 않는다.

## 증거와 게시

요청된 보고서9개와 추가 alias namespace 증거, scripts/fixtures/tests를 이 경로에 기록했다. integrity.json은 보존 비교, handoff_snapshot.json은 관측 프로세스를 기록한다. 원시 보존 manifest·binary·REL object·로컬 게시 영수증은 Git에서 제외한다. /tmp/ignored/untracked 자료는 다른 기기로 자동 전달되지 않는다. Commit/Push SHA는 로컬 git_publication.json과 최종 응답에서 확인한다. 원본 main·시스템 패키지·Clock/Capture 기준은 수정하지 않았다.

## 중단 복구

Git staging 승인 취소 후 기존 staged17개와 unstaged tracked 변경0을 확인했다. integrity.json은 생성 완료·ignored 상태였고 삭제되지 않았다. 요청된 보고서9개 및 참조 evidence 해시를 확인했다. 신규15개 테스트만 재실행하며 기존 회귀31개와 alias namespace 성공은 이전 검증을 재사용한다. 구현·DART 실행·service 실행은 재시작하지 않았다. 보존 재비교 결과는 integrity.json을 따른다.
