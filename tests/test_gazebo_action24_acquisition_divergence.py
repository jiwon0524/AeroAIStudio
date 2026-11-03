import json
from types import SimpleNamespace

from aero_ai_studio.simulation.action_mapping import gazebo_physics_twist
from aero_ai_studio.simulation.base import PhysicalControlFailure
from tools import diagnose_v07_gazebo_action24_acquisition_divergence as diagnostic


def _actions():
    return ["up", "down", "up", "up", "up", "down", "up", "right",
        "left", "down", "right", "up", "down", "right", "left", "up",
        "down", "up", "right", "left", "left", "up", "down", "up"]


def _replay():
    return {"completed_episode_actions": [_actions()], "run_id": "fixture-run",
        "artifact_dir": "fixture-artifact", "scenario": {}, "max_steps": 250,
        "training_seed": 42}


def _retry():
    return {"target_episode": 1, "target_action_index_in_episode_1_based": 138,
        "target_global_action_index_1_based": 138, "prefix_replayed_count": 23,
        "production_environment_step_used_for_target": False,
        "failed_prefix_action": {"index_1_based": 24, "action": "up",
            "type": "PhysicalControlFailure"}}


def test_target_sequence_is_exact_action24_and_prefix_is_production_step_path():
    assert _actions()[22:24] == ["down", "up"]


def test_joint_telemetry_is_explicitly_unavailable_without_joint_topics():
    adapter = SimpleNamespace(env=SimpleNamespace(discovery={"topics": []},
        controller=SimpleNamespace(poses={"simple_agent": {}})))
    evidence = diagnostic._joint_availability(adapter)
    assert evidence["direct_joint_position_velocity_telemetry_available"] is False
    assert evidence["joint_state_topics_discovered"] == []
    assert evidence["wheel_link_pose_samples_are_joint_velocity"] is False


def test_command_delivery_levels_do_not_equate_publish_with_body_motion():
    validator = {"world_pose_forward": 0., "body_forward_displacement": 0.,
        "world_direction_ok": False, "world_pose_history_summary": {"world_pose_sample_count": 3},
        "odometry_before": {"linear_x": 0.}, "odometry_after": {"linear_x": .5},
        "odometry_integrated_forward": .047, "odometry_sample_count": 11,
        "odometry_sample_timestamps": [1., 1.1], "odometry_sample_linear_x": [0., .5],
        "discrepancy_classification": "wheel_odometry_without_world_translation"}
    transition = {"action_publish_sequence": 2, "zero_publish_sequence": 3,
        "commanded_twist": gazebo_physics_twist("up")}
    report = {"target_exception": {"physical_failure": {"evidence": {
        "execution_evidence": {"requested_command": gazebo_physics_twist("up"),
                "execution_evidence": {"production_validator": validator},
                "validator_evidence": {"action_transition": transition}}}}},
        "target_runtime_after_failure": {"last_command_controller_state": gazebo_physics_twist("up"),
            "last_published_command_controller_state": {"linear": {"x": 0.},
                "angular": {"z": 0.}}}}
    levels = diagnostic._command_delivery_report(report)
    assert levels["A_python_requested_twist"] == gazebo_physics_twist("up")
    assert levels["publish_sequence_evidence"]["action_publish_sequence"] == 2
    assert levels["C_diffdrive_consumption_ack"]["status"] == "NOT_DIRECTLY_OBSERVED"
    assert levels["D_physical_wheel_joint_motion"]["status"] == "UNAVAILABLE"
    assert levels["E_rigid_body_translation"]["validator"]["world_direction_ok"] is False


