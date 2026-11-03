from __future__ import annotations
import math
from aero_ai_studio.observation.canonical import CanonicalSensorObservation
from aero_ai_studio.observation.models import Observation,direction
from aero_ai_studio.gazebo.transport import stamp
from aero_ai_studio.gazebo.contracts import ObservationFrame,SensorTimeoutError


class RangeSensorProvider:
    def __init__(self,transport,world,goal,timeout=5,*,max_sensor_age_ms=20,physics=False,topic=None):
        self.transport,self.topic,self.goal,self.timeout=transport,f'/aero/{world}/scan',goal,timeout
        self.latest=None
        self.topic=topic or self.topic
        self.previous_timestamp=None
        self.sequence=0
        self.max_sensor_age_ms=max_sensor_age_ms
        self.physics=physics
        self.frame=None
        self.epoch_receive_sequence=None

    def start(self):self.transport.subscribe(self.topic,'LaserScan')
    def stop(self):self.latest=None

    def reset_epoch(self):
        """Start a new freshness epoch after Gazebo simulation time rewinds."""
        self.previous_timestamp=None
        self.latest=None
        self.frame=None
        self.epoch_receive_sequence=(self.transport.cursor(self.topic)
                                     if hasattr(self.transport,'cursor') else None)

    def get_range_observation(self,pose,min_time=0,simulation_time=None):
        minimum=max(min_time,self.previous_timestamp+1e-9 if self.previous_timestamp is not None else min_time)
        try:
            if self.epoch_receive_sequence is not None and hasattr(self.transport,'sample_after_sequence'):
                scan,sequence=self.transport.sample_after_sequence(self.topic,self.epoch_receive_sequence,
                    min_time=minimum,
                    max_time=None if simulation_time is None else simulation_time+self.max_sensor_age_ms/1000.,
                    timeout=self.timeout)
                self.epoch_receive_sequence=None
            else:
                scan=self.transport.sample(self.topic,minimum,self.timeout)
        except TimeoutError as error:raise SensorTimeoutError(str(error)) from error
        ranges=scan.get('ranges',[])
        if len(ranges)!=4:raise RuntimeError('Expected four world-aligned LaserScan ranges')
        maximum=float(scan.get('range_max',30))
        ranges=[maximum if str(v).lower() in ('inf','infinity') else float(v) for v in ranges]
        if any(not math.isfinite(v) or v<0 for v in ranges):raise RuntimeError('Invalid LaserScan measurement')
        sample_time=stamp(scan)
        sim_time=simulation_time if simulation_time is not None else max(min_time,sample_time)
        indices=(0,1,3,2) if self.physics else (3,2,0,1)
        front,left,right,back=(max(0.,ranges[i]-.2) for i in indices)
        frame=ObservationFrame(sim_time,sample_time,self.sequence+1,'gazebo_lidar',front,left,right,back,self.goal,dict(pose),
                               age_ms=(sim_time-sample_time)*1000)
        frame.validate(self.previous_timestamp,self.max_sensor_age_ms)
        self.previous_timestamp=sample_time
        self.sequence+=1
        self.frame=frame
        dx,dy=self.goal[0]-pose['x'],self.goal[1]-pose['y']
        if self.physics:
            yaw=pose.get('yaw',0.)
            bx,by=math.cos(yaw)*dx+math.sin(yaw)*dy,-math.sin(yaw)*dx+math.cos(yaw)*dy
            dx,dy=-by,-bx
        # Lidar beam height is above the body. Convert ray origin distances to body-edge clearances.
        c=CanonicalSensorObservation(direction(dx,dy),math.hypot(dx,dy),
                front,left,right,back,
                collision_imminent=min(ranges)<=.21,source='gazebo_lidar')
        s={n+'_distance':getattr(c,n+'_clearance')+.7 for n in ('front','left','right','back')}
        s.update(goal_direction=c.goal_direction,goal_distance=c.goal_distance,goal_delta=[dx,dy],
                 canonical=c.to_dict(),nearest_obstacle_distance=min(ranges),nearest_obstacle_direction=None,
                 moving_obstacle_distance=None,moving_obstacle_direction=None,moving_obstacle_relative_motion='UNKNOWN',
                 moving_object_relative_motion='UNKNOWN',danger_zone=False,sample_time=sample_time,
                 simulation_timestamp=sim_time,sensor_timestamp=sample_time,sequence=self.sequence,source='gazebo_lidar',
                 observation_frame=frame.to_dict())
        self.latest=Observation('sensor',(math.floor(pose['x']),math.floor(pose['y'])),(math.floor(self.goal[0]),math.floor(self.goal[1])),sensor_state=s)
        return self.latest

    def get_latest_observation(self):return self.latest
    def get_sensor_status(self):return {'status':'Available' if self.latest else 'Waiting','topic':self.topic,'backend':'gpu_lidar'}
    def get_lidar_scan(self):return self.transport.sample(self.topic,timeout=self.timeout)
    def get_camera_frame(self):return None
