import hashlib
import json

import pytest

from tools import diagnose_v07_gazebo_action24_native_contact_kinematics as diag


def test_native_contact_point_velocity_uses_world_twist_and_offset():
    # omega=(0,5,0), r=(0,0,-.1) gives -0.5 m/s along world X.
    result = diag.contact_point_velocity((1, 0, 0), (1, 0, .1),
        (0, 0, 0), (0, 5, 0))
    assert result == pytest.approx((-0.5, 0, 0))


def test_relative_velocity_requires_proven_static_ground_and_decomposes_world_frame():
    with pytest.raises(ValueError, match="proven static ground"):
        diag.relative_contact_velocity((0, 0, 0), (0, 0, 1), (0, 0, 0),
            (1, 2, 3), (0, 0, 0), ground_static=None)
    result = diag.relative_contact_velocity((0, 0, 0), (0, 0, 4), (0, 0, 0),
        (1, 2, 3), (0, 0, 0), ground_static=True)
    assert result["normal_relative_velocity_m_s"] == pytest.approx(3)
    assert result["tangential_relative_velocity_world_m_s"] == pytest.approx((1, 2, 0))
    assert result["provenance"].startswith("DERIVED_FROM_NATIVE")


def test_native_samples_require_finite_values_and_monotonic_sim_time_and_iteration():
    link = {"position_world_m": [0, 0, 0], "orientation_world_xyzw": [0, 0, 0, 1],
        "linear_velocity_world_m_s": [0, 0, 0],
        "angular_velocity_world_rad_s": [0, 0, 0]}
    sample = lambda t, i: {"simulation_time_s": t, "iteration": i,
        "links": [dict(link, name=name) for name in
                  ("simple_agent::body", "simple_agent::left_wheel", "simple_agent::right_wheel")]}
    assert diag.classify_native_samples([sample(.001, 1), sample(.002, 2)]) == \
        "NATIVE_WORLD_LINK_VELOCITY_VALID"
    assert diag.classify_native_samples([sample(.001, 2), sample(.002, 1)]) == \
        "NATIVE_VELOCITY_INVALID"
    bad = sample(.003, 3)
    bad["links"][0]["linear_velocity_world_m_s"][0] = float("nan")
    assert diag.classify_native_samples([bad]) == "NATIVE_VELOCITY_INVALID"


def test_repeated_paused_native_samples_are_valid_but_reversals_are_not():
    link = {"position_world_m": [0, 0, 0], "orientation_world_xyzw": [0, 0, 0, 1],
        "linear_velocity_world_m_s": [0, 0, 0],
        "angular_velocity_world_rad_s": [0, 0, 0]}
    def sample(t, i, paused):
        return {"simulation_time_s": t, "iteration": i, "paused": paused,
            "links": [dict(link, name=name) for name in
                ("simple_agent::body", "simple_agent::left_wheel", "simple_agent::right_wheel")]}
    repeated = [sample(.2, 200, False), sample(.2, 200, True),
                sample(.201, 201, False)]
    assert diag.classify_native_samples(repeated) == "NATIVE_WORLD_LINK_VELOCITY_VALID"
    selected, ambiguous = diag.select_native_physics_samples(repeated)
    assert [row["iteration"] for row in selected] == [200, 201]
    assert selected[0]["paused"] is False
    assert ambiguous == []
    assert diag.classify_native_samples([repeated[2], repeated[0]]) == "NATIVE_VELOCITY_INVALID"


def test_paused_only_conflicting_state_is_excluded_from_contact_sync():
    link = {"position_world_m": [0, 0, 0], "orientation_world_xyzw": [0, 0, 0, 1],
        "linear_velocity_world_m_s": [0, 0, 0],
        "angular_velocity_world_rad_s": [0, 0, 0]}
    row = {"simulation_time_s": .2, "iteration": 200, "paused": True,
        "links": [dict(link, name=name) for name in
            ("simple_agent::body", "simple_agent::left_wheel", "simple_agent::right_wheel")]}
    changed = json.loads(json.dumps(row))
    changed["links"][1]["linear_velocity_world_m_s"][0] = 1.0
    selected, ambiguous = diag.select_native_physics_samples([row, changed])
    assert selected == []
    assert ambiguous == [{"simulation_time_ns": 200000000, "iteration": 200,
        "reason": "paused_samples_disagree", "count": 2}]


def test_replay_evidence_phase_intervals_use_production_execution_schema():
    replay = {"action23": {"production_telemetry": {"execution_evidence": {
        "execution_phases": [{"phase": "BRAKE_LINEAR", "start_sim_time": 4.8,
            "end_sim_time": 5.0}, {"phase": "ACQUIRE_LINEAR", "start_sim_time": 5.0,
            "end_sim_time": 5.1}]}}},
        "action24_production_macro_evidence": {
            "braking_phase": {"start_sim_time": 5.1, "end_sim_time": 5.3},
            "acquisition_phase_evidence": {"start_sim_time": 5.3,
                "end_sim_time": 5.4}}}
    assert diag._phase_intervals_from_replay_evidence(replay) == {
        "action23_down_acquisition": (5.0, 5.1),
        "action24_brake": (5.1, 5.3),
        "action24_up_acquisition": (5.3, 5.4)}


