import json
import math
import pytest

from aero_ai_studio.simulation.action_mapping import gazebo_physics_twist
from aero_ai_studio.simulation.base import StepResult
from tools.verify_v07_gazebo_up_to_down_production_integration import (
    _optional_metric,
    _recompute_macro_reward,
    _write_report_with_fallback,
    assess_production_up_to_down,
    find_nonfinite_paths,
    prepare_report_for_json,
)
from aero_ai_studio.core.storage import write_json


def _fixture():
    brake = {"phase": "BRAKE_LINEAR",
        "command": {"linear": {"x": 0.}, "angular": {"z": 0.}},
        "chunks": [{
        "body_stopped_contract": {"pass": True, "world_body_is_authority": True},
        "collision_events": []},
        {"body_stopped_contract": {"pass": True, "world_body_is_authority": True},
         "collision_events": []}]}
    acquire = {"phase": "ACQUIRE_LINEAR",
        "command": gazebo_physics_twist("down"),
        "command_published_after_braking": True,
        "brake_completion_event_sequence": 4,
        "acquire_command_publish_event_sequence": 5,
        "world_pose_history_contract": {"pass": True},
        "world_pose_history": {"world_forward_velocity_samples": [
            {"forward_velocity": -.03}]},
        "requested_direction_established": True,
        "world_forward_displacement": -.026,
        "end_body_forward_velocity": -.5,
        "end_body_angular_velocity": 0.,
        "production_pose_validation": {"valid": True},
        "sensor_contract_pass": True, "contact_contract_pass": True,
        "collision": False}
    chunks = [
        {"phase": "BRAKE_LINEAR", "reward": -.053546370482323274,
         "elapsed_execution_time": .1, "terminated": False,
         },
        {"phase": "BRAKE_LINEAR", "reward": -.0999938451671806,
         "elapsed_execution_time": .1, "terminated": False,
         },
        {"phase": "ACQUIRE_LINEAR", "reward": -.15108178048844892,
         "elapsed_execution_time": .1, "terminated": False},
    ]
    gamma = .95
    reward = _recompute_macro_reward(gamma, chunks)
    summary = {"agent_intent": "down", "previous_action": "up",
        "transition_type": "LINEAR_REVERSAL", "production_macro": True,
        "activation_pair": "UP_TO_DOWN", "control_chunk_count": 3,
        "macro_reward": reward, "elapsed_execution_time": .3,
        "elapsed_discount_units": 3., "collision": False,
        "physical_status": "EXECUTED", "reward_chunks": chunks,
        "execution_phases": [brake, acquire],
        # Raw executor details are intentionally nested and do not own the
        # production reward/collision/SMDP summary.
        "execution_evidence": {"phase_evidence": [brake, acquire]}}
    training = {"agent_intent": "down", "previous_action": "up",
        "previous_command": gazebo_physics_twist("up"),
        "transition_type": "LINEAR_REVERSAL", "production_macro": True,
        "activation_pair": "UP_TO_DOWN",
        "control_executor_activation": {"active": True,
            "activation_pair": "UP_TO_DOWN"},
        "execution_evidence": summary}
    result = StepResult((1, 1), reward, False, False, "moving",
        elapsed_execution_time=.3, elapsed_discount_units=3.)
    payload = [[0.] * 22, 1, reward, [0.] * 22, False, 3.]
    return result, training, payload, reward


def test_production_up_to_down_acceptance_checks_exact_macro_and_transition():
    result, training, payload, recomputed = _fixture()
    assessment = assess_production_up_to_down(result, training,
        previous_command=gazebo_physics_twist("up"), before_steps=5,
        after_steps=6, process_alive=True, replay_payload=payload,
        recomputed_reward=recomputed)
    assert assessment["all_pass"] is True
    assert assessment["checks"]["brake_world_body_stopped"] is True
    assert assessment["checks"]["command_ordering"] is True
    assert assessment["checks"]["one_six_field_down_transition"] is True


