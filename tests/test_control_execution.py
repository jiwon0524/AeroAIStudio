import ast
import json
import math
from pathlib import Path

import pytest

from aero_ai_studio.simulation.control_execution import (
    ControlExecutionPhase,
    ControlExecutionRequest,
    ControlExecutionResult,
    ControlExecutionStatus,
    ControlPhaseKind,
    FeedbackCondition,
    plan_control_execution,
)


ZERO = {"linear": {"x": 0.0}, "angular": {"z": 0.0}}


def _request(previous, requested, transition, intent="down"):
    return ControlExecutionRequest(intent, previous, requested, transition)


@pytest.mark.parametrize("previous,requested,transition", [
    (ZERO, {"linear": {"x": 0.5}, "angular": {"z": 0.0}}, "OTHER"),
    (ZERO, {"linear": {"x": 0.0}, "angular": {"z": -0.8}}, "OTHER"),
    ({"linear": {"x": 0.5}, "angular": {"z": 0.0}},
     {"linear": {"x": 0.5}, "angular": {"z": 0.0}}, "STEADY_LINEAR"),
    ({"linear": {"x": 0.0}, "angular": {"z": -0.8}},
     {"linear": {"x": 0.0}, "angular": {"z": -0.8}}, "STEADY_ROTATION"),
])
def test_direct_safe_transitions_make_direct_plan(previous, requested, transition):
    plan = plan_control_execution(_request(previous, requested, transition))
    assert [phase.kind for phase in plan.phases] == [ControlPhaseKind.DIRECT]
    assert plan.phases[0].command == requested
    assert plan.phases[0].completion_conditions == (FeedbackCondition.COMMAND_ACCEPTED,)


@pytest.mark.parametrize("previous,requested", [
    ({"linear": {"x": 0.0}, "angular": {"z": -0.8}},
     {"linear": {"x": -0.5}, "angular": {"z": 0.0}}),
    ({"linear": {"x": 0.0}, "angular": {"z": 0.8}},
     {"linear": {"x": 0.5}, "angular": {"z": 0.0}}),
])
def test_rotation_to_linear_plans_angular_braking_then_linear_acquisition(previous, requested):
    plan = plan_control_execution(_request(previous, requested, "ROTATION_TO_LINEAR"))
    assert [phase.kind for phase in plan.phases] == [
        ControlPhaseKind.BRAKE_ANGULAR, ControlPhaseKind.ACQUIRE_LINEAR]
    assert plan.phases[0].completion_conditions == (FeedbackCondition.ANGULAR_VELOCITY_WITHIN_DEADBAND,)
    assert plan.phases[0].command is None
    assert plan.phases[1].command == requested
    assert plan.phases[1].completion_conditions == (
        FeedbackCondition.REQUESTED_LINEAR_DIRECTION_ESTABLISHED,)


@pytest.mark.parametrize("previous,requested", [
    ({"linear": {"x": 0.5}, "angular": {"z": 0.0}},
     {"linear": {"x": 0.0}, "angular": {"z": -0.8}}),
    ({"linear": {"x": -0.5}, "angular": {"z": 0.0}},
     {"linear": {"x": 0.0}, "angular": {"z": 0.8}}),
])
def test_linear_to_rotation_plans_linear_braking_then_angular_acquisition(previous, requested):
    plan = plan_control_execution(_request(previous, requested, "LINEAR_TO_ROTATION"))
    assert [phase.kind for phase in plan.phases] == [
        ControlPhaseKind.BRAKE_LINEAR, ControlPhaseKind.ACQUIRE_ANGULAR]
    assert plan.phases[0].completion_conditions == (FeedbackCondition.LINEAR_VELOCITY_WITHIN_DEADBAND,)
    assert plan.phases[1].completion_conditions == (
        FeedbackCondition.REQUESTED_ANGULAR_DIRECTION_ESTABLISHED,)


