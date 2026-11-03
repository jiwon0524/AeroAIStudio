import json
import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from aero_ai_studio.gazebo.control_executor import GazeboLinearReversalControlExecutor
from aero_ai_studio.gazebo.entity_controller import summarize_world_pose_history
from aero_ai_studio.simulation.action_mapping import gazebo_physics_twist
from aero_ai_studio.simulation.control_execution import (
    ControlExecutionRequest,
    ControlExecutionStatus,
    plan_control_execution,
)
from aero_ai_studio.simulation.base import StepResult
from tools.verify_v07_gazebo_control_executor_linear_reversal import (
    _episode_boundary_reset_gate,
    build_reversal_replay,
)


def _pose_history(start, end, *, x0=0., x1=0., yaw=0.):
    times = [start, start + (end - start) * .25, start + (end - start) * .5,
             start + (end - start) * .75, end]
    xs = [x0 + (x1 - x0) * index / 4 for index in range(5)]
    return [{"simulation_timestamp": time, "world_x": x,
             "world_y": 0., "world_yaw": yaw} for time, x in zip(times, xs)]


def _prehistory():
    return summarize_world_pose_history(_pose_history(0., .1, x0=0., x1=-.05), 0., .1)


class _FakePhysics:
    def __init__(self, *, brake_modes=("moving", "stopped"), collision=False,
                 previous_action="down", requested_action="up"):
        self.pose = {"x": 1.5, "y": 1.5, "yaw": 0.}
        self.stepper = SimpleNamespace(time=2., dt=.1, last_verification={})
        self.process = SimpleNamespace(poll=lambda: None)
        self.odometry_topic = "/model/agent/odometry"
        self.controller = SimpleNamespace(
            pose_topic="/world/test/pose/info",
            last_command=gazebo_physics_twist(previous_action),
            last_published_command=gazebo_physics_twist(previous_action),
            publish_sequence=0,
            stop_agent=self._stop)
        self.controller.pose_history_after = self.pose_history_after
        self.transport = SimpleNamespace(cursor=lambda _topic: 0)
        self.contacts = SimpleNamespace(
            poll=lambda *_args: ([{"pair": "agent::wall"}] if collision else []),
            state={"topic": "/aero/contact", "semantics": "event_only",
                   "assessment": "no_new_contact_event", "events": 0},
            schema={"message_type": "gz.msgs.Contacts"})
        self.contact_topic = "/aero/contact"
        self.telemetry = {}
        self.collision_event = None
        self.brake_modes = list(brake_modes)
        self.brake_index = 0
        self.acquisition = False
        self.requested_action = requested_action
        self.acquisition_calls = []
        self.stepper.step_simulation = self._step
        self._refresh = lambda: None

    def _stop(self):
        self.controller.last_command = {"linear": {"x": 0.}, "angular": {"z": 0.}}
        self.controller.last_published_command = self.controller.last_command
        self.controller.publish_sequence += 1

    def _step(self):
        self.stepper.time += .1
        self.stepper.last_verification = {"iteration_delta": 100,
                                          "expected_iteration_delta": 100}

    def pose_history_after(self, _cursor, start, end):
        if self.acquisition:
            direction = 1. if self.requested_action == "up" else -1.
            return _pose_history(start, end, x0=self.pose["x"] - .05 * direction,
                                 x1=self.pose["x"], yaw=0.)
        mode = self.brake_modes[min(self.brake_index, len(self.brake_modes) - 1)]
        self.brake_index += 1
        if mode == "stale":
            return _pose_history(start - .1, end - .1)
        if mode == "sparse":
            return _pose_history(start, end)[:2]
        if mode == "nonfinite":
            return [{**row, "world_x": math.nan} for row in _pose_history(start, end)]
        if mode == "moving":
            return _pose_history(start, end, x0=self.pose["x"], x1=self.pose["x"] - .05)
        return _pose_history(start, end, x0=self.pose["x"], x1=self.pose["x"])

    def read_odometry_after_sequence(self, *_args, **_kwargs):
        return {"timestamp": self.stepper.time, "linear_x": 0., "angular_z": 0.}


