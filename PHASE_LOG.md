# V0.7 (2026-10-31)

V0.7 CODE COMPLETE / ACTUAL GAZEBO VALIDATION PENDING

GAZEBO ACTUAL INTEGRATION: NOT VERIFIED

기존 V0.6 확장. native timestamp/contact/physics/lifecycle/discovery, telemetry/UI, curriculum quota, Safety audit와 Ubuntu check-first 도구를 추가했습니다. 기존 테스트 소스 유지. Grid3seed×2000 학습·1200평가 실행, 상세 결과 VALIDATION.md. Ubuntu 배포판과 gz가 없어 P0 실제 검증 및 후속 Geo 기능 보류.

# Phase 기록

아래 첫 표는 V0.3 당시 기록입니다. 현재 V0.4 작업은 뒤의 V0.4 Phase 절을 참고하세요.

작업일: 2026-10-31 (Asia/Seoul). 빈 작업 폴더에서 새 독립 프로젝트를 생성했습니다. 기존 소스·Git 저장소·실행 방법·중복 구현은 없었고 F450 파일은 접근하거나 수정하지 않았습니다. 파일은 아래 영역 단위로 추가했습니다. Core 구현 후 Core 실행 검증, UI 연결 후 통합 검증, 화면 수정 후 회귀 검증을 진행했습니다. 테스트 결과는 최종 회귀 실행 기준이며 Phase마다 별도 실행했다고 주장하지 않습니다.

| Phase | 추가/수정 파일 | 구현 | 확인 결과 | 남은 문제 |
|---|---|---|---|---|
| 1 분석/구조 | pyproject.toml, .gitignore, src/aero_ai_studio | Python/Qt 모듈 구조, 독립 디렉터리 | 기존 폴더 조사, Python 3.14.3 발견, compileall 성공 | 기존 코드 마이그레이션 대상 없음 |
| 2 Project/Scenario | core/storage.py, projects/repository.py, scenario/models.py, scenario/repository.py | dataclass·검증·UTF-8 atomic JSON·로컬 프로젝트 | test_project_persistence, test_scenario_save_load 통과 | 활성 scenario 하나, schema migration 미구현 |
| 3 GridWorld | simulation/base.py, simulation/grid_world.py | Protocol·4방향·충돌·goal·timeout·도달 가능성·seed 랜덤화 | reset/step/collision/goal/timeout/seed/invalid-world 테스트 통과 | 2D 점유 grid, 물리·센서 미구현 |
| 4 Q-Learning | agents/base.py, agents/q_learning.py | epsilon-greedy·동점 처리·terminal bootstrap 차단·Q-table 저장 | 수치 update·terminal·save/load 테스트 통과 | 상태는 (x,y), 환경 변화 일반화 한계 |
| 5 Training UI | app/main.py, __main__.py, ui/window.py, ui/widgets.py | 11개 페이지·QThread·진행률·reward/success 그래프·취소 | Qt offscreen 1,000회 학습 통합 테스트 통과 | Linux/native Windows 수동 상호작용 미검증 |
| 6 Logging | training/trainer.py, training/logger.py | Episode 전이·pre-update scores·정책·결과·run/metrics 기록 | 로그 roundtrip·취소 후 부분 저장 테스트 통과 | 강제 종료 복구·대용량 최적화 미구현 |
| 7 Brain Map | explainability/brain_map.py, ui/widgets.py, ui/window.py | 실제 scores·선택·탐험 구분·결과, 4단계 시각 흐름 | 테스트 로그 데이터 일치, brain.png 육안 확인 | 감지/위험 모듈은 아직 없음 |
| 8 Replay | replay/replay_engine.py, ui/window.py | run/episode·failure filter·play/pause·step/speed/slider·동기화 | seek 경계·전이 연속성·페이지 간 선택 유지 통과 | 3D renderer·영상 동기화 미구현 |
| 9 Registry/Export | models/registry.py, deploy/export.py, adapters/interfaces.py | 메타데이터·Q-table·Local Python export·미래 Adapter | 모델 저장·재로드·exported policy 목표 도달 통과 | 버전 자동 관리·다른 export 미구현 |
| 10 Tests/Docs | tests/test_pipeline.py, tests/test_ui.py, tools/verify_demo.py, README.md, VALIDATION.md, Setup.ps1, Start.ps1 | 재현 가능한 검증·설치/실행·상태/부채 문서 | 10 tests passed, 1,000회 학습·38-step greedy goal | 별도 평가 UI·패키지 EXE 미구현 |

