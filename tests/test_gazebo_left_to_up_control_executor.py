from __future__ import annotations

import json
import math
from types import SimpleNamespace

import pytest

from aero_ai_studio.gazebo.control_executor import GazeboLeftToUpControlExecutor
from aero_ai_studio.gazebo.entity_controller import summarize_world_pose_history
from aero_ai_studio.simulation.action_mapping import (
    classify_physics_command_transition, gazebo_physics_twist)
from aero_ai_studio.simulation.base import StepResult
from aero_ai_studio.simulation.control_execution import (
    ControlExecutionRequest, ControlExecutionStatus, plan_control_execution)
from tools.verify_v07_gazebo_control_executor_left_to_up import (
    _nonfinite_paths, assess_execution, validate_sources)


def _pose_rows(start, end, *, x=(0., 0., 0.), yaw=(0., 0., 0.)):
    def values(points):
        a, b, c = points
        return (a, (a+b)/2, b, (b+c)/2, c)
    return [{"simulation_timestamp": t, "world_x": px, "world_y": 0.,
        "world_yaw": angle} for t, px, angle in zip(
            [start, start+(end-start)*.25, start+(end-start)*.5,
             start+(end-start)*.75, end], values(x), values(yaw))]


def _left_history():
    return summarize_world_pose_history(
        _pose_rows(.9, 1., yaw=(0., .04, .08)), .9, 1.)


class _Physics:
    def __init__(self, *, brake="stops", acquisition="up", collision_brake=False,
                 collision_acquire=False, step_failure=False, sensor_failure=False,
                 contact_failure=False, process_dead=False):
        self.stepper = SimpleNamespace(time=1., dt=.1, last_verification={})
        self.pose = {"x": 1.5, "y": 1.5, "yaw": 0.}
        self.goal = (5.5, 1.5)
        self.process = SimpleNamespace(poll=lambda: 1 if process_dead else None)
        self.odometry_topic = "/agent/odom"
        self.contact_topic = "/agent/contact"
        self.controller = SimpleNamespace(last_command=gazebo_physics_twist("left"),
            last_published_command=gazebo_physics_twist("left"), publish_sequence=10,
            pose_topic="/world/test/pose/info", stop_agent=self.stop)
        self.controller.pose_history_after = self.pose_history_after
        self.transport = SimpleNamespace(cursor=lambda _topic: 0)
        self.contacts = SimpleNamespace(poll=self.poll_contacts,
            state={"topic": self.contact_topic, "semantics": "event_only",
                "assessment": "no_new_contact_event"},
            schema={"message_type": "gz.msgs.Contacts"})
        self.telemetry = {"contacts": dict(self.contacts.state)}
        self.collision_event = None
        self.brake_mode = brake
        self.acquisition_mode = acquisition
        self.collision_brake = collision_brake
        self.collision_acquire = collision_acquire
        self.step_failure = step_failure
        self.sensor_failure = sensor_failure
        self.contact_failure = contact_failure
        self.brake_count = 0
        self.acquiring = False
        self._refresh = lambda: None
        self.stepper.step_simulation = self.step

    def stop(self):
        self.controller.last_command = {"linear": {"x": 0.}, "angular": {"z": 0.}}
        self.controller.last_published_command = dict(self.controller.last_command)
        self.controller.publish_sequence += 1

    def poll_contacts(self, *_args):
        if self.collision_brake and not self.acquiring:
            return [{"pair": "agent::wall"}]
        return []

    def step(self):
        if self.step_failure:
            raise RuntimeError("step service unavailable")
        self.stepper.time += .1
        self.stepper.last_verification = {"iteration_delta": 100,
            "expected_iteration_delta": 100}

    def pose_history_after(self, _cursor, start, end):
        if self.acquiring:
            if self.acquisition_mode == "opposite_then_up":
                return [{"simulation_timestamp": start, "world_x": self.pose["x"],
                    "world_y": 0., "world_yaw": 0.},
                    {"simulation_timestamp": start+.025, "world_x": self.pose["x"]+.01,
                     "world_y": 0., "world_yaw": 0.},
                    {"simulation_timestamp": start+.05, "world_x": self.pose["x"]+.005,
                     "world_y": 0., "world_yaw": 0.},
                    {"simulation_timestamp": start+.075, "world_x": self.pose["x"]+.03,
                     "world_y": 0., "world_yaw": 0.},
                    {"simulation_timestamp": end, "world_x": self.pose["x"]+.05,
                     "world_y": 0., "world_yaw": 0.}]
            dx = .05 if self.acquisition_mode == "up" else -.05
            yaw = .03 if self.acquisition_mode == "residual_yaw" else 0.
            return _pose_rows(start, end, x=(self.pose["x"], self.pose["x"]+dx/2,
                self.pose["x"]+dx), yaw=(0., yaw/2, yaw))
        mode = self.brake_mode
        self.brake_count += 1
        if mode == "stops" and self.brake_count > 1:
            return _pose_rows(start, end)
        if mode == "stale":
            return _pose_rows(start-.1, end-.1)
        if mode == "sparse":
            return _pose_rows(start, end)[:2]
        if mode == "nonfinite":
            rows = _pose_rows(start, end)
            rows[2]["world_yaw"] = math.nan
            return rows
        return _pose_rows(start, end, yaw=(0., .025, .05))


