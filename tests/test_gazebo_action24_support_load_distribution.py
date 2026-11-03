import hashlib
import xml.etree.ElementTree as ET

import pytest

from aero_ai_studio.gazebo.world_generator import GazeboWorldGenerator
from tools.diagnose_v07_gazebo_action24_support_load_distribution import (
    SUPPORTS, _deduplicated_points, _phase_rows, _support_sensor_instrumenter,
    add_caster_contact_sensors,
)
from tools.diagnose_v07_gazebo_action24_wheel_ground_contact import (
    instrument_contact_sensors, resolve_model_and_joint_configuration,
)
from tools.diagnose_v07_gazebo_action24_wheel_joint_state import (
    instrument_diagnostic_sdf,
)
from test_v06 import tiny


def _semantic(node):
    if node.tag == "sensor" and node.get("name", "").endswith("_support_contact_diagnostic"):
        return None
    if node.tag == "sensor" and node.get("name", "").endswith("_wheel_ground_contact_diagnostic"):
        return None
    if node.tag == "plugin" and node.get("name") == "gz::sim::systems::JointStatePublisher":
        return None
    children = tuple(child for child in (_semantic(item) for item in node) if child is not None)
    return (node.tag, tuple(sorted(node.attrib.items())), (node.text or "").strip(), children)


def test_caster_sensor_additions_are_diagnostic_only_and_keep_physics_tree(tmp_path):
    production = GazeboWorldGenerator().generate(
        tiny(), tmp_path, closed_loop=True, control_mode="PHYSICS")
    before = production.read_bytes()
    diagnostic, _ = instrument_diagnostic_sdf(production)
    info = instrument_contact_sensors(diagnostic, production)
    result = add_caster_contact_sensors(diagnostic, production, info)

    assert production.read_bytes() == before
    assert result["production_sdf_unchanged"] is True
    assert result["production_sdf_sha256_before"] == result["production_sdf_sha256_after"]
    assert set(result["contact_topics"]) >= {"left", "right", "front_caster", "rear_caster"}
    prod = ET.parse(production).getroot().find("world")
    diag = ET.parse(diagnostic).getroot().find("world")
    assert _semantic(prod) == _semantic(diag)
    model = ET.parse(diagnostic).getroot().find(".//model[@name='simple_agent']")
    for label, (link_name, collision_name) in SUPPORTS.items():
        if label in ("left_wheel", "right_wheel", "chassis"):
            continue
        sensor = model.find(f"link[@name='{link_name}']/sensor[@name='{label}_support_contact_diagnostic']")
        assert sensor is not None and sensor.get("type") == "contact"
        assert sensor.findtext("contact/collision") == collision_name
        assert sensor.findtext("contact/topic") == result["contact_topics"][label]
        assert sensor.findtext("update_rate") == "1000"


def test_support_instrumenter_calls_captured_base_instrumenter_without_recursion(tmp_path):
    production = GazeboWorldGenerator().generate(
        tiny(), tmp_path, closed_loop=True, control_mode="PHYSICS")
    diagnostic, _ = instrument_diagnostic_sdf(production)
    calls = []
    def base_instrumenter(diag, prod):
        calls.append((diag, prod))
        return instrument_contact_sensors(diag, prod)
    info = _support_sensor_instrumenter(
        diagnostic, production, base_instrumenter=base_instrumenter)
    assert len(calls) == 1
    assert set(info["support_contact_sensors"]) == {"front_caster", "rear_caster"}


def test_joint_configuration_resolver_recovers_from_canonical_sdf_source_and_fails_loudly(tmp_path):
    production = GazeboWorldGenerator().generate(
        tiny(), tmp_path, closed_loop=True, control_mode="PHYSICS")
    _, config = instrument_diagnostic_sdf(production)
    # Regression for H-AA's missing top-level field: the exact SDF instrumenter
    # already produced the required, validated config even when a compatible
    # report wrapper omits model_and_joint_configuration.
    success_without_field = {"verdict": "ACTION24_WHEEL_JOINT_DIAGNOSTIC_CAPTURED"}
    assert resolve_model_and_joint_configuration(
        success_without_field, generated_configuration=config) is config
    assert resolve_model_and_joint_configuration({
        "verdict": "ACTION24_WHEEL_JOINT_DIAGNOSTIC_CAPTURED",
        "model_and_joint_configuration": config}) is config
    failed = {"verdict": "ACTION24_JOINT_TELEMETRY_INSTRUMENTATION_FAILED",
        "base_replay_evidence": {"error": {"type": "RecursionError",
            "message": "instrument wrapper recursed"}}}
    with pytest.raises(RuntimeError, match="RecursionError.*instrument wrapper recursed"):
        resolve_model_and_joint_configuration(failed, generated_configuration=config)
    with pytest.raises(ValueError, match="Unsupported joint-state diagnostic schema"):
        resolve_model_and_joint_configuration({"verdict": "UNKNOWN"})


