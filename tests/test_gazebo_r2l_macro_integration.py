from __future__ import annotations

from types import SimpleNamespace

import pytest

from aero_ai_studio.agents.dqn import DQNAgent
from aero_ai_studio.gazebo.control_executor import GazeboControlExecutor
from aero_ai_studio.observation.models import Observation
from aero_ai_studio.simulation.base import PhysicalControlFailure, StepResult
from aero_ai_studio.simulation.action_mapping import (
    gazebo_physics_action_mapping, gazebo_physics_twist)
from aero_ai_studio.simulation.control_execution import ControlExecutionResult, ControlExecutionStatus
from aero_ai_studio.training.gazebo_physics import (
    GazeboPhysicsTrainingEnvironment,
    LINEAR_REVERSAL_VERIFIED_ACTION_PAIR,
    LINEAR_REVERSAL_UP_TO_DOWN_VERIFIED_ACTION_PAIR,
    LINEAR_TO_ROTATION_DOWN_TO_LEFT_VERIFIED_ACTION_PAIR,
    LINEAR_TO_ROTATION_UP_TO_RIGHT_VERIFIED_ACTION_PAIR,
    R2L_VERIFIED_ACTION_PAIR,
    GazeboTrainingInfrastructureError,
)


def _body_history():
    return {"world_pose_history_available": True, "world_pose_history_fresh": True,
        "world_pose_history_dense_enough": True, "world_end_forward_velocity": 0.0,
        "world_end_angular_velocity": -0.8}


class _FakePhysics:
    def __init__(self, *, terminal=None):
        self.pose = {"x": 1.5, "y": 1.5, "yaw": 0.0}
        self.goal = (5.5, 1.5)
        self.stepper = SimpleNamespace(time=3.5)
        self.controller = SimpleNamespace(last_command={"linear": {"x": 0.0}, "angular": {"z": -0.8}})
        self.telemetry = {"action_transition": {"world_pose_history_summary": _body_history()}}
        self.last_reward_components = {}
        self.steps = 10
        self.done = False
        self.lifecycle = SimpleNamespace(PAUSED="paused")
        self.collision_event = None
        self.contacts = SimpleNamespace(state={}, reset=lambda *_: None)
        self.sensor_sequence = 0
        self.sensors = SimpleNamespace(frame=None)
        self.terminal = terminal
        self.acquisition_actions = []
        self.distance = 0.0

    def get_agent_observation(self, *_args):
        self.sensor_sequence += 1
        self.sensors.frame = SimpleNamespace(source="gazebo_lidar", age_ms=0.0)
        return Observation("sensor", (1, 1), (5, 1), sensor_state={
            "front_distance": 5.0, "back_distance": 5.0, "left_distance": 5.0, "right_distance": 5.0,
            "goal_distance": 4.0, "goal_direction": "E", "goal_delta": [4.0, 0.0],
            "moving_obstacle_distance": None, "moving_obstacle_relative_motion": "UNKNOWN",
            "source": "gazebo_lidar", "sensor_timestamp": self.stepper.time,
            "sequence": self.sensor_sequence,
        })

    def step(self, action):
        if action in ("up", "down") and self.controller.last_command == {"linear": {"x": 0.0}, "angular": {"z": 0.0}}:
            self.acquisition_actions.append(action)
        start = self.stepper.time
        self.stepper.time += 0.1
        self.pose["x"] += 0.05
        self.distance += 0.05
        self.controller.last_command = {"linear": {"x": -0.5 if action == "down" else 0.5},
                                        "angular": {"z": 0.0 if action in ("up", "down") else -0.8}}
        self.telemetry["pose_validation"] = {"valid": True}
        self.telemetry["action_transition"] = {"simulation_duration": self.stepper.time - start,
            "action_command_sim_time": start, "world_pose_history_summary": _body_history()}
        self.steps += 1
        return StepResult((1, 1), 0.0, False, False, "moving")

    def get_observation(self):
        return (1, 1)


