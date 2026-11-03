> V0.5 현재 문서: 프로젝트 루트 GAZEBO_INTEGRATION.md / OBSERVATION_ARCHITECTURE.md / AGENT_ARCHITECTURE.md. 아래는 V0.4 당시 계약·계획 이력입니다.

# SimulationEnvironment V0.4 계약

정의: `src/aero_ai_studio/simulation/base.py`. 기존 `TrainingEnvironment` 이름은 동일 Protocol의 alias입니다. `GridWorld`가 구현하며 Trainer와 Evaluator는 factory `(ScenarioSpec, max_steps) -> SimulationEnvironment`를 주입받습니다.

| API | 의미 |
|---|---|
| reset(seed=None) -> (x,y) | episode 초기화. 같은 spec/seed의 GridWorld 재현. closed 상태도 다시 활성화 |
| step(action) -> StepResult | up/down/left/right 중 하나. finished/closed 상태에서는 오류 |
| get_observation() -> (x,y) | Basic Q-table 인코딩을 유지한 위치 관측 |
| get_state() -> dict | UI와 기록을 위한 JSON snapshot. 정책 입력과 구분 |
| get_metrics() -> dict | steps, distance, shortest_path_distance, done |
| render() -> dict | Qt 독립 snapshot. UI는 renderer 역할만 수행 |
| close() | 자원 해제. GridWorld는 재호출 가능 |
| capabilities | real_time=False, 3d=False, dynamic_objects=True, sensors=False |

`StepResult`: observation, reward, terminated, truncated, reason. 종료 이유는 moving/goal/collision/moving_obstacle_collision/danger_zone/timeout입니다. goal·collision·danger는 terminated이고 max_steps는 truncated입니다. 두 플래그 중 하나가 참이면 episode가 끝납니다. Q-table은 두 경우 모두 bootstrap을 중단해 V0.3 semantics를 보존합니다.

snapshot 필수: agent, goal, obstacles, width, height, steps. 선택 확장: dynamic_objects, danger_zones, slow_zones, mission, action_evidence. 현재 UI는 2D 투영을 요구합니다. 향후 3D는 확장 renderer/codec이 필요합니다.

## GridWorld 규칙

- 정적 wall/legacy object/static_obstacle은 한 셀 장애물입니다. 경계/정적 충돌이면 agent 위치를 유지하고 reward -100으로 종료합니다.
- 한 step에서 moving object를 먼저 갱신한 뒤 agent의 의도 위치와 이전/이후 dynamic cell을 검사합니다. 진입·마주침·자리교환을 보수적으로 충돌로 판단합니다. 이동 객체가 이전 agent cell을 통과해도 충돌로 처리합니다. 실제 연속 물리 모델은 아닙니다.
- Horizontal/Vertical은 경계·장애물에서 반전합니다. Random은 seeded 방향 순서에서 이동 가능한 첫 셀로 갑니다. 동적 객체끼리 겹치지 않으며 goal로 이동하지 않습니다.
- Danger Zone 진입은 -50 terminal입니다. Slow Zone은 매 진입 step reward에 -3을 더합니다. 물리 속도 감소는 구현하지 않습니다.
- Goal +100. 안전 이동 -1, Manhattan 목표 거리가 줄면 +2를 추가합니다.
- 정적 최단 경로는 BFS로 계산하며 danger를 차단하고 dynamic timing 및 slow cost를 무시합니다. reset에서 정적 도달 가능성을 검사합니다.
- action validity는 경계/정적 점유만 판단합니다. collision_risk는 blocked/dynamic nearby/clear인 기하학적 휴리스틱이며 확률·정책 점수·완전한 미래 예측이 아닙니다. clear여도 이후 dynamic 충돌이 가능합니다.

## ObservationSpec

basic/extended, local_radius, include_nearest_obstacle, include_dynamic_positions를 저장합니다. `get_extended_observation()`은 agent·goal·local occupancy·최근접 장애물 거리/상대 방향·moving positions를 제공합니다. V0.4 Q-agent와 export는 **Basic (x,y)** 인코더만 사용합니다. UI도 이를 명시합니다. Extended encoder를 학습에 쓰려면 상태공간 제어와 모델 호환성 버전을 추가해야 합니다.

## 저장 및 checkpoint

JSON은 임시 파일에 UTF-8 쓰기 → flush/fsync → JSON 재파싱 → atomic replace 순서입니다. schema별 검증은 repository/engine에서 수행합니다. Checkpoint는 검증된 단일 `checkpoint.json`이 있는 staging directory를 committed directory로 rename합니다. `.pending_*`는 Resume 목록에서 제외됩니다. 전원 손실·파일시스템 고장까지 보장하는 database transaction은 아닙니다.

Checkpoint에는 Q-table, agent RNG, completed episode, 다음 episode의 epsilon, config, scenario snapshot, metrics, source run이 있습니다. 재개는 원본을 보존한 새 **Training Run**에 prefix episode 로그를 복사한 뒤 N+1에서 시작합니다. 새 코드 프로젝트를 만들지 않습니다. 원본 episode 로그는 Replay 연속성을 위해 필요하며 workspace 경로를 옮기면 source_run 경로 조정이 필요합니다. 실행 중인 여러 프로세스가 같은 workspace를 동시에 수정하는 것은 지원하지 않습니다.
