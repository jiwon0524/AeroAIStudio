import json
from types import SimpleNamespace

from aero_ai_studio.simulation.action_mapping import gazebo_physics_twist
from aero_ai_studio.simulation.base import PhysicalControlFailure, StepResult
from tools.diagnose_v07_gazebo_macro_composition_80_82 import (
    EXPECTED_ACTIONS, _route, run_diagnostic)


def _sources():
    actions = ["up"] * 138
    actions[136:138] = ["left", "up"]
    actions[77:82] = ["left", "right", "down", "up", "down"]
    retry_rows = [{"episode_action_index_1_based": index,
        "global_action_index_1_based": index, "action": action}
        for index, action in enumerate(actions[:137], start=1)]
    retry = {"episode_replays": [{"actions": retry_rows}],
        "failed_replay_action": {"episode": 1,
            "episode_action_index_1_based": 138,
            "global_action_index_1_based": 138, "action": "up",
            "type": "PhysicalControlFailure"},
        "target_episode": 2,
        "target_action_index_in_episode_1_based": 40,
        "target_global_action_index_1_based": 290}
    failed = {"prefix_replayed_count": 81,
        "failed_prefix_action": {"index_1_based": 82, "action": "down",
            "type": "PhysicalControlFailure"}}
    replay = {"completed_episode_actions": [actions], "scenario": {},
        "max_steps": 250, "training_seed": 42, "run_id": "fixture"}
    return replay, retry, failed


def test_source_action_sequence_and_exact_macro_routes_80_82():
    assert [EXPECTED_ACTIONS[i] for i in range(78, 83)] == [
        "left", "right", "down", "up", "down"]
    assert _route("right", "down", gazebo_physics_twist("right"),
        gazebo_physics_twist("down")) == (
            "ROTATION_TO_LINEAR", "RIGHT_TO_DOWN", "GazeboControlExecutor")
    assert _route("down", "up", gazebo_physics_twist("down"),
        gazebo_physics_twist("up")) == (
            "LINEAR_REVERSAL", "DOWN_TO_UP",
            "GazeboLinearReversalControlExecutor")
    assert _route("up", "down", gazebo_physics_twist("up"),
        gazebo_physics_twist("down")) == (
            "LINEAR_REVERSAL", "UP_TO_DOWN",
            "GazeboLinearReversalControlExecutor")


def test_diagnostic_records_action_82_physical_failure_and_shuts_down(
        tmp_path, monkeypatch):
    import tools.diagnose_v07_gazebo_macro_composition_80_82 as module

    replay, retry, failed = _sources()
    monkeypatch.setattr(module, "extract_reversal_replay", lambda _path: replay)
    retry_path = tmp_path / "retry.json"
    failed_path = tmp_path / "failed.json"
    retry_path.write_text(json.dumps(retry))
    failed_path.write_text(json.dumps(failed))

    class Process:
        pid = 123
        def poll(self): return None

    class Manager:
        partition = "fixture-partition"
        def status(self): return {"status": "Running", "available": True,
                                  "partition": self.partition}

    class FakeAdapter:
        def __init__(self, *_args, **_kwargs):
            self.injected = False
            self.control_mode = "PHYSICS"
            self.process = Process()
            self.manager = Manager()
            self.restart_fallbacks = 0
            self.last_reset_evidence = {"normal_reset_pass": True,
                "reset_method": "fresh_process_initialization",
                "restart_fallback_used": False}
            self.env = SimpleNamespace(steps=0, world_name="fixture-world",
                pose={"x": 1., "y": 1., "yaw": 0.},
                stepper=SimpleNamespace(time=0.2, last_verification={
                    "iteration_delta": 100}),
                controller=SimpleNamespace(last_command={"linear": {"x": 0.},
                    "angular": {"z": 0.}}, last_published_command={
                    "linear": {"x": 0.}, "angular": {"z": 0.}},
                    publish_sequence=0), sensors=SimpleNamespace(frame=None),
                contacts=SimpleNamespace(state={"events": 0}), collision_event=None,
                telemetry={"action_transition": {"world_pose_history": [],
                    "world_pose_history_summary": {"world_pose_history_available": True,
                        "world_pose_history_fresh": True,
                        "world_pose_history_dense_enough": True,
                        "world_end_forward_velocity": 0.1,
                        "world_end_angular_velocity": 0.}}})
            self.closed = False

        def reset(self, _seed): return None
        def step(self, action):
            self.env.steps += 1
            self.env.stepper.time += 0.1
            previous = next((name for name in ("up", "down", "left", "right")
                if gazebo_physics_twist(name) == self.env.controller.last_command), None)
            route = {("right", "down"): "RIGHT_TO_DOWN",
                ("down", "up"): "DOWN_TO_UP", ("up", "down"): "UP_TO_DOWN"}.get(
                    (previous, action))
            self.env.controller.last_command = gazebo_physics_twist(action)
            self.env.controller.last_published_command = gazebo_physics_twist(action)
            self.env.controller.publish_sequence += 1
            transition = {"action": action, "action_publish_sequence":
                self.env.controller.publish_sequence, "odometry_after": {
                    "linear_x": 0.5, "angular_z": 0.0}}
            self.env.telemetry["action_transition"] = transition
            if route:
                self.env.telemetry["gazebo_dqn_training"] = {
                    "activation_pair": route, "production_macro": True,
                    "execution_evidence": {"activation_pair": route,
                        "execution_phases": [{"phase": "BRAKE_LINEAR"},
                            {"phase": "ACQUIRE_LINEAR"}]}}
            if self.env.steps == 82:
                raise PhysicalControlFailure("Physics movement outside validated tolerance",
                    evidence={"validator_evidence": {"valid": False},
                        "action_transition": transition})
            return StepResult(None, 0.0, False, False, "moving",
                elapsed_execution_time=0.1, elapsed_discount_units=1.0)

        def close(self): self.closed = True

    fake = None
    def factory(*args, **kwargs):
        nonlocal fake
        fake = FakeAdapter(*args, **kwargs)
        return fake

    report = run_diagnostic("unused", retry_path, failed_path,
        tmp_path / "diagnostic", env_factory=factory)
    trial = report["trials"][0]
    assert trial["status"] == "FAILED"
    assert trial.get("failure_action") == 82, trial.get("error")
    assert [row["global_action_index"] for row in trial["actions"]] == [80, 81, 82]
    assert [row["activation_pair_expected_from_production_source"]
            for row in trial["actions"]] == ["RIGHT_TO_DOWN", "DOWN_TO_UP", "UP_TO_DOWN"]
    assert all(row["production_environment_step_used"] for row in trial["actions"])
    assert trial["actions"][-1]["exception"]["type"] == "PhysicalControlFailure"
    assert trial["actions"][-1]["exception"]["physical_evidence"][
        "validator_evidence"]["valid"] is False
    assert trial["shutdown"] == "PASS" and fake.closed
    assert report["nonfinite_field_paths"] == []
    saved = json.loads((tmp_path / "diagnostic" /
        "macro_composition_80_82.json").read_text())
    assert saved["json_evidence_audit"]["status"] == "PASS"