def test_diagnostic_replays_1_to_23_then_calls_production_target_and_preserves_failure(
        tmp_path, monkeypatch):
    module = diagnostic

    class Adapter:
        def __init__(self, *_args, **_kwargs):
            self.injected = False
            self.control_mode = "PHYSICS"
            self.last_reset_evidence = {"normal_reset_pass": True,
                "reset_method": "fresh_process_initialization"}
            self.manager = SimpleNamespace(partition="fixture-partition",
                status=lambda: {"status": "Running", "available": True,
                    "pid": 55, "partition": "fixture-partition"})
            self.process = SimpleNamespace(pid=55)
            self.env = SimpleNamespace(stepper=SimpleNamespace(time=0.,
                topic="/world/test/stats", last_verification={}),
                controller=SimpleNamespace(last_command={}, last_published_command={},
                    publish_sequence=0, pose_topic="/world/test/pose", poses={}),
                sensors=SimpleNamespace(topic="/scan", frame=None),
                contact_topic="/contacts", odometry_topic="/odom", contacts=None,
                telemetry={}, pose={"x": 1.5, "y": 1.5, "yaw": 0.}, steps=0,
                discovery={"topics": []})
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
            if len(self.calls) == 23:
                self.env.telemetry["gazebo_dqn_training"] = {
                    "activation_pair": "UP_TO_DOWN", "production_macro": True,
                    "execution_evidence": {"physical_status": "EXECUTED"}}
            if len(self.calls) == 24:
                failure_evidence = {"execution_evidence": {
                    "agent_intent": "up", "status": "PHYSICAL_CONTROL_FAILURE",
                    "requested_command": gazebo_physics_twist("up"),
                    "transition_type": "LINEAR_REVERSAL", "activation_pair": "DOWN_TO_UP",
                        "execution_phases": [{"phase": "BRAKE_LINEAR"},
                            {"phase": "ACQUIRE_LINEAR"}], "execution_evidence": {
                        "braking_phase": {"completion_result": True},
                            "braking_chunks": [{"iterations": 100}],
                            "phase_evidence": [{"phase": "BRAKE_LINEAR"},
                                {"phase": "ACQUIRE_LINEAR", "completion_result": False}],
                        "production_validator": {"valid": False,
                            "world_direction_ok": False,
                            "odometry_after": {"linear_x": .5}}}}}
                failure = PhysicalControlFailure("validator rejected stationary body",
                    evidence=failure_evidence)
                raise failure
            return SimpleNamespace(reason="moving", terminated=False, truncated=False,
                elapsed_execution_time=.1, elapsed_discount_units=1., execution_evidence=None)

        def close(self):
            self.closed = True

    adapter = Adapter()
    monkeypatch.setattr(module, "extract_reversal_replay", lambda _path: _replay())
    monkeypatch.setattr(module.ScenarioSpec, "from_dict", lambda value: value)
    monkeypatch.setattr(module, "GazeboPhysicsTrainingEnvironment", lambda *_a, **_k: adapter)
    monkeypatch.setattr(module, "validate_sources", lambda *_a: {"checks": {"fixture": True}})
    monkeypatch.setattr(module, "_snapshot", lambda _adapter: {
        "simulation_time": _adapter.env.stepper.time, "simulation_stats": {"iterations": 10},
        "last_command_controller_state": dict(_adapter.env.controller.last_command),
        "diffdrive_odometry_latest": None, "model_pose": dict(_adapter.env.pose)})
    monkeypatch.setattr(module, "_topic_cursor", lambda *_a: 0)
    monkeypatch.setattr(module, "_topic_history", lambda *_a: {"world_pose_frames": {
        "status": "AVAILABLE", "samples": []}})
    monkeypatch.setattr(module, "_stats_sample", lambda _a: {"available": True,
        "simulation_time": _a.env.stepper.time, "iterations": 10})
    monkeypatch.setattr(module, "_joint_availability", lambda _a: {
        "direct_joint_position_velocity_telemetry_available": False,
        "joint_state_topics_discovered": [], "wheel_link_pose_samples_are_joint_velocity": False})

    out = tmp_path / "diagnostic"
    report = module.run_diagnostic("unused", out, prior_failure=tmp_path / "prior-missing.json",
        successful_down_up=tmp_path / "success-missing.json")
    assert adapter.calls == _actions()[:23] + ["up"]
    assert report["prefix_replayed_count"] == 23
    assert report["target_production_step_call_started"] is True
    assert report["target_production_step_returned"] is False
    assert report["target_exception"]["type"] == "PhysicalControlFailure"
    assert report["target_exception"]["physical_failure"]["evidence"][
        "execution_evidence"]["activation_pair"] == "DOWN_TO_UP"
    assert report["action23_to_action24_handoff"]["same_simulation_time"] is True
    assert (report["action23_to_action24_handoff"]["action23_final_pose"] ==
        report["action23_to_action24_handoff"]["action24_initial_pose"])
    assert report["action24_production_macro_evidence"]["braking_chunks"][0][
        "iterations"] == 100
    assert report["action24_production_macro_evidence"]["acquisition_phase_evidence"][
        "phase"] == "ACQUIRE_LINEAR"
    assert report["simulation_advancement"]["observed_time_delta"] > 0
    assert report["simulation_advancement"]["iterations_delta"] is not None
    assert report["available_signal_inventory"]["joint_controller_state"] == "UNAVAILABLE"
    assert report["shutdown"] == "PASS" and adapter.closed
    assert report["nonfinite_field_paths"] == []
    stored = json.loads((out / "action24_acquisition_divergence.json").read_text())
    assert stored["target_production_step_call_started"] is True
