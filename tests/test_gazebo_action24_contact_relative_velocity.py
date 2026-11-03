import math

from tools import diagnose_v07_gazebo_action24_contact_relative_velocity as diag


def _qz(deg):
    h = math.radians(deg) / 2
    return {"x": 0.0, "y": 0.0, "z": math.sin(h), "w": math.cos(h)}


def test_compose_model_relative_wheel_pose_into_world_frame():
    body = {"x": 2.0, "y": 3.0, "z": 0.1, "orientation": _qz(90)}
    wheel = {"x": 0.0, "y": 0.2, "z": -0.06,
        "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}}
    result = diag.compose_link_world_pose(body, wheel)
    assert result["position_world_m"] == pytest.approx((1.8, 3.0, 0.04))


def test_contact_point_velocity_matches_rolling_baseline():
    # DOWN: body -0.5 X and wheel rotation -5 Y at a 0.1 m bottom contact.
    row = diag.contact_relative_velocity((0, 0, -0.1), (0, 0, 1),
        (-0.5, 0, 0), (0, -5, 0), (0, 0, 0))
    assert row["wheel_contact_velocity_world_m_s"] == pytest.approx((0, 0, 0))
    assert row["tangential_relative_speed_m_s"] == pytest.approx(0)
    assert row["provenance"].startswith("DERIVED:")


def test_contact_point_velocity_detects_forward_wheel_surface_sliding():
    # UP: stationary body, +5 Y wheel rotation, bottom contact at -Z.
    row = diag.contact_relative_velocity((0, 0, -0.1), (0, 0, 1),
        (0, 0, 0), (0, 5, 0), (0, 0, 0))
    assert row["relative_velocity_world_m_s"] == pytest.approx((-0.5, 0, 0))
    assert row["normal_relative_velocity_m_s"] == pytest.approx(0)
    assert row["tangential_relative_velocity_world_m_s"] == pytest.approx((-0.5, 0, 0))
    assert row["tangential_relative_speed_m_s"] == pytest.approx(0.5)


def test_world_contact_normal_is_normalized_before_projection():
    row = diag.contact_relative_velocity((0, 0, 0), (0, 0, 4),
        (1, 2, 3), (0, 0, 0), (0, 0, 0))
    assert row["normal_relative_velocity_m_s"] == pytest.approx(3)
    assert row["tangential_relative_velocity_world_m_s"] == pytest.approx((1, 2, 0))


def test_action24_target_must_be_production_replay():
    evidence = {"target": {"global_action_index": 24, "previous_action": "down",
        "requested_action": "up"}, "actions_1_to_23_used_production_adapter": True,
        "target_used_production_adapter": True, "target_production_step_call_started": True}
    assert diag.validate_production_replay_contract(evidence)
    evidence["target_used_production_adapter"] = False
    with pytest.raises(ValueError):
        diag.validate_production_replay_contract(evidence)


def test_action23_baseline_classifies_each_wheel_independently():
    assert diag.compare_against_rolling_baseline([0.01, 0.02, 0.03], [0.5, 0.51]) == \
        "SUBSTANTIAL_RELATIVE_SLIDING"
    assert diag.compare_against_rolling_baseline([0.01, 0.02, 0.03], [0.01, 0.02]) == \
        "ROLLING_LIKE_BASELINE"
    assert diag.compare_against_rolling_baseline([0.01], [], contact_observable=False) == \
        "CONTACT_LOST_OR_UNOBSERVABLE"


def test_timestamps_require_bracketed_pose_feedback_and_reject_sparse_history():
    rows = [{"simulation_timestamp": 1.0, "v": (0, 0, 0)},
        {"simulation_timestamp": 1.01, "v": (1, 0, 0)}]
    assert diag.interpolate_vector(rows, 1.005, "v", max_delta_s=.01) == pytest.approx((.5, 0, 0))
    assert diag.interpolate_vector(rows, .9, "v", max_delta_s=.01) is None
    samples = [
        {"simulation_timestamp": 0.0, "receive_sequence": 1, "entities": [
            {"name": "simple_agent", "x": 0, "y": 0, "z": 0, "orientation": _qz(0)},
            {"name": "left_wheel", "x": 0, "y": .2, "z": 0, "orientation": _qz(0)}]},
        {"simulation_timestamp": .02, "receive_sequence": 2, "entities": [
            {"name": "simple_agent", "x": 0, "y": 0, "z": 0, "orientation": _qz(0)},
            {"name": "left_wheel", "x": 0, "y": .2, "z": 0, "orientation": _qz(1)}]}]
    with pytest.raises(ValueError):
        diag.build_link_twist_samples(samples, "left_wheel")


def test_native_joint_velocity_is_only_retained_as_corroboration():
    row = diag.contact_relative_velocity((0, 0, -.1), (0, 0, 1),
        (0, 0, 0), (0, 5, 0), (0, 0, 0))
    assert "DERIVED" in row["provenance"]
    assert "odometry" not in row


def test_action24_brake_and_acquisition_intervals_resolve_from_production_evidence():
    raw = {"action23": {"production_telemetry": {"execution_evidence": {
        "execution_phases": [{"phase": "ACQUIRE_LINEAR", "start_sim_time": 4.0,
            "end_sim_time": 4.1}]}}},
        "action24_production_macro_evidence": {
            "braking_phase": {"start_sim_time": 4.1, "end_sim_time": 4.3},
            "acquisition_phase_evidence": {"start_sim_time": 4.3, "end_sim_time": 4.4}}}
    assert diag._phase_interval(raw, "action23_down_acquisition") == (4.0, 4.1)
    assert diag._phase_interval(raw, "action24_brake") == (4.1, 4.3)
    assert diag._phase_interval(raw, "action24_up_acquisition") == (4.3, 4.4)


def test_contact_without_observed_pair_never_gets_fabricated_velocity():
    assert diag.compare_against_rolling_baseline([0.0, 0.0], [], contact_observable=False) == \
        "CONTACT_LOST_OR_UNOBSERVABLE"


def test_quaternion_angular_velocity_and_pose_provenance_are_finite():
    w = diag._angular_velocity_world(_qz(0), _qz(90), 0.5)
    assert w == pytest.approx((0, 0, math.pi))


import pytest
