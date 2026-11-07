# Autonomous AI Experiment Lab — 향후 설계 요구사항

상태: **DEFERRED — DART/Gazebo 검증 완료 대기**. 구현·실험 실행·패키지 설치·실제 제어 기능 활성화는 이번 범위가 아니다. DART Probe A 기록과 분리한 backlog이며 기존 실행 제한을 해제하지 않는다. 현재 NOT_RUNTIME_VERIFIED / Stage B BLOCKED를 유지한다.

## 목표와 착수 조건

사용자가 목표·환경·실험 횟수·예산을 설정하면 여러 정책을 반복 학습·평가하고 모델과 경로 후보를 비교하는 범용 실험 엔진을 설계한다. 드론·로봇·게임 환경에 확장한다. 모든 알고리즘이나 환경을 한 번에 구현하지 않는다.

사용자는 DART 및 Gazebo 검증 완료 후 구현 착수를 요청했다. 두 검증의 완료 증거와 그때의 작업 지침·승인 범위를 대조한 뒤 구현을 시작한다. Probe A의 무해 Fixture INTEGRATION_READY만으로 이 조건을 충족했다고 해석하지 않는다. 자동 시작 daemon/hook나 백그라운드 작업은 만들지 않는다. 실제 드론 제어는 별도 안전 검증과 명시 승인 전 비활성 상태로 유지한다.

## 기존 구조 확인과 재사용 후보

2026-11-07 실험 worktree의 파일·선언을 읽기 전용 확인했다. 아래는 재사용 후보이며, 새 엔진과의 호환성·기능 완전성을 검증했다는 뜻은 아니다.

|역할|기존 코드|
|---|---|
|정책과 생성|`src/aero_ai_studio/agents/{base,factory,q_learning,dqn}.py`|
|환경 추상화·GridWorld|`src/aero_ai_studio/simulation/{base,factory,grid_world}.py`|
|학습·체크포인트·비교|`src/aero_ai_studio/training/{trainer,checkpoint,comparison,curriculum}.py`|
|평가·일반화·안전 지표|`src/aero_ai_studio/evaluation/{evaluator,suites,generalization,safety_metrics}.py`|
|환경 생성·보관|`src/aero_ai_studio/scenario/{generator,models,repository}.py`|
|Brain Map·실패 분석|`src/aero_ai_studio/explainability/{brain_map,failure_analyzer}.py`|
|Replay|`src/aero_ai_studio/replay/{replay_engine,trajectory}.py`|
|외부 환경 연결|`src/aero_ai_studio/adapters/interfaces.py`, 기존 `gazebo/`와 `training/gazebo_dqn.py`|

`pyproject.toml`은 Python>=3.11, PySide6, 선택 DQN 의존성 torch/numpy, pytest tests 경로와 opt-in gazebo marker를 정의한다. 착수 시 `tests/test_pipeline.py`, `test_v07.py`, `test_temporal_dqn.py`, UI 및 관련 환경 테스트를 먼저 검토한다. 이번 문서 단계에서 테스트나 Gazebo는 실행하지 않았다.

## 제안하는 공통 계약

기존 인터페이스를 먼저 읽고 확장 가능한지 판단한다. 아래 이름은 개념 계약이며 신규 클래스를 반드시 별도로 만들라는 지시가 아니다.

- ExperimentSpec: 목표, 환경·지도 버전, 알고리즘/모델 목록, seed, train/validation/test 분할, episode/step/wall-time/메모리/프로세스 예산, 중지 정책, 지표·후보 선정 규칙.
- EnvironmentAdapter: 관측/행동 공간·단위·좌표계, seed 기반 reset, step 결과와 terminated/truncated 구분, 장애물·목표·상태 snapshot, close. GridWorld/Gazebo/지도3D/로봇/게임은 각각 adapter로 연결한다.
- AlgorithmAdapter: supported observation/action capabilities, configure, act(training/evaluation), update, save/load. DQN과 Q-Learning을 우선 재사용하고 지원하지 않는 연속행동 등은 실행 전 거부한다. PPO/SAC/A*/Dijkstra/RRT*는 확장 등록 지점만 둔다. 학습 정책과 비학습 planner의 update 지원 여부를 구분한다.
- ExperimentRunner: 환경과 분리된 유한 실행 state machine, 모델별 독립 상태/출력, 예산 검사, cancel, checkpoint/resume, 오류 분류. cancelled/resource-limit/timeout을 모델 실패와 구분하고 모두 기록한다.
- Evaluation/Analysis: 동결된 정책으로 독립 환경 평가, 공통 지표 집계와 후보 순위. 평가 데이터로 학습·모델 선택하지 않는다.
- Event/Artifact: run/model/episode/step/seed ID, simulation/관측 시각, schema version, provenance, 환경·설정·모델 hash, 좌표·단위. 동일 사건을 Brain Map/Replay/live UI에서 공유한다.

