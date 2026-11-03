from pathlib import Path
from typing import Protocol, runtime_checkable
from dataclasses import dataclass
import math
from aero_ai_studio.observation.models import Observation
from aero_ai_studio.simulation.base import Position


@dataclass(frozen=True)
class Transition:
    observation: Observation
    action: str
    reward: float
    next_observation: Observation
    done: bool
    elapsed_discount_units: float = 1.0

    def __post_init__(self) -> None:
        units = float(self.elapsed_discount_units)
        if not math.isfinite(units) or units <= 0:
            raise ValueError("elapsed_discount_units must be finite and positive")
        object.__setattr__(self, "elapsed_discount_units", units)


@runtime_checkable
class Agent(Protocol):
    supports_training: bool
    supports_continuous_actions: bool
    supports_images: bool
    supports_sensors: bool
    artifact_name: str
    def reset(self) -> None: ...
    def select_action(self, observation: Observation, epsilon: float = 0) -> str: ...
    def learn(self, transition: Transition) -> None: ...
    def get_decision_info(self) -> dict: ...
    def get_metadata(self) -> dict: ...
    def save(self, path: Path) -> None: ...
    @classmethod
    def load(cls, path: Path): ...