def _adapter(fake_env, monkeypatch, *, gamma=0.95):
    adapter = GazeboPhysicsTrainingEnvironment.__new__(GazeboPhysicsTrainingEnvironment)
    adapter.env = fake_env
    adapter.scenario = SimpleNamespace(objects=[])
    adapter.max_sensor_age_ms = 20
    adapter.goal_radius = 0.45
    adapter.gamma = gamma
    adapter.last_reward_components = {}
    adapter.last_step_seconds = 0.0
    return adapter


class _FakeExecutor:
    terminal_reason = None
    chunks = 2

    def __init__(self, adapter, *, pre_braking_history, **_kwargs):
        self.adapter = adapter
        self.env = adapter.env
        self.prehistory = pre_braking_history

    def execute_plan(self, plan, *, on_braking_chunk=None):
        phases = [{"phase": "BRAKE_ANGULAR"}, {"phase": "ACQUIRE_LINEAR"}]
        executed = []
        for index in range(self.chunks):
            start = self.env.stepper.time
            before = dict(self.env.pose)
            self.env.stepper.time += 0.1
            if self.terminal_reason == "collision":
                collision = [{"pair": "agent::wall", "timestamp": self.env.stepper.time}]
            else:
                collision = []
                self.env.pose["x"] += 0.01
            row = {"simulation_start": start, "simulation_end": self.env.stepper.time,
                "pose_before": before, "pose_after": dict(self.env.pose),
                "collision_events": collision}
            outcome = on_braking_chunk(row)
            if outcome.get("terminated") or outcome.get("truncated"):
                phases = [{"phase": "BRAKE_ANGULAR", "chunks": [row]}]
                status = (ControlExecutionStatus.COLLISION if outcome.get("collision")
                          else ControlExecutionStatus.TASK_TERMINAL)
                return ControlExecutionResult("down", status, plan.request.requested_command,
                    plan.request.transition_type, executed_commands=tuple(executed), phases=tuple(),
                    elapsed_simulation_time=self.env.stepper.time - 3.5,
                    reason=outcome["reason"], execution_evidence={"phase_evidence": phases})
            executed.append({"linear": {"x": 0.0}, "angular": {"z": 0.0}})
        self.env.controller.last_command = {"linear": {"x": 0.0}, "angular": {"z": 0.0}}
        acquisition = self.adapter.step("down")
        return ControlExecutionResult("down", ControlExecutionStatus.EXECUTED,
            plan.request.requested_command, plan.request.transition_type,
            executed_commands=tuple(executed + [plan.request.requested_command]),
            elapsed_simulation_time=self.env.stepper.time - 3.5,
            execution_evidence={"phase_evidence": phases}, step_result=acquisition)


def test_r2l_production_adapter_returns_one_macro_transition(monkeypatch):
    import aero_ai_studio.training.gazebo_physics as module

    fake = _FakePhysics()
    adapter = _adapter(fake, monkeypatch)
    monkeypatch.setattr(module, "GazeboControlExecutor", _FakeExecutor)
    result = adapter.step("down")

    assert result.elapsed_execution_time == pytest.approx(0.3)
    assert result.elapsed_discount_units == pytest.approx(3.0)
    assert result.reason == "moving" and not result.terminated
    assert result.execution_evidence["transition_type"] == "ROTATION_TO_LINEAR"
    assert result.execution_evidence["execution_phases"]
    assert result.execution_evidence["control_chunk_count"] == 3
    assert result.execution_evidence["macro_reward"] == pytest.approx(
        sum(chunk["reward"] * (0.95 ** index)
            for index, chunk in enumerate(result.execution_evidence["reward_chunks"])))
    assert fake.acquisition_actions == ["down"]
    assert fake.steps == 11

    observation = adapter.get_agent_observation("sensor")
    agent = DQNAgent(batch_size=8, buffer_size=8)
    agent.learn(__import__("aero_ai_studio.agents.base", fromlist=["Transition"]).Transition(
        observation, "down", result.reward, observation, False, result.elapsed_discount_units))
    stored = agent.buffer.items[0]
    assert len(stored) == 6 and stored[1] == 1 and stored[5] == pytest.approx(3.0)


