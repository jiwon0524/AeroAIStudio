# V0.7 (2026-10-31)

V0.7 CODE COMPLETE / ACTUAL GAZEBO VALIDATION PENDING

GAZEBO ACTUAL INTEGRATION: NOT VERIFIED

기존 V0.6 확장. native timestamp/contact/physics/lifecycle/discovery, telemetry/UI, curriculum quota, Safety audit와 Ubuntu check-first 도구를 추가했습니다. 기존 테스트 소스 유지. Grid3seed×2000 학습·1200평가 실행, 상세 결과 VALIDATION.md. Ubuntu 배포판과 gz가 없어 P0 실제 검증 및 후속 Geo 기능 보류.

# V0.5 → V0.6 파일 변경

같은 프로젝트를 확장했습니다. 기존 파일 삭제0개, 기존 V0.5 테스트6개 파일은 byte 단위로 보존했습니다. 사용자데이터/venv/중간학습로그는 제외합니다.

## 추가

- DYNAMIC_OBSTACLE.md
- REWARD_SYSTEM.md
- SAFETY_LAYER.md
- docs/V0.5-GAZEBO_INTEGRATION.md
- docs/V0.5-README.md
- docs/V0.5-VALIDATION.md
- scripts/check_sim_environment.py
- scripts/setup_ubuntu_sim.sh
- src/aero_ai_studio/evaluation/suites.py
- src/aero_ai_studio/gazebo/entity_controller.py
- src/aero_ai_studio/gazebo/process_manager.py
- src/aero_ai_studio/gazebo/sensor_provider.py
- src/aero_ai_studio/gazebo/stepping.py
- src/aero_ai_studio/gazebo/transport.py
- src/aero_ai_studio/observation/canonical.py
- src/aero_ai_studio/observation/prediction.py
- src/aero_ai_studio/replay/trajectory.py
- src/aero_ai_studio/safety/__init__.py
- src/aero_ai_studio/safety/layer.py
- src/aero_ai_studio/simulation/factory.py
- src/aero_ai_studio/training/curriculum.py
- src/aero_ai_studio/training/rewards.py
- src/aero_ai_studio/ui/v06_panels.py
- tests/test_gazebo_integration.py
- tests/test_ui_v06.py
- tests/test_v06.py
- tools/capture_v06.py
- tools/closed_loop_smoke.py
- tools/verify_v06.py
- validation/v06/brain.png
- validation/v06/closed_loop_smoke.json
- validation/v06/closed_loop_world.sdf
- validation/v06/closed_loop_world_metadata.json
- validation/v06/diagnostics.png
- validation/v06/evaluation.png
- validation/v06/observation.png
- validation/v06/performance_v06.json
- validation/v06/replay.png
- validation/v06/training.png
- validation/v06/trajectory.png

## 수정

- AGENT_ARCHITECTURE.md
- FILES.txt
- GAZEBO_INTEGRATION.md
- OBSERVATION_ARCHITECTURE.md
- PHASE_LOG.md
- README.md
- VALIDATION.md
- pyproject.toml
- src/aero_ai_studio/__init__.py
- src/aero_ai_studio/agents/dqn.py
- src/aero_ai_studio/agents/factory.py
- src/aero_ai_studio/agents/q_learning.py
- src/aero_ai_studio/evaluation/evaluator.py
- src/aero_ai_studio/explainability/brain_map.py
- src/aero_ai_studio/explainability/failure_analyzer.py
- src/aero_ai_studio/gazebo/diagnostics.py
- src/aero_ai_studio/gazebo/environment.py
- src/aero_ai_studio/gazebo/world_generator.py
- src/aero_ai_studio/observation/encoder.py
- src/aero_ai_studio/observation/provider.py
- src/aero_ai_studio/scenario/models.py
- src/aero_ai_studio/simulation/grid_world.py
- src/aero_ai_studio/training/checkpoint.py
- src/aero_ai_studio/training/trainer.py
- src/aero_ai_studio/ui/research_panels.py
- src/aero_ai_studio/ui/v05_panels.py
- src/aero_ai_studio/ui/widgets.py
- src/aero_ai_studio/ui/window.py
