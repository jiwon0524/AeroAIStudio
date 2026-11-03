import json
import math
from types import SimpleNamespace

import pytest

from aero_ai_studio.gazebo.control_executor import (
    GazeboDownToLeftControlExecutor, GazeboUpToRightControlExecutor)
from aero_ai_studio.gazebo.entity_controller import summarize_world_pose_history
from aero_ai_studio.simulation.action_mapping import gazebo_physics_twist
from aero_ai_studio.simulation.base import StepResult
from aero_ai_studio.simulation.control_execution import (
    ControlExecutionRequest, ControlExecutionStatus, plan_control_execution)
from tools.verify_v07_gazebo_control_executor_down_to_left import (
    PREFIX, _strict_json_evidence, validate_saved_failure_source)


def _poses(start, end, *, x0, x1, yaw0=0., yaw1=0.):
    rows = []
    for i in range(5):
        f = i / 4
        rows.append({"simulation_timestamp": start + (end-start)*f,
            "world_x": x0 + (x1-x0)*f, "world_y": 0.,
            "world_yaw": yaw0 + (yaw1-yaw0)*f})
    return rows


def _prehistory():
    return summarize_world_pose_history(_poses(1.2, 1.3, x0=1.55, x1=1.50), 1.2, 1.3)


class _FakeEnv:
    def __init__(self, *, brake_mode="stopped", collision_brake=False,
                 wrong_rotation=False, collision_acquire=False, validator_valid=True,
                 bad_contact=False):
        self.pose = {"x": 1.5, "y": 1.5, "yaw": 0.}
        self.stepper = SimpleNamespace(time=1.3, dt=.1, last_verification={})
        self.process = SimpleNamespace(poll=lambda: None)
        self.controller = SimpleNamespace(last_command=gazebo_physics_twist("down"),
            last_published_command=gazebo_physics_twist("down"), publish_sequence=10,
            pose_topic="/world/test/pose/info", stop_agent=self._stop)
        self.controller.pose_history_after = self.pose_history_after
        self.transport = SimpleNamespace(cursor=lambda _topic: 0)
        self.odometry_topic = "/model/agent/odometry"
        self.brake_mode = brake_mode
        self.collision_brake = collision_brake
        self.wrong_rotation = wrong_rotation
        self.collision_acquire = collision_acquire
        self.validator_valid = validator_valid
        self.acquiring = False
        self.brake_chunks = 0
        self.contact_topic = "/aero/contact"
        self.contacts = SimpleNamespace(poll=self._contacts,
            state={"topic": self.contact_topic, "semantics": "event_only",
                "assessment": "no_new_contact_event", "events": 0},
            schema={"message_type": "gz.msgs.Contacts"})
        if bad_contact:
            self.contacts.state["topic"] = "/wrong/contact"
        self.collision_event = None
        self.telemetry = {"gazebo_dqn_training": {"sensor_after": {
            "source": "gazebo_lidar", "sequence": 3, "age_ms": 0., "dimension": 22}}}
        self._refresh = lambda: None
        self.stepper.step_simulation = self._step

    def _stop(self):
        command = {"linear": {"x": 0.}, "angular": {"z": 0.}}
        self.controller.last_command = command
        self.controller.last_published_command = command
        self.controller.publish_sequence += 1

    def _step(self):
        self.stepper.time += .1
        self.stepper.last_verification = {"iteration_delta": 100,
            "expected_iteration_delta": 100}
        if not self.acquiring:
            self.brake_chunks += 1
            if self.brake_mode == "stopped":
                self.pose["x"] = 1.5
                self.pose["yaw"] = 0.

    def _contacts(self, *_args, **_kwargs):
        if self.collision_brake and not self.acquiring:
            return [{"pair": "agent::wall"}]
        return []

    def pose_history_after(self, _cursor, start, end):
        if not self.acquiring:
            if self.brake_mode == "stale":
                return _poses(start-.1, end-.1, x0=1.5, x1=1.5)
            if self.brake_mode == "sparse":
                return _poses(start, end, x0=1.5, x1=1.5)[:2]
            if self.brake_mode == "nonfinite":
                rows = _poses(start, end, x0=1.5, x1=1.5)
                rows[2]["world_yaw"] = math.nan
                return rows
            if self.brake_mode == "moving":
                return _poses(start, end, x0=1.5, x1=1.45)
            return _poses(start, end, x0=1.5, x1=1.5)
        yaw1 = -.08 if self.wrong_rotation else .08
        return _poses(start, end, x0=1.5, x1=1.5, yaw0=0., yaw1=yaw1)

    def read_odometry_after_sequence(self, *_args, **_kwargs):
        return {"timestamp": self.stepper.time, "linear_x": 0., "angular_z": .8}


