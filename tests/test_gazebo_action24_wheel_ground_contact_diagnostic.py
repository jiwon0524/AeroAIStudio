import xml.etree.ElementTree as ET

from aero_ai_studio.gazebo.world_generator import GazeboWorldGenerator
from tools.diagnose_v07_gazebo_action24_wheel_ground_contact import (
    GROUND_COLLISION, _collision_map_from_sdf, _static_sdf_audit,
    classify_contact_observations,
    classify_contact_pair, instrument_contact_sensors, parse_contacts_message,
)
from tools.diagnose_v07_gazebo_action24_wheel_joint_state import (
    instrument_diagnostic_sdf,
)
from test_v06 import tiny


def _semantic(element, omit_diagnostic=True):
    children = []
    for child in element:
        if omit_diagnostic and child.tag == "sensor":
            continue
        if (omit_diagnostic and child.tag == "plugin" and
                child.get("name") == "gz::sim::systems::JointStatePublisher"):
            continue
        children.append(_semantic(child, omit_diagnostic))
    return (element.tag, tuple(sorted(element.attrib.items())),
        (element.text or "").strip(), tuple(children))


def test_contact_sensor_instrumentation_is_diagnostic_only_and_production_sdf_unchanged(tmp_path):
    production = GazeboWorldGenerator().generate(
        tiny(), tmp_path, closed_loop=True, control_mode="PHYSICS")
    production_bytes = production.read_bytes()
    diagnostic, joint_info = instrument_diagnostic_sdf(production)
    info = instrument_contact_sensors(diagnostic, production)

    assert production.read_bytes() == production_bytes
    assert info["production_sdf_unchanged"] is True
    assert info["production_sdf_sha256_before"] == info["production_sdf_sha256_after"]
    assert info["instrumentation_semantics"].startswith("Adds only SDF contact-sensor declarations")
    assert info["observation_only_api_basis"]["actuation_interface_added"] is False
    assert info["observation_only_api_basis"]["physical_parameter_edits"] == []

    production_root = ET.parse(production).getroot()
    diagnostic_root = ET.parse(diagnostic).getroot()
    production_world = production_root.find("world")
    diagnostic_world = diagnostic_root.find("world")
    assert _semantic(production_world) == _semantic(diagnostic_world)
    model = diagnostic_root.find(".//model[@name='simple_agent']")
    for side in ("left", "right"):
        sensor = model.find(f".//sensor[@name='{side}_wheel_ground_contact_diagnostic']")
        assert sensor is not None and sensor.get("type") == "contact"
        assert sensor.findtext("contact/collision") == f"{side}_collision"
        assert sensor.findtext("contact/topic") == info["contact_topics"][side]
        assert sensor.findtext("update_rate") == "1000"
    assert joint_info["production_sdf_unchanged"]


def test_static_audit_resolves_collision_pairs_and_reports_symmetric_drive_configuration(tmp_path):
    production = GazeboWorldGenerator().generate(
        tiny(), tmp_path, closed_loop=True, control_mode="PHYSICS")
    mapping = _collision_map_from_sdf(production)
    assert mapping["ground"] == "ground::body::collision"
    assert mapping["left_wheel"] == "simple_agent::left_wheel::left_collision"
    assert mapping["right_wheel"] == "simple_agent::right_wheel::right_collision"
    assert mapping["body"] == "simple_agent::body::body_collision"
    assert GROUND_COLLISION == ("ground", "body", "collision")
    audit = _static_sdf_audit(production)
    assert audit["direction_asymmetry_in_drive_wheels"] is False
    assert audit["joints"]["left_joint"]["type"] == "revolute"
    assert audit["joints"]["right_joint"]["axis_xyz"] == "0 1 0"
    assert audit["diffdrive"]["wheel_radius"] == ".1"


