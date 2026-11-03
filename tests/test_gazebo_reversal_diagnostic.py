from types import SimpleNamespace

from aero_ai_studio.core.storage import read_json
from tools import diagnose_v07_gazebo_reversal as diagnostic


def test_reversal_diagnostic_uses_physics_steps_and_serializes_action_evidence(tmp_path, monkeypatch):
    constructed = {}

    class FakeEnvironment:
        def __init__(self, scenario, **kwargs):
            constructed.update(kwargs)
            self.injected = False
            self.control_mode = kwargs["control_mode"]
            self.world_name = "fixture_world"
            self.manager = SimpleNamespace(partition="fixture_partition", status=lambda: {"status": "Running"})
            self.controller = SimpleNamespace(pose_topic="/world/fixture_world/pose/info")
            self.initialization_checks = {"reset_applied": "PASS"}
            self.pose = {"x": 1.5, "y": 1.5, "yaw": 0.}
            self.stepper = SimpleNamespace(time=0.)
            self.telemetry = {}
            self.actions = []

        def launch(self):
            return {"available": True}

        def reset(self, seed=None):
            return None

        def step(self, action):
            self.actions.append(action)
            self.stepper.time += .1
            self.pose["x"] += .01
            self.telemetry = {"action_transition": {"action": action,
                "world_pose_history": [{"simulation_timestamp": self.stepper.time - .02},
                    {"simulation_timestamp": self.stepper.time - .01},
                    {"simulation_timestamp": self.stepper.time}],
                "world_pose_history_summary": {"world_pose_sample_count": 3,
                    "world_pose_history_dense_enough": True},
                "commanded_twist": {"linear": {"x": .5}, "angular": {"z": 0.}}},
                "pose_validation": {"valid": True}}
            return SimpleNamespace(reward=0., terminated=False, truncated=False, reason="moving")

        def close(self):
            return None

    monkeypatch.setattr(diagnostic, "GazeboEnvironment", FakeEnvironment)
    report = diagnostic.run_diagnostic(tmp_path)
    saved = read_json(tmp_path / "reversal_diagnostic.json")
    assert report["status"] == "CAPTURED" and saved["status"] == "CAPTURED"
    assert report["endpoint_evidence_captured"]
    assert report["world_pose_history_captured"] and report["world_pose_history_sufficient"]
    assert constructed["control_mode"] == "PHYSICS"
    assert constructed["capture_world_pose_history"] is True
    assert report["actions"][0]["action_transition"]["world_pose_history"]
    assert [entry["action"] for entry in report["actions"]] == ["up", "down", "up"]


def test_empty_or_sparse_pose_history_is_not_reported_as_captured():
    empty = {"actions": [{"before_pose": {}, "after_pose": {}, "action_transition": {
        "world_pose_history": [], "world_pose_history_summary": {
            "world_pose_sample_count": 0, "world_pose_history_dense_enough": False}}}]}
    diagnostic.finalize_capture_status(empty)
    assert empty["endpoint_evidence_captured"]
    assert not empty["world_pose_history_captured"]
    assert not empty["world_pose_history_sufficient"]
    assert empty["status"] == "CAPTURED_WITH_INSUFFICIENT_POSE_HISTORY"

    sparse = {"actions": [{"before_pose": {}, "after_pose": {}, "action_transition": {
        "world_pose_history": [{"simulation_timestamp": .1}],
        "world_pose_history_summary": {"world_pose_sample_count": 1,
                                        "world_pose_history_dense_enough": False}}}]}
    diagnostic.finalize_capture_status(sparse)
    assert sparse["world_pose_history_captured"]
    assert not sparse["world_pose_history_sufficient"]
    assert sparse["status"] == "CAPTURED_WITH_INSUFFICIENT_POSE_HISTORY"
