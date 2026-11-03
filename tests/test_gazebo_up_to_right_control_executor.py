from types import SimpleNamespace

from aero_ai_studio.gazebo.physics_feedback import BODY_STOPPED_EPSILON
from aero_ai_studio.simulation.action_mapping import (
    classify_physics_command_transition, gazebo_physics_twist)
from aero_ai_studio.simulation.control_execution import (
    ControlExecutionRequest, plan_control_execution)
from tools.verify_v07_gazebo_control_executor_up_to_right import (
    execute_experimental_up_to_right, validate_sources, _task_chunk)
from tools.verify_v07_gazebo_up_to_down_production_integration import find_nonfinite_paths


def _prehistory():
    return {"world_pose_history_available": True,
        "world_pose_history_fresh": True, "world_pose_history_dense_enough": True,
        "world_end_forward_velocity": .5,
        "world_forward_velocity_samples": [
            {"simulation_timestamp": 1.0, "forward_velocity": .4},
            {"simulation_timestamp": 1.05, "forward_velocity": .5}]}


def _adapter():
    class Controller:
        last_command = gazebo_physics_twist("up")
        last_published_command = last_command
        publish_sequence = 1
        pose_topic = "/world/test/pose/info"
        def stop_agent(self):
            self.last_command = {"linear": {"x": 0.0}, "angular": {"z": 0.0}}
            self.last_published_command = self.last_command
            self.publish_sequence += 1
        def pose_history_after(self, *_args): return []

    class Stepper:
        time = 1.0
        dt = .1
        last_verification = {"iteration_delta": 100, "expected_iteration_delta": 100}
        def step_simulation(self): self.time += .1

    env = SimpleNamespace(stepper=Stepper(), controller=Controller(),
        process=SimpleNamespace(poll=lambda: None), transport=SimpleNamespace(cursor=lambda *_: 1),
        odometry_topic="/odom", pose={"x": 1., "y": 1., "yaw": 0.},
        contacts=SimpleNamespace(poll=lambda *_: [], state={}, schema={
            "message_type": "gz.msgs.Contacts"}), goal=(5., 5.),
        telemetry={}, _refresh=lambda: None,
        read_odometry_after_sequence=lambda *_args, **_kwargs: {"linear_x": .5})
    adapter = SimpleNamespace(env=env, max_sensor_age_ms=20, scenario=SimpleNamespace(objects=[]),
        goal_radius=.45, steps=0, acquisition_calls=0)
    adapter.get_agent_observation = lambda *_: object()
    adapter._require_actual_sensor = lambda _observation, _previous: {"sequence": 1}
    adapter.step = lambda _action: setattr(adapter, "acquisition_calls",
        adapter.acquisition_calls + 1)
    return adapter


def test_exact_up_to_right_mapping_and_l2r_plan():
    up, right = gazebo_physics_twist("up"), gazebo_physics_twist("right")
    assert up == {"linear": {"x": .5}, "angular": {"z": 0.0}}
    assert right == {"linear": {"x": 0.0}, "angular": {"z": -.8}}
    assert classify_physics_command_transition(up, right) == "LINEAR_TO_ROTATION"
    plan = plan_control_execution(ControlExecutionRequest(
        "right", up, right, "LINEAR_TO_ROTATION"))
    assert [phase.kind.value for phase in plan.phases] == [
        "BRAKE_LINEAR", "ACQUIRE_ANGULAR"]