@pytest.mark.parametrize("terminal,expected_reward", [("collision", -100.0), ("danger_zone", -50.0)])
def test_braking_terminal_stops_before_linear_acquisition(monkeypatch, terminal, expected_reward):
    import aero_ai_studio.training.gazebo_physics as module

    fake = _FakePhysics(terminal=terminal)
    adapter = _adapter(fake, monkeypatch)

    class TerminalExecutor(_FakeExecutor):
        terminal_reason = terminal
        chunks = 1

    monkeypatch.setattr(module, "GazeboControlExecutor", TerminalExecutor)
    if terminal == "danger_zone":
        adapter.scenario.objects = [SimpleNamespace(type="danger_zone", position=(1, 1))]
    result = adapter.step("down")
    assert result.reward == pytest.approx(expected_reward)
    assert result.terminated
    assert result.elapsed_execution_time == pytest.approx(0.1)
    assert result.elapsed_discount_units == pytest.approx(1.0)
    assert fake.acquisition_actions == []
    assert fake.steps == 11


def test_non_r2l_transition_keeps_direct_path_and_one_discount_unit(monkeypatch):
    fake = _FakePhysics()
    fake.controller.last_command = {"linear": {"x": 0.5}, "angular": {"z": 0.0}}
    adapter = _adapter(fake, monkeypatch)
    result = adapter.step("up")
    assert result.elapsed_discount_units == pytest.approx(1.0)
    assert fake.acquisition_actions == []


def test_unverified_r2l_command_pair_stays_on_existing_direct_path(monkeypatch):
    fake = _FakePhysics()
    fake.controller.last_command = {"linear": {"x": 0.0}, "angular": {"z": 0.8}}
    adapter = _adapter(fake, monkeypatch)
    result = adapter.step("down")
    assert result.elapsed_discount_units == pytest.approx(1.0)
    assert fake.acquisition_actions == []
    assert fake.telemetry["gazebo_dqn_training"]["control_executor_activation"]["active"] is False


def test_r2l_physical_and_infrastructure_failures_do_not_return_transition(monkeypatch):
    import aero_ai_studio.training.gazebo_physics as module

    class FailedExecutor(_FakeExecutor):
        failure_status = ControlExecutionStatus.PHYSICAL_CONTROL_FAILURE

        def execute_plan(self, plan, *, on_braking_chunk=None):
            return ControlExecutionResult("down", self.failure_status,
                plan.request.requested_command, plan.request.transition_type,
                elapsed_simulation_time=0.2, reason="bounded phase failed",
                execution_evidence={"phase_evidence": []})

    fake = _FakePhysics()
    adapter = _adapter(fake, monkeypatch)
    monkeypatch.setattr(module, "GazeboControlExecutor", FailedExecutor)
    with pytest.raises(PhysicalControlFailure):
        adapter.step("down")
    assert fake.acquisition_actions == []

    class InfrastructureExecutor(FailedExecutor):
        failure_status = ControlExecutionStatus.INFRASTRUCTURE_FAILURE

    monkeypatch.setattr(module, "GazeboControlExecutor", InfrastructureExecutor)
    with pytest.raises(GazeboTrainingInfrastructureError):
        adapter.step("down")
    assert fake.acquisition_actions == []


def test_direct_l2r_remains_outside_macro_activation(monkeypatch):
    import aero_ai_studio.training.gazebo_physics as module

    fake = _FakePhysics()
    adapter = _adapter(fake, monkeypatch)
    fake.controller.last_command = gazebo_physics_twist("up")
    result = adapter.step("left")  # Unverified UP→LEFT L2R remains direct.
    assert result.elapsed_discount_units == pytest.approx(1.0)