@pytest.mark.parametrize("previous,requested", [
    ({"linear": {"x": 0.5}, "angular": {"z": 0.0}},
     {"linear": {"x": -0.5}, "angular": {"z": 0.0}}),
    ({"linear": {"x": -0.5}, "angular": {"z": 0.0}},
     {"linear": {"x": 0.5}, "angular": {"z": 0.0}}),
])
def test_longitudinal_reversal_plans_braking_then_requested_linear(previous, requested):
    plan = plan_control_execution(_request(previous, requested, "LINEAR_REVERSAL"))
    assert [phase.kind for phase in plan.phases] == [
        ControlPhaseKind.BRAKE_LINEAR, ControlPhaseKind.ACQUIRE_LINEAR]


def test_rotation_reversal_plans_braking_then_requested_angular():
    plan = plan_control_execution(_request(
        {"linear": {"x": 0.0}, "angular": {"z": 0.8}},
        {"linear": {"x": 0.0}, "angular": {"z": -0.8}}, "ROTATION_REVERSAL"))
    assert [phase.kind for phase in plan.phases] == [
        ControlPhaseKind.BRAKE_ANGULAR, ControlPhaseKind.ACQUIRE_ANGULAR]


def test_planner_is_deterministic_and_does_not_invent_execution_bounds():
    request = _request(ZERO, {"linear": {"x": -0.5}, "angular": {"z": 0.0}}, "ROTATION_TO_LINEAR")
    first = plan_control_execution(request)
    second = plan_control_execution(request)
    assert first.to_dict() == second.to_dict()
    assert first.requires_execution_bound is True
    assert all(phase.max_control_ticks is None for phase in first.phases)
    assert all(phase.to_dict()["execution_bound_configured"] is False for phase in first.phases)


def test_request_plan_result_are_json_safe_for_replay_artifacts():
    request = _request(ZERO, {"linear": {"x": -0.5}, "angular": {"z": 0.0}},
                       "ROTATION_TO_LINEAR", "down")
    plan = plan_control_execution(request)
    result = ControlExecutionResult(
        agent_intent="down", status=ControlExecutionStatus.PLANNED,
        requested_command=request.requested_command, transition_type=request.transition_type,
        phases=plan.phases, elapsed_simulation_time=None)
    encoded = json.dumps({"request": request.to_dict(), "plan": plan.to_dict(), "result": result.to_dict()})
    assert json.loads(encoded)["request"]["agent_intent"] == "down"
    assert json.loads(encoded)["plan"]["phases"][0]["kind"] == "BRAKE_ANGULAR"
    assert json.loads(encoded)["result"]["status"] == "PLANNED"


def test_phase_can_carry_a_finite_control_tick_bound():
    phase = ControlExecutionPhase(
        ControlPhaseKind.BRAKE_ANGULAR,
        (FeedbackCondition.ANGULAR_VELOCITY_WITHIN_DEADBAND,),
        max_control_ticks=7)
    assert phase.to_dict()["max_control_ticks"] == 7
    assert phase.to_dict()["execution_bound_configured"] is True


def test_nonfinite_runtime_evidence_serializes_as_json_null():
    result = ControlExecutionResult(
        agent_intent="down", status=ControlExecutionStatus.PHYSICAL_CONTROL_FAILURE,
        requested_command={"linear": {"x": -.5}}, transition_type="ROTATION_TO_LINEAR",
        execution_evidence={"body_velocity": math.nan})
    payload = result.to_dict()
    assert payload["execution_evidence"]["body_velocity"] is None
    json.dumps(payload, allow_nan=False)


def test_contract_and_planner_do_not_import_gazebo_or_transport_modules():
    path = Path(__file__).parents[1] / "src/aero_ai_studio/simulation/control_execution.py"
    tree = ast.parse(path.read_text())
    imported = {
        alias.name for node in ast.walk(tree)
        if isinstance(node, ast.Import) for alias in node.names
    }
    imported.update(
        node.module for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    )
    assert not any(name.startswith(("aero_ai_studio.gazebo", "gz", "transport")) for name in imported)