Paper/Video/Korea 기반 파일: `paper/models.py`, `video/models.py`, `adapters/interfaces.py`. 참조 저장 UI와 Protocol만 제공하며 실제 분석·지도 조회를 수행하지 않습니다.

검증 과정의 수정: Replay → Brain Map 이동 시 선택 보존, training worker의 취소/종료 처리, Qt offscreen Windows 글꼴 로딩, Dashboard의 최신 실패 시간순 계산을 반영했습니다. 기존 파일 삭제는 없습니다.

## V0.4 Phase 1 — 분석 완료
기존 outputs/AeroAIStudio를 계속 사용. 구조·pyproject·Trainer→GridWorld→Q-learning→로그→Replay/BrainEvent와 Registry 확인. 기준 테스트 10/10 통과(3.93s). Git 저장소가 없는 기존 작업 폴더이며 기존 파일은 보존. V0.3 상태 tuple과 로그 필드는 호환 유지하고 V0.4 필드를 추가한다.

### V0.4 Phase 2 — Evaluation Engine
evaluation/evaluator.py 추가. epsilon=0, weight update 없음, 별도 JSON/episodes, 성공·실패·reward·steps·충돌·timeout·정적 경로 비율. Core 검증17개 통과; 이후 UI도 연결했습니다.
### V0.4 Phase 3 — Checkpoint/Resume Core
training/checkpoint.py와 Trainer 확장. 단일 atomic payload, agent RNG, 다음 epsilon, metrics, scenario snapshot. Episode 경계 저장, 원본 Run 보존 후 이력 복사. 30→31→80이 연속 실행과 Q-table/metrics 완전 일치했습니다.
### V0.4 Phase 4 — Scenario/Grid Editor
0.3→0.4 migration, grid presets/custom, click 배치/삭제/goal/agent, seeded generator, ObservationSpec. Core seed/serialization 검증 후 Qt mouseClick 테스트로 연결을 확인했습니다.
### V0.4 Phase 5 — Dynamic Objects
Horizontal/Vertical/Random 이동, dynamic collision, danger terminal, slow reward 비용. seed 재현·이동/충돌/swap·위험/저속 테스트를 통과했습니다. 실시간 표시도 기존 worker 신호로 연결했습니다.

### V0.4 Phase 6 — Brain Map V2 완료
brain_map.py와 widgets.py: 실제 pre-update Q, Exploration/Exploitation, 주변 객체·mission·action validity·기하학적 risk. Legacy 필드 fallback 유지. 새 테스트에서 실제 로그 기반 표현 확인.
### V0.4 Phase 7 — Timeline 완료
window.py: Decision Timeline 클릭으로 공유 seek, Grid·BrainMap 동기화. Qt 통합 테스트 통과.
### V0.4 Phase 8 — Failure Analyzer 완료
failure_analyzer.py: 충돌·이동장애물·위험·timeout·반복 상태 규칙 분석. 관측 근거와 가능한 원인만 보고. Loop/Collision/Timeout 테스트 통과.
### V0.4 Phase 9 — Comparison 완료
training/comparison.py, ComparisonChart, research_panels.py: Run별 설정·metrics·연결 모델 및 reward/success 곡선. 2개 Run UI 비교 검증.
### V0.4 Phase 10 — Model Versioning 완료
registry.py: 자동 v1/v2/v3, parent, notes, evaluation reference, duplicate/rename/delete. 삭제 기본값 No 확인창과 경로 검증. 버전 roundtrip·삭제 취소 검증.
### V0.4 Phase 11 — Simulation 계약/연결 완료
SimulationEnvironment는 lifecycle·metrics·capabilities를 규정하며 TrainingEnvironment는 호환 alias. GridWorld와 Trainer/Evaluator가 factory로 연동. Adapter 오류 시 close 검증. UI 평가·재개·Map Editor·실시간 표시 통합 16개 신규 테스트 통과. 남은 작업: A/B/C 성능 검증, 전체 회귀, 문서/ZIP.