class _FakeAdapter:
    max_sensor_age_ms = 20.

    def __init__(self, env):
        self.env = env
        self.actions = []

    def step(self, action):
        assert action == "left"
        assert self.env.controller.last_command == {"linear": {"x": 0.}, "angular": {"z": 0.}}
        self.actions.append(action)
        self.env.acquiring = True
        before_sequence = self.env.controller.publish_sequence
        self.env.controller.last_command = gazebo_physics_twist("left")
        self.env.controller.last_published_command = gazebo_physics_twist("left")
        self.env.controller.publish_sequence += 1
        action_sequence = self.env.controller.publish_sequence
        self.env.stepper.step_simulation()
        self.env.pose["yaw"] = -.08 if self.env.wrong_rotation else .08
        if self.env.collision_acquire:
            self.env.collision_event = SimpleNamespace(to_dict=lambda: {"pair": "agent::wall"})
        # Match production cleanup: the published last command is neutral, while
        # action_transition retains the actual LEFT publish sequence and Twist.
        self.env.controller.last_command = gazebo_physics_twist("left")
        self.env.controller.last_published_command = {"linear": {"x": 0.}, "angular": {"z": 0.}}
        self.env.controller.publish_sequence += 1
        raw = _poses(1.4, 1.5, x0=1.5, x1=1.5, yaw0=0., yaw1=self.env.pose["yaw"])
        summary = summarize_world_pose_history(raw, 1.4, 1.5)
        self.env.telemetry["pose_validation"] = {"valid": self.env.validator_valid,
            "world_pose_history_summary": summary,
            "world_pose_history": raw}
        self.env.telemetry["action_transition"] = {"action": "left",
            "commanded_twist": gazebo_physics_twist("left"),
            "action_publish_sequence": action_sequence,
            "command_publish_sequence_before": before_sequence,
            "odometry_history": [{"timestamp": 1.45, "linear_x": 0., "angular_z": .8}]}
        self.env.telemetry["gazebo_dqn_training"] = {"sensor_after": {
            "source": "gazebo_lidar", "sequence": 5, "age_ms": 0., "dimension": 22}}
        self.env.telemetry["contacts"] = dict(self.env.contacts.state)
        return StepResult((1, 1), 0., False, False,
            "collision" if self.env.collision_acquire else "moving",
            elapsed_execution_time=.1, elapsed_discount_units=1.)


def _target(*, brake_mode="stopped", collision_brake=False,
            wrong_rotation=False, collision_acquire=False, validator_valid=True,
            bad_contact=False, callback=None):
    env = _FakeEnv(brake_mode=brake_mode, collision_brake=collision_brake,
        wrong_rotation=wrong_rotation, collision_acquire=collision_acquire,
        validator_valid=validator_valid, bad_contact=bad_contact)
    adapter = _FakeAdapter(env)
    request = ControlExecutionRequest("left", gazebo_physics_twist("down"),
        gazebo_physics_twist("left"), "LINEAR_TO_ROTATION")
    executor = GazeboDownToLeftControlExecutor(adapter, pre_braking_history=_prehistory())
    result = executor.execute_plan(executor.plan(request), on_braking_chunk=callback)
    return result, adapter, env


def test_exact_down_to_left_planner_is_brake_linear_then_acquire_angular():
    request = ControlExecutionRequest("left", gazebo_physics_twist("down"),
        gazebo_physics_twist("left"), "LINEAR_TO_ROTATION")
    plan = plan_control_execution(request)
    assert [phase.kind.value for phase in plan.phases] == [
        "BRAKE_LINEAR", "ACQUIRE_ANGULAR"]
    assert gazebo_physics_twist("down")["linear"]["x"] == -.5
    assert gazebo_physics_twist("left")["angular"]["z"] == .8


def test_up_to_right_executor_reuses_linear_braking_with_exact_forward_precondition():
    env = _FakeEnv(brake_mode="moving")
    env.controller.last_command = gazebo_physics_twist("up")
    env.controller.last_published_command = gazebo_physics_twist("up")
    adapter = _FakeAdapter(env)
    positive_history = summarize_world_pose_history(
        _poses(1.2, 1.3, x0=1.5, x1=1.55), 1.2, 1.3)
    request = ControlExecutionRequest("right", gazebo_physics_twist("up"),
        gazebo_physics_twist("right"), "LINEAR_TO_ROTATION")
    executor = GazeboUpToRightControlExecutor(adapter,
        pre_braking_history=positive_history)
    result = executor.execute_plan(executor.plan(request))
    assert result.status is ControlExecutionStatus.PHYSICAL_CONTROL_FAILURE
    assert len(result.execution_evidence["braking_chunks"]) == 20
    assert result.execution_evidence["source_action"] == "up"
    assert result.execution_evidence["requested_action"] == "right"
    assert adapter.actions == []


def test_executor_brakes_on_world_pose_then_acquires_left_through_production_step():
    result, adapter, env = _target(callback=lambda _row: {"sensor_contract": {"sequence": 4}})
    assert result.status is ControlExecutionStatus.EXECUTED
    assert adapter.actions == ["left"]
    assert len(result.executed_commands) == 2
    assert result.executed_commands[0]["linear"]["x"] == 0.
    phases = result.execution_evidence["phase_evidence"]
    assert [row["phase"] for row in phases] == ["BRAKE_LINEAR", "ACQUIRE_ANGULAR"]
    assert phases[0]["completion_result"] is True
    assert phases[1]["production_pose_validation"]["valid"] is True
    assert phases[1]["requested_angular_direction_established"] is True
    assert phases[1]["command_published_after_braking"] is True
    assert phases[1]["brake_completion_publish_sequence"] < \
        phases[1]["acquire_command_publish_sequence"]
    assert result.elapsed_simulation_time == pytest.approx(.2)
    json.dumps(result.to_dict(), allow_nan=False)


