import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from tools import diagnose_v07_gazebo_action24_joint_transmitted_wrench as diag


def _robot_sdf():
    return ET.fromstring('''<sdf version="1.9"><world name="w"><model name="simple_agent">
      <link name="body"/><link name="left_wheel"/><link name="right_wheel"/>
      <joint name="left_joint" type="revolute"><parent>body</parent><child>left_wheel</child>
        <axis><xyz expressed_in="__model__">0 2 0</xyz></axis></joint>
      <joint name="right_joint" type="revolute"><parent>body</parent><child>right_wheel</child>
        <axis><xyz expressed_in="__model__">0 -3 0</xyz></axis></joint>
      </model></world></sdf>''')


def test_left_right_joint_resolution_uses_sdf_axis_without_fallback():
    out = diag.resolve_joints(_robot_sdf())
    assert out["left_joint"]["axis_xyz"] == [0.0, 1.0, 0.0]
    assert out["right_joint"]["axis_xyz"] == [0.0, -1.0, 0.0]
    assert out["left_joint"]["axis_frame"] == "__model__"


def test_joint_resolution_fails_loudly_for_missing_joint_or_axis():
    root = _robot_sdf()
    root.find(".//joint[@name='right_joint']").remove(root.find(".//joint[@name='right_joint']/axis"))
    with pytest.raises(ValueError, match="no canonical SDF axis"):
        diag.resolve_joints(root)


def test_observer_sdf_adds_only_world_observation_plugin(tmp_path):
    path = tmp_path / "diag.sdf"
    path.write_text(ET.tostring(_robot_sdf(), encoding="unicode"), encoding="utf-8")
    before = ET.parse(path).getroot()
    info = diag.insert_observer(path, tmp_path / "observer.so", tmp_path / "wrench.ndjson",
                                diag.resolve_joints(before))
    after = ET.parse(path).getroot()
    assert after.find(f"world/plugin[@name='{diag.PLUGIN}']") is not None
    assert info["world_scoped"] is True
    assert before.find(".//joint[@name='left_joint']") is not None
    assert after.find(".//physics") is None
    assert after.find(".//collision") is None
    plugin = after.find(f"world/plugin[@name='{diag.PLUGIN}']")
    assert plugin.findtext("left_axis_xyz") == "0,1,0"
    assert plugin.findtext("right_axis_xyz") == "0,-1,0"


def test_wrench_stream_accepts_complete_6d_vectors_and_separates_health(tmp_path):
    p = tmp_path / "stream.ndjson"
    row = {"kind": "joint_wrench_sample", "epoch": 0, "iteration": 2, "sim_time_ns": 2000000,
           "left": {"state": "VALID_WRENCH", "force_xyz_N": [1, 2, 3], "torque_xyz_N_m": [4, 5, 6]},
           "right": {"state": "UNAVAILABLE", "wrench_available": False}}
    health = {"kind": "observer_health", "event": "configured"}
    p.write_text(json.dumps(health) + "\n" + json.dumps(row) + "\n", encoding="utf-8")
    samples, health_rows = diag._load_samples(p)
    assert len(samples) == len(health_rows) == 1
    assert samples[0]["left"]["force_xyz_N"] == [1, 2, 3]
    assert samples[0]["left"]["torque_xyz_N_m"] == [4, 5, 6]
    assert samples[0]["right"]["state"] == "UNAVAILABLE"


def test_duplicate_iteration_rejected_and_nonfinite_json_rejected(tmp_path):
    p = tmp_path / "duplicate.ndjson"
    row = {"kind": "joint_wrench_sample", "epoch": 1, "iteration": 10}
    p.write_text(json.dumps(row) + "\n" + json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate epoch/iteration"):
        diag._load_samples(p)
    p.write_text('{"kind":"joint_wrench_sample","epoch":0,"iteration":1,"v":NaN}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="nonfinite JSON"):
        diag._load_samples(p)


def test_observer_source_enables_checks_preupdate_and_samples_postupdate():
    source = Path("tools/gazebo_joint_transmitted_wrench_observer.cc").read_text(encoding="utf-8")
    assert "EnableTransmittedWrenchCheck(_ecm)" in source
    assert "EnableVelocityCheck(_ecm)" in source
    assert "joint.TransmittedWrench(_ecm)" in source
    assert "joint.Velocity(_ecm)" in source
    assert "ISystemPreUpdate" in source and "ISystemPostUpdate" in source
    assert "if (_info.paused)" in source
    assert "_info.iterations == this->lastIteration" in source
    assert "composite_joint_transmitted_wrench" in source
    assert "motor torque" not in source.lower()


def test_preflight_switch_is_offline_only_and_runtime_path_is_separate():
    import inspect
    source = inspect.getsource(diag.main)
    assert 'parser.add_argument("--preflight-only"' in source
    assert 'preflight(args.artifact_dir, args.output) if args.preflight_only else run(' in source
    assert '"runtime_evidence_created": False' in inspect.getsource(diag.preflight)


def test_invalid_wrench_is_not_serialized_as_zero_by_observer_contract():
    source = Path("tools/gazebo_joint_transmitted_wrench_observer.cc").read_text(encoding="utf-8")
    assert '"INVALID_WRENCH"' in source
    assert '"UNAVAILABLE"' in source
    assert 'if (finite)' in source
    assert "std::isfinite" in source