def test_same_record_force_normal_projection_is_sign_robust_and_deduplicated():
    contact = {"collision1_name": "simple_agent::front_caster::front_collision",
        "collision2_name": "ground::body::collision",
        "position_native": [{"x": 0, "y": 0, "z": 0}],
        "normal_native": [{"x": 0, "y": 0, "z": 2}],
        "depth_m_native": [0.001],
        "wrench_native": [{"body_1_wrench": {"force": {"x": 3, "y": 0, "z": 4}}}]}
    message = {"sensor_label": "front_caster", "simulation_timestamp": 1.0,
        "contacts": [contact]}
    points, malformed, labels, duplicates = _deduplicated_points([message, message])
    assert malformed == 0
    assert labels == ["front_caster"]
    assert duplicates == 1
    assert len(points) == 1
    assert points[0]["normal_force_magnitude_n"] == pytest.approx(4)
    assert points[0]["tangential_force_magnitude_n"] == pytest.approx(3)


def test_load_share_requires_exact_timestamp_coverage_of_all_support_sensors():
    labels = {"left": "left_wheel", "right": "right_wheel",
        "front_caster": "front_caster", "rear_caster": "rear_caster",
        "chassis": "chassis"}
    samples = [{"sensor_label": label, "simulation_timestamp": 1.0}
        for label in labels]
    points = [{"support": support, "time_ns": 1_000_000_000,
        "simulation_timestamp_s": 1.0, "normal_force_magnitude_n": load,
        "tangential_force_magnitude_n": 0.0, "depth_m": 0.001}
        for support, load in zip(SUPPORTS, (5, 5, 5, 5, 4.5))]
    report = _phase_rows(points, samples, (1.0, 1.0))
    assert report["synchronized_load"]["status"] == "EXACT_TIMESTAMP_MATCH"
    assert report["synchronized_load"]["complete_timestamp_count"] == 1
    assert report["synchronized_load"]["per_timestamp"][0]["total_over_weight"] == pytest.approx(1)
    incomplete = _phase_rows(points, samples[:-1], (1.0, 1.0))
    assert incomplete["synchronized_load"]["status"] == "INSUFFICIENT_EXACT_TIMESTAMP_COVERAGE"


def test_ground_contact_pair_filter_does_not_count_non_ground_collisions():
    from tools.diagnose_v07_gazebo_action24_support_load_distribution import _contact_pair_is_ground
    assert _contact_pair_is_ground({"collision1_name": "ground::body::collision",
        "collision2_name": "simple_agent::body::body_collision"})
    assert not _contact_pair_is_ground({"collision1_name": "simple_agent::body::body_collision",
        "collision2_name": "wall_0::body::collision"})


def test_sensor_timestamp_matching_is_exact_and_does_not_interpolate():
    samples = [{"sensor_label": label, "simulation_timestamp": 1.0}
        for label in ("left", "right", "front_caster", "rear_caster", "chassis")]
    samples[-1] = {"sensor_label": "chassis", "simulation_timestamp": 1.001}
    result = _phase_rows([], samples, (1.0, 1.001))
    assert result["synchronized_load"]["complete_timestamp_count"] == 0
    assert result["synchronized_load"]["status"] == "INSUFFICIENT_EXACT_TIMESTAMP_COVERAGE"


def test_event_silence_is_unavailable_not_fabricated_zero_contact_or_load():
    result = _phase_rows([], [], (1.0, 1.1))
    assert result["by_support"]["front_caster"]["contact_state"] == "OBSERVATION_UNAVAILABLE"
    assert result["by_support"]["front_caster"]["normal_force_magnitude_n"]["median"] is None
    assert result["synchronized_load"]["complete_timestamp_count"] == 0


def test_malformed_same_record_contact_fields_are_excluded_and_counted():
    contact = {"collision1_name": "simple_agent::right_wheel::right_collision",
        "collision2_name": "ground::body::collision",
        "position_native": [{"x": 0, "y": 0, "z": 0}],
        "normal_native": [{"x": 0, "y": 0, "z": 1}],
        "depth_m_native": [0.001], "wrench_native": []}
    points, malformed, labels, duplicates = _deduplicated_points([{
        "sensor_label": "right", "simulation_timestamp": 1.0,
        "contacts": [contact]}])
    assert points == []
    assert malformed == 1
    assert labels == ["right_wheel"]
    assert duplicates == 0


def test_robot_weight_reference_uses_all_five_link_masses():
    from tools.diagnose_v07_gazebo_action24_support_load_distribution import WEIGHT_N
    assert WEIGHT_N == pytest.approx((2.0 + 0.2 + 0.2 + 0.05 + 0.05) * 9.8)