def test_wheel_odometry_cannot_replace_actual_backward_precondition():
    env = _FakeEnv()
    adapter = _FakeAdapter(env)
    request = ControlExecutionRequest("left", gazebo_physics_twist("down"),
        gazebo_physics_twist("left"), "LINEAR_TO_ROTATION")
    executor = GazeboDownToLeftControlExecutor(adapter,
        pre_braking_history={"world_pose_history_available": True,
            "world_pose_history_fresh": True,"world_pose_history_dense_enough": True,
            "world_end_forward_velocity": 0., "world_forward_velocity_samples": []})
    failed = executor.execute_plan(executor.plan(request))
    assert failed.status is ControlExecutionStatus.INCONCLUSIVE
    assert adapter.actions == []


def test_stopped_timeout_fails_physically_without_sending_left():
    result, adapter, _ = _target(brake_mode="moving")
    assert result.status is ControlExecutionStatus.PHYSICAL_CONTROL_FAILURE
    assert len(result.execution_evidence["braking_chunks"]) == 20
    assert adapter.actions == []


def test_stale_pose_feedback_is_infrastructure_failure_and_sends_no_left():
    result, adapter, _ = _target(brake_mode="stale")
    assert result.status is ControlExecutionStatus.INFRASTRUCTURE_FAILURE
    assert adapter.actions == []


@pytest.mark.parametrize("mode", ["sparse", "nonfinite"])
def test_sparse_or_nonfinite_pose_feedback_is_infrastructure_failure(mode):
    result, adapter, _ = _target(brake_mode=mode)
    assert result.status is ControlExecutionStatus.INFRASTRUCTURE_FAILURE
    assert adapter.actions == []


def test_sensor_or_contact_failure_during_braking_is_infrastructure_failure():
    result, adapter, _ = _target(callback=lambda _row: (_ for _ in ()).throw(
        RuntimeError("sensor/contact contract failure")))
    assert result.status is ControlExecutionStatus.INFRASTRUCTURE_FAILURE
    assert adapter.actions == []


def test_collision_during_braking_prevents_left_acquisition():
    result, adapter, _ = _target(collision_brake=True)
    assert result.status is ControlExecutionStatus.COLLISION
    assert adapter.actions == []


def test_wrong_direction_angular_response_is_physical_failure():
    result, adapter, _ = _target(wrong_rotation=True)
    assert result.status is ControlExecutionStatus.PHYSICAL_CONTROL_FAILURE
    assert adapter.actions == ["left"]


def test_collision_during_acquisition_is_collision_outcome():
    result, _, _ = _target(collision_acquire=True)
    assert result.status is ControlExecutionStatus.COLLISION
    assert result.execution_evidence["collision"] is True


def test_production_validator_rejection_is_physical_failure():
    result, _, _ = _target(validator_valid=False)
    assert result.status is ControlExecutionStatus.PHYSICAL_CONTROL_FAILURE


def test_acquisition_contact_contract_failure_is_infrastructure_failure():
    result, _, _ = _target(bad_contact=True)
    assert result.status is ControlExecutionStatus.INFRASTRUCTURE_FAILURE


def test_retry3_action_14_and_thirteen_action_prefix_are_cross_checked():
    replay = {"completed_episode_actions": [PREFIX + ["left"]]}
    failure = {"episode_replays": [{"actions": [{"action": action} for action in PREFIX]}],
        "failed_replay_action": {"episode": 1, "episode_action_index_1_based": 14,
            "global_action_index_1_based": 14, "action": "left",
            "type": "PhysicalControlFailure"}}
    evidence = validate_saved_failure_source(replay, failure)
    assert evidence["expected_prefix_count"] == 13
    assert evidence["target_global_action_index_1_based"] == 14
    failure["failed_replay_action"]["action"] = "up"
    with pytest.raises(ValueError):
        validate_saved_failure_source(replay, failure)


def test_only_exact_down_to_left_l2r_executor_is_production_routed():
    from pathlib import Path
    source = (Path(__file__).parents[1] /
        "src/aero_ai_studio/training/gazebo_physics.py").read_text()
    step_source = source[source.index("def step(self,action)"):]
    assert "GazeboDownToLeftControlExecutor" in step_source
    assert "LINEAR_TO_ROTATION_DOWN_TO_LEFT_VERIFIED_ACTION_PAIR" in step_source
    assert "transition=='LINEAR_TO_ROTATION' and action==l2r_requested" in step_source


def test_report_evidence_strict_json_conversion_records_nonfinite_paths():
    paths = []
    safe = _strict_json_evidence({"phase": [{"velocity": math.nan}]}, nonfinite=paths)
    assert paths == ["$.phase[0].velocity"]
    assert safe == {"phase": [{"velocity": None}]}
    json.dumps(safe, allow_nan=False)