def test_native_message_keeps_provenance_and_receive_order():
    payload = {"data": json.dumps({"simulation_time_s": .123,
        "iteration": 123, "paused": False, "links": []})}
    result = diag.parse_native_message(payload, 7, 10.5)
    assert result["simulation_time_s"] == .123
    assert result["iteration"] == 123
    assert result["receive_sequence"] == 7
    assert result["wall_receive_monotonic_seconds"] == 10.5


def test_contact_kinematics_requires_exact_timestamp_match_and_static_ground():
    native = [{"simulation_time_s": 1.001, "iteration": 1001, "links": [
        {"name": "simple_agent::left_wheel", "position_world_m": [0, 0, .1],
         "linear_velocity_world_m_s": [0, 0, 0], "angular_velocity_world_rad_s": [0, 5, 0]},
        {"name": "simple_agent::right_wheel", "position_world_m": [0, .4, .1],
         "linear_velocity_world_m_s": [0, 0, 0], "angular_velocity_world_rad_s": [0, 5, 0]},
        {"name": "simple_agent::body", "position_world_m": [0, 0, .2],
         "linear_velocity_world_m_s": [0, 0, 0], "angular_velocity_world_rad_s": [0, 0, 0]}]}]
    contact = {"simulation_timestamp": 1.001, "contacts": [{
        "pair_classification": "RIGHT_WHEEL_GROUND",
        "collision1_name": "simple_agent::right_wheel::right_collision",
        "collision2_name": "ground::body::collision",
        "position_native": [{"x": 0, "y": .4, "z": 0}],
        "normal_native": [{"x": 0, "y": 0, "z": 1}]}]}
    result = diag._native_contact_rows([contact], native,
        {"ground": "ground::body::collision"}, ground_static=True)
    assert len(result) == 1
    assert result[0]["iteration"] == 1001
    assert result[0]["derived_contact_kinematics"]["provenance"].startswith("DERIVED")
    assert diag._native_contact_rows([contact], native,
        {"ground": "ground::body::collision"}, ground_static=False) == []
    mismatch = dict(contact, simulation_timestamp=1.002)
    assert diag._native_contact_rows([mismatch], native,
        {"ground": "ground::body::collision"}, ground_static=True) == []


def test_left_and_right_are_kept_as_separate_contact_results():
    kin = {"tangential_relative_speed_m_s": .001}
    rows = [{"wheel": "left_wheel", "simulation_timestamp_s": 1.0,
             "derived_contact_kinematics": kin},
            {"wheel": "left_wheel", "simulation_timestamp_s": 1.02,
             "derived_contact_kinematics": kin}]
    baseline = [{"wheel": "left_wheel", "simulation_timestamp_s": .9,
                 "derived_contact_kinematics": kin}]
    assert diag._side_status(rows, "left_wheel", baseline, .01)["sample_count"] == 2
    assert diag._side_status(rows, "right_wheel", baseline, .01)["sample_count"] == 0


def test_diagnostic_plugin_changes_only_diagnostic_sdf(tmp_path):
    production = tmp_path / "production.sdf"
    diagnostic = tmp_path / "diagnostic.sdf"
    production.write_text('<sdf><world name="w"><model name="simple_agent"/></world></sdf>')
    diagnostic.write_bytes(production.read_bytes())
    before = hashlib.sha256(production.read_bytes()).hexdigest()
    info = diag.instrument_native_velocity_plugin(diagnostic, production,
        "/tmp/observer.so")
    assert hashlib.sha256(production.read_bytes()).hexdigest() == before
    plugin = diag.ET.parse(diagnostic).getroot().find(
        "world/plugin[@name='aero_diagnostic::NativeLinkVelocityObserver']")
    assert plugin is not None
    assert info["production_sdf_unchanged"] is True
    assert "PostUpdate" in info["observation_contract"]


def test_diagnostic_source_does_not_use_pose_differences_or_odometry_for_kinematics():
    source = diag.Path(diag.__file__).read_text()
    assert "build_link_twist_samples" not in source
    assert "odometry_or_command_used_as_kinematic_input\": False" in source
    assert "native_link_linear_velocity_world_m_s" in source
    assert "World Pose_V production validator remains unchanged" in source


def test_observer_only_uses_postupdate_const_ecm_and_no_physics_setters():
    source = diag.PLUGIN_SOURCE.read_text()
    assert "ISystemPostUpdate" in source
    assert "const gz::sim::EntityComponentManager &_ecm" in source
    assert "EnableVelocityChecks(_ecm)" in source
    for forbidden in ("SetLinearVelocity", "SetAngularVelocity", "AddWorldForce",
                      "JointVelocityCmd", "SetAngularVelocityCmd", "AddWorldForceCmd"):
        assert forbidden not in source


