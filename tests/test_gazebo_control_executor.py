import ast
import json
import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from aero_ai_studio.gazebo.control_executor import GazeboControlExecutor
from aero_ai_studio.gazebo.entity_controller import summarize_world_pose_history
from aero_ai_studio.simulation.control_execution import (
    ControlExecutionRequest,
    ControlExecutionStatus,
    FeedbackCondition,
)
from aero_ai_studio.simulation.base import StepResult


def _rows(start, end, *, x=(0., 0., 0.), yaw=(0., 0., 0.), timestamps=None):
    duration = end - start
    ts = timestamps or (start, start + duration * .25, start + duration * .5,
                        start + duration * .75, end)

    def expand(values):
        if len(values) == 3:
            first, middle, last = values
            return (first, (first + middle) / 2, middle, (middle + last) / 2, last)
        return values

    return [{"simulation_timestamp": t, "world_x": px, "world_y": 0., "world_yaw": angle}
            for t, px, angle in zip(ts, expand(x), expand(yaw))]


def _moving_history():
    return summarize_world_pose_history(
        _rows(0., .1, yaw=(0., -.04, -.08)), 0., .1)


class _FakePhysics:
    def __init__(self, *, brake_modes=None, acquisition_valid=True, collision=False,
                 progression_error=None):
        self.stepper = SimpleNamespace(time=1., dt=.1, last_verification={})
        self.pose = {"x": 1.5, "y": 1.5, "yaw": 0.}
        self.process = SimpleNamespace(poll=lambda: None)
        self.odometry_topic = "/agent/odom"
        self.controller = SimpleNamespace(
            pose_topic="/world/test/pose/info", last_command={"linear": {"x": 0.}, "angular": {"z": -.8}},
            last_published_command=None, stop_agent=self._stop)
        self.controller.pose_history_after = self.pose_history_after
        self.transport = SimpleNamespace(cursor=lambda _topic: 0)
        self.contacts = SimpleNamespace(poll=lambda *_args: ([{"collision": True}] if collision else []))
        self.collision_event = None
        self.telemetry = {}
        self.brake_modes = list(brake_modes or ["moving", "stopped"])
        self.acquisition_valid = acquisition_valid
        self.progression_error = progression_error
        self.brake_chunks = 0
        self.acquisition_started = False
        self.stepper.step_simulation = self._step
        self._refresh = lambda: None

    def _stop(self):
        self.controller.last_command = {"linear": {"x": 0.}, "angular": {"z": 0.}}
        self.controller.last_published_command = {
            "linear": {"x": 0.}, "angular": {"z": 0.}}

    def _step(self):
        if self.progression_error:
            raise self.progression_error
        self.stepper.time += .1
        self.stepper.last_verification = {
            "iteration_delta": 100, "expected_iteration_delta": 100}

    def pose_history_after(self, _cursor, start, end):
        if self.acquisition_started:
            return _rows(start, end, x=(self.pose["x"], self.pose["x"] - .025,
                                        self.pose["x"] - .05))
        mode = self.brake_modes[min(self.brake_chunks, len(self.brake_modes) - 1)]
        self.brake_chunks += 1
        if mode == "missing":
            return []
        if mode == "sparse":
            return _rows(start, end)[:2]
        if mode == "stale":
            return _rows(start - .1, end - .1)
        if mode == "nonfinite":
            return _rows(start, end, yaw=(0., math.nan, 0.))
        if mode == "moving":
            return _rows(start, end, yaw=(0., -.025, -.05))
        return _rows(start, end)

    def read_odometry_after_sequence(self, *_args, **_kwargs):
        return {"timestamp": self.stepper.time, "receive_sequence": 10,
                "linear_x": 0., "angular_z": 0.}


class _FakeTrainingAdapter:
    def __init__(self, physics, *, collision=False):
        self.env = physics
        self.collision = collision
        self.commands = []

    def step(self, action):
        assert action == "down"
        assert self.env.controller.last_command["angular"]["z"] == 0.
        self.commands.append(action)
        self.env.acquisition_started = True
        self.env._step()
        self.env.pose["x"] -= .05
        validation = {"valid": self.env.acquisition_valid,
                      "world_direction_ok": True, "collision_may_block_motion": False}
        self.env.telemetry["pose_validation"] = validation
        self.env.telemetry["action_transition"] = {"odometry_history": [{"linear_x": -.5}]}
        self.env.collision_event = {"pair": "agent::wall"} if self.collision else None
        return StepResult((0, 0), 0., False, False, "collision" if self.collision else "moving")


def _request():
    return ControlExecutionRequest("down",
        {"linear": {"x": 0.}, "angular": {"z": -.8}},
        {"linear": {"x": -.5}, "angular": {"z": 0.}},
        "ROTATION_TO_LINEAR")


