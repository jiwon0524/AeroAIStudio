"""Backend-neutral contracts and pure planning for physical command execution.

This module describes intent and plans only. It does not publish commands, wait
for feedback, or advance a simulator. An executor must supply finite bounds
before executing any phase whose ``max_control_ticks`` is unset.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Any, Mapping, Protocol


def _json_safe(value):
    if isinstance(value, Enum):
        return value.value
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    raise TypeError(f"Unsupported execution evidence value: {type(value).__name__}")


class ControlPhaseKind(str, Enum):
    DIRECT = "DIRECT"
    BRAKE_ANGULAR = "BRAKE_ANGULAR"
    ACQUIRE_LINEAR = "ACQUIRE_LINEAR"
    BRAKE_LINEAR = "BRAKE_LINEAR"
    ACQUIRE_ANGULAR = "ACQUIRE_ANGULAR"


class FeedbackCondition(str, Enum):
    COMMAND_ACCEPTED = "COMMAND_ACCEPTED"
    LINEAR_VELOCITY_WITHIN_DEADBAND = "LINEAR_VELOCITY_WITHIN_DEADBAND"
    ANGULAR_VELOCITY_WITHIN_DEADBAND = "ANGULAR_VELOCITY_WITHIN_DEADBAND"
    REQUESTED_LINEAR_DIRECTION_ESTABLISHED = "REQUESTED_LINEAR_DIRECTION_ESTABLISHED"
    REQUESTED_ANGULAR_DIRECTION_ESTABLISHED = "REQUESTED_ANGULAR_DIRECTION_ESTABLISHED"


class ControlExecutionStatus(str, Enum):
    PLANNED = "PLANNED"
    EXECUTED = "EXECUTED"
    PHYSICAL_CONTROL_FAILURE = "PHYSICAL_CONTROL_FAILURE"
    INFRASTRUCTURE_FAILURE = "INFRASTRUCTURE_FAILURE"
    COLLISION = "COLLISION"
    TASK_TERMINAL = "TASK_TERMINAL"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True)
class ControlExecutionRequest:
    """Agent intent plus the adjacent actuator commands and their transition."""

    agent_intent: str
    previous_command: Mapping[str, Any]
    requested_command: Mapping[str, Any]
    transition_type: str

    def to_dict(self) -> dict:
        return {
            "agent_intent": self.agent_intent,
            "previous_command": _json_safe(self.previous_command),
            "requested_command": _json_safe(self.requested_command),
            "transition_type": self.transition_type,
        }


@dataclass(frozen=True)
class ControlExecutionPhase:
    kind: ControlPhaseKind
    completion_conditions: tuple[FeedbackCondition, ...]
    # None means the backend must choose its braking/neutral command; it does
    # not mean to hold the previous command.
    command: Mapping[str, Any] | None = None
    # Phase 3 must provide a finite policy-derived bound before execution.
    max_control_ticks: int | None = None

    def to_dict(self) -> dict:
        return {
            "kind": self.kind.value,
            "completion_conditions": [condition.value for condition in self.completion_conditions],
            "command": None if self.command is None else _json_safe(self.command),
            "command_source": "backend_braking" if self.command is None else "requested_command",
            "max_control_ticks": self.max_control_ticks,
            "execution_bound_configured": self.max_control_ticks is not None,
        }


@dataclass(frozen=True)
class ControlExecutionPlan:
    request: ControlExecutionRequest
    phases: tuple[ControlExecutionPhase, ...]

    @property
    def requires_execution_bound(self) -> bool:
        return any(phase.max_control_ticks is None for phase in self.phases)

    def to_dict(self) -> dict:
        return {
            "request": self.request.to_dict(),
            "phases": [phase.to_dict() for phase in self.phases],
            "requires_execution_bound": self.requires_execution_bound,
        }


@dataclass(frozen=True)
class ControlExecutionResult:
    agent_intent: str
    status: ControlExecutionStatus
    requested_command: Mapping[str, Any]
    transition_type: str
    executed_commands: tuple[Mapping[str, Any], ...] = ()
    phases: tuple[ControlExecutionPhase, ...] = ()
    elapsed_simulation_time: float | None = None
    failure_category: str | None = None
    reason: str | None = None
    validator_evidence: Mapping[str, Any] | None = None
    execution_evidence: Mapping[str, Any] | None = None
    # Runtime hand-off to the training adapter; deliberately excluded from
    # serialized execution evidence.
    step_result: Any = field(default=None, compare=False, repr=False)

    def to_dict(self) -> dict:
        return {
            "agent_intent": self.agent_intent,
            "status": self.status.value,
            "requested_command": _json_safe(self.requested_command),
            "executed_commands": [_json_safe(command) for command in self.executed_commands],
            "transition_type": self.transition_type,
            "phases": [phase.to_dict() for phase in self.phases],
            "elapsed_simulation_time": self.elapsed_simulation_time,
            "failure_category": self.failure_category,
            "reason": self.reason,
            "validator_evidence": (None if self.validator_evidence is None
                                    else _json_safe(self.validator_evidence)),
            "execution_evidence": (None if self.execution_evidence is None
                                   else _json_safe(self.execution_evidence)),
        }


class ControlExecutor(Protocol):
    """Backend contract; Phase 2 defines the interface but no executor."""

    def plan(self, request: ControlExecutionRequest) -> ControlExecutionPlan: ...

    def execute_plan(self, plan: ControlExecutionPlan) -> ControlExecutionResult: ...


def plan_control_execution(request: ControlExecutionRequest) -> ControlExecutionPlan:
    """Create a deterministic feedback-oriented phase plan without executing it.

    Transition labels follow ``classify_physics_command_transition`` today,
    while this planner accepts only serializable contracts and imports no
    simulator/controller implementation.
    """
    requested = request.requested_command
    transition = request.transition_type

    if transition == "ROTATION_TO_LINEAR":
        phases = (
            ControlExecutionPhase(
                ControlPhaseKind.BRAKE_ANGULAR,
                (FeedbackCondition.ANGULAR_VELOCITY_WITHIN_DEADBAND,),
            ),
            ControlExecutionPhase(
                ControlPhaseKind.ACQUIRE_LINEAR,
                (FeedbackCondition.REQUESTED_LINEAR_DIRECTION_ESTABLISHED,),
                command=requested,
            ),
        )
    elif transition == "LINEAR_TO_ROTATION":
        phases = (
            ControlExecutionPhase(
                ControlPhaseKind.BRAKE_LINEAR,
                (FeedbackCondition.LINEAR_VELOCITY_WITHIN_DEADBAND,),
            ),
            ControlExecutionPhase(
                ControlPhaseKind.ACQUIRE_ANGULAR,
                (FeedbackCondition.REQUESTED_ANGULAR_DIRECTION_ESTABLISHED,),
                command=requested,
            ),
        )
    elif transition == "LINEAR_REVERSAL":
        phases = (
            ControlExecutionPhase(
                ControlPhaseKind.BRAKE_LINEAR,
                (FeedbackCondition.LINEAR_VELOCITY_WITHIN_DEADBAND,),
            ),
            ControlExecutionPhase(
                ControlPhaseKind.ACQUIRE_LINEAR,
                (FeedbackCondition.REQUESTED_LINEAR_DIRECTION_ESTABLISHED,),
                command=requested,
            ),
        )
    elif transition == "ROTATION_REVERSAL":
        phases = (
            ControlExecutionPhase(
                ControlPhaseKind.BRAKE_ANGULAR,
                (FeedbackCondition.ANGULAR_VELOCITY_WITHIN_DEADBAND,),
            ),
            ControlExecutionPhase(
                ControlPhaseKind.ACQUIRE_ANGULAR,
                (FeedbackCondition.REQUESTED_ANGULAR_DIRECTION_ESTABLISHED,),
                command=requested,
            ),
        )
    else:
        phases = (
            ControlExecutionPhase(
                ControlPhaseKind.DIRECT,
                (FeedbackCondition.COMMAND_ACCEPTED,),
                command=requested,
            ),
        )
    return ControlExecutionPlan(request=request, phases=phases)
