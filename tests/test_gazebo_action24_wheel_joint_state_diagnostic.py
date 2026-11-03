import hashlib
import xml.etree.ElementTree as ET

from aero_ai_studio.gazebo.world_generator import GazeboWorldGenerator
from tools.diagnose_v07_gazebo_action24_wheel_joint_state import (
    JOINTS, LINKS, classify_joint_odometry_body, instrument_diagnostic_sdf,
    parse_joint_model_data, _pose_entities_for_diagnostic,
)
from test_v06 import tiny


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _semantic_xml(element):
    return (element.tag, tuple(sorted(element.attrib.items())),
        (element.text or "").strip(), tuple(_semantic_xml(child) for child in element))


def test_diagnostic_sdf_adds_read_only_joint_publisher_and_preserves_production_sdf(tmp_path):
    production = GazeboWorldGenerator().generate(
        tiny(), tmp_path, closed_loop=True, control_mode="PHYSICS")
    before = production.read_bytes()
    diagnostic, info = instrument_diagnostic_sdf(production)
    assert production.read_bytes() == before
    assert info["production_sdf_unchanged"] is True
    assert info["production_sdf_sha256_before"] == info["production_sdf_sha256_after"]
    assert diagnostic != production and diagnostic.is_file()
    root = ET.parse(diagnostic).getroot()
    model = root.find(".//model[@name='simple_agent']")
    plugin = model.find("plugin[@name='gz::sim::systems::JointStatePublisher']")
    assert plugin.get("filename") == "gz-sim-joint-state-publisher-system"
    assert plugin.findtext("topic") == info["joint_state_topic"]
    assert plugin.findall("joint_name") and [e.text for e in plugin.findall("joint_name")] == list(JOINTS)
    assert plugin.findtext("update_rate") == "0"
    for name in JOINTS:
        joint = model.find(f"joint[@name='{name}']")
        assert joint.findtext("child") == LINKS[name]
        assert joint.findtext("axis/xyz") == "0 1 0"
    # The diagnostic copy adds observation only; dynamics/actuation configuration
    # still matches the generated production SDF exactly.
    normal_model = ET.parse(production).getroot().find(".//model[@name='simple_agent']")
    diag_model = model
    assert _semantic_xml(normal_model.find("plugin[@name='gz::sim::systems::DiffDrive']")) == \
        _semantic_xml(diag_model.find("plugin[@name='gz::sim::systems::DiffDrive']"))
    assert [_semantic_xml(node) for node in normal_model.findall("joint")] == \
        [_semantic_xml(node) for node in diag_model.findall("joint")]
    assert _hash(production) == info["production_sdf_sha256_after"]


def test_joint_model_parser_preserves_native_position_velocity_and_timestamp():
    row = parse_joint_model_data({"name": "simple_agent", "header": {"stamp": {
        "sec": 12, "nsec": 345000000}}, "joint": [
            {"name": "left_joint", "axis1": {"position": 1.25, "velocity": 5.0}},
            {"name": "right_joint", "axis1": {"position": -1.25, "velocity": 4.9}}]},
        7, 42.5)
    assert row["receive_sequence"] == 7
    assert row["simulation_timestamp"] == 12.345
    assert row["wall_receive_monotonic_seconds"] == 42.5
    assert row["joint_states"][0]["position_rad_native"] == 1.25
    assert row["joint_states"][0]["velocity_rad_s_native"] == 5.0
    assert "native" in row["joint_states"][0]["velocity_source"]


def test_joint_model_parser_marks_missing_message_timestamp_unavailable():
    row = parse_joint_model_data({"joint": [{"name": "left_joint",
        "axis1": {"position": 0.0, "velocity": 0.0}}]}, 1, 3.0)
    assert row["simulation_timestamp"] is None
    assert row["message_timestamp_available"] is False
    assert row["joint_states"][0]["position_rad_native"] == 0.0
    assert row["joint_states"][0]["velocity_rad_s_native"] == 0.0


def test_pose_v_secondary_capture_selects_wheels_without_calling_them_joint_velocity():
    frame = {"pose": [{"name": "simple_agent", "x": 1.},
        {"name": "left_wheel", "x": 1.1}, {"name": "right_wheel", "x": .9},
        {"name": "wall_0", "x": 5.}]}
    selected = _pose_entities_for_diagnostic(frame, "simple_agent",
        lambda pose: {"x": pose["x"]})
    assert [row["name"] for row in selected] == ["simple_agent", "left_wheel", "right_wheel"]
    assert "joint_velocity" not in selected[1]


def test_classification_requires_native_joint_samples_and_never_uses_odometry_as_joint_state():
    assert classify_joint_odometry_body({}, .5, 0.0) == "JOINT_TELEMETRY_UNAVAILABLE"
    states = {name: [{"velocity_rad_s_native": 5.0} for _ in range(2)] for name in JOINTS}
    assert classify_joint_odometry_body(states, .5, 0.0) == "JOINTS_ROTATING_BODY_STATIONARY"
    states["right_joint"][-1]["velocity_rad_s_native"] = -5.0
    assert classify_joint_odometry_body(states, .5, 0.0) == "JOINTS_ASYMMETRIC_OR_ABNORMAL"


def test_action24_diagnostic_source_is_exact_target_and_production_path_only():
    from tools import diagnose_v07_gazebo_action24_acquisition_divergence as source
    text = open(source.__file__, encoding="utf-8").read()
    assert 'actions[22:24] != ["down", "up"]' in text
    assert 'result = adapter.step("up")' in text
    assert 'result = adapter.step(action)' in text
    assert "run_diagnostic(artifact_dir, base_dir, env_factory=factory" in \
        open(__import__("tools.diagnose_v07_gazebo_action24_wheel_joint_state",
            fromlist=["__file__"]).__file__, encoding="utf-8").read()

