import json
from types import SimpleNamespace

import pytest

from aero_ai_studio.simulation.base import PhysicalControlFailure
from aero_ai_studio.simulation.action_mapping import gazebo_physics_twist
from tools import diagnose_v07_gazebo_macro_composition_action24 as diagnostic


def _actions():
    return ["up", "down", "up", "up", "up", "down", "up", "right",
        "left", "down", "right", "up", "down", "right", "left", "up",
        "down", "up", "right", "left", "left", "up", "down", "up",
        "up", "right", "left", "left", "left", "up"]


def _replay():
    return {"completed_episode_actions": [_actions()], "run_id": "fixture",
        "artifact_dir": "fixture", "scenario": {}, "max_steps": 250,
        "training_seed": 42}


def _retry():
    return {"status": "FAILED", "target_episode": 1,
        "target_action_index_in_episode_1_based": 138,
        "production_environment_step_used_for_target": False,
        "prefix_replayed_count": 23,
        "failed_prefix_action": {"index_1_based": 24, "action": "up",
            "type": "PhysicalControlFailure",
            "message": "Physics movement outside validated tolerance"}}


def test_retry2_source_sequence_proves_action24_down_to_up_and_window():
    source = diagnostic.validate_sources(_replay(), _retry())
    assert source["expected_prefix_count"] == 23
    assert source["failed_action_index"] == 24
    assert source["previous_action"] == "down"
    assert [row["action"] for row in source["source_actions_19_to_29"]] == [
        "right", "left", "left", "up", "down", "up", "up", "right",
        "left", "left", "left"]


def test_source_validation_rejects_wrong_failed_prefix_action():
    retry = _retry()
    retry["failed_prefix_action"]["index_1_based"] = 82
    with pytest.raises(ValueError):
        diagnostic.validate_sources(_replay(), retry)


def test_diagnostic_preserves_target_physical_failure_and_runtime_evidence(
        tmp_path, monkeypatch):
    import tools.diagnose_v07_gazebo_macro_composition_action24 as module

    class Adapter:
        def __init__(self, *_args, **_kwargs):
            self.injected = False
            self.control_mode = "PHYSICS"
            self.last_reset_evidence = {"normal_reset_pass": True,
                "reset_method": "fresh_process_initialization"}
            self.process = SimpleNamespace(poll=lambda: None, pid=101)
            self.manager = SimpleNamespace(status=lambda: {
                "status": "Running", "available": True, "pid": 101,
                "partition": "fixture-partition"})
            self.env = SimpleNamespace(
                stepper=SimpleNamespace(time=0., last_verification={}), steps=0,
                pose={"x": 1.5, "y": 1.5, "yaw": 0.},
                controller=SimpleNamespace(last_command={}, last_published_command={},
                    publish_sequence=0), telemetry={}, sensors=SimpleNamespace(frame=None),
                contacts=SimpleNamespace(state={"semantics": "event_only"},
                    schema={"message_type": "gz.msgs.Contacts"}), collision_event=None)
            self.calls = []
            self.closed = False

        def reset(self, _seed):
            return None

        def step(self, action):
            self.calls.append(action)
            self.env.steps += 1
            self.env.stepper.time += .1
            self.env.controller.last_command = gazebo_physics_twist(action)
            self.env.controller.last_published_command = gazebo_physics_twist(action)
            if len(self.calls) == 24:
                raise PhysicalControlFailure("fixture validator rejection", evidence={
                    "validator_evidence": {"valid": False},
                    "action_transition": {"command_mode_transition": "LINEAR_REVERSAL"}})
            return SimpleNamespace(reason="moving", terminated=False, truncated=False,
                elapsed_execution_time=.1, elapsed_discount_units=1., execution_evidence=None)

        def close(self):
            self.closed = True

    adapter = Adapter()
    monkeypatch.setattr(module, "extract_reversal_replay", lambda _path: _replay())
    monkeypatch.setattr(module.ScenarioSpec, "from_dict", lambda value: value)
    monkeypatch.setattr(module, "GazeboPhysicsTrainingEnvironment", lambda *_a, **_k: adapter)
    retry_path = tmp_path / "retry2.json"
    retry_path.write_text(json.dumps(_retry()))

    report = module.run_diagnostic("unused", retry_path, tmp_path / "diagnostic")

    assert adapter.calls == _actions()[:23] + ["up"]
    assert report["prefix_replayed_count"] == 23
    assert report["target_production_step_call_started"] is True
    assert report["target_production_step_returned"] is False
    assert report["target_exception"]["type"] == "PhysicalControlFailure"
    assert report["target_exception"]["physical_failure"]["evidence"][
        "validator_evidence"]["valid"] is False
    assert report["target_exception"]["runtime_after_failure"]["process"][
        "partition"] == "fixture-partition"
    assert report["shutdown"] == "PASS" and adapter.closed
    output = tmp_path / "diagnostic" / "macro_composition_action24.json"
    parsed = json.loads(output.read_text())
    assert parsed["json_evidence_audit"]["status"] == "PASS"
