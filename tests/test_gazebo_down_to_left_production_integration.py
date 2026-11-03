from __future__ import annotations

from types import SimpleNamespace

import pytest

from aero_ai_studio.simulation.action_mapping import gazebo_physics_twist
from tools.verify_v07_gazebo_control_executor_down_to_left import PREFIX
from tools.verify_v07_gazebo_down_to_left_production_integration import (
    _acceptance, _validate_sources)


def test_production_verifier_requires_exact_saved_action_14_source():
    replay = {"completed_episode_actions": [PREFIX + ["left"]]}
    retry = {"episode_replays": [{"actions": [{"action": action} for action in PREFIX]}],
        "failed_replay_action": {"episode": 1,
            "episode_action_index_1_based": 14,
            "global_action_index_1_based": 14, "action": "left",
            "type": "PhysicalControlFailure"}}
    assert _validate_sources(replay, retry)["expected_prefix_count"] == 13
    retry["failed_replay_action"]["action"] = "up"
    with pytest.raises(ValueError):
        _validate_sources(replay, retry)


def _acceptance_fixture():
    chunks = [
        {"phase": "BRAKE_LINEAR", "reward": -0.1,
            "elapsed_execution_time": .1, "collision_events": []},
        {"phase": "BRAKE_LINEAR", "reward": -.1,
            "elapsed_execution_time": .1, "collision_events": []},
        {"phase": "ACQUIRE_ANGULAR", "reward": -.15,
            "elapsed_execution_time": .1},
    ]
    macro = -.1 + .95 * -.1 + .95**2 * -.15
    execution = {"physical_status": "EXECUTED", "activation_pair": "DOWN_TO_LEFT",
        "collision": False, "macro_reward": macro, "reward_chunks": chunks,
        "control_chunk_count": 3, "elapsed_execution_time": .3,
        "execution_phases": [
            {"phase": "BRAKE_LINEAR", "command": {"linear": {"x": 0.},
                "angular": {"z": 0.}}, "chunks": [{"collision_events": [],
                    "body_stopped_contract": {"pass": True,
                        "world_body_is_authority": True}},
                    {"collision_events": [], "body_stopped_contract": {
                        "pass": True, "world_body_is_authority": True}}],
                "completion_result": True},
            {"phase": "ACQUIRE_ANGULAR", "command": gazebo_physics_twist("left"),
                "collision": False, "command_published_after_braking": True,
                "brake_completion_publish_sequence": 5,
                "acquire_command_publish_sequence": 6,
                "world_pose_history_contract": {"pass": True},
                "world_pose_history": {"world_angular_velocity_samples": [
                    {"simulation_timestamp": 1.31, "angular_velocity": .1},
                    {"simulation_timestamp": 1.32, "angular_velocity": .8}]},
                "end_body_angular_velocity": .8,
                "production_pose_validation": {"valid": True},
                "sensor_contract_pass": True, "contact_contract_pass": True},
        ]}
    training = {"agent_intent": "left", "previous_action": "down",
        "transition_type": "LINEAR_TO_ROTATION", "production_macro": True,
        "activation_pair": "DOWN_TO_LEFT",
        "control_executor_activation": {"active": True},
        "execution_evidence": execution}
    result = SimpleNamespace(reward=macro, elapsed_execution_time=.3,
        elapsed_discount_units=3., terminated=False, truncated=False)
    payload = ([0.] * 22, 2, macro, [0.] * 22, False, 3.)
    return result, training, payload


def test_production_acceptance_passes_exact_pair_macro_evidence():
    result, training, payload = _acceptance_fixture()
    report = _acceptance(result, training, gazebo_physics_twist("down"),
        13, 14, payload, True, recomputed=result.reward)
    assert report["all_pass"] is True
    assert report["left_action_index"] == 2
    assert report["reward_chunk_count"] == report["control_chunk_count"] == 3
    assert report["elapsed_discount_units"] == pytest.approx(3.)


def test_production_acceptance_requires_explicit_collision_evidence():
    result, training, payload = _acceptance_fixture()
    execution = training["execution_evidence"]
    execution["execution_phases"][1].pop("collision")
    report = _acceptance(result, training, gazebo_physics_twist("down"),
        13, 14, payload, True, recomputed=result.reward)
    assert report["checks"]["collision_explicitly_false"] is False
    assert report["all_pass"] is False
