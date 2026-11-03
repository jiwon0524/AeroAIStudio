from __future__ import annotations
from dataclasses import asdict,dataclass,field
from enum import StrEnum
import math


class SimulationState(StrEnum):
    STARTING='STARTING'
    RUNNING='RUNNING'
    PAUSED='PAUSED'
    ERROR='ERROR'
    STOPPING='STOPPING'
    STOPPED='STOPPED'


class SensorTimeoutError(TimeoutError):pass


@dataclass(frozen=True)
class ObservationFrame:
    simulation_time: float
    sensor_timestamp: float
    sequence: int
    source: str
    front: float
    left: float
    right: float
    back: float
    goal_pose: tuple
    agent_pose: dict
    valid: bool=True
    age_ms: float=0.

    def to_dict(self):return asdict(self)

    def validate(self,previous_timestamp: float | None,max_age_ms: float):
        values=(self.simulation_time,self.sensor_timestamp,self.front,self.left,self.right,self.back)
        if not all(math.isfinite(v) for v in values) or min(self.front,self.left,self.right,self.back)<0:
            raise SensorTimeoutError('Invalid sensor frame values')
        if previous_timestamp is not None and self.sensor_timestamp<=previous_timestamp:
            raise SensorTimeoutError('Repeated/stale sensor timestamp')
        age=(self.simulation_time-self.sensor_timestamp)*1000
        if age < -2 or age>max_age_ms:raise SensorTimeoutError(f'Sensor age outside contract: {age:.3f}ms')


@dataclass(frozen=True)
class CollisionEvent:
    timestamp: float
    agent_entity: str
    other_entity: str
    contact_position: dict=field(default_factory=dict)
    normal: dict=field(default_factory=dict)
    source: str='gazebo_contact'
    agent_collision: str=''
    collision1: dict=field(default_factory=dict)
    collision2: dict=field(default_factory=dict)
    def to_dict(self):return asdict(self)


def parse_contacts(message: dict,agent_entity: str) -> list[CollisionEvent]:
    from aero_ai_studio.gazebo.transport import stamp
    result=[]
    for contact in message.get('contact',[]):
        a,b=contact.get('collision1',''),contact.get('collision2','')
        # gz-msgs10 Contact carries Entity messages, not string fields.
        # String support is retained for older saved fixtures/replays.
        a={'name':a} if isinstance(a,str) else a
        b={'name':b} if isinstance(b,str) else b
        an,bn=a.get('name',''),b.get('name','')
        if not an or not bn:raise ValueError('Contact collision Entity names required')
        own_a=agent_entity in an.split('::')
        own_b=agent_entity in bn.split('::')
        if not own_a and not own_b:continue
        other=bn if own_a else an
        # Support surface is not an obstacle collision.
        if own_a and own_b or {'ground','floor'} & set(other.split('::')):continue
        timestamp=stamp(contact) if 'stamp' in contact.get('header',{}) else stamp(message)
        if not math.isfinite(timestamp):raise ValueError('Non-finite contact timestamp')
        result.append(CollisionEvent(timestamp,agent_entity,other,
                     next(iter(contact.get('position',[])),{}),next(iter(contact.get('normal',[])),{}),
                     agent_collision=an if own_a else bn,collision1=a,collision2=b))
    return result