def test_macro_reward_recomputation_counts_brake_and_acquire_once():
    _, training, _, recomputed = _fixture()
    canonical = training["execution_evidence"]
    expected = (-.053546370482323274 + .95 * -.0999938451671806 +
                (.95 ** 2) * -.15108178048844892)
    assert recomputed == pytest.approx(expected)
    assert recomputed == pytest.approx(canonical["macro_reward"])
    assert len(canonical["reward_chunks"]) == canonical["control_chunk_count"] == 3


def test_canonical_production_evidence_resolves_outer_summary_not_raw_executor():
    from aero_ai_studio.training.temporal import NOMINAL_DISCOUNT_TIME_UNIT_SECONDS
    from tools.verify_v07_gazebo_up_to_down_production_integration import (
        canonical_production_execution_evidence,
    )
    result, training, payload, _ = _fixture()
    training["execution_evidence"]["execution_evidence"].update(
        reward_chunks=[], collision=True, macro_reward=999.)
    canonical = canonical_production_execution_evidence(training)
    chunks = canonical["reward_chunks"]
    recomputed = _recompute_macro_reward(.95, chunks)
    assert len(chunks) == 3
    assert canonical["collision"] is False
    assert canonical["physical_status"] == "EXECUTED"
    assert canonical["control_chunk_count"] == 3
    assert recomputed == pytest.approx(-0.28489183028196996)
    assert sum(row["elapsed_execution_time"] for row in chunks) == \
        pytest.approx(canonical["elapsed_execution_time"])
    assert canonical["elapsed_discount_units"] == pytest.approx(
        canonical["elapsed_execution_time"] / NOMINAL_DISCOUNT_TIME_UNIT_SECONDS)
    assessment = assess_production_up_to_down(result, training,
        previous_command=gazebo_physics_twist("up"), before_steps=5,
        after_steps=6, process_alive=True, replay_payload=payload,
        recomputed_reward=recomputed)
    assert assessment["all_pass"] is True
    assert assessment["checks"]["reward_chunk_count_matches_control_chunks"] is True
    assert assessment["checks"]["reward_chunk_durations_match_execution"] is True
    assert assessment["checks"]["physical_execution_status_pass"] is True


def test_missing_canonical_collision_is_not_treated_as_collision_free():
    result, training, payload, recomputed = _fixture()
    del training["execution_evidence"]["collision"]
    assessment = assess_production_up_to_down(result, training,
        previous_command=gazebo_physics_twist("up"), before_steps=5,
        after_steps=6, process_alive=True, replay_payload=payload,
        recomputed_reward=recomputed)
    assert assessment["checks"]["collision_false"] is False
    assert assessment["all_pass"] is False


@pytest.mark.parametrize("field_value, expected", [(True, False)])
def test_canonical_collision_true_is_rejected(field_value, expected):
    result, training, payload, recomputed = _fixture()
    training["execution_evidence"]["collision"] = field_value
    assessment = assess_production_up_to_down(result, training,
        previous_command=gazebo_physics_twist("up"), before_steps=5,
        after_steps=6, process_alive=True, replay_payload=payload,
        recomputed_reward=recomputed)
    assert assessment["checks"]["collision_false"] is expected


@pytest.mark.parametrize("acquisition_collision", [None, True])
def test_acquisition_collision_missing_or_true_is_rejected(acquisition_collision):
    result, training, payload, recomputed = _fixture()
    acquire = training["execution_evidence"]["execution_phases"][1]
    if acquisition_collision is None:
        del acquire["collision"]
    else:
        acquire["collision"] = acquisition_collision
    assessment = assess_production_up_to_down(result, training,
        previous_command=gazebo_physics_twist("up"), before_steps=5,
        after_steps=6, process_alive=True, replay_payload=payload,
        recomputed_reward=recomputed)
    assert assessment["checks"]["collision_false"] is False


