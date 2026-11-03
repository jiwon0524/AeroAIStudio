from __future__ import annotations

from dataclasses import asdict, dataclass, field

ENVIRONMENTS = ("indoor", "warehouse", "urban", "forest", "open_field")
MISSIONS = ("obstacle_avoidance", "target_tracking", "navigation", "landing", "reconnaissance")
WEATHERS = ("clear", "rain", "fog", "snow", "strong_wind")
OBJECTS = ("person", "vehicle", "drone", "wall", "tree", "container", "custom_obstacle", "static_obstacle", "danger_zone", "slow_zone")
RANDOMIZATIONS = ("obstacle_position", "obstacle_count", "speed", "lighting", "sensor_noise", "gps_error", "weather",'goal_position','moving_speed')


@dataclass
class SceneObject:
    type: str
    position: tuple[int, int]


@dataclass
class DynamicObject:
    type: str = "moving_obstacle"
    position: tuple[int, int] = (5, 5)
    movement: str = "horizontal"
    direction: int = 1


@dataclass
class ObservationSpec:
    mode: str = "basic"
    local_radius: int = 1
    include_nearest_obstacle: bool = True
    include_dynamic_positions: bool = True


@dataclass
class ScenarioSpec:
    name: str = "warehouse_test_01"
    world_mode: str = "synthetic"
    environment: str = "warehouse"
    mission: str = "obstacle_avoidance"
    weather: str = "clear"
    width: int = 20
    height: int = 20
    start: tuple[int, int] = (0, 0)
    goal: tuple[int, int] = (19, 19)
    objects: list[SceneObject] = field(default_factory=list)
    sensors: list[str] = field(default_factory=lambda: ["camera", "lidar", "gps"])
    randomization: dict[str, bool] = field(default_factory=dict)
    seed: int = 42
    schema_version: str = "0.4"
    world_type: str = "grid_world"
    difficulty: str = "normal"
    dynamic_objects: list[DynamicObject] = field(default_factory=list)
    observation: ObservationSpec = field(default_factory=ObservationSpec)

    @property
    def grid_size(self) -> tuple[int, int]:
        return self.width, self.height

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("Scenario name is required")
        if self.world_mode not in ("synthetic", "korea_real", "hybrid"):
            raise ValueError("Invalid world mode")
        if self.environment not in ENVIRONMENTS or self.mission not in MISSIONS or self.weather not in WEATHERS:
            raise ValueError("Invalid environment, mission or weather")
        if not 4 <= self.width <= 100 or not 4 <= self.height <= 100:
            raise ValueError("Grid dimensions must be between 4 and 100")
        if self.schema_version != "0.4" or self.world_type != "grid_world":
            raise ValueError("Unsupported scenario schema/world type")
        if self.difficulty not in ("easy", "normal", "hard", "extreme"):
            raise ValueError("Invalid difficulty")
        if self.observation.mode not in ("basic", "extended", "local", "sensor", "full_debug") or not 1 <= self.observation.local_radius <= 5:
            raise ValueError("Invalid observation specification")
        if any(o.movement not in ("horizontal", "vertical", "random") or o.direction not in (-1, 1)
               or o.type != "moving_obstacle" for o in self.dynamic_objects):
            raise ValueError("Invalid dynamic object")
        for position in [self.start, self.goal] + [o.position for o in self.objects + self.dynamic_objects]:
            if len(position) != 2 or any(type(v) is not int for v in position):
                raise ValueError("Positions must contain two integers")
            if not 0 <= position[0] < self.width or not 0 <= position[1] < self.height:
                raise ValueError("Position outside grid")
        if self.start == self.goal:
            raise ValueError("Start and goal must differ")
        if any(o.type not in OBJECTS for o in self.objects):
            raise ValueError("Invalid object type")
        if any(o.position in (self.start, self.goal) for o in self.objects):
            raise ValueError("Obstacle overlaps start or goal")
        if len({o.position for o in self.objects}) != len(self.objects):
            raise ValueError("Duplicate obstacle position")
        occupied = [o.position for o in self.objects + self.dynamic_objects]
        if len(set(occupied)) != len(occupied) or any(o.position in (self.start, self.goal) for o in self.dynamic_objects):
            raise ValueError("Objects overlap")
        if any(s not in ("camera", "lidar", "gps") for s in self.sensors):
            raise ValueError("Invalid sensor")
        if any(k not in RANDOMIZATIONS or type(v) is not bool for k, v in self.randomization.items()):
            raise ValueError("Invalid randomization")

    def to_dict(self) -> dict:
        return {**asdict(self), "grid_size": [self.width, self.height]}

    @classmethod
    def from_dict(cls, data: dict) -> ScenarioSpec:
        values = dict(data)
        version = values.get("schema_version", "0.3")
        if version not in ("0.3", "0.4"):
            raise ValueError(f"Unsupported scenario schema {version}")
        values["schema_version"] = "0.4"
        grid = values.pop("grid_size", None)
        if grid is not None:
            if ("width" in values and values["width"] != grid[0]) or ("height" in values and values["height"] != grid[1]):
                raise ValueError("grid_size and width/height disagree")
            values["width"], values["height"] = grid
        values["dynamic_objects"] = [DynamicObject(**{**o, "position": tuple(o["position"])}) for o in values.get("dynamic_objects", [])]
        values["observation"] = ObservationSpec(**values.get("observation", {}))
        values["objects"] = [SceneObject(o["type"], tuple(o["position"])) for o in values.get("objects", [])]
        for key in ("start", "goal"):
            if key in values:
                values[key] = tuple(values[key])
        result = cls(**values)
        result.validate()
        return result