class _FakeAdapter:
    def __init__(self, physics):
        self.env = physics
        self.actions = []
        self.sensor_after = {"source": "gazebo_lidar", "sequence": 2,
                             "age_ms": 0., "dimension": 22}
        self.validator_valid = True

    def step(self, action):
        assert action == self.env.requested_action
        assert self.env.controller.last_command == {"linear": {"x": 0.}, "angular": {"z": 0.}}
        self.actions.append(action)
        self.env.acquisition = True
        brake_publish_sequence = self.env.controller.publish_sequence
        publish_time = self.env.stepper.time
        self.env.controller.publish_sequence += 1
        action_publish_sequence = self.env.controller.publish_sequence
        self.env._step()
        direction = 1. if action == "up" else -1.
        self.env.pose["x"] += .05 * direction
        self.env.controller.last_command = gazebo_physics_twist(action)
        # Production env.step publishes the requested command, progresses
        # physics, then publishes neutral Twist during cleanup. The last
        # published value is therefore zero even though UP was published.
        self.env.controller.last_published_command = {
            "linear": {"x": 0.}, "angular": {"z": 0.}}
        self.env.controller.publish_sequence += 1
        self.env.telemetry["pose_validation"] = {"valid": self.validator_valid,
                                                   "collision_may_block_motion": False}
        self.env.telemetry["action_transition"] = {
            "action": action, "commanded_twist": gazebo_physics_twist(action),
            "action_publish_sequence": action_publish_sequence,
            "zero_publish_sequence": self.env.controller.publish_sequence,
            "command_publish_sequence_before": brake_publish_sequence,
            "action_command_sim_time": publish_time,
            "zero_command_sim_time": self.env.stepper.time,
            "odometry_history": [{"linear_x": .5}]}
        self.env.telemetry["gazebo_dqn_training"] = {"sensor_after": self.sensor_after}
        self.env.telemetry["contacts"] = dict(self.env.contacts.state)
        return StepResult((1, 1), 0., False, False, "moving", elapsed_execution_time=.1)


def _request(previous_action="down", requested_action="up"):
    return ControlExecutionRequest(requested_action,
        gazebo_physics_twist(previous_action), gazebo_physics_twist(requested_action),
        "LINEAR_REVERSAL")


def _executor(*, previous_action="down", requested_action="up", **kwargs):
    physics = _FakePhysics(previous_action=previous_action,
        requested_action=requested_action, **kwargs)
    adapter = _FakeAdapter(physics)
    executor = GazeboLinearReversalControlExecutor(adapter, pre_braking_history=_prehistory())
    return executor, adapter, physics


def _up_prehistory():
    return summarize_world_pose_history(_pose_history(0., .1, x0=0., x1=.05), 0., .1)


def test_down_to_up_planner_is_brake_then_acquire():
    plan = plan_control_execution(_request())
    assert [phase.kind.value for phase in plan.phases] == ["BRAKE_LINEAR", "ACQUIRE_LINEAR"]


def test_reversal_brakes_on_world_pose_then_calls_production_up_step():
    executor, adapter, physics = _executor()
    result = executor.execute_plan(executor.plan(_request()))
    assert result.status is ControlExecutionStatus.EXECUTED
    assert physics.brake_index == 2
    assert adapter.actions == ["up"]
    assert result.executed_commands == (
        {"linear": {"x": 0.}, "angular": {"z": 0.}},
        gazebo_physics_twist("up"))
    phases = result.execution_evidence["phase_evidence"]
    assert phases[0]["phase"] == "BRAKE_LINEAR"
    assert phases[0]["completion_result"] is True
    assert phases[1]["production_pose_validation"]["valid"] is True
    assert phases[1]["command_published_after_braking"] is True
    assert phases[1]["brake_end_sim_time"] == phases[1]["acquire_publish_sim_time"]
    assert phases[1]["simulation_time_equal_at_publish"] is True
    assert phases[1]["brake_completion_event_sequence"] < phases[1]["acquire_command_publish_event_sequence"]
    assert phases[1]["acquire_command_publish_sequence"] > phases[1]["brake_completion_publish_sequence"]
    assert phases[1]["ordering_proof_source"] == "executor_control_flow_and_action_transition_publish_sequence"
    assert physics.controller.last_published_command["linear"]["x"] == 0.
    assert result.elapsed_simulation_time == pytest.approx(.3)
    json.dumps(result.to_dict())


def test_up_to_down_experimental_exact_pair_brakes_then_acquires_backward_motion():
    physics = _FakePhysics(previous_action="up", requested_action="down")
    adapter = _FakeAdapter(physics)
    executor = GazeboLinearReversalControlExecutor(adapter,
        pre_braking_history=_up_prehistory(), previous_action="up",
        requested_action="down")
    request = _request("up", "down")
    plan = executor.plan(request)
    assert [phase.kind.value for phase in plan.phases] == [
        "BRAKE_LINEAR", "ACQUIRE_LINEAR"]
    result = executor.execute_plan(plan)
    assert result.status is ControlExecutionStatus.EXECUTED
    assert adapter.actions == ["down"]
    phases = result.execution_evidence["phase_evidence"]
    assert phases[0]["command"]["linear"]["x"] == 0.
    assert phases[0]["chunks"][-1]["body_stopped_contract"]["pass"] is True
    assert phases[1]["world_forward_displacement"] < 0.
    assert phases[1]["end_body_forward_velocity"] < -.02
    assert phases[1]["requested_direction_established"] is True
    assert phases[1]["command_published_after_braking"] is True
    assert phases[1]["acquire_command_publish_event_sequence"] > \
        phases[1]["brake_completion_event_sequence"]
    assert result.elapsed_simulation_time == pytest.approx(.3)
    json.dumps(result.to_dict())


