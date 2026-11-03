# Aero AI Studio

**AI training, simulation, safety evaluation, and physics-validation platform for autonomous systems.**

Aero AI Studio는 항공·방산 및 자율시스템 연구를 목표로 개발 중인 데스크톱 AI 연구 플랫폼입니다. GridWorld에서의 강화학습부터 Gazebo 기반 물리 시뮬레이션, 센서 관측, Safety Layer, Replay, Brain Map, 모델 평가·내보내기까지 하나의 연구 흐름으로 연결하는 것을 목표로 합니다.

> **Current status — V0.7.1 / active validation**  
> Ubuntu 24.04 + Gazebo Harmonic 실제 환경에서 핵심 물리 통합 경로를 검증하고 있으며, 특정 history-sensitive motion anomaly(Action24)는 원인을 축소하는 진단 연구를 계속하고 있습니다. 해당 현상은 해결된 것으로 주장하지 않습니다.

## Why this project

강화학습 모델의 성공률만 보는 것이 아니라 다음 질문까지 추적할 수 있는 연구 환경을 만드는 것이 목적입니다.

- 모델이 어떤 관측을 기반으로 행동했는가?
- Safety 개입이 충돌과 timeout에 어떤 영향을 주는가?
- 시뮬레이터의 센서·접촉·물리 상태가 실제로 동기화되어 있는가?
- 같은 정지 상태처럼 보여도 이전 action history가 다음 물리 응답에 영향을 주는가?
- 학습된 모델을 실제 UAV/로봇 시스템으로 옮기기 전에 어떤 검증이 필요한가?

## Core capabilities

### Reinforcement Learning
- Q-Learning 및 DQN 계열 agent
- Replay Buffer / Target Network / Checkpoint & Resume
- Curriculum 기반 난이도 증가
- 학습 run 비교 및 평가
- 모델 export 경로

### Simulation
- GridWorld 기반 빠른 학습·회귀 검증
- Gazebo Harmonic 물리 backend
- KINEMATIC / PHYSICS 실행 경로 분리
- DiffDrive/Twist 기반 물리 제어
- step 단위 simulation-time 검증
- persistent reset 및 episode lifecycle 관리

### Observation & Sensors
- BASIC / LOCAL / SENSOR / FULL_DEBUG observation 구성
- timestamp / sequence / freshness 검사
- sensor synchronization 계약
- contact 기반 collision 판정
- 실제 scene pose / telemetry 수집

### Safety & Evaluation
- Safety Layer를 통한 행동 개입
- collision / timeout / success / clearance 평가
- 동일 조건에서 Safety ON/OFF 비교
- generalization 및 evaluation suite

### Explainability & Replay
- Brain Map을 통한 **관측 가능한 의사결정 증거** 시각화
- trajectory 저장 및 Replay
- failure analysis
- 내부 hidden chain-of-thought를 노출하거나 추정하지 않음

## Gazebo validation status

초기 V0.7 문서는 실제 Ubuntu/Gazebo 환경 부재 때문에 `NOT VERIFIED` 상태에서 작성되었습니다. 이후 native Ubuntu 24.04 환경으로 이동하여 검증을 계속했습니다.

현재 실제 Gazebo 환경에서 확인한 핵심 범위:

- world launch 및 simulation stepping
- sensor acquisition / freshness 경로
- 실제 model movement
- contact / collision 관측
- persistent reset 경계
- Sensor → Agent → Action → Physics → Sensor closed-loop 경로
- DiffDrive/Twist 기반 production control path

다만 **UAV 비행 물리 검증을 완료했다는 의미는 아닙니다.** 현재 PHYSICS 검증의 중심은 지상 DiffDrive agent이며, 실제 F450/PX4 비행체 적용은 별도 프로젝트에서 진행합니다.

## Action24 — determinism / physics diagnostics

실제 Gazebo 검증 중 특정 action history에서 `DOWN → UP` 전환 시 wheel command와 odometry는 진행하지만 body acquisition이 거의 발생하지 않는 현상을 재현했습니다.

이를 단순 workaround로 덮지 않고 다음과 같은 방식으로 원인을 단계적으로 축소하고 있습니다.