class _FakeUpToRightExecutor(_FakeExecutor):
    chunks = 2

    def execute_plan(self, plan, *, on_braking_chunk=None):
        assert plan.request.agent_intent == "right"
        assert plan.request.previous_command == gazebo_physics_twist("up")
        assert plan.request.requested_command == gazebo_physics_twist("right")
        assert [phase.kind.value for phase in plan.phases] == [
            "BRAKE_LINEAR", "ACQUIRE_ANGULAR"]
        executed = []
        for _ in range(self.chunks):
            start = self.env.stepper.time
            before = dict(self.env.pose)
            self.env.stepper.time += .1
            row = {"simulation_start": start, "simulation_end": self.env.stepper.time,
                "pose_before": before, "pose_after": dict(self.env.pose),
                "collision_events": []}
            on_braking_chunk(row)
            executed.append({"linear": {"x": 0.}, "angular": {"z": 0.}})
        self.env.controller.last_command = {"linear": {"x": 0.}, "angular": {"z": 0.}}
        acquisition = self.adapter.step("right")
        return ControlExecutionResult("right", ControlExecutionStatus.EXECUTED,
            plan.request.requested_command, plan.request.transition_type,
            executed_commands=tuple(executed + [plan.request.requested_command]),
            elapsed_simulation_time=self.env.stepper.time - 3.5,
            execution_evidence={"phase_evidence": [
                {"phase": "BRAKE_LINEAR"}, {"phase": "ACQUIRE_ANGULAR"}]},
            step_result=acquisition)


def test_up_to_right_exact_production_pair_uses_one_macro_transition(monkeypatch):
    import aero_ai_studio.training.gazebo_physics as module

    fake = _FakePhysics()
    fake.controller.last_command = gazebo_physics_twist("up")
    adapter = _adapter(fake, monkeypatch, gamma=.95)
    monkeypatch.setattr(module, "GazeboUpToRightControlExecutor", _FakeUpToRightExecutor)
    before_steps = fake.steps
    result = adapter.step("right")
    evidence = result.execution_evidence

    assert evidence["production_macro"] is True
    assert evidence["activation_pair"] == "UP_TO_RIGHT"
    assert evidence["transition_type"] == "LINEAR_TO_ROTATION"
    assert evidence["previous_action"] == "up" and evidence["agent_intent"] == "right"
    assert [row["phase"] for row in evidence["execution_phases"]] == [
        "BRAKE_LINEAR", "ACQUIRE_ANGULAR"]
    assert [row["phase"] for row in evidence["reward_chunks"]] == [
        "BRAKE_LINEAR", "BRAKE_LINEAR", "ACQUIRE_ANGULAR"]
    assert evidence["control_chunk_count"] == 3
    expected = sum(row["reward"] * .95 ** index
                   for index, row in enumerate(evidence["reward_chunks"]))
    assert evidence["macro_reward"] == pytest.approx(expected)
    assert result.elapsed_execution_time == pytest.approx(.3)
    assert result.elapsed_discount_units == pytest.approx(.3 / .1)
    assert fake.steps == before_steps + 1
    assert fake.acquisition_actions == []
    mapping = gazebo_physics_action_mapping()
    right_index = next(row["index"] for row in mapping if row["action"] == "right")
    assert right_index == 3
    replay_payload = ([0.] * 22, right_index, result.reward, [0.] * 22,
                      result.terminated or result.truncated,
                      result.elapsed_discount_units)
    assert len(replay_payload) == 6 and replay_payload[1] == 3