class _Adapter:
    max_sensor_age_ms = 20.

    def __init__(self, env):
        self.env = env
        self.actions = []

    def step(self, action):
        assert action == "up"
        assert self.env.controller.last_command == {"linear": {"x": 0.},
            "angular": {"z": 0.}}
        baseline = self.env.controller.publish_sequence
        self.actions.append(action)
        self.env.acquiring = True
        self.env.controller.last_command = gazebo_physics_twist("up")
        self.env.controller.last_published_command = gazebo_physics_twist("up")
        self.env.controller.publish_sequence += 1
        publish = self.env.controller.publish_sequence
        self.env.stepper.step_simulation()
        dx = .05 if self.env.acquisition_mode != "wrong_direction" else -.05
        self.env.pose["x"] += dx
        self.env.collision_event = ({"pair": "agent::wall"}
            if self.env.collision_acquire else None)
        self.env.telemetry["pose_validation"] = {"valid": True}
        self.env.telemetry["action_transition"] = {"action": "up",
            "commanded_twist": gazebo_physics_twist("up"),
            "command_publish_sequence_before": baseline,
            "action_publish_sequence": publish,
            "odometry_history": [{"linear_x": .5, "angular_z": 0.}]}
        self.env.telemetry["gazebo_dqn_training"] = ({ } if self.env.sensor_failure else {
            "sensor_after": {"source": "gazebo_lidar", "sequence": 2,
                "age_ms": 0., "dimension": 22}})
        if self.env.contact_failure:
            self.env.contacts.state["topic"] = "/wrong/contact"
        self.env.telemetry["contacts"] = dict(self.env.contacts.state)
        return StepResult((0, 0), .25, False, False,
            "collision" if self.env.collision_acquire else "moving",
            elapsed_execution_time=.1, elapsed_discount_units=1.)


def _request():
    return ControlExecutionRequest("up", gazebo_physics_twist("left"),
        gazebo_physics_twist("up"), "ROTATION_TO_LINEAR")


def _run(**kwargs):
    env = _Physics(**kwargs)
    adapter = _Adapter(env)
    executor = GazeboLeftToUpControlExecutor(adapter, pre_braking_history=_left_history())
    def task_callback(_row):
        collisions = list(_row.get("collision_events") or [])
        return {"reason": "collision" if collisions else "moving",
            "terminated": bool(collisions), "truncated": False,
            "collision": bool(collisions), "collision_events": collisions,
            "sensor_contract": {"source": "gazebo_lidar", "sequence": 10 + env.brake_count,
                "age_ms": 0., "dimension": 22},
            "contact_state": dict(env.contacts.state),
            "contact_schema": dict(env.contacts.schema),
            "contact_topic": env.contact_topic}
    result = executor.execute_plan(executor.plan(_request()),
        on_braking_chunk=task_callback)
    return result, adapter, env


def test_left_to_up_is_exact_r2l_plan_and_world_feedback_executor():
    request = _request()
    assert classify_physics_command_transition(request.previous_command,
        request.requested_command) == "ROTATION_TO_LINEAR"
    assert [phase.kind.value for phase in plan_control_execution(request).phases] == [
        "BRAKE_ANGULAR", "ACQUIRE_LINEAR"]
    result, adapter, env = _run()
    assert result.status is ControlExecutionStatus.EXECUTED
    assert adapter.actions == ["up"] and env.brake_count == 2
    evidence = result.to_dict()["execution_evidence"]
    assert evidence["left_rotation_precondition"]["pass"] is True
    assert evidence["phase_evidence"][0]["completion_result"] is True
    assert evidence["phase_evidence"][1]["requested_direction_established"] is True
    assert evidence["phase_evidence"][1]["command_published_after_braking"] is True
    assert evidence["phase_evidence"][1]["brake_completion_publish_sequence"] < \
        evidence["phase_evidence"][1]["acquire_command_publish_sequence"]
    assert result.elapsed_simulation_time == pytest.approx(.3)
    assert result.executed_commands == ({"linear": {"x": 0.}, "angular": {"z": 0.}},
        gazebo_physics_twist("up"))
    json.dumps(result.to_dict(), allow_nan=False)


