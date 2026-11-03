from __future__ import annotations
from dataclasses import asdict, dataclass
import math
from aero_ai_studio.observation.models import Observation


@dataclass(frozen=True)
class CanonicalSensorObservation:
    goal_direction: str
    goal_distance: float
    front_clearance: float
    left_clearance: float
    right_clearance: float
    back_clearance: float
    moving_obstacle_distance: float | None = None
    moving_obstacle_direction: str | None = None
    moving_object_relative_motion: str = 'UNKNOWN'
    time_to_collision: float | None = None
    collision_imminent: bool = False
    source: str = 'grid'
    units: str = 'm'

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_observation(cls, observation: Observation):
        s=observation.sensor_state
        if 'canonical' in s:
            return cls(**s['canonical'])
        if not s:
            raise ValueError('Safety/canonical sensors require SENSOR observation')
        # Grid ranges are center-to-center: subtract obstacle half-cell and agent radius.
        c={n+'_clearance':max(0.,float(s[n+'_distance'])-.7) for n in ('front','left','right','back')}
        return cls(s['goal_direction'],s['goal_distance'],**c,
                   moving_obstacle_distance=s.get('moving_obstacle_distance'),
                   moving_obstacle_direction=s.get('moving_obstacle_direction'),
                   moving_object_relative_motion=s.get('moving_obstacle_relative_motion','UNKNOWN'),
                   time_to_collision=s.get('time_to_collision'),
                   collision_imminent=min(c.values())<.35,source='grid')


class ContinuousDistanceDiscretizer:
    def distance(self, value: float) -> str:
        if not math.isfinite(value) or value < 0:
            raise ValueError('Distance must be finite and nonnegative')
        return 'VERY_NEAR' if value<.4 else 'NEAR' if value<1.1 else 'MEDIUM' if value<3 else 'FAR' if value<6 else 'CLEAR'

    def encode(self, canonical: CanonicalSensorObservation) -> tuple:
        return (canonical.goal_direction,*(self.distance(getattr(canonical,n+'_clearance')) for n in ('front','left','right','back')),
                'HIGH' if canonical.collision_imminent else 'MEDIUM' if canonical.time_to_collision is not None and canonical.time_to_collision<2 else 'LOW')