class _FakeLeftToUpExecutor(_FakeExecutor):
    chunks = 2

    def execute_plan(self, plan, *, on_braking_chunk=None):
        from aero_ai_studio.simulation.control_execution import ControlExecutionResult

        assert [phase.kind.value for phase in plan.phases] == [
            "BRAKE_ANGULAR", "ACQUIRE_LINEAR"]
        executed = []
        for _ in range(self.chunks):
            start = self.env.stepper.time
            before = dict(self.env.pose)
            self.env.stepper.time += 0.1
            row = {"simulation_start": start, "simulation_end": self.env.stepper.time,
                "pose_before": before, "pose_after": dict(self.env.pose),
                "collision_events": []}
            outcome = on_braking_chunk(row)
            assert outcome["collision"] is False
            executed.append({"linear": {"x": 0.0}, "angular": {"z": 0.0}})
        self.env.controller.last_command = {"linear": {"x": 0.0},
                                            "angular": {"z": 0.0}}
        acquisition = self.adapter.step("up")
        return ControlExecutionResult("up", ControlExecutionStatus.EXECUTED,
            plan.request.requested_command, plan.request.transition_type,
            executed_commands=tuple(executed + [plan.request.requested_command]),
            elapsed_simulation_time=self.env.stepper.time - 3.5,
            execution_evidence={"phase_evidence": [
                {"phase": "BRAKE_ANGULAR"}, {"phase": "ACQUIRE_LINEAR"}]},
            step_result=acquisition)


def test_left_to_up_exact_production_pair_uses_one_macro_decision(monkeypatch):
    import aero_ai_studio.training.gazebo_physics as module
    from aero_ai_studio.agents.base import Transition

    fake = _FakePhysics()
    fake.controller.last_command = gazebo_physics_twist("left")
    adapter = _adapter(fake, monkeypatch, gamma=0.95)
    monkeypatch.setattr(module, "GazeboLeftToUpControlExecutor",
                        _FakeLeftToUpExecutor)

    result = adapter.step("up")

    assert result.execution_evidence["production_macro"] is True
    assert result.execution_evidence["activation_pair"] == "LEFT_TO_UP"
    assert result.execution_evidence["transition_type"] == "ROTATION_TO_LINEAR"
    assert result.execution_evidence["previous_action"] == "left"
    assert result.execution_evidence["agent_intent"] == "up"
    assert [p["phase"] for p in result.execution_evidence["execution_phases"]] == [
        "BRAKE_ANGULAR", "ACQUIRE_LINEAR"]
    assert result.elapsed_execution_time == pytest.approx(0.3)
    assert result.elapsed_discount_units == pytest.approx(
        result.elapsed_execution_time / 0.1)
    chunks = result.execution_evidence["reward_chunks"]
    expected = sum(row["reward"] * 0.95 ** index
                   for index, row in enumerate(chunks))
    assert len(chunks) == result.execution_evidence["control_chunk_count"] == 3
    assert result.reward == pytest.approx(expected)
    assert fake.acquisition_actions == ["up"]
    assert fake.steps == 11  # one adapter decision; internal chunks did not step the task

    observation = adapter.get_agent_observation("sensor")
    transition = Transition(observation, "up", result.reward, observation, False,
                            result.elapsed_discount_units)
    agent = DQNAgent(batch_size=8, buffer_size=8)
    agent.learn(transition)
    stored = agent.buffer.items[0]
    up_index = next(row["index"] for row in gazebo_physics_action_mapping()
                    if row["action"] == "up")
    assert len(stored) == 6 and stored[1] == up_index == 0
    assert stored[2] == pytest.approx(result.reward)
    assert stored[5] == pytest.approx(result.elapsed_discount_units)


@pytest.mark.parametrize("previous", ["up", "right"])
def test_unverified_rotation_to_linear_pairs_remain_direct(monkeypatch, previous):
    fake = _FakePhysics()
    fake.controller.last_command = gazebo_physics_twist(previous)
    adapter = _adapter(fake, monkeypatch)
    result = adapter.step("up")
    assert result.execution_evidence is None
    assert result.elapsed_discount_units == pytest.approx(1.0)