@pytest.mark.parametrize("events", [None, [{"collision": "wall"}]])
def test_brake_collision_events_missing_or_nonempty_are_rejected(events):
    result, training, payload, recomputed = _fixture()
    brake = training["execution_evidence"]["execution_phases"][0]
    if events is None:
        del brake["chunks"][0]["collision_events"]
    else:
        brake["chunks"][0]["collision_events"] = events
    assessment = assess_production_up_to_down(result, training,
        previous_command=gazebo_physics_twist("up"), before_steps=5,
        after_steps=6, process_alive=True, replay_payload=payload,
        recomputed_reward=recomputed)
    assert assessment["checks"]["collision_false"] is False


def test_acquire_reward_chunk_may_omit_collision_events_when_authorities_are_false():
    result, training, payload, recomputed = _fixture()
    chunks = training["execution_evidence"]["reward_chunks"]
    assert "collision_events" not in chunks[-1]
    assessment = assess_production_up_to_down(result, training,
        previous_command=gazebo_physics_twist("up"), before_steps=5,
        after_steps=6, process_alive=True, replay_payload=payload,
        recomputed_reward=recomputed)
    assert assessment["checks"]["collision_false"] is True
    assert assessment["checks"]["macro_reward_finite_and_exact"] is True
    assert assessment["checks"]["reward_chunk_count_matches_control_chunks"] is True
    assert assessment["checks"]["reward_chunk_durations_match_execution"] is True
    assert assessment["checks"]["one_six_field_down_transition"] is True


def test_acquisition_collision_event_evidence_cannot_conflict_with_false_summary():
    result, training, payload, recomputed = _fixture()
    acquire = training["execution_evidence"]["execution_phases"][1]
    acquire["collision_events"] = [{"collision": "wall"}]
    assessment = assess_production_up_to_down(result, training,
        previous_command=gazebo_physics_twist("up"), before_steps=5,
        after_steps=6, process_alive=True, replay_payload=payload,
        recomputed_reward=recomputed)
    assert assessment["checks"]["collision_false"] is False


def test_up_to_down_acceptance_rejects_missing_body_or_odometry_only_evidence():
    result, training, payload, recomputed = _fixture()
    phase = training["execution_evidence"]["execution_phases"][1]
    phase["world_pose_history_contract"]["pass"] = False
    assessment = assess_production_up_to_down(result, training,
        previous_command=gazebo_physics_twist("up"), before_steps=5,
        after_steps=6, process_alive=True, replay_payload=payload,
        recomputed_reward=recomputed)
    assert assessment["checks"]["down_world_body_acquisition"] is False
    assert assessment["all_pass"] is False


def test_production_verifier_uses_environment_step_for_exact_target():
    from pathlib import Path
    source = (Path(__file__).parents[1] /
        "tools/verify_v07_gazebo_up_to_down_production_integration.py").read_text()
    assert 'result = adapter.step("down")' in source
    assert '"production_environment_step_used_for_target": False' in source
    assert 'last_completed_stage="REPLAYING_PREFIX"' in source
    assert "executor.execute_plan" not in source


def test_nonfinite_audit_reports_exact_nested_nan_inf_paths():
    payload = {"acceptance": {"metric": math.nan},
        "execution": [{"velocity": math.inf}, {"reward": -math.inf}]}
    assert find_nonfinite_paths(payload) == [
        "$.acceptance.metric", "$.execution[0].velocity", "$.execution[1].reward"]


def test_optional_unavailable_metric_is_null_with_explicit_reason():
    metric = _optional_metric(None, "reward chunks absent")
    assert metric == {"value": None, "status": "UNAVAILABLE",
        "reason": "reward chunks absent"}


def test_nonfinite_required_metric_forces_acceptance_rejection_and_null_json_value():
    report = {"status": "ACCEPTANCE_COMPLETE",
        "verdict": "PRODUCTION_UP_TO_DOWN_LINEAR_REVERSAL_ACTUAL_VERIFIED",
        "target_physical_result_returned": True,
        "acceptance": {"checks": {"physical": True}, "all_pass": True},
        "target_execution": {"transition": [[], 1, math.nan, [], False, 3.]}}
    prepared = prepare_report_for_json(report)
    assert prepared["nonfinite_field_paths"] == ["$.target_execution.transition[2]"]
    assert prepared["target_execution"]["transition"][2] is None
    assert prepared["acceptance"]["checks"]["strict_json_evidence_finite"] is False
    assert prepared["acceptance"]["all_pass"] is False
    assert prepared["verdict"] != "PRODUCTION_UP_TO_DOWN_LINEAR_REVERSAL_ACTUAL_VERIFIED"
    json.dumps(prepared, allow_nan=False)


