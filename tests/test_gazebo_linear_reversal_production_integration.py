from types import SimpleNamespace

from aero_ai_studio.gazebo.control_executor import GazeboLinearReversalControlExecutor
from aero_ai_studio.simulation.action_mapping import gazebo_physics_twist
from aero_ai_studio.simulation.base import StepResult
from tools.verify_v07_gazebo_linear_reversal_production_integration import (
    assess_production_macro,
    _validate_replayed_target_prefix,
    run_verifier,
)


def _fixture():
    brake = {"phase": "BRAKE_LINEAR", "completion_result": True,
        "chunks": [{"body_stopped_contract": {"pass": True}}]}
    acquire = {"phase": "ACQUIRE_LINEAR", "command_published_after_braking": True,
        "brake_completion_event_sequence": 7,
        "acquire_command_publish_event_sequence": 8,
        "world_pose_history_contract": {"pass": True},
        "requested_direction_established": True,
        "world_forward_displacement": .034,
        "end_body_forward_velocity": .5,
        "production_pose_validation": {"valid": True},
        "sensor_contract_pass": True, "contact_contract_pass": True,
        "collision": False}
    result = StepResult((1, 1), -0.3, False, False, "moving",
        elapsed_execution_time=.3, elapsed_discount_units=3.)
    result.execution_evidence = {"execution_phases": [brake, acquire]}
    rewards = [{"phase": "BRAKE_LINEAR", "reward": -.1},
               {"phase": "BRAKE_LINEAR", "reward": -.1},
               {"phase": "ACQUIRE_LINEAR", "reward": -.1}]
    training = {"agent_intent": "up", "previous_action": "down",
        "previous_command": gazebo_physics_twist("down"),
        "transition_type": "LINEAR_REVERSAL", "production_macro": True,
        "activation_pair": "DOWN_TO_UP", "control_chunk_count": 3,
        "macro_reward": result.reward, "elapsed_discount_units": 3.,
        "collision": False, "reward_chunks": rewards,
        "control_executor_activation": {"active": True,
            "activation_pair": "DOWN_TO_UP"},
        "execution_evidence": {"execution_phases": [brake, acquire]}}
    payload = [[0.] * 22, 0, result.reward, [0.] * 22, False, 3.]
    return result, training, payload, acquire


def test_production_integration_acceptance_checks_exact_down_up_macro():
    result, training, payload, _ = _fixture()
    assessment = assess_production_macro(result, training,
        previous_command=gazebo_physics_twist("down"), before_steps=39,
        after_steps=40, process_alive=True, replay_transition=payload)
    assert assessment["all_pass"] is True
    assert assessment["checks"]["exact_activation_pair"] is True
    assert assessment["checks"]["brake_before_acquire_publish"] is True


def test_production_integration_rejects_up_down_or_incorrect_pair():
    result, training, payload, _ = _fixture()
    training["previous_command"] = gazebo_physics_twist("up")
    assessment = assess_production_macro(result, training,
        previous_command=gazebo_physics_twist("up"), before_steps=39,
        after_steps=40, process_alive=True, replay_transition=payload)
    assert assessment["checks"]["previous_action_down"] is True
    assert assessment["checks"]["previous_command_down"] is False


def test_ordering_event_sequence_is_required_even_when_phases_exist():
    result, training, payload, acquire = _fixture()
    acquire["acquire_command_publish_event_sequence"] = 6
    assessment = assess_production_macro(result, training,
        previous_command=gazebo_physics_twist("down"), before_steps=39,
        after_steps=40, process_alive=True, replay_transition=payload)
    assert assessment["checks"]["brake_before_acquire_publish"] is False


def test_replay_payload_requires_one_six_field_up_transition_and_one_decision():
    result, training, payload, _ = _fixture()
    payload[1] = 1  # DOWN instead of source-of-truth UP index 0.
    assessment = assess_production_macro(result, training,
        previous_command=gazebo_physics_twist("down"), before_steps=39,
        after_steps=42, process_alive=True, replay_transition=payload)
    assert assessment["checks"]["one_six_field_replay_transition"] is False
    assert assessment["checks"]["one_agent_decision"] is False


def test_verifier_uses_production_step_not_experimental_executor_directly():
    from pathlib import Path
    source = (Path(__file__).parents[1] /
        "tools/verify_v07_gazebo_linear_reversal_production_integration.py").read_text()
    assert 'result = adapter.step("up")' in source
    assert "executor.execute_plan" not in source