재개 체크포인트에는 정책뿐 아니라 optimizer/replay buffer/탐험률/RNG·환경 generator 상태, 분할 ID, 완료 episode·예산 사용량·마지막 확정 event를 포함한다. 원자적 저장과 불완전 체크포인트 거부, 설정/지도 버전 불일치 거부가 필요하다. 환경 상태를 정확히 복원할 수 없으면 episode 경계 재개로 제한하고 완전 재현이라고 주장하지 않는다. 실패 run 삭제나 자동 무한 재시도는 금지한다.

## 자동 실험과 데이터 분리

실험 횟수·모델 수·총 step/time/resource 상한을 명시한다. 실패 원인, 충돌, 환경 생성 실패, 유효하지 않은 평가, 중단을 보존한다. 실패 사례를 추가 학습하는 작업은 train partition 안에서만 수행하고 반복 횟수와 budget을 제한한다.

환경을 seed만이 아니라 layout·지도 지역·장애물 구성·환경 변화 조건으로 분리한다. train/validation/최종 holdout test를 사전에 고정하고 누수를 검사한다. 새 지역·미관측 layout에서 일반화를 평가한다. 후보 선택은 validation, 최종 성능 보고는 미사용 test로 수행한다. 학습 전후/모델/고전 planner 비교는 동일한 평가 조건·예산·seed와 분모를 사용한다. 여러 반복의 분산·표본 수·가능한 불확실성을 함께 보고한다.

## 실제 지도 기반 경로계획

지도 provider는 아직 선정하지 않는다. 지도 수입 단계에서 출처/이용조건/취득·관측 시각, CRS·수직 datum·해상도, 건물 높이·지형고도·장애물의 정확도와 누락·unknown 영역을 보존한다. 누락 높이를 0 또는 안전한 빈 공간으로 간주하지 않는다. 좌표 변환과 단위·고도 기준을 검증하고 보간/추정 영역을 표시한다.

출발·목적지·고도/공간 제약을 지정하고 3D 환경을 구성한다. 건물·지형·동적 장애물과 환경 변화 시나리오를 버전 관리한다. 거리·시간·충돌/여유거리·에너지 추정의 여러 경로 후보를 제시하며 가중치/모델 가정을 공개한다. 지도 경로는 별도 adapter를 통해 엔진과 연결한다.

에너지는 기체/질량/속도/바람/전력 모형이 없으면 추정 불가로 기록한다. 실행 step 수를 실제 시간이나 실제 에너지로 오인하지 않는다. 불확실한 지도와 시뮬레이션 성공은 실제 비행 안전성의 증명이 아니다. 실제 적용에는 별도 데이터 최신성·장애물/지오펜스·기체/센서·통신·제어/비상정지·현장 검증이 필요하다.

## 시각화와 종료 분석

live event로 현재/전체 실험 횟수, 진행률, 위치·목표·장애물, 이동 경로, 충돌·실패 원인, 누적 보상, 성공률, 이동 거리를 표시한다. 학습·평가 상태와 모델 ID, 데이터 지연/누락을 명확히 구분한다. UI queue 크기를 제한하고 중지 응답성을 유지한다. 기존 Brain Map과 Replay schema를 재사용하며 호환성이 없으면 versioned adapter를 둔다.

최종 보고에는 성공률·충돌률·실패 원인별 분모, 평균 거리·시간과 성공 episode 한정/전체 분모 구분, 에너지 추정과 불가 사유, 학습 전후·일반화·고전 planner 비교, 모델/경로 후보와 선택 규칙, 실제 적용 전 미검증 항목을 포함한다. 단일 reward 최고값만으로 안전하거나 최적이라고 선언하지 않는다.

## 단계별 구현 후보와 수용 기준

1. 선행 검증 완료 후 기존 인터페이스/테스트 재확인. GridWorld + 기존 DQN/Q-Learning 기반 유한 실험 설정·비교·artifact 계약을 우선 구현한다.
2. 중지/예산/실패 기록·체크포인트/episode 경계 재개를 검증한다. 중단 복구 시 episode 이중집계·데이터 누수·다른 모델 상태 공유가 없어야 한다.
3. 분리된 평가/새 환경 검증·실패기반 train-only 추가 학습과 Brain Map/Replay/live UI를 연결한다.
4. 지도 provenance·불확실성 및 3D adapter를 도입한다. 고전 planner 기준선은 환경/행동 공간과 평가 조건을 확인한 뒤 하나씩 추가한다.
5. 별도 승인된 Gazebo adapter 및 로봇/게임 환경을 확장한다. PPO/SAC/RRT* 등은 실제 필요와 테스트 근거가 생길 때 순차 구현한다.

이번 작업의 산출물은 이 설계 요구사항과 handoff 연결뿐이다. 일정·성능·정확도 목표와 구체 지도 provider는 미정이며 착수 시 확정한다. DART 기존 보고서·코드·판정·실행 경로는 변경하지 않는다.
