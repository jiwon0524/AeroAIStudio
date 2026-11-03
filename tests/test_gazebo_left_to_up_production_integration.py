import math

from aero_ai_studio.simulation.action_mapping import gazebo_physics_twist
from aero_ai_studio.simulation.base import StepResult
from tools.verify_v07_gazebo_left_to_up_production_integration import (
    assess_production_left_to_up, find_nonfinite_paths)


def _fixture():
    brake = {"phase": "BRAKE_ANGULAR", "completion_result": True,
        "command": {"linear": {"x": 0.0}, "angular": {"z": 0.0}},
        "elapsed_simulation_time": 0.2,
        "chunks": [{"collision_events": [],
            "body_stopped_contract": {"pass": True,
                "world_body_is_authority": True}},
            {"collision_events": [], "body_stopped_contract": {"pass": True,
                "world_body_is_authority": True}}]}
    acquire = {"phase": "ACQUIRE_LINEAR",
        "command": gazebo_physics_twist("up"),
        "command_published_after_braking": True,
        "brake_completion_publish_sequence": 10,
        "acquire_command_publish_sequence": 11,
        "elapsed_simulation_time": 0.1,
        "world_pose_history_contract": {"pass": True},
        "world_pose_history": {"world_forward_velocity_samples": [
            {"simulation_timestamp": 1.31, "forward_velocity": 0.04},
            {"simulation_timestamp": 1.35, "forward_velocity": 0.5}]},
        "end_body_forward_velocity": 0.5,
        "end_body_angular_velocity": 0.0,
        "world_forward_displacement": 0.03,
        "collision": False,
        "production_pose_validation": {"valid": True}}
    chunks = [
        {"phase": "BRAKE_ANGULAR", "reward": -0.1,
         "elapsed_execution_time": 0.1},
        {"phase": "BRAKE_ANGULAR", "reward": -0.1,
         "elapsed_execution_time": 0.1},
        {"phase": "ACQUIRE_LINEAR", "reward": -0.2,
         "elapsed_execution_time": 0.1},
    ]
    raw = {"left_rotation_precondition": {"pass": True,
            "world_pose_is_authority": True, "end_body_angular_velocity": 0.8,
            "world_angular_velocity_samples": [{"angular_velocity": 0.8}]},
        "acquisition_sensor_contract_pass": True,
        "acquisition_sensor_evidence": {"source": "gazebo_lidar",
            "sequence": 10, "age_ms": 0.0, "dimension": 22},
        "acquisition_contact_evidence": {"contract_pass": True,
            "expected_topic": "/world/test/contacts",
            "state": {"topic": "/world/test/contacts", "semantics": "event_only",
                "assessment": "healthy"},
            "schema": {"message_type": "gz.msgs.Contacts"}}}
    execution = {"agent_intent": "up", "previous_action": "left",
        "previous_command": gazebo_physics_twist("left"),
        "transition_type": "ROTATION_TO_LINEAR", "production_macro": True,
        "activation_pair": "LEFT_TO_UP", "physical_status": "EXECUTED",
        "control_executor_activation": {"active": True,
            "activation_pair": "LEFT_TO_UP",
            "verified_action_pair": ["left", "up"]},
        "collision": False, "macro_reward": -0.39,
        "reward_chunks": chunks, "control_chunk_count": 3,
        "elapsed_execution_time": 0.3, "elapsed_discount_units": 3.0,
        "execution_phases": [brake, acquire], "execution_evidence": raw}
    training = {"execution_evidence": execution,
        "agent_intent": "up", "previous_action": "left",
        "transition_type": "ROTATION_TO_LINEAR", "production_macro": True,
        "activation_pair": "LEFT_TO_UP",
        "control_executor_activation": execution["control_executor_activation"]}
    result = StepResult([0.0] * 22, -0.39, False, False, "moving",
        elapsed_execution_time=0.3, elapsed_discount_units=3.0)
    payload = [[0.0] * 22, 0, -0.39, [0.0] * 22, False, 3.0]
    return result, training, payload


def test_left_to_up_production_acceptance_reads_summary_and_raw_physical_evidence():
    result, training, payload = _fixture()
    assessment = assess_production_left_to_up(result, training,
        previous_command=gazebo_physics_twist("left"), before_steps=10,
        after_steps=11, process_alive=True, replay_payload=payload,
        recomputed_reward=-0.39)
    assert assessment["all_pass"] is True
    assert assessment["checks"]["initial_actual_left_rotation"] is True
    assert assessment["checks"]["collision_explicit_false"] is True
    assert assessment["checks"]["one_six_field_up_transition"] is True


def test_left_to_up_acceptance_does_not_treat_missing_collision_as_false():
    result, training, payload = _fixture()
    del training["execution_evidence"]["collision"]
    assessment = assess_production_left_to_up(result, training,
        previous_command=gazebo_physics_twist("left"), before_steps=10,
        after_steps=11, process_alive=True, replay_payload=payload,
        recomputed_reward=-0.39)
    assert assessment["checks"]["collision_explicit_false"] is False
    assert assessment["all_pass"] is False


def test_production_left_to_up_strict_json_nonfinite_path_detection():
    assert find_nonfinite_paths({"macro": {"chunks": [{"reward": math.nan}]}}) == [
        "$.macro.chunks[0].reward"]
