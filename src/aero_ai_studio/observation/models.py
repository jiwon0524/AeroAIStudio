from __future__ import annotations
from dataclasses import asdict, dataclass, field
from enum import IntEnum, StrEnum


class ObservationMode(StrEnum):
    BASIC = 'basic'
    LOCAL = 'local'
    SENSOR = 'sensor'
    FULL_DEBUG = 'full_debug'


class Cell(IntEnum):
    EMPTY = 0
    WALL = 1
    STATIC_OBSTACLE = 2
    MOVING_OBSTACLE = 3
    GOAL = 4
    DANGER = 5
    SLOW_ZONE = 6
    AGENT = 7


@dataclass(frozen=True)
class Observation:
    mode: str
    agent_position: tuple[int, int]
    goal_position: tuple[int, int]
    local_grid: list[list[int]] = field(default_factory=list)
    sensor_state: dict = field(default_factory=dict)
    full_grid: list[list[int]] = field(default_factory=list)
    schema_version: str = '0.5'

    def to_dict(self) -> dict:
        return asdict(self)


def direction(dx: float, dy: float) -> str:
    if dx == 0 and dy == 0:
        return 'HERE'
    return ('N' if dy < 0 else 'S' if dy > 0 else '') + ('W' if dx < 0 else 'E' if dx > 0 else '')