def test_up_to_down_requires_actual_forward_body_motion_before_braking():
    physics = _FakePhysics(previous_action="up", requested_action="down")
    adapter = _FakeAdapter(physics)
    executor = GazeboLinearReversalControlExecutor(adapter,
        pre_braking_history=_prehistory(), previous_action="up",
        requested_action="down")
    result = executor.execute_plan(executor.plan(_request("up", "down")))
    assert result.status is ControlExecutionStatus.INCONCLUSIVE
    assert adapter.actions == []
    assert physics.brake_index == 0


def test_elapsed_time_uses_observed_single_brake_chunk_count():
    executor, adapter, physics = _executor(brake_modes=("stopped",))
    result = executor.execute_plan(executor.plan(_request()))
    assert result.status is ControlExecutionStatus.EXECUTED
    assert physics.brake_index == 1
    assert result.elapsed_simulation_time == pytest.approx(.2)


def test_stale_sensor_after_acquisition_is_infrastructure_failure():
    executor, adapter, _ = _executor()
    adapter.sensor_after = {"source": "gazebo_lidar", "sequence": 2,
                            "age_ms": 80., "dimension": 22}
    result = executor.execute_plan(executor.plan(_request()))
    assert result.status is ControlExecutionStatus.INFRASTRUCTURE_FAILURE
    assert result.failure_category == "sensor_contact_or_command_contract"


def test_contact_schema_mismatch_after_acquisition_is_infrastructure_failure():
    executor, adapter, physics = _executor()
    physics.contacts.schema = {"message_type": "gz.msgs.Other"}
    result = executor.execute_plan(executor.plan(_request()))
    assert result.status is ControlExecutionStatus.INFRASTRUCTURE_FAILURE
    assert result.failure_category == "sensor_contact_or_command_contract"


def test_production_validator_rejection_remains_physical_failure():
    executor, adapter, _ = _executor()
    adapter.validator_valid = False
    result = executor.execute_plan(executor.plan(_request()))
    assert result.status is ControlExecutionStatus.PHYSICAL_CONTROL_FAILURE
    assert result.execution_evidence["phase_evidence"][-1]["production_pose_validation"]["valid"] is False


def test_requested_up_is_never_sent_before_world_body_stops():
    executor, adapter, physics = _executor(brake_modes=("moving",) * 20)
    result = executor.execute_plan(executor.plan(_request()))
    assert result.status is ControlExecutionStatus.PHYSICAL_CONTROL_FAILURE
    assert result.failure_category == "physical_control_failure"
    assert physics.brake_index == 20
    assert result.elapsed_simulation_time == pytest.approx(2.)
    assert adapter.actions == []
    assert physics.controller.last_published_command["linear"]["x"] == 0.


def test_acquisition_publish_sequence_before_brake_boundary_is_not_ordered():
    from aero_ai_studio.gazebo.control_executor import _acquisition_publish_ordered
    transition = {"action": "up", "commanded_twist": gazebo_physics_twist("up"),
                  "action_publish_sequence": 7}
    assert not _acquisition_publish_ordered(8, transition, gazebo_physics_twist("up"))


def test_equal_simulation_time_does_not_replace_event_order_proof():
    from aero_ai_studio.gazebo.control_executor import _acquisition_publish_ordered
    transition = {"action": "up", "commanded_twist": gazebo_physics_twist("up"),
                  "action_publish_sequence": 9, "action_command_sim_time": 34.7}
    assert _acquisition_publish_ordered(8, transition, gazebo_physics_twist("up"))


def test_down_acquisition_ordering_uses_requested_action_and_event_sequence():
    from aero_ai_studio.gazebo.control_executor import _acquisition_publish_ordered
    transition = {"action": "down", "commanded_twist": gazebo_physics_twist("down"),
                  "action_publish_sequence": 12, "action_command_sim_time": 34.7}
    assert _acquisition_publish_ordered(11, transition,
        gazebo_physics_twist("down"), expected_action="down")
    assert not _acquisition_publish_ordered(12, transition,
        gazebo_physics_twist("down"), expected_action="down")


