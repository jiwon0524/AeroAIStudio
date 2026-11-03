"""Small, backend-neutral helpers for variable-duration RL transitions."""
from __future__ import annotations

from dataclasses import dataclass
import math


NOMINAL_DISCOUNT_TIME_UNIT_SECONDS = 0.1


@dataclass(frozen=True)
class MacroReward:
    reward: float
    elapsed_execution_time: float
    elapsed_discount_units: float
    terminal: bool


class MacroRewardAccumulator:
    """Accumulate chunk rewards using their offset within one macro action.

    The reward for each chunk is discounted by the amount of execution time
    that elapsed before that chunk. This helper does not decide which events
    are terminal; callers pass ``terminal=True`` when their existing task
    semantics say the macro action has ended.
    """

    def __init__(self, gamma: float, nominal_time_unit_seconds: float = NOMINAL_DISCOUNT_TIME_UNIT_SECONDS):
        gamma = float(gamma)
        nominal_time_unit_seconds = float(nominal_time_unit_seconds)
        if not math.isfinite(gamma) or not 0.0 <= gamma <= 1.0:
            raise ValueError("gamma must be finite and in [0, 1]")
        if not math.isfinite(nominal_time_unit_seconds) or nominal_time_unit_seconds <= 0.0:
            raise ValueError("nominal_time_unit_seconds must be finite and positive")
        self.gamma = gamma
        self.nominal_time_unit_seconds = nominal_time_unit_seconds
        self._reward = 0.0
        self._elapsed_execution_time = 0.0
        self._terminal = False

    def add_chunk(self, reward: float, elapsed_execution_time: float, *, terminal: bool = False) -> None:
        if self._terminal:
            raise ValueError("cannot add a reward chunk after a terminal chunk")
        reward = float(reward)
        elapsed_execution_time = float(elapsed_execution_time)
        if not math.isfinite(reward):
            raise ValueError("chunk reward must be finite")
        if not math.isfinite(elapsed_execution_time) or elapsed_execution_time <= 0.0:
            raise ValueError("elapsed_execution_time must be finite and positive")

        elapsed_before_units = self._elapsed_execution_time / self.nominal_time_unit_seconds
        self._reward += (self.gamma ** elapsed_before_units) * reward
        self._elapsed_execution_time += elapsed_execution_time
        self._terminal = bool(terminal)

    def result(self) -> MacroReward:
        return MacroReward(
            reward=self._reward,
            elapsed_execution_time=self._elapsed_execution_time,
            elapsed_discount_units=self._elapsed_execution_time / self.nominal_time_unit_seconds,
            terminal=self._terminal,
        )