def test_report_preparation_preserves_physical_evidence_and_is_strict_json(tmp_path):
    report = {"status": "ACCEPTANCE_COMPLETE", "target_physical_result_returned": True,
        "last_completed_stage": "TARGET_PHYSICAL_RESULT_RETURNED",
        "target_execution": {"physical_status": "EXECUTED",
            "elapsed_execution_time": .3, "execution_history": [math.inf]},
        "acceptance": {"checks": {"physical": True}, "all_pass": True}}
    prepared = prepare_report_for_json(report)
    path = tmp_path / "nested" / "report.json"
    write_json(path, prepared)
    saved = json.loads(path.read_text())
    assert saved["target_physical_result_returned"] is True
    assert saved["target_execution"]["physical_status"] == "EXECUTED"
    assert saved["target_execution"]["execution_history"] == [None]
    assert saved["acceptance"]["all_pass"] is False
    assert find_nonfinite_paths(saved) == []


def test_serialization_failure_fallback_keeps_target_physical_evidence(tmp_path,
                                                                      monkeypatch):
    import tools.verify_v07_gazebo_up_to_down_production_integration as verifier
    original = verifier.write_json
    calls = []
    def fail_first(path, data):
        calls.append(1)
        if len(calls) == 1:
            raise ValueError("injected report serialization failure")
        return original(path, data)
    monkeypatch.setattr(verifier, "write_json", fail_first)
    report = {"schema_version": "0.7.1", "verifier": "fixture",
        "status": "BUILDING_ACCEPTANCE", "failure_stage": "ACCEPTANCE_CALCULATION",
        "last_completed_stage": "TARGET_PHYSICAL_RESULT_RETURNED",
        "target_physical_result_returned": True,
        "target_production_step_call_started": True,
        "production_environment_step_used_for_target": True,
        "acceptance_calculation_completed": False,
        "target_execution": {"step_result": {"reward": -.3},
            "production_training_evidence": {"physical_status": "EXECUTED"}},
        "shutdown": "PASS"}
    saved = _write_report_with_fallback(tmp_path / "fallback.json", report)
    parsed = json.loads((tmp_path / "fallback.json").read_text())
    assert saved["status"] == "REPORT_SERIALIZATION_FAILED"
    assert parsed["target_physical_result_returned"] is True
    assert parsed["production_training_evidence"]["physical_status"] == "EXECUTED"
    assert parsed["acceptance_calculation_completed"] is False


def test_empty_reward_chunks_are_unavailable_not_nan_and_cannot_pass():
    assert _recompute_macro_reward(.95, []) is None
    result, training, payload, _ = _fixture()
    training["execution_evidence"]["reward_chunks"] = []
    training["execution_evidence"]["control_chunk_count"] = 0
    assessment = assess_production_up_to_down(result, training,
        previous_command=gazebo_physics_twist("up"), before_steps=5,
        after_steps=6, process_alive=True, replay_payload=payload,
        recomputed_reward=None)
    assert assessment["macro_reward_recomputation_status"] == \
        "UNAVAILABLE_REQUIRED_FOR_ACCEPTANCE"
    assert assessment["checks"]["macro_reward_finite_and_exact"] is False
    assert assessment["all_pass"] is False


def test_acceptance_requires_finite_six_field_payload_reward_macro_and_time():
    result, training, payload, recomputed = _fixture()
    assert len(payload) == 6 and payload[1] == 1
    assert all(math.isfinite(value) for value in (payload[2], payload[5],
        result.elapsed_execution_time, result.elapsed_discount_units,
        training["execution_evidence"]["macro_reward"], recomputed))
    assert result.elapsed_execution_time > 0.
    assert result.elapsed_discount_units > 0.