def test_heartbeat_is_parsed_even_when_native_velocity_is_unavailable():
    payload = {"data": json.dumps({"message_kind": "observer_health_heartbeat",
        "plugin_loaded": True, "configure_called": True, "postupdate_count": 12,
        "simulation_time_s": .012, "iteration": 12,
        "native_velocity_sample_ready": False,
        "links": [{"expected_scoped_name": name, "resolved": True,
            "velocity_checks_requested": True,
            "world_linear_velocity_available": False,
            "world_angular_velocity_available": False} for name in diag.LINKS]})}
    parsed = diag.parse_native_message(payload, 1, 5.0)
    assert parsed["postupdate_count"] == 12
    assert not diag.native_payload_has_all_velocities(parsed)

    class Capture:
        subscribed = True
        topic = "/aero/w/native_link_velocity_diagnostic"
        raw_callback_count = 1
        heartbeat_messages = [parsed]
        parse_failures = []
    health = diag._observer_health(Capture())
    assert health["status"] == "HEARTBEAT_RECEIVED"
    assert health["native_velocity_ready_heartbeat_count"] == 0


def test_observer_health_exposes_lifecycle_and_retries_entity_resolution():
    source = diag.PLUGIN_SOURCE.read_text()
    for field in ("configure_called", "postupdate_count", "lookup_match_count",
                  "velocity_checks_requested", "world_linear_velocity_available",
                  "world_angular_velocity_available", "publisher_advertised",
                  "native_velocity_sample_ready"):
        assert field in source
    assert "ISystemPreUpdate" in source
    assert source.count("ResolveLinks(_ecm)") >= 2


def test_zero_kinematics_has_distinct_observer_and_velocity_stage_counts():
    class Capture:
        subscribed = True
        topic = "/aero/w/native_link_velocity_diagnostic"
        raw_callback_count = 1
        parse_failures = []
        heartbeat_messages = [{"message_kind": "observer_health_heartbeat",
            "simulation_time_s": .01, "iteration": 10,
            "native_velocity_sample_ready": False,
            "links": [{"expected_scoped_name": name, "resolved": True,
                "velocity_checks_requested": True,
                "world_linear_velocity_available": False,
                "world_angular_velocity_available": False} for name in diag.LINKS]}]
    result = diag._observer_pipeline(Capture(), [], "INSUFFICIENT_EVIDENCE", [], {
        "action23_down_acquisition": (0.0, .1),
        "action24_brake": (.1, .3), "action24_up_acquisition": (.3, .4)})
    assert result["raw_callback_messages"] == 1
    assert result["parsed_heartbeat_messages"] == 1
    assert result["entity_valid_messages"] == 1
    assert result["timestamp_iteration_valid_messages"] == 1
    assert result["native_velocity_ready_messages"] == 0
    assert result["finite_monotonic_native_samples"] == 0


def test_native_plugin_sdf_uses_absolute_library_and_world_scope(tmp_path):
    production = tmp_path / "p.sdf"
    diagnostic = tmp_path / "d.sdf"
    production.write_text('<sdf><world name="aero_run"><model name="simple_agent"/></world></sdf>')
    diagnostic.write_bytes(production.read_bytes())
    info = diag.instrument_native_velocity_plugin(diagnostic, production,
        "/tmp/observer.so")
    plugin = diag.ET.parse(diagnostic).getroot().find(
        "world/plugin[@name='aero_diagnostic::NativeLinkVelocityObserver']")
    assert plugin.get("filename") == "/tmp/observer.so"
    assert plugin.findtext("topic") == info["topic"]
    assert info["plugin_scope"] == "world"


def test_host_launch_inherits_diagnostic_plugin_path_and_topic_type_match():
    source = diag.Path(diag.__file__).read_text()
    plugin_source = diag.PLUGIN_SOURCE.read_text()
    assert 'os.environ["GZ_SIM_SYSTEM_PLUGIN_PATH"]' in source
    assert "env=dict(os.environ,GZ_PARTITION=self.partition)" in \
        diag.Path("src/aero_ai_studio/gazebo/process_manager.py").read_text()
    assert 'Advertise<gz::msgs::StringMsg>' in plugin_source
    assert "stringmsg_pb2.StringMsg" in source
    assert 'native_link_velocity_diagnostic' in source
    assert 'native.subscribe(adapter, capture_box["info"]["topic"])' in source
    assert 'Get<std::string>("topic")' in plugin_source


def test_phase_intervals_use_contact_report_windows_not_nested_runner_shape():
    report = {"action23_working_contact_window": {"simulation_interval": [1.0, 1.1]},
        "action24_brake_contact_window": {"simulation_interval": [1.1, 1.3]},
        "action24_up_acquisition_contact_window": {"simulation_interval": [1.3, 1.4]}}
    assert diag._phase_intervals_from_contact_report(report) == {
        "action23_down_acquisition": (1.0, 1.1),
        "action24_brake": (1.1, 1.3),
        "action24_up_acquisition": (1.3, 1.4)}
