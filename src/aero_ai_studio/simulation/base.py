from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from aero_ai_studio.observation.models import Observation

ACTIONS = ("up", "down", "left", "right")
Position = tuple[int, int]


@dataclass
class StepResult:
    observation: Position
    reward: float
    terminated: bool
    truncated: bool
    reason: str
    elapsed_execution_time: float | None = None
    elapsed_discount_units: float = 1.0
    execution_evidence: dict | None = None


class PhysicalControlFailure(RuntimeError):
    """A simulated physical command was rejected by body-response validation.

    This is distinct from a simulator/service failure. The command has already
    traversed the physical environment path, so callers can persist its actual
    validator and command evidence without treating it as infrastructure loss.
    """

    training_status = "physical_control_failure"
    failure_category = "physical_control_failure"

    def __init__(self, reason: str, *, evidence: dict):
        super().__init__(reason)
        self.reason = reason
        self.evidence = dict(evidence)

    def to_dict(self) -> dict:
        return {"category": self.failure_category, "reason": self.reason,
                "evidence": self.evidence}


@dataclass(frozen=True)
class SimulationCapabilities:
    supports_real_time: bool = False
    supports_3d: bool = False
    supports_dynamic_objects: bool = True
    supports_sensors: bool = False


@runtime_checkable
class SimulationEnvironment(Protocol):
    capabilities: SimulationCapabilities
    def reset(self, seed: int | None = None) -> Position: ...
    def step(self, action: str) -> StepResult: ...
    def get_observation(self) -> Position: ...
    def get_agent_observation(self, mode: str = 'basic', radius: int = 2) -> Observation: ...
    def get_state(self) -> dict: ...
    def render(self) -> dict: ...
    def get_metrics(self) -> dict: ...
    def close(self) -> None: ...


# Compatibility name, a single contract rather than a duplicate interface.
TrainingEnvironment = SimulationEnvironment
