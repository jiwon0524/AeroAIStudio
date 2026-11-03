from __future__ import annotations

import random
from collections import deque

from aero_ai_studio.scenario.models import ScenarioSpec
from aero_ai_studio.simulation.base import ACTIONS, Position, StepResult, SimulationCapabilities


class GridWorld:
    """Deterministic occupancy grid; metadata sensors are not simulated sensors."""
    capabilities = SimulationCapabilities(supports_sensors=True)
    def __init__(self, scenario: ScenarioSpec, max_steps: int = 200):
        scenario.validate()
        if scenario.world_mode != "synthetic":
            raise ValueError("Only Synthetic World can execute in V0.4")
        if scenario.mission not in ("obstacle_avoidance", "navigation"):
            raise ValueError("V0.4 executes obstacle avoidance/navigation only")
        if max_steps < 1:
            raise ValueError("Max steps must be positive")
        self.spec = scenario
        self.max_steps = max_steps
        self.rng = random.Random(scenario.seed)
        self.closed = False
        self.reward_version='legacy'
        self.reset()

    def reset(self, seed: int | None = None) -> Position:
        if seed is not None:
            self.rng.seed(seed)
        self.position = self.spec.start
        self.steps = 0
        self.done = False
        self._previous_snapshot = None
        self.closed = False
        self.distance_travelled = 0
        self.previous_action=None
        self.last_reward_components={}
        self.minimum_clearance=float('inf')
        self.goal=self.spec.goal
        self.danger_zones = {o.position for o in self.spec.objects if o.type == "danger_zone"}
        self.slow_zones = {o.position for o in self.spec.objects if o.type == "slow_zone"}
        self.obstacles = {o.position for o in self.spec.objects if o.type not in ("danger_zone", "slow_zone")}
        self.dynamic = [{"position": o.position, "movement": o.movement, "direction": o.direction} for o in self.spec.dynamic_objects]
        if self.spec.randomization.get('moving_speed'):
            for d in self.dynamic:d['speed']=self.rng.choice([1,1,2])
        flags = self.spec.randomization
        if flags.get("obstacle_position") or flags.get("obstacle_count"):
            cells = [(x, y) for x in range(self.spec.width) for y in range(self.spec.height)
                     if (x, y) not in (self.spec.start, self.spec.goal)]
            cells = [p for p in cells if p not in self.danger_zones | self.slow_zones | {d['position'] for d in self.dynamic}]
            count = len(self.obstacles)
            if flags.get("obstacle_count"):
                count = self.rng.randint(0, min(len(cells) // 4, max(1, count * 2)))
            for _ in range(100):
                self.obstacles = set(self.rng.sample(cells, count))
                if self._reachable():
                    break
            else:
                raise ValueError("Unable to generate reachable randomized scenario")
        if not self._reachable():
            raise ValueError("Goal is unreachable in this scenario")
        if flags.get('goal_position'):
            choices=[(x,y) for x in range(self.spec.width) for y in range(self.spec.height)
                     if (x,y) not in self.obstacles|self.danger_zones|{d['position'] for d in self.dynamic}|{self.spec.start}]
            self.rng.shuffle(choices)
            for p in choices:
                self.goal=p
                if self._reachable():break
        self._shortest_distance=self.shortest_path_distance()
        return self.position

    def _reachable(self) -> bool:
        return self.shortest_path_distance() is not None

    def shortest_path_distance(self) -> int | None:
        queue = deque([(self.spec.start, 0)])
        seen = {self.spec.start}
        while queue:
            (x, y), distance = queue.popleft()
            if (x, y) == self.goal:
                return distance
            for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
                p = (x + dx, y + dy)
                if self._inside(p) and p not in self.obstacles | self.danger_zones and p not in seen:
                    seen.add(p)
                    queue.append((p, distance + 1))
        return None

    def _inside(self, p: Position) -> bool:
        return 0 <= p[0] < self.spec.width and 0 <= p[1] < self.spec.height

    def _advance_dynamic(self, only_fast: bool=False) -> list[tuple[Position, Position]]:
        moves = []
        occupied = {d['position'] for d in self.dynamic}
        for item in self.dynamic:
            if only_fast and item.get('speed',1)<2:continue
            old = item['position']
            occupied.remove(old)
            candidates = [(1, 0), (-1, 0), (0, 1), (0, -1)]
            if item['movement'] == 'random':
                self.rng.shuffle(candidates)
            else:
                dx, dy = (item['direction'], 0) if item['movement'] == 'horizontal' else (0, item['direction'])
                candidates = [(dx, dy), (-dx, -dy)]
            target = old
            for index, (dx, dy) in enumerate(candidates):
                p = old[0] + dx, old[1] + dy
                if self._inside(p) and p not in self.obstacles | self.danger_zones | occupied and p != self.goal:
                    target = p
                    if item['movement'] != 'random' and index == 1:
                        item['direction'] *= -1
                    break
            item['position'] = target
            occupied.add(target)
            moves.append((old, target))
        return moves

    def action_evidence(self) -> dict:
        risks = {}
        for action, (dx, dy) in zip(ACTIONS, ((0, -1), (0, 1), (-1, 0), (1, 0))):
            p = self.position[0] + dx, self.position[1] + dy
            invalid = not self._inside(p) or p in self.obstacles
            dynamic_near = any(abs(p[0] - d['position'][0]) + abs(p[1] - d['position'][1]) <= 1 for d in self.dynamic)
            risks[action] = {"valid": not invalid, "collision_risk": "blocked" if invalid else "dynamic nearby" if dynamic_near else "clear",
                             "danger_zone": p in self.danger_zones}
        return risks

    def step(self, action: str) -> StepResult:
        if self.closed:
            raise RuntimeError('Environment is closed; reset first')
        if self.done:
            raise RuntimeError("Episode is finished; reset first")
        if action not in (*ACTIONS,'stop'):
            raise ValueError("Unknown action")
        self._previous_snapshot = self.get_state()
        dx, dy = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0),'stop':(0,0)}[action]
        x, y = self.position
        target = (x + dx, y + dy)
        self.steps += 1
        collision = not (0 <= target[0] < self.spec.width and 0 <= target[1] < self.spec.height) or target in self.obstacles
        moves = self._advance_dynamic()
        if any(d.get('speed',1)>1 for d in self.dynamic):
            # All moving objects share the second substep; intermediate cells remain collision candidates.
            moves += self._advance_dynamic(True)
        dynamic_collision = not collision and any(target == old or target == new or new == (x, y) for old, new in moves)
        old_distance = abs(x - self.goal[0]) + abs(y - self.goal[1])
        if not collision:
            self.position = target
            self.distance_travelled += abs(dx)+abs(dy)
        danger = not collision and not dynamic_collision and self.position in self.danger_zones
        collision = collision or dynamic_collision
        success = not collision and not danger and self.position == self.goal
        distance = abs(self.position[0] - self.goal[0]) + abs(self.position[1] - self.goal[1])
        reward = -100.0 if collision else -50.0 if danger else 100.0 if success else -1.0 + (2.0 if distance < old_distance else 0.0)
        if self.position in self.slow_zones and not (collision or danger or success):
            reward -= 3.0
        truncated = not collision and not danger and not success and self.steps >= self.max_steps
        self.done = collision or danger or success or truncated
        reason = "moving_obstacle_collision" if dynamic_collision else "collision" if collision else "danger_zone" if danger else "goal" if success else "timeout" if truncated else "moving"
        from aero_ai_studio.training.rewards import reward_components
        import math
        clearance=min([max(0.,math.dist(self.position,p)-.7) for p in self.obstacles|{d['position'] for d in self.dynamic}]+
                      [self.position[0]+.3,self.position[1]+.3,self.spec.width-self.position[0]-.7,self.spec.height-self.position[1]-.7])
        self.minimum_clearance=min(self.minimum_clearance,clearance)
        self.last_reward_components=reward_components(self._previous_snapshot,self.get_state(),reason,version=self.reward_version,
                previous_action=self.previous_action,action=action,clearance=clearance,
                ttc=self.get_agent_observation('sensor').sensor_state.get('time_to_collision') if self.reward_version=='v2' else None)
        reward=sum(self.last_reward_components.values())
        self.previous_action=action
        return StepResult(self.position, reward, collision or danger or success, truncated, reason)

    def get_observation(self) -> Position:
        return self.position

    def get_state(self) -> dict:
        return {"agent": list(self.position), "goal": list(self.goal),
                "obstacles": [list(p) for p in sorted(self.obstacles)],
                "width": self.spec.width, "height": self.spec.height, "steps": self.steps,
                "dynamic_objects": [{**d, 'position': list(d['position'])} for d in self.dynamic],
                "danger_zones": [list(p) for p in sorted(self.danger_zones)],
                "slow_zones": [list(p) for p in sorted(self.slow_zones)],
                "mission": self.spec.mission, "action_evidence": self.action_evidence()}

    def get_agent_observation(self, mode: str = 'basic', radius: int = 2):
        from aero_ai_studio.observation.provider import observe
        snapshot = self.get_state()
        snapshot['walls'] = [o.position for o in self.spec.objects if o.type == 'wall' and o.position in self.obstacles]
        return observe(snapshot, mode, radius, self._previous_snapshot)

    def render(self) -> dict:
        return self.get_state()

    def get_extended_observation(self) -> dict:
        x, y = self.position
        occupied = self.obstacles | {d['position'] for d in self.dynamic}
        nearest = min(occupied, key=lambda p: abs(x - p[0]) + abs(y - p[1]), default=None)
        radius = self.spec.observation.local_radius
        result = {'agent': list(self.position), 'goal': list(self.spec.goal),
                  'local_grid': [[int((x + dx, y + dy) in occupied or not self._inside((x + dx, y + dy)))
                                  for dx in range(-radius, radius + 1)] for dy in range(-radius, radius + 1)]}
        if self.spec.observation.include_nearest_obstacle:
            result['nearest_obstacle_distance'] = abs(x - nearest[0]) + abs(y - nearest[1]) if nearest else None
            result['obstacle_direction'] = [nearest[0] - x, nearest[1] - y] if nearest else None
        if self.spec.observation.include_dynamic_positions:
            result['moving_obstacle_positions'] = [list(d['position']) for d in self.dynamic]
        return result

    def get_metrics(self) -> dict:
        return {'steps': self.steps, 'distance': self.distance_travelled,
                'shortest_path_distance': self._shortest_distance, 'done': self.done,
                'minimum_clearance':self.minimum_clearance if self.minimum_clearance!=float('inf') else None,
                'reward_components':dict(self.last_reward_components)}

    def close(self) -> None:
        self.closed = True