def test_contact_pairs_are_classified_by_sdf_collision_identity():
    mapping = {"ground": "ground::body::collision",
        "body": "simple_agent::body::body_collision",
        "left_wheel": "simple_agent::left_wheel::left_collision",
        "right_wheel": "simple_agent::right_wheel::right_collision"}
    assert classify_contact_pair({"name": mapping["left_wheel"]},
        {"name": mapping["ground"]}, mapping) == "LEFT_WHEEL_GROUND"
    assert classify_contact_pair({"name": mapping["ground"]},
        {"name": mapping["right_wheel"]}, mapping) == "RIGHT_WHEEL_GROUND"
    assert classify_contact_pair({"name": mapping["body"]},
        {"name": mapping["ground"]}, mapping) == "CHASSIS_GROUND"
    assert classify_contact_pair({"name": mapping["left_wheel"]},
        {"name": mapping["body"]}, mapping) == "WHEEL_CHASSIS"
    assert classify_contact_pair({"name": "unknown::collision"},
        {"name": mapping["ground"]}, mapping) == "OTHER"


def test_native_contact_message_fields_and_provenance_are_preserved():
    mapping = {"ground": "ground::body::collision",
        "body": "simple_agent::body::body_collision",
        "left_wheel": "simple_agent::left_wheel::left_collision",
        "right_wheel": "simple_agent::right_wheel::right_collision"}
    data = {"header": {"stamp": {"sec": 5, "nsec": 300000000}},
        "contact": [{"collision1": {"name": mapping["left_wheel"]},
            "collision2": {"name": mapping["ground"]},
            "position": [{"x": 1.0, "y": 2.0, "z": 0.0}],
            "normal": [{"x": 0.0, "y": 0.0, "z": 1.0}],
            "depth": [0.001], "wrench": [{"body_1_name": mapping["left_wheel"],
                "body_1_wrench": {"force": {"x": 0.0, "y": 0.0, "z": 1.2},
                    "torque": {"x": 0.0, "y": 0.0, "z": 0.0}}}]}]}
    row = parse_contacts_message(data, "/test/contacts", 7, 42.0, mapping)
    assert row["simulation_timestamp"] == 5.3
    assert row["receive_sequence"] == 7
    contact = row["contacts"][0]
    assert contact["pair_classification"] == "LEFT_WHEEL_GROUND"
    assert contact["position_native"] == data["contact"][0]["position"]
    assert contact["normal_native"] == data["contact"][0]["normal"]
    assert contact["depth_m_native"] == [0.001]
    assert contact["wrench_native"] == data["contact"][0]["wrench"]
    assert "tangential_force" not in contact


def test_contact_classification_does_not_infer_traction_from_contact_presence():
    def window(left_available=True, right_available=True, left_count=1, right_count=1):
        return {"by_sensor": {
            "left": {"availability": "AVAILABLE" if left_available else "NO_SAMPLES_IN_WINDOW",
                "pair_counts": {"LEFT_WHEEL_GROUND": left_count}},
            "right": {"availability": "AVAILABLE" if right_available else "NO_SAMPLES_IN_WINDOW",
                "pair_counts": {"RIGHT_WHEEL_GROUND": right_count}}}}
    baseline = window()
    assert classify_contact_observations(baseline, window()) == \
        "CONTACT_TELEMETRY_AVAILABLE_CAUSE_UNRESOLVED"
    assert classify_contact_observations(baseline, window(left_count=0)) == \
        "WHEEL_GROUND_CONTACT_MISSING"
    assert classify_contact_observations(baseline, window(right_available=False)) == \
        "CONTACT_TELEMETRY_UNAVAILABLE"


def test_contact_diagnostic_delegates_exact_action24_to_current_production_replay():
    from pathlib import Path
    from tools import diagnose_v07_gazebo_action24_acquisition_divergence as base
    source = Path(__import__(
        "tools.diagnose_v07_gazebo_action24_wheel_ground_contact",
        fromlist=["__file__"]).__file__).read_text(encoding="utf-8")
    base_source = Path(base.__file__).read_text(encoding="utf-8")
    assert "joint_diag._run_with_instrumented_factory(artifact_dir, output, **kwargs)" in source
    assert 'actions[22:24] != ["down", "up"]' in base_source
    assert 'result = adapter.step("up")' in base_source
    assert "experimental" not in source.lower()