def test_brake_completion_failure_never_calls_acquisition():
    executor, adapter, _ = _executor(brake_modes=("moving",) * 20)
    result = executor.execute_plan(executor.plan(_request()))
    phase = result.execution_evidence["phase_evidence"][0]
    assert phase["completion_result"] is False
    assert adapter.actions == []


def test_process_death_is_infrastructure_failure_before_braking():
    executor, adapter, physics = _executor()
    physics.process.poll = lambda: 1
    result = executor.execute_plan(executor.plan(_request()))
    assert result.status is ControlExecutionStatus.INFRASTRUCTURE_FAILURE
    assert result.failure_category == "process_death"
    assert adapter.actions == []
    assert physics.brake_index == 0


@pytest.mark.parametrize("mode", ["stale", "sparse", "nonfinite"])
def test_bad_pose_feedback_is_infrastructure_failure(mode):
    executor, adapter, _ = _executor(brake_modes=(mode,))
    result = executor.execute_plan(executor.plan(_request()))
    assert result.status is ControlExecutionStatus.INFRASTRUCTURE_FAILURE
    assert result.failure_category == "world_pose_feedback_unavailable"
    assert adapter.actions == []


def test_zero_odometry_does_not_override_moving_world_body():
    executor, adapter, physics = _executor(brake_modes=("moving",) * 20)
    result = executor.execute_plan(executor.plan(_request()))
    assert result.status is ControlExecutionStatus.PHYSICAL_CONTROL_FAILURE
    assert all(row["odometry"]["linear_x"] == 0.
               for row in result.execution_evidence["braking_chunks"])
    assert any(not row["body_stopped_contract"]["pass"]
               for row in result.execution_evidence["braking_chunks"])
    assert adapter.actions == []


def test_collision_during_braking_prevents_up_acquisition():
    executor, adapter, _ = _executor(collision=True)
    result = executor.execute_plan(executor.plan(_request()))
    assert result.status is ControlExecutionStatus.COLLISION
    assert adapter.actions == []
    assert [row["phase"] for row in result.execution_evidence["phase_evidence"]] == ["BRAKE_LINEAR"]


def test_task_terminal_during_braking_prevents_up_acquisition():
    executor, adapter, _ = _executor()
    result = executor.execute_plan(executor.plan(_request()),
        on_braking_chunk=lambda _row: {"reason": "goal", "terminated": True,
                                       "truncated": False, "collision": False})
    assert result.status is ControlExecutionStatus.TASK_TERMINAL
    assert adapter.actions == []


def test_production_linear_reversal_routing_is_exact_down_to_up_pair():
    source = Path(__file__).parents[1] / "src/aero_ai_studio/training/gazebo_physics.py"
    text = source.read_text()
    assert "LINEAR_REVERSAL_VERIFIED_ACTION_PAIR=('down','up')" in text
    assert "transition=='LINEAR_REVERSAL'" in text
    assert "previous_command==gazebo_physics_twist(previous_reversal_action)" in text


def test_reversal_saved_artifact_sequence_builds_exact_episode_prefix():
    mapping = [{"action": "up", "twist": {"linear_x": .5, "angular_z": 0.}},
               {"action": "down", "twist": {"linear_x": -.5, "angular_z": 0.}}]
    checkpoint = {"global_step": 5, "buffer": [
        ([0.] * 22, 0, 0., [0.] * 22, False, 1.),
        ([0.] * 22, 1, 0., [0.] * 22, True, 1.),
        ([0.] * 22, 1, 0., [0.] * 22, False, 1.),
        ([0.] * 22, 1, 0., [0.] * 22, False, 1.),
        ([0.] * 22, 1, 0., [0.] * 22, False, 1.)]}
    failure = {"transition_type": "LINEAR_REVERSAL", "collision": False,
        "validator_evidence": {"command_mode_transition": "LINEAR_REVERSAL",
            "previous_action_twist": gazebo_physics_twist("down"),
            "requested_command_twist": gazebo_physics_twist("up"),
            "collision_may_block_motion": False, "contact_blocked_world_motion": False}}
    replay = build_reversal_replay(checkpoint, failure,
        [{"episode": 1, "steps": 2, "reason": "timeout"}], mapping,
        artifact_dir=Path("artifact"), run_dir=Path("artifact/run_x"),
        config={"seed": 42, "max_steps": 10}, scenario={"start": [1, 1]})
    assert replay["completed_episode_actions"] == [["up", "down"]]
    assert replay["failed_episode_saved_prefix"] == ["down", "down", "down"]
    assert replay["failed_episode_reset_seed"] == 44
    assert replay["target_action"] == "up"
    assert replay["target_action_index_in_episode_1_based"] == 4
    assert len(replay["failed_episode_saved_prefix"]) == 3
    assert replay["target_global_action_index_1_based"] == 6


