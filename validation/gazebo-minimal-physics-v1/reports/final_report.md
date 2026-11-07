# Gazebo 사전검사·첫 스텝 gate 준비 결과

**PREPARED_BLOCKED_NOT_EXECUTION_READY / Stage B BLOCKED**.
시작 HEAD는 aae135bf487a554b7be678b7ae64c3d03c00d601이며 실험 브랜치와 clean 상태를 확인했다. 이번에는 구현·컴파일·링크·모의 입력 검사만 수행했다. 실제 DART/Gazebo 로딩, native/observer 실행, 물리 스텝, 서비스 시작, marker 소비, sudo·설치·시스템 변경은 모두 0회다.

## 구현과 입력 고정

새 task에 headless Server API 후보(src/server.cc, adapter.cc), observer 플러그인, 최소 world, 입력/마운트 사전검사, 순수 GO/100스텝 정책, fail-closed launcher, 기존 systemd·정리 정책 재사용과 테스트를 추가했다. 기존 CLI를 재실행하지 않고 Run 호출 전 경계를 둘 수 있는 직접 Server API frontend를 컴파일했다.

server SHA-256은 f8252d1e130207abe72eda6d44d5ceaaca511a26bc8847454c7d82dd8a2c5612, observer는 d3bba7b32205c0f69c215d598d3fdf4661e6af28bc0c152a3a9c10addb165a7a다. 둘 다 링크했지만 실행하지 않았다. 초기 observer include 이름 오류는 설치 헤더 Pose.hh/LinearVelocity.hh로 수정했다. 성공한 server를 덮어쓰지 않고 observer만 다시 빌드했으며 초기 결과와 로그를 보존했다. inputs.py의 공유 resolution import 경로 오류도 수정했다.

ELF 166개, NEEDED 연결 738개, canonical/SONAME 읽기 전용 ELF mount 306개를 고정하고 검사했다. Core own SONAME은 같은 검증된 FD에 연결하며 Core16 해시는 이전 기록과 일치한다. 외부 ELF는 /usr/lib canonical 경로만, local ELF는 새 server와 observer만 허용한다. SDFormat schema 후보 125개도 해시했으나 실제 resource/config/dlopen 경로 전체는 검증하지 못했다. 정적 ELF closure를 완전한 runtime closure로 간주하지 않는다.

## 실행을 차단한 근거

설치 Server.hh는 paused RunOnce도 iteration을 1 증가시키고 Run iterations=0은 무한 실행이라고 명시한다. System.hh의 simTime은 업데이트 후 도달 시간이다. PhysicsEnginePlugin은 문자열 component이며, active engine/world/detector 객체와 provider를 신뢰할 수 있게 연결하는 installed Sim public bridge는 확보하지 못했다.

adapter는 false를 반환하고 driver는 Server/world 생성 전에 거부한다. 별도의 trustedReadyCollected=false도 Run 경로를 차단한다. observer는 PreUpdate에서 _Exit(78)로 중단한다. 이를 실제 스케줄러·초기화 단계에서 검증한 무스텝 보장으로 주장하지 않는다. PostUpdate 후보 역시 orientation, component materialization과 관측 provenance가 미완성이다. 실제 backend/detector/provider는 UNVERIFIED다.

launcher는 입력을 읽기 전용으로 검사한 뒤 서비스·marker·native 전에 거부한다. 실제 runtime을 실행하는 supervisor 연결은 없다. 모든 ready flag를 위조해도 실행 분기가 열리지 않는다. 따라서 실행 승인만 받으면 돌릴 수 있는 상태가 아니다.

## 비실행 검사

최종 42개 검사 PASS, 실패·오류 0개다. backend/detector/provider 불일치, 매핑 누락·추가·해시/inode 불일치, SONAME alias 동등성, GO 전 iteration/time 변화, 관측 누락, 설정값 대체, NaN·100스텝 개수/시간·자유낙하 기준, source 변조, launcher 차단, 재GO와 정리·InvocationID 조건을 검사했다. 양성 GO는 합성 정책 입력에서만 확인했으며 live 측정의 신뢰성을 증명하지 않는다. C++ artifact나 플러그인을 테스트로 실행하지 않았다. 로그는 work/policy_tests_final.log다.

100스텝 계약은 100×1ms, iteration 1..100, 최종 time 100ms, z=0.95095±0.002m, vz=-0.981±0.02m/s, lateral/rotation 오차 1e-6이며 finite 실측 state 100개가 필수다. 초기 iteration/time 0과 실제 active instance/provider, mapping 및 격리·한도를 완전히 관측하기 전 GO를 허용하지 않는다. 현 capability는 false다.

## 한도·보존·남은 결정

새 Gazebo 제안 상한은 512MiB/swap0/tasks64/CPU100%/service30s/stop2s/host40s다. prlimit은 CPU10s/AS2GiB/FSIZE1MiB/NOFILE256/CORE0이다. 기존 64MiB 성공을 Gazebo에 전용하지 않았으며, 실제 startup/RSS/tasks와 한도 강제효과는 UNKNOWN이다. 기존 readonly FD layout과 systemd argv·정리 불변조건은 재사용했지만 새 payload의 실제 수집/서비스/cleanup 연결은 미완성이다.

원본 55,017개 파일의 변경·누락 0, 기존 범위 추가 0, main HEAD/status 유지로 integrity PASS다. 이전 증거와 marker는 보존했고 새 runtime/attempt/before/stdout/stderr/canary는 없다. raw ELF, pin, 로그와 snapshot은 local /tmp에 있으며 Git만으로 다른 기기에 이전되지 않는다. 알려진 빌드·테스트 작업은 종료했고 external-CWD/remote/container 작업은 UNKNOWN이다.

Bullet 정상 수명·cast/deleter, 개별 destructor/D0/free, allocator, C 예외 해제 위험은 NOT_ACCEPTED다. 비교 arm과 D local trace는 installed-only, local trace·recorder·neutrality 주장 없음, 실제 closure 확인 조건에서만 기술적으로 비적용이며 기존 문서 gate의 생략 결정은 별개다. 이번에 위험 수용·면제를 결정하지 않았다. active instance adapter, iteration 0 관측, resource·supervisor 연결이라는 기술적 부재는 위험 수용으로 대체할 수 없다.

정확한 현재 차단 명령·입력 해시·출력/one-shot·통과/중단/정리 기준은 approval_plan.md와 runtime_contract.json에 있다. 소스·테스트·경량 보고서와 인계만 게시하고 추가 실행 없이 멈춘다.