def _executor(**kwargs):
    physics = _FakePhysics(**kwargs)
    adapter = _FakeTrainingAdapter(physics, collision=kwargs.get("collision", False))
    return GazeboControlExecutor(adapter, pre_braking_history=_moving_history()), adapter, physics


def test_r2l_executor_brakes_from_world_body_then_calls_production_step():
    executor, adapter, physics = _executor()
    plan = executor.plan(_request())
    result = executor.execute_plan(plan)
    assert result.status is ControlExecutionStatus.EXECUTED
    assert physics.brake_chunks == 2
    assert adapter.commands == ["down"]
    assert result.phases[0].completion_conditions == (
        FeedbackCondition.ANGULAR_VELOCITY_WITHIN_DEADBAND,
        FeedbackCondition.LINEAR_VELOCITY_WITHIN_DEADBAND)
    assert result.executed_commands == (
        {"linear": {"x": 0.}, "angular": {"z": 0.}},
        {"linear": {"x": -.5}, "angular": {"z": 0.}},
    )
    evidence = result.to_dict()["execution_evidence"]
    assert evidence["phase_evidence"][0]["completion_result"] is True
    assert evidence["phase_evidence"][1]["production_pose_validation"]["valid"] is True
    json.dumps(result.to_dict())


@pytest.mark.parametrize("mode", ["missing", "stale", "sparse", "nonfinite"])
def test_bad_world_pose_history_cannot_complete_braking(mode):
    executor, adapter, physics = _executor(brake_modes=[mode])
    result = executor.execute_plan(executor.plan(_request()))
    assert result.status is ControlExecutionStatus.PHYSICAL_CONTROL_FAILURE
    assert adapter.commands == []
    assert physics.stepper.time == pytest.approx(1.1)


def test_wheel_stopped_cannot_replace_moving_world_body_evidence():
    executor, adapter, physics = _executor(brake_modes=["moving"] * 20)
    result = executor.execute_plan(executor.plan(_request()))
    assert result.status is ControlExecutionStatus.PHYSICAL_CONTROL_FAILURE
    assert result.failure_category == "physical_control_failure"
    assert physics.brake_chunks == 20
    assert physics.stepper.time == pytest.approx(3.0)
    assert adapter.commands == []
    assert result.elapsed_simulation_time == pytest.approx(2.)


def test_linear_command_is_not_sent_until_angular_braking_completes():
    executor, adapter, physics = _executor(brake_modes=["moving"] * 20)
    result = executor.execute_plan(executor.plan(_request()))
    assert result.status is ControlExecutionStatus.PHYSICAL_CONTROL_FAILURE
    assert physics.controller.last_published_command["linear"]["x"] == 0.
    assert adapter.commands == []


def test_physics_progression_failure_is_infrastructure_not_physical():
    executor, _, _ = _executor(progression_error=RuntimeError("step service unavailable"))
    result = executor.execute_plan(executor.plan(_request()))
    assert result.status is ControlExecutionStatus.INFRASTRUCTURE_FAILURE
    assert result.failure_category == "physics_progression_or_telemetry"


def test_collision_remains_distinct_and_does_not_pass_executor():
    executor, adapter, _ = _executor(collision=True)
    result = executor.execute_plan(executor.plan(_request()))
    assert result.status is ControlExecutionStatus.COLLISION
    assert result.failure_category == "collision"
    assert adapter.commands == []


def test_executor_emits_each_completed_braking_chunk_to_training_callback():
    executor, adapter, physics = _executor()
    rows = []
    result = executor.execute_plan(executor.plan(_request()),
        on_braking_chunk=lambda row: rows.append(row) or {
            "reason": "moving", "terminated": False, "truncated": False,
            "collision": False})
    assert result.status is ControlExecutionStatus.EXECUTED
    assert len(rows) == physics.brake_chunks == 2
    assert [row["elapsed_simulation_time"] for row in rows] == pytest.approx([0.1, 0.1])
    assert adapter.commands == ["down"]


def test_unsupported_plan_is_not_executed():
    executor, adapter, _ = _executor()
    from aero_ai_studio.simulation.control_execution import plan_control_execution
    request = ControlExecutionRequest("right", {}, {}, "LINEAR_TO_ROTATION")
    with pytest.raises(NotImplementedError):
        executor.execute_plan(plan_control_execution(request))
    assert adapter.commands == []


def test_production_environment_step_has_no_experimental_executor_wiring():
    path = Path(__file__).parents[1] / "src/aero_ai_studio/gazebo/environment.py"
    tree = ast.parse(path.read_text())
    imported = [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
                for alias in node.names]
    imported += [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert not any("control_executor" in name for name in imported)
