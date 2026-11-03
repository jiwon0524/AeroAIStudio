from __future__ import annotations
import math
from aero_ai_studio.observation.models import Observation, Cell, direction

BLOCKERS = {int(Cell.WALL), int(Cell.STATIC_OBSTACLE), int(Cell.MOVING_OBSTACLE), int(Cell.DANGER)}
DIRECTIONS = ('N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW', 'HERE')


class BasicStateEncoder:
    name = 'basic'
    def encode(self, observation: Observation) -> tuple:
        return observation.agent_position


class CanonicalStateEncoder:
    name='canonical'
    def encode(self,observation: Observation) -> tuple:
        from aero_ai_studio.observation.canonical import CanonicalSensorObservation,ContinuousDistanceDiscretizer
        return ContinuousDistanceDiscretizer().encode(CanonicalSensorObservation.from_observation(observation))


class CompactStateEncoder:
    name = 'compact'
    def encode(self, observation: Observation) -> tuple:
        if observation.mode == 'basic':
            raise ValueError('Compact encoder requires LOCAL or SENSOR observation')
        dx = observation.goal_position[0] - observation.agent_position[0]
        dy = observation.goal_position[1] - observation.agent_position[1]
        s = observation.sensor_state
        def bucket(distance: float) -> str:
            return 'BLOCKED' if distance <= 1 else 'NEAR' if distance <= 3 else 'CLEAR'
        distances = []
        grid = observation.local_grid
        for name, (vx, vy) in zip(('front', 'left', 'right', 'back'), ((0,-1),(-1,0),(1,0),(0,1))):
            if s:
                distance = s[name + '_distance']
            else:
                r = len(grid) // 2
                distance = next((i for i in range(1, r+1) if grid[r+vy*i][r+vx*i] in BLOCKERS), 99)
            distances.append(bucket(distance))
        moving = (s.get('moving_obstacle_distance') is not None and s['moving_obstacle_distance'] <= 3) if s else any(int(Cell.MOVING_OBSTACLE) in row for row in grid)
        danger = bool(s.get('danger_zone')) if s else any(int(Cell.DANGER) in row for row in grid)
        return direction(dx, dy), *distances, bool(moving), danger


def observation_vector(observation: Observation) -> list[float]:
    """Fixed 22-vector, distances clipped to 10 cells; no map dimensions or optimal paths."""
    encoded = CompactStateEncoder().encode(observation)
    goal, *rest = encoded
    vector = [float(goal == d) for d in DIRECTIONS]
    vector += [{'CLEAR': 1.0, 'NEAR': 0.5, 'BLOCKED': 0.0}[b] for b in rest[:4]]
    vector += [float(rest[4]), float(rest[5])]
    s = observation.sensor_state
    vector += [min(10, s.get(n + '_distance', 10)) / 10 for n in ('front','back','left','right')]
    vector += [min(30, s.get('goal_distance', math.dist(observation.agent_position, observation.goal_position))) / 30]
    vector += [min(10, s.get('moving_obstacle_distance') or 10) / 10,
               {'APPROACHING': -1., 'LEAVING': 1., 'STATIC': 0., 'UNKNOWN': 0.}[s.get('moving_obstacle_relative_motion', 'UNKNOWN')]]
    return vector