def test_production_activation_pairs_are_exact_and_non_generic():
    assert R2L_VERIFIED_ACTION_PAIR == ("right", "down")
    assert LINEAR_REVERSAL_VERIFIED_ACTION_PAIR == ("down", "up")
    assert LINEAR_REVERSAL_UP_TO_DOWN_VERIFIED_ACTION_PAIR == ("up", "down")
    assert LINEAR_TO_ROTATION_DOWN_TO_LEFT_VERIFIED_ACTION_PAIR == ("down", "left")
    assert LINEAR_TO_ROTATION_UP_TO_RIGHT_VERIFIED_ACTION_PAIR == ("up", "right")


def test_exact_down_to_left_uses_one_production_macro_transition(monkeypatch):
    import aero_ai_studio.training.gazebo_physics as module
    from aero_ai_studio.simulation.action_mapping import gazebo_physics_action_mapping
    from aero_ai_studio.training.temporal import NOMINAL_DISCOUNT_TIME_UNIT_SECONDS
    from aero_ai_studio.agents.base import Transition

    class DownToLeftExecutor(_FakeExecutor):
        chunks = 2

        def execute_plan(self, plan, *, on_braking_chunk=None):
            phase_rows = [{"phase": "BRAKE_LINEAR"}, {"phase": "ACQUIRE_ANGULAR"}]
            executed = []
            for _ in range(self.chunks):
                start = self.env.stepper.time
                before = dict(self.env.pose)
                self.env.stepper.time += .1
                self.env.pose["x"] += .01
                row = {"simulation_start": start, "simulation_end": self.env.stepper.time,
                    "pose_before": before, "pose_after": dict(self.env.pose),
                    "collision_events": []}
                on_braking_chunk(row)
                executed.append({"linear": {"x": 0.}, "angular": {"z": 0.}})
            self.env.controller.last_command = {"linear": {"x": 0.}, "angular": {"z": 0.}}
            acquire = self.adapter.step("left")
            return ControlExecutionResult("left", ControlExecutionStatus.EXECUTED,
                plan.request.requested_command, plan.request.transition_type,
                executed_commands=tuple(executed + [plan.request.requested_command]),
                elapsed_simulation_time=self.env.stepper.time - 3.5,
                execution_evidence={"phase_evidence": phase_rows}, step_result=acquire)

    fake = _FakePhysics()
    fake.controller.last_command = gazebo_physics_twist("down")
    adapter = _adapter(fake, monkeypatch, gamma=.95)
    monkeypatch.setattr(module, "GazeboDownToLeftControlExecutor", DownToLeftExecutor)
    result = adapter.step("left")
    evidence = result.execution_evidence
    mapping = gazebo_physics_action_mapping()
    left_index = next(row["index"] for row in mapping if row["action"] == "left")

    assert evidence["production_macro"] is True
    assert evidence["activation_pair"] == "DOWN_TO_LEFT"
    assert evidence["transition_type"] == "LINEAR_TO_ROTATION"
    assert [row["phase"] for row in evidence["execution_phases"]] == [
        "BRAKE_LINEAR", "ACQUIRE_ANGULAR"]
    assert [row["phase"] for row in evidence["reward_chunks"]] == [
        "BRAKE_LINEAR", "BRAKE_LINEAR", "ACQUIRE_ANGULAR"]
    assert evidence["control_chunk_count"] == 3
    assert evidence["macro_reward"] == pytest.approx(sum(
        row["reward"] * .95 ** index
        for index, row in enumerate(evidence["reward_chunks"])))
    assert result.elapsed_execution_time == pytest.approx(.3)
    assert result.elapsed_discount_units == pytest.approx(
        result.elapsed_execution_time / NOMINAL_DISCOUNT_TIME_UNIT_SECONDS)
    assert fake.steps == 11
    assert fake.acquisition_actions == []  # only linear actions are recorded by this fixture
    payload = ("state", left_index, result.reward, "next", False,
        result.elapsed_discount_units)
    assert len(payload) == 6 and payload[1] == 2
    observation = adapter.get_agent_observation("sensor")
    agent = DQNAgent(batch_size=8, buffer_size=8)
    agent.learn(Transition(observation, "left", result.reward, observation,
        False, result.elapsed_discount_units))
    stored = agent.buffer.items[0]
    assert len(stored) == 6 and stored[1] == left_index
    assert stored[2] == pytest.approx(evidence["macro_reward"])
    assert stored[5] == pytest.approx(result.elapsed_discount_units)