def test_odometry_or_command_without_actual_left_rotation_cannot_start_braking():
    env = _Physics()
    adapter = _Adapter(env)
    stopped_history = summarize_world_pose_history(_pose_rows(.9, 1.), .9, 1.)
    result = GazeboLeftToUpControlExecutor(adapter,
        pre_braking_history=stopped_history).execute_plan(
            plan_control_execution(_request()))
    assert result.status is ControlExecutionStatus.INCONCLUSIVE
    assert adapter.actions == [] and env.brake_count == 0


@pytest.mark.parametrize("mode", ["stale", "sparse", "nonfinite"])
def test_invalid_world_pose_braking_feedback_is_infrastructure(mode):
    result, adapter, _ = _run(brake=mode)
    assert result.status is ControlExecutionStatus.INFRASTRUCTURE_FAILURE
    assert adapter.actions == []


def test_moving_body_times_out_with_physical_failure_and_never_sends_up():
    result, adapter, env = _run(brake="moving")
    assert result.status is ControlExecutionStatus.PHYSICAL_CONTROL_FAILURE
    assert env.brake_count == 20
    assert adapter.actions == []
    assert result.elapsed_simulation_time == pytest.approx(2.)


def test_collision_or_step_failure_during_braking_stops_before_acquisition():
    result, adapter, _ = _run(collision_brake=True)
    assert result.status is ControlExecutionStatus.COLLISION
    assert adapter.actions == []
    result, adapter, _ = _run(step_failure=True)
    assert result.status is ControlExecutionStatus.INFRASTRUCTURE_FAILURE
    assert adapter.actions == []


def test_wrong_direction_opposite_transient_and_residual_yaw_do_not_pass():
    result, adapter, _ = _run(acquisition="wrong_direction")
    assert result.status is ControlExecutionStatus.PHYSICAL_CONTROL_FAILURE
    assert adapter.actions == ["up"]
    result, _, _ = _run(acquisition="opposite_then_up")
    assert result.status is ControlExecutionStatus.PHYSICAL_CONTROL_FAILURE
    result, _, _ = _run(acquisition="residual_yaw")
    assert result.status is ControlExecutionStatus.PHYSICAL_CONTROL_FAILURE


def test_acquisition_collision_is_distinct_and_not_execution_pass():
    result, _, _ = _run(collision_acquire=True)
    assert result.status is ControlExecutionStatus.COLLISION


@pytest.mark.parametrize("failure", ["sensor_failure", "contact_failure", "process_dead"])
def test_sensor_contact_and_process_failures_remain_infrastructure(failure):
    result, adapter, _ = _run(**{failure: True})
    assert result.status is ControlExecutionStatus.INFRASTRUCTURE_FAILURE
    assert adapter.actions == ([] if failure == "process_dead" else ["up"])


def test_retry4_target_and_prefix_source_are_exact():
    actions = ["left"] * 137 + ["up"]
    replay = {"completed_episode_actions": [actions]}
    retry_rows = [{"action": action,
        "episode_action_index_1_based": index,
        "global_action_index_1_based": index}
        for index, action in enumerate(actions[:137], start=1)]
    retry = {"target_episode": 2,
        "target_action_index_in_episode_1_based": 40,
        "target_global_action_index_1_based": 290,
        "episode_replays": [{"actions": retry_rows}], "failed_replay_action": {
            "episode": 1, "episode_action_index_1_based": 138,
            "global_action_index_1_based": 138, "action": "up",
            "type": "PhysicalControlFailure"}}
    assert validate_sources(replay, retry)["expected_prefix_count"] == 137
    retry["failed_replay_action"]["action"] = "down"
    with pytest.raises(ValueError):
        validate_sources(replay, retry)


def test_left_to_up_verifier_acceptance_and_exact_production_wiring():
    result, _, env = _run()
    status = {"status": "Running", "available": True}
    acceptance = assess_execution(result, status)
    assert acceptance["all_pass"] is True
    assert acceptance["elapsed_execution_time"] == pytest.approx(.3)
    assert acceptance["elapsed_discount_units"] == pytest.approx(3.)
    from pathlib import Path
    production_source = (Path(__file__).parents[1] /
        "src/aero_ai_studio/training/gazebo_physics.py").read_text()
    assert "left_to_up_macro_supported" in production_source
    assert "activation_pair='LEFT_TO_UP'" in production_source
    assert "ROTATION_TO_LINEAR_LEFT_TO_UP_VERIFIED_ACTION_PAIR" in production_source


def test_nonfinite_execution_evidence_is_detected_for_strict_json():
    assert _nonfinite_paths({"body": [{"velocity": math.nan},
        {"yaw": math.inf}]}) == ["$.body[0].velocity", "$.body[1].yaw"]