- canonical action sequence 고정 및 반복 재현
- standalone transition과 history-dependent transition 비교
- wheel/contact/support-load/joint-state 관측
- duration-matched sham 비교
- yaw / phase / physical microstate 진단
- one-tick intervention 및 dose-response 비교
- public Gazebo observer를 이용한 instrumentation-neutrality 검증

현재 증거는 **history-sensitive physical state가 존재할 가능성**을 강하게 보여주지만, 최종 mediator/root mechanism은 아직 확정하지 않았습니다. 진단 과정에서는 관찰 결과와 인과 결론을 구분합니다.

대용량 raw Gazebo evidence는 로컬에 보존하며 Git 저장소에는 포함하지 않습니다. GitHub에는 재현 코드, 테스트, 진단 도구와 문서만 유지합니다.

## Architecture

```text
Aero AI Studio
├── Agent
│   ├── Q-Learning
│   └── DQN
├── Observation
│   ├── Canonical State
│   ├── Sensor Encoder
│   └── Prediction
├── Simulation
│   ├── GridWorld
│   └── Gazebo Physics
├── Training
│   ├── Curriculum
│   ├── Checkpoint
│   └── Reward / Temporal Logic
├── Safety
├── Evaluation
├── Replay / Brain Map
├── Deployment Export
└── PySide6 Desktop UI
```

## Tech stack

- Python
- PyTorch
- PySide6
- Gazebo Harmonic
- ROS 2 Jazzy (optional integration path)
- C++ Gazebo observer utilities
- pytest

Primary native validation environment: **Ubuntu 24.04**.

## Repository structure

```text
src/aero_ai_studio/
├── agents/          # Q-Learning / DQN
├── gazebo/          # bridge, sensors, stepping, physics control
├── observation/     # observation models and encoding
├── training/        # trainer, curriculum, checkpoint, rewards
├── evaluation/      # evaluation and safety metrics
├── safety/          # Safety Layer
├── replay/          # trajectory / replay
├── explainability/  # Brain Map / failure analysis
├── deploy/          # model export
└── ui/              # PySide6 desktop UI

tests/               # regression / integration / diagnostic tests
tools/               # Gazebo verification and forensic diagnostics
docs/                # architecture and validation notes
scripts/             # environment setup / verification
```

## Run locally

Ubuntu development environment:

```bash
bash scripts/setup_ubuntu_dev.sh
```

Run tests from the project virtual environment:

```bash
PYTHONPATH=.:src .venv-ubuntu/bin/python -m pytest -q
```

Launch the application:

```bash
PYTHONPATH=src .venv-ubuntu/bin/python -m aero_ai_studio
```

Gazebo-dependent validation requires a compatible native Gazebo environment. Runtime absence or skipped integration tests must not be interpreted as successful physical validation.

## Related UAV project

Aero AI Studio와 실제 UAV 시스템은 역할을 분리합니다.

**Aero AI Studio**  
AI 학습 → 시뮬레이션 → 평가 → Safety 검증 → 모델 export

↓

**[autonomous-uav-system](https://github.com/jiwon0524/autonomous-uav-system)**  
ROS 2 / PX4 → 센서·카메라 → 경로계획·회피 → F450 실제 기체 통합

이 구조를 통해 학습·검증 플랫폼과 실제 비행체 코드를 독립적으로 관리하면서 최종적으로 연결하는 것을 목표로 합니다.

## Roadmap

- [x] GridWorld Q-Learning / DQN
- [x] Evaluation / Checkpoint / Replay
- [x] Observation V2
- [x] Gazebo closed-loop foundation
- [x] Safety evaluation path
- [x] Native Gazebo core integration validation
- [ ] Action24 root-mechanism closure
- [ ] Gazebo validation framework generalization
- [ ] richer 3D / map environments
- [ ] trained-model deployment interface
- [ ] ROS 2 / PX4 / F450 integration

## Documentation

- [Agent architecture](AGENT_ARCHITECTURE.md)
- [Gazebo integration](GAZEBO_INTEGRATION.md)
- [Observation architecture](OBSERVATION_ARCHITECTURE.md)
- [Safety Layer](SAFETY_LAYER.md)
- [Reward system](REWARD_SYSTEM.md)
- [Validation notes](VALIDATION.md)
- [Change log](CHANGES.md)

---

This repository is an active research/development project. Validation status is reported conservatively: reproduced evidence, unresolved behavior, and completed verification are intentionally distinguished.