@pytest.mark.parametrize(("previous", "requested"), [
    ("up", "left"), ("down", "right")])
def test_unverified_l2r_pairs_remain_direct(previous, requested, monkeypatch):
    fake = _FakePhysics()
    fake.controller.last_command = gazebo_physics_twist(previous)
    result = _adapter(fake, monkeypatch).step(requested)
    assert result.elapsed_discount_units == pytest.approx(1.)
    assert fake.telemetry["gazebo_dqn_training"].get("production_macro") is not True
    assert fake.telemetry["action_transition"]["simulation_duration"] == pytest.approx(.1)


def test_down_to_up_uses_one_production_macro_step_and_one_up_intent_transition(monkeypatch):
    import json
    import aero_ai_studio.training.gazebo_physics as module

    class ReversalExecutor(_FakeExecutor):
        def execute_plan(self, plan, *, on_braking_chunk=None):
            phases = [{"phase": "BRAKE_LINEAR", "completion_result": True},
                      {"phase": "ACQUIRE_LINEAR"}]
            executed = []
            for _ in range(self.chunks):
                start = self.env.stepper.time
                before = dict(self.env.pose)
                self.env.stepper.time += .1
                self.env.pose["x"] -= .01
                row = {"simulation_start": start, "simulation_end": self.env.stepper.time,
                       "pose_before": before, "pose_after": dict(self.env.pose),
                       "collision_events": [], "body_stopped_contract": {"pass": True}}
                on_braking_chunk(row)
                executed.append({"linear": {"x": 0.}, "angular": {"z": 0.}})
            self.env.controller.last_command = {"linear": {"x": 0.}, "angular": {"z": 0.}}
            acquisition = self.adapter.step("up")
            return ControlExecutionResult("up", ControlExecutionStatus.EXECUTED,
                plan.request.requested_command, plan.request.transition_type,
                executed_commands=tuple(executed + [plan.request.requested_command]),
                elapsed_simulation_time=self.env.stepper.time - 3.5,
                execution_evidence={"plan": plan.to_dict(),
                    "phase_evidence": [{"phase": "BRAKE_LINEAR", "completion_result": True},
                                       {"phase": "ACQUIRE_LINEAR"}]},
                step_result=acquisition)

    fake = _FakePhysics()
    fake.controller.last_command = {"linear": {"x": -.5}, "angular": {"z": 0.}}
    adapter = _adapter(fake, monkeypatch)
    monkeypatch.setattr(module, "GazeboLinearReversalControlExecutor", ReversalExecutor)
    steps_before = fake.steps
    result = adapter.step("up")
    evidence = result.execution_evidence
    transition_payload = ([0.] * 22, 0, result.reward, [0.] * 22,
                          result.terminated or result.truncated,
                          result.elapsed_discount_units)
    assert len(transition_payload) == 6
    assert transition_payload[1] == 0  # Mapping index 0 is UP.
    assert result.elapsed_execution_time == pytest.approx(.3)
    assert result.elapsed_discount_units == pytest.approx(
        result.elapsed_execution_time / .1)
    assert result.execution_evidence["transition_type"] == "LINEAR_REVERSAL"
    assert evidence["production_macro"] is True
    assert evidence["activation_pair"] == "DOWN_TO_UP"
    assert evidence["agent_intent"] == "up"
    assert evidence["previous_action"] == "down"
    assert evidence["control_chunk_count"] == 3
    assert [c["phase"] for c in evidence["reward_chunks"]] == [
        "BRAKE_LINEAR", "BRAKE_LINEAR", "ACQUIRE_LINEAR"]
    chunks = evidence["reward_chunks"]
    expected_reward = sum(c["reward"] * (adapter.gamma ** index)
                          for index, c in enumerate(chunks))
    assert evidence["macro_reward"] == pytest.approx(expected_reward)
    assert result.reward == pytest.approx(expected_reward)
    assert fake.acquisition_actions == ["up"]
    assert fake.steps == steps_before + 1
    assert fake.acquisition_actions.count("up") == 1
    json.dumps(evidence)