### V0.4 Phase 12 — 전체 검증
기존 10개를 유지한 전체 pytest 26개 통과(18.56s). Test A: 1000회 학습 후 100회 평가 성공 100%, 평균38 steps. Test B: reset마다 장애물 변경, 학습1000/평가100 성공0%, 충돌8·timeout92. Basic 위치 관측의 일반화 한계를 확인. Test C:100 episodes/6255 steps에서 이동객체 6255회 갱신. 430→431→1000 재개는 전체 Q-table 및 metrics 연속학습과 완전 일치. 이후 화면 레이아웃 점검·최종 회귀 예정.

### V0.4 Phase 13 — 문서/최종 패키지
README.md·VALIDATION.md를 현재 구현으로 갱신하고 V0.3 문서는 docs/V0.3-*에 보존했습니다. docs/SimulationContract.md와 docs/GazeboIntegration.md, 재개 CLI, 실제 benchmark·화면 캡처 도구를 추가했습니다. 최종 pytest 26/26 통과(21.95s), compileall 성공, V0.3 실제 workspace 7개 화면 호환 캡처 성공. 새 Python 프로세스에서430회 checkpoint→431→1000을 실행한 Q-table/metrics도 연속 학습과 정확히 일치했습니다. Editable package0.4.0 갱신. FILES.txt·CHANGES.md·V0.4 소스ZIP은 기존 V0.3 ZIP을 보존하며 생성합니다. UI native 수동 조작/Linux/실기체/실제 OS kill은 미검증이며 Basic random-map 평가0%를 알려진 한계로 명시했습니다.

## V0.5 진행 기록
Phase 1: 기존 Simulation/Observation/Agent/Trainer/Evaluator/Replay/Brain/Registry/Checkpoint/UI/Tests 조사. 기준26개 통과(22.15s). 동일 프로젝트 유지.
Phase 2: Observation V2 BASIC/LOCAL/SENSOR/FULL_DEBUG와 Compact encoder 추가. 정책 입력과 debug snapshot 분리. local/sensor/motion/encoder 신규 테스트 통과.
Phase 3: Agent Protocol을 reset/select_action/learn/decision/metadata/save/load로 확장. Q-Learning legacy API/키 유지. PyTorch DQN MLP22-128-128-4, buffer/target/optimizer/checkpoint 실제 구현. DQN 재개 exact match·저장·greedy 평가 검증.
Phase 4: 공통 Trainer/Evaluator/Registry/Checkpoint/Export 연결. 기존26개+신규Core11개=37개 회귀 통과(29.45s). 별도 DQN UI 테스트도 통과.
Phase 5: Brain V3/Observation Debug/Replay/Timeline 동기화, algorithm/observation UI, Generalization/Compare 확장.
Phase 6: provider 독립 SDF generator, gz process launch/stop/status, sensor protocol, ROS bridge manager, Diagnostics 구현. Windows 미설치 graceful fallback·XML 구조 테스트 통과. 실제 Gazebo 런타임 없음. A/B/C/D/E benchmark 진행 중.

