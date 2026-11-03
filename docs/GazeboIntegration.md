> V0.5 현재 문서: 프로젝트 루트 GAZEBO_INTEGRATION.md / OBSERVATION_ARCHITECTURE.md / AGENT_ARCHITECTURE.md. 아래는 V0.4 당시 계약·계획 이력입니다.

# V0.5 Gazebo 연결 계획

V0.4에는 Gazebo 설치나 실제 연동 코드, ROS2/PX4 실기체 연결이 없습니다. 기존 `SimulationEnvironment` 계약과 `environment_factory` 주입 지점으로 다음 단계를 준비했습니다.

## 변환 경로

| Aero 데이터 | Gazebo 대응 | 담당 |
|---|---|---|
| ScenarioSpec 0.4 | 재현 가능한 world·seed·환경 설정 | GazeboWorldGenerator |
| SceneObject / DynamicObject | SDF entity, geometry, collision, scripted motion | GazeboWorldGenerator |
| Agent / Goal | 시뮬레이션 UAV/Robot 및 mission entity | GazeboEnvironment |
| ObservationSpec | sensor topics, timestamps, frame/단위, discrete encoder | GazeboSensorBridge |
| action up/down/left/right | 명시적 로컬 좌표의 제한된 목표 속도/변위 | GazeboEnvironment |
| step(action) | 명령 적용 → 고정 dt stepping → 관측 barrier → StepResult | GazeboEnvironment |
| state / metrics / render | 2D 투영과 3D pose·sensor summary·평가 지표 | Bridge + renderer |

## 필요한 Adapter

`GazeboEnvironment`는 reset/step/get_observation/get_state/get_metrics/render/close와 capabilities를 구현합니다. `Trainer(..., environment_factory=...)`와 `Evaluator(..., environment_factory=...)`로 주입합니다. UI나 Trainer에 `if gazebo` 분기를 추가하지 않습니다.

`GazeboWorldGenerator`는 ScenarioSpec을 검증해 SDF world/entity를 생성합니다. 좌표계, grid cell 크기(m), 원점, altitude, physics dt, simulator 버전, plugin 버전, seed를 manifest에 저장합니다. 동적 객체의 실제 운동은 V0.4의 한 셀 이동 규칙과 다르므로 버전별 semantic 차이를 명시해야 합니다.

`GazeboSensorBridge`는 관측을 timestamp/sequence로 정렬하고 stale sample, 누락, timeout을 처리합니다. raw sensor payload는 별도 파일에 저장하고 event에는 경로·요약만 기록합니다. provider 이미지 복제나 지도 API를 전제로 하지 않습니다.

## 현재 계약의 범위와 V0.5 확장

V0.4 계약은 **discrete 2D action/observation adapter용**입니다. 현재 Q-agent는 위치 tuple만 사용하고 event·Grid UI는 width/height/agent/goal/obstacles가 있는 2D 투영을 요구합니다. Gazebo 초기 adapter는 이 투영과 기본 인코더를 제공해야 기존 파이프라인을 바로 재사용할 수 있습니다.

연속 제어, 3D pose 관측, 카메라 Tensor 정책을 붙일 때는 action/observation codec, renderer 선택, BrainEvent schema를 버전과 함께 확장해야 합니다. capabilities만 `supports_3d=True`로 바꾸는 것으로 3D 학습이 구현되지는 않습니다. Basic Q-table을 비행 정책으로 직접 export하지 않습니다.

## lifecycle 및 재현성

1. reset은 이전 episode entity/command를 정리하고 seed를 적용한 뒤 최초 유효 관측을 반환합니다.
2. step은 유한 시간 내에 반환하며 종료(충돌/목표)와 truncation(시간/step 한도)을 분리합니다.
3. close는 simulator 자원을 해제하고 여러 번 호출해도 안전해야 합니다. Trainer/Evaluator는 정상·예외 경로에서 호출합니다.
4. UI Stop은 episode 경계에서 checkpoint를 저장합니다. 네이티브 simulator가 멈춘 경우를 위해 Adapter 내부 timeout과 bounded close가 필수입니다.
5. 현재 GridWorld의 checkpoint 재현성은 episode마다 seed를 재설정하기 때문에 성립합니다. Gazebo는 physics 비결정성·entity 상태·sensor timing·plugin RNG까지 별도로 다뤄야 하며 bit-for-bit 일치를 자동 보장하지 않습니다.

## V0.5 검증 순서

- mock transport로 reset/step timeout, stale sensors, command ack, close 검증
- GUI 없는 Gazebo world 생성 및 정적 robot 이동 smoke test
- GridWorld와 동일한 작은 장애물 지도를 투영해 event/replay/evaluation 비교
- 고정 seed 집합, 학습/평가 분리, dynamic collision 및 센서 누락 시험
- simulator 버전과 실행 manifest를 모델 호환성에 포함
- 3D renderer·sensor summary를 점진적으로 연결

실기체 연결은 이 계획의 범위에 포함하지 않습니다.