def test_experimental_executor_does_not_acquire_until_world_body_stop(monkeypatch):
    import tools.verify_v07_gazebo_control_executor_up_to_right as module

    adapter = _adapter()
    monkeypatch.setattr(module, "summarize_world_pose_history", lambda *_: {
        "world_pose_history_available": True, "world_pose_history_fresh": True,
        "world_pose_history_dense_enough": True, "world_end_forward_velocity": .3,
        "world_end_angular_velocity": 0., "world_forward_velocity_samples": [],
        "world_angular_velocity_samples": []})
    monkeypatch.setattr(module, "_history_contract", lambda *_: {"pass": True})
    monkeypatch.setattr(module, "body_stopped_contract", lambda *_: {
        "pass": False, "world_body_is_authority": True,
        "velocity_epsilon_mps_and_radps": BODY_STOPPED_EPSILON})
    monkeypatch.setattr(module, "_task_chunk", lambda _adapter, sequence, _row: {
        "reason": "moving", "terminated": False, "truncated": False,
        "collision": False, "sensor_contract": {"sequence": sequence}})
    evidence = execute_experimental_up_to_right(adapter, _prehistory(),
        initial_sensor_sequence=0)
    assert evidence["status"] == "PHYSICAL_CONTROL_FAILURE"
    assert evidence["failure_stage"] == "BRAKE_LINEAR"
    assert len(evidence["braking_chunks"]) == 20
    assert evidence["executed_commands"] == [
        {"linear": {"x": 0.0}, "angular": {"z": 0.0}}]
    assert adapter.acquisition_calls == 0


def test_stale_pose_feedback_is_infrastructure_and_never_acquires(monkeypatch):
    import tools.verify_v07_gazebo_control_executor_up_to_right as module

    adapter = _adapter()
    monkeypatch.setattr(module, "summarize_world_pose_history", lambda *_: {})
    monkeypatch.setattr(module, "_history_contract", lambda *_: {"pass": False})
    monkeypatch.setattr(module, "body_stopped_contract", lambda *_: {"pass": False})
    monkeypatch.setattr(module, "_task_chunk", lambda _adapter, sequence, _row: {
        "reason": "moving", "terminated": False, "truncated": False,
        "collision": False, "sensor_contract": {"sequence": sequence}})
    evidence = execute_experimental_up_to_right(adapter, _prehistory(),
        initial_sensor_sequence=0)
    assert evidence["status"] == "INFRASTRUCTURE_FAILURE"
    assert evidence["failure_stage"] == "BRAKE_FEEDBACK"
    assert adapter.acquisition_calls == 0


def test_saved_sources_prove_action8_up_to_right_and_exact_production_pair():
    actions = ["up", "down", "up", "up", "up", "down", "up", "right"]
    retry = {"episode_replays": [{"actions": [
        {"action": action, "reason": "moving", "terminated": False,
         "truncated": False} for action in actions]}]}
    phase3fb = {"prefix_replayed_count": 81}
    final_transition = {"action": "right", "command_mode_transition": "LINEAR_TO_ROTATION",
        "previous_action_twist": gazebo_physics_twist("up"),
        "commanded_twist": gazebo_physics_twist("right")}
    diagnostic = {"trials": [{"failure_action": 8,
        "failure_exception": {"type": "PhysicalControlFailure"},
        "final_runtime": {"action_transition": final_transition,
            "pose_validation": {"valid": False}}}]}
    assert validate_sources({"completed_episode_actions": [actions]},
        diagnostic, retry, phase3fb)["checks"]["runtime_classification_l2r"]
    from pathlib import Path
    source = (Path(__file__).parents[1] /
        "src/aero_ai_studio/training/gazebo_physics.py").read_text()
    assert "UP_TO_RIGHT" in source
    assert "LINEAR_TO_ROTATION_UP_TO_RIGHT_VERIFIED_ACTION_PAIR" in source


def test_braking_collision_preserves_task_terminal_and_json_evidence():
    adapter = _adapter()
    adapter.env.contact_topic = "/contacts"
    adapter.env.contacts.state = {"topic": "/contacts", "semantics": "event_only",
        "assessment": "no_new_contact_event"}
    adapter.env.contacts.schema = {"message_type": "gz.msgs.Contacts"}
    outcome = _task_chunk(adapter, 0, {"pose_after": adapter.env.pose,
        "collision_events": [{"pair": "agent::wall"}]})
    assert outcome["collision"] is True
    assert outcome["terminated"] is True
    assert outcome["reason"] == "collision"
    assert find_nonfinite_paths({"result": outcome}) == []