def test_up_to_down_linear_reversal_uses_one_production_macro(monkeypatch):
    import aero_ai_studio.training.gazebo_physics as module

    class ForwardReversalExecutor(_FakeExecutor):
        def execute_plan(self, plan, *, on_braking_chunk=None):
            assert plan.request.agent_intent == "down"
            assert plan.request.previous_command == gazebo_physics_twist("up")
            assert plan.request.requested_command == gazebo_physics_twist("down")
            assert [phase.kind.value for phase in plan.phases] == [
                "BRAKE_LINEAR", "ACQUIRE_LINEAR"]
            return super().execute_plan(plan, on_braking_chunk=on_braking_chunk)

    fake = _FakePhysics()
    fake.controller.last_command = {"linear": {"x": .5}, "angular": {"z": 0.}}
    adapter = _adapter(fake, monkeypatch)
    monkeypatch.setattr(module, "GazeboLinearReversalControlExecutor",
                        ForwardReversalExecutor)
    before_steps = fake.steps
    result = adapter.step("down")
    evidence = result.execution_evidence
    assert evidence["production_macro"] is True
    assert evidence["activation_pair"] == "UP_TO_DOWN"
    assert evidence["previous_action"] == "up"
    assert evidence["agent_intent"] == "down"
    activation = fake.telemetry["gazebo_dqn_training"]["control_executor_activation"]
    assert activation["active"] is True
    assert activation["verified_action_pair"] == ["up", "down"]
    assert evidence["control_chunk_count"] == 3
    assert result.elapsed_execution_time == pytest.approx(.3)
    assert result.elapsed_discount_units == pytest.approx(3.)
    assert fake.acquisition_actions == ["down"]
    assert fake.steps == before_steps + 1
    chunks = evidence["reward_chunks"]
    assert [chunk["phase"] for chunk in chunks] == [
        "BRAKE_LINEAR", "BRAKE_LINEAR", "ACQUIRE_LINEAR"]
    expected_reward = sum(chunk["reward"] * adapter.gamma ** index
        for index, chunk in enumerate(chunks))
    assert evidence["macro_reward"] == pytest.approx(expected_reward)
    assert result.reward == pytest.approx(expected_reward)
    replay_payload = ([0.] * 22, 1, result.reward, [0.] * 22,
        result.terminated or result.truncated, result.elapsed_discount_units)
    assert len(replay_payload) == 6 and replay_payload[1] == 1


def test_unverified_reversal_and_unrelated_commands_remain_direct(monkeypatch):
    for previous, requested in [("up", "up"), ("down", "down"),
                                ("up", "left"), ("down", "right"),
                                ("left", "right"), ("right", "left")]:
        fake = _FakePhysics()
        fake.controller.last_command = gazebo_physics_twist(previous)
        adapter = _adapter(fake, monkeypatch)
        result = adapter.step(requested)
        assert result.elapsed_discount_units == pytest.approx(1.)
        assert fake.telemetry["gazebo_dqn_training"].get(
            "control_executor_activation", {}).get("active", False) is False

