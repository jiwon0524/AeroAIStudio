from __future__ import annotations
import random
from aero_ai_studio.scenario.models import ScenarioSpec, SceneObject, DynamicObject
from aero_ai_studio.simulation.grid_world import GridWorld

PRESETS = {"easy": (0.05, 1, 0), "normal": (0.10, 2, 3), "hard": (0.18, 4, 8), "extreme": (0.25, 6, 15)}


def generate_scenario(size: int = 20, seed: int = 42, difficulty: str = "normal",
                      density: float | None = None, moving_count: int | None = None,
                      danger_count: int | None = None) -> ScenarioSpec:
    if difficulty not in PRESETS or not 4 <= size <= 100:
        raise ValueError("Invalid difficulty or grid size")
    defaults = PRESETS[difficulty]
    density = defaults[0] if density is None else density
    moving_count = defaults[1] if moving_count is None else moving_count
    danger_count = defaults[2] if danger_count is None else danger_count
    if not 0 <= density <= 0.6 or min(moving_count, danger_count) < 0:
        raise ValueError("Invalid generator counts/density")
    rng = random.Random(seed)
    # Keep one seeded monotone path free from static hazards; dynamics can cross it.
    path, x, y = {(0, 0)}, 0, 0
    while (x, y) != (size - 1, size - 1):
        if x < size - 1 and (y == size - 1 or rng.random() < 0.5):
            x += 1
        else:
            y += 1
        path.add((x, y))
    available = [(x, y) for x in range(size) for y in range(size) if (x, y) not in path]
    rng.shuffle(available)
    count = int(size * size * density)
    if count + danger_count + moving_count > len(available):
        raise ValueError("Too many objects for this grid and a reachable path")
    objects = [SceneObject("static_obstacle", available.pop()) for _ in range(count)]
    objects += [SceneObject("danger_zone", available.pop()) for _ in range(danger_count)]
    dynamic = [DynamicObject(position=available.pop(), movement=rng.choice(["horizontal", "vertical", "random"])) for _ in range(moving_count)]
    spec = ScenarioSpec(name=f"generated_{difficulty}_{seed}", width=size, height=size, goal=(size - 1, size - 1),
                        objects=objects, dynamic_objects=dynamic, seed=seed, difficulty=difficulty)
    GridWorld(spec).close()
    return spec