def test_normal_persistent_boundary_reset_allows_deterministic_replay():
    method = "world_control_reset_model_only_after_quiescence"
    evidence = {"reset_method": method, "process_reused": True,
        "restart_fallback_count": 0, "restart_fallback_used": False,
        "normal_reset_pass": True,
        "primary_reset_attempt": {"reset_method": method,
            "normal_reset_pass": True, "restart_fallback_used": False}}
    gate = _episode_boundary_reset_gate(evidence, fallback_count_before=0,
        fallback_count_after=0, pid_before=123, pid_after=123, process_alive=True)
    assert gate["continue_replay"] is True
    assert gate["actual_process_restart_fallback"] is False


def test_actual_restart_fallback_blocks_deterministic_replay_and_preserves_cause():
    evidence = {"reset_method": "fresh_process_restart", "process_reused": False,
        "restart_fallback_count": 1, "restart_fallback_used": True,
        "normal_reset_pass": False,
        "primary_reset_attempt": {"reset_method": "world_control_reset_model_only_after_quiescence",
            "normal_reset_pass": False, "restart_fallback_used": True,
            "normal_reset_failure_reason": "contact readiness failure"}}
    gate = _episode_boundary_reset_gate(evidence, fallback_count_before=0,
        fallback_count_after=1, pid_before=123, pid_after=456, process_alive=True)
    assert gate["continue_replay"] is False
    assert gate["actual_process_restart_fallback"] is True
    assert gate["original_persistent_reset_failure"]["normal_reset_failure_reason"] == \
        "contact readiness failure"


def test_fresh_initial_process_is_not_misclassified_as_episode_fallback():
    evidence = {"reset_method": "fresh_process_initialization", "process_reused": False,
        "restart_fallback_count": 0, "restart_fallback_used": False,
        "normal_reset_pass": True,
        "primary_reset_attempt": {"reset_method": "fresh_process_initialization",
            "normal_reset_pass": True, "restart_fallback_used": False}}
    gate = _episode_boundary_reset_gate(evidence, fallback_count_before=0,
        fallback_count_after=0, pid_before=123, pid_after=123, process_alive=True)
    assert gate["actual_process_restart_fallback"] is False
    assert gate["continue_replay"] is False
    assert "provenance" in gate["reason"]


def test_inconsistent_fallback_flag_and_count_is_classified_as_fallback():
    evidence = {"reset_method": "world_control_reset_model_only_after_quiescence",
        "process_reused": True, "restart_fallback_count": 1,
        "restart_fallback_used": False, "normal_reset_pass": False,
        "primary_reset_attempt": {"reset_method": "world_control_reset_model_only_after_quiescence",
            "normal_reset_pass": False, "restart_fallback_used": False,
            "normal_reset_failure_reason": "body settle failed"}}
    gate = _episode_boundary_reset_gate(evidence, fallback_count_before=0,
        fallback_count_after=1, pid_before=123, pid_after=456, process_alive=True)
    assert gate["actual_process_restart_fallback"] is True
    assert gate["original_persistent_reset_failure"]["normal_reset_failure_reason"] == \
        "body settle failed"


def test_reversal_artifact_replay_rejects_misaligned_done_boundary():
    mapping = [{"action": "up", "twist": {"linear_x": .5, "angular_z": 0.}},
               {"action": "down", "twist": {"linear_x": -.5, "angular_z": 0.}}]
    checkpoint = {"global_step": 2, "buffer": [
        ([0.] * 22, 0, 0., [0.] * 22, False, 1.),
        ([0.] * 22, 1, 0., [0.] * 22, False, 1.)]}
    failure = {"transition_type": "LINEAR_REVERSAL", "collision": False,
        "validator_evidence": {"command_mode_transition": "LINEAR_REVERSAL",
            "previous_action_twist": gazebo_physics_twist("down"),
            "requested_command_twist": gazebo_physics_twist("up")}}
    with pytest.raises(ValueError, match="done flag"):
        build_reversal_replay(checkpoint, failure,
            [{"episode": 1, "steps": 1, "reason": "timeout"}], mapping,
            artifact_dir=Path("artifact"), run_dir=Path("artifact/run_x"),
            config={"seed": 42, "max_steps": 10}, scenario={})