### V0.5 Phase 7 — 실제 Validation 완료
A 고정지도1000학습/100평가 성공100%, 평균38steps 유지. B/C 동일랜덤10% 지도 각3000학습/200평가: Basic0%, Compact Sensor64.5%(충돌0/timeout71). D DQN1000학습/200평가 성공74.5%(충돌51/timeout0). 학습seed43…3042(Q)/43…1042(DQN), 평가10043…10242로 분리했습니다. 별도 generalization50회: 기준66%, hard+moving+danger 새조건0%, Gap66%p. 이 한계를 그대로 보고합니다. 실제SDF 생성 및 미설치 smoke 수행: actual_launch=false/render_verified=false. Gazebo/ROS2/bridge 없음, CPU torch2.15.0, GPU RTX5070 진단, CUDA runtime 없음.
### V0.5 Phase 8 — 최종 회귀/문서/배포
기존26개 테스트 변경 없이 유지. 신규12개 포함 총38개 전체통과(31.19s), 마지막 UI문구 후 DQN UI 추가통과(4.51s), compileall 성공. Brain/Observation/Diagnostics/Training 화면 캡처 확인. 현재 README/VALIDATION 및 Observation/Agent/Gazebo 설계문서 작성, V0.4 문서 보존. 최종 generator로 실제ground plane 포함20×20 예제SDF 재생성/파싱 확인. CHANGES/FILES는 V0.4소스ZIP과 비교하여 갱신하며 기존 파일 삭제 여부·기존 테스트 hash·최종 ZIP 무결성을 확인합니다. Ubuntu/Harmonic 실제launch/render와 3D학습은 미검증/범위밖, 동적 분포 일반화는 미해결로 남깁니다.

## V0.6 진행 기록
1. V0.5 Simulation/Gazebo/Observation/Agent/Trainer/Evaluation/Checkpoint/Registry/Replay/UI 조사. 기준38개 통과(30.13s). 기존 폴더와 테스트 유지.
2. CanonicalSensorObservation, 거리 discretizer, 센서 기반 Safety, motion prediction/TTC, Reward components, minimum clearance 연결. 기본legacy 경로 유지.
3. Double DQN·warm-up·선택 reward clipping, 평가기반 Curriculum·checkpoint stage 복원 구현. 전체49개 테스트 통과(34.77s).
4. Gazebo process/transport/stepping/entity/sensor_provider 책임 분리. Harmonic native bindings lazy import, fixed sim-time barrier, 실제4-ray GPU LiDAR, 관측 pose 확인, reset/action/goal/collision interface 구현. 전송fixture unit contract와 실제환경 integration test 분리.
5. Headless/GUI·비동기 launch/stop/closed-loop·평가 suite·Safety/Reward/Curriculum UI·Trajectory 연결. Windows Gazebo 미설치. 기존 WSL 목록은 읽기 전용 확인 결과 비어 있어 Ubuntu 접근환경 없음. 실제 smoke: NOT VERIFIED. benchmark 및 최종회귀 진행 중.

### V0.6 最終 — 최종 검증/문서/배포
전체 pytest51 passed,1 skipped(36.34s). skip은 실제 Ubuntu/Gazebo integration이며 NOT VERIFIED로 기록했습니다. 마지막 좌표 floor/UI라벨 후 관련13개 테스트 통과(4.98s), compileall 성공. 새로운 Canonical Q encoder도 실제 factory/metadata/UI에 연결하고 검증했습니다.
Validation: 기본1000학습/100평가 성공100%,평균38steps 유지. 새 Compact/DQN2 Curriculum와 DirectHard 각600학습, frozenV0.5 모델 포함44개 Safety OFF/ON 평가행×20episodes=880회와 회귀100회 실행. DQN_V05 Hard 성공25→45%,충돌75→20%,Timeout0→35%,개입551회. DQN2 Curriculum은600회 종료 시stage4 진입(그Stage학습0회); DirectHard와의 비교를 인과적 효과로 단정하지 않습니다. Compact Curriculum Hard0%도 그대로 보고했습니다.
Gazebo: process/transport/stepping/entity/sensor module 및 실제native API 경로 구현, fixture contract 검증. Windows gz없음/WSL distro목록없음, actual closed-loop smoke NOT VERIFIED. 최종 LiDAR SDF4-system/4-ray XML 구조 확인. 설치스크립트는 안내만 출력하고 시스템변경 자동실행 없음.
현재 README/VALIDATION/GAZEBO/OBSERVATION/AGENT 및 신규 SAFETY/REWARD/DYNAMIC 문서를 갱신하고 V0.5 문서를 보존했습니다. UI BrainV4 고정요약·Trajectory·worker async 화면을 확인했습니다. 기존V0.5 테스트 파일 hash/기존파일 삭제 없음/소스ZIP byte 무결성을 검사합니다. 실제 Ubuntu 실행 검증은 V0.7 최우선 과제로 남습니다.