def test_target_prefix_validation_requires_and_preserves_all_39_actions():
    actions = ["right"] * 38 + ["down"]
    report = {"target_episode_prefix_actions": [
        {"action": action, "episode_action_index_1_based": index}
        for index, action in enumerate(actions, 1)]}
    _validate_replayed_target_prefix(report, actions)
    assert len(report["target_episode_prefix_actions"]) == 39
    report["target_episode_prefix_actions"].pop()
    try:
        _validate_replayed_target_prefix(report, actions)
    except RuntimeError as error:
        assert "expected 39, replayed 38" in str(error)
    else:
        raise AssertionError("incomplete target prefix was accepted")


def test_artifact_extraction_failure_is_written_with_stage_and_error(tmp_path,
                                                                    monkeypatch):
    import tools.verify_v07_gazebo_linear_reversal_production_integration as verifier
    monkeypatch.setattr(verifier, "extract_reversal_replay",
        lambda _: (_ for _ in ()).throw(ValueError("bad saved artifact")))
    report = run_verifier(tmp_path / "missing", tmp_path / "out")
    assert report["status"] == "FAILED"
    assert report["failure_stage"] == "ARTIFACT_EXTRACTION"
    assert report["error"] == {"type": "ValueError", "message": "bad saved artifact"}
    assert report["target_prefix_expected_count"] is None
    assert report["acceptance"] is None
    assert report["production_environment_step_used_for_target"] is False


def test_startup_failure_keeps_stage_process_and_last_reset_evidence(tmp_path,
                                                                     monkeypatch):
    import json
    import tools.verify_v07_gazebo_linear_reversal_production_integration as verifier
    replay = {"failed_episode_number": 2,
        "target_action_index_in_episode_1_based": 40,
        "target_global_action_index_1_based": 290,
        "failed_episode_saved_prefix": ["down"] * 39,
        "scenario": {}, "max_steps": 250, "training_seed": 42}
    monkeypatch.setattr(verifier, "extract_reversal_replay", lambda _: replay)

    class Manager:
        def status(self):
            return {"status": "Running", "available": True}

    class Process:
        pid = 123
        def poll(self):
            return None

    class Adapter:
        injected = False
        control_mode = "PHYSICS"
        process = Process()
        manager = Manager()
        restart_fallbacks = 0
        last_reset_evidence = {"reset_method": "fresh_process_initialization"}
        def __init__(self, *args, **kwargs):
            pass
        def reset(self, seed):
            raise RuntimeError("initial reset evidence unavailable")
        def close(self):
            pass

    monkeypatch.setattr(verifier.ScenarioSpec, "from_dict", lambda _: object())
    report = run_verifier(tmp_path, tmp_path / "out", env_factory=Adapter)
    saved = json.loads((tmp_path / "out" /
        "linear_reversal_production_integration.json").read_text())
    assert report["status"] == "FAILED"
    assert report["failure_stage"] == "INITIAL_RESET"
    assert report["last_completed_stage"] == "ENVIRONMENT_STARTUP"
    assert report["error"]["message"] == "initial reset evidence unavailable"
    assert report["last_reset_evidence"]["reset_method"] == "fresh_process_initialization"
    assert report["process_status"] == {"status": "Running", "available": True}
    assert saved["target_prefix_expected_count"] == 39
    assert saved["target_prefix_replayed_count"] == 0
    assert saved["production_environment_step_used_for_target"] is False
    assert saved["acceptance"] is None
    assert saved["shutdown"] == "PASS"


def test_fresh_initialization_not_episode_boundary_fallback():
    from tools.verify_v07_gazebo_control_executor_linear_reversal import (
        _episode_boundary_reset_gate,
    )
    gate = _episode_boundary_reset_gate(
        {"reset_method": "fresh_process_initialization",
         "restart_fallback_used": False, "restart_fallback_count": 0,
         "normal_reset_pass": True},
        fallback_count_before=0, fallback_count_after=0,
        pid_before=101, pid_after=101,
        process_alive=True)
    # The shared deterministic gate is for episode boundaries; the initial
    # fresh process is validated separately and is never treated as fallback.
    assert gate["actual_process_restart_fallback"] is False


def test_target_call_evidence_defaults_false_until_actual_call():
    from pathlib import Path
    source = (Path(__file__).parents[1] /
        "tools/verify_v07_gazebo_linear_reversal_production_integration.py").read_text()
    assert '"production_environment_step_used_for_target": False' in source
    assert source.index('report["production_environment_step_used_for_target"] = True') < \
        source.index('result = adapter.step("up")')
