from __future__ import annotations
import math
from aero_ai_studio.observation.models import Observation, ObservationMode, Cell, direction


def observe(snapshot: dict, mode: str = 'basic', radius: int = 2, previous: dict | None = None) -> Observation:
    mode = 'sensor' if mode == 'extended' else mode.lower()
    ObservationMode(mode)
    x, y = snapshot['agent']
    gx, gy = snapshot['goal']
    if mode == 'basic':
        return Observation(mode, (x, y), (gx, gy))
    width, height = snapshot['width'], snapshot['height']
    blocked = {tuple(p) for p in snapshot['obstacles']}
    walls = {tuple(p) for p in snapshot.get('walls', [])}
    moving = [tuple(d['position']) for d in snapshot.get('dynamic_objects', [])]
    danger = {tuple(p) for p in snapshot.get('danger_zones', [])}
    slow = {tuple(p) for p in snapshot.get('slow_zones', [])}
    occupied = blocked | set(moving)
    def cell(px: int, py: int) -> int:
        p = px, py
        if not 0 <= px < width or not 0 <= py < height or p in walls:
            return int(Cell.WALL)
        if p in blocked:
            return int(Cell.STATIC_OBSTACLE)
        if p in moving:
            return int(Cell.MOVING_OBSTACLE)
        if p == (gx, gy):
            return int(Cell.GOAL)
        if p in danger:
            return int(Cell.DANGER)
        if p in slow:
            return int(Cell.SLOW_ZONE)
        if p == (x, y):
            return int(Cell.AGENT)
        return int(Cell.EMPTY)
    local = [[cell(x + dx, y + dy) for dx in range(-radius, radius + 1)] for dy in range(-radius, radius + 1)]
    sensors: dict = {}
    for name, (dx, dy) in {'front': (0, -1), 'back': (0, 1), 'left': (-1, 0), 'right': (1, 0)}.items():
        distance = 1
        while 0 <= x + dx * distance < width and 0 <= y + dy * distance < height and (x + dx * distance, y + dy * distance) not in occupied | danger:
            distance += 1
        sensors[name + '_distance'] = distance
    nearest = min(sorted(occupied), key=lambda p: math.dist((x, y), p), default=None)
    dynamic_index = min(range(len(moving)), key=lambda i: math.dist((x, y), moving[i]), default=None)
    dynamic = moving[dynamic_index] if dynamic_index is not None else None
    motion = 'UNKNOWN'
    if dynamic is not None and previous and dynamic_index < len(previous.get('dynamic_objects', [])):
        old = previous['dynamic_objects'][dynamic_index]['position']
        delta = math.dist((x, y), dynamic) - math.dist(previous['agent'], old)
        motion = 'APPROACHING' if delta < -1e-6 else 'LEAVING' if delta > 1e-6 else 'STATIC'
    sensors.update(goal_distance=math.dist((x, y), (gx, gy)), goal_direction=direction(gx - x, gy - y),
                   goal_delta=[gx - x, gy - y],
                   nearest_obstacle_distance=math.dist((x, y), nearest) if nearest else None,
                   nearest_obstacle_direction=direction(nearest[0] - x, nearest[1] - y) if nearest else None,
                   moving_obstacle_distance=math.dist((x, y), dynamic) if dynamic else None,
                   moving_obstacle_direction=direction(dynamic[0] - x, dynamic[1] - y) if dynamic else None,
                   moving_obstacle_relative_motion=motion,
                   danger_zone=any(abs(px-x) + abs(py-y) <= 1 for px, py in danger))
    from aero_ai_studio.observation.prediction import predict_motion
    prediction=predict_motion((x,y),moving,previous)
    sensors['prediction']=prediction
    sensors['moving_object_relative_motion']=prediction['motion']
    sensors['time_to_collision']=prediction['ttc']
    from aero_ai_studio.observation.canonical import CanonicalSensorObservation
    sensors['canonical']=CanonicalSensorObservation.from_observation(Observation('sensor',(x,y),(gx,gy),sensor_state=sensors)).to_dict()
    full = [[cell(px, py) for px in range(width)] for py in range(height)] if mode == 'full_debug' else []
    # LOCAL only carries local cells and goal; SENSOR carries idealized range features.
    return Observation(mode, (x, y), (gx, gy), local if mode in ('local', 'full_debug') else [],
                       sensors if mode != 'local' else {}, full)
