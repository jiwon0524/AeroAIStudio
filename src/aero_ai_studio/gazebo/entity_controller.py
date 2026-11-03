from __future__ import annotations
import math
from aero_ai_studio.gazebo.transport import stamp

VELOCITY_DIRECTION_EPSILON=0.02


def directed_velocity_zero_crossing(samples,previous_sign,requested_sign,*,epsilon=VELOCITY_DIRECTION_EPSILON,
                                    interval_start=None,interval_end=None):
    """Find an ordered previous -> deadband/zero -> requested body velocity transition.

    The epsilon suppresses sign decisions near zero, while interpolation uses
    the actual adjacent finite-difference values. A significant return to the
    previous direction after requested-direction motion invalidates the event.
    """
    rows=[]
    for sample in samples or ():
        try:
            timestamp=float(sample['simulation_timestamp'])
            velocity=float(sample['forward_velocity'])
        except (KeyError,TypeError,ValueError):
            return {'valid':False,'time':None,'requested_index':None,'deadband_samples':0}
        if not math.isfinite(timestamp) or not math.isfinite(velocity):
            return {'valid':False,'time':None,'requested_index':None,'deadband_samples':0}
        rows.append((timestamp,velocity))
    if (previous_sign not in (-1,1) or requested_sign not in (-1,1) or
        previous_sign==requested_sign or len(rows)<2 or
        any(b[0]<=a[0] for a,b in zip(rows,rows[1:]))):
        return {'valid':False,'time':None,'requested_index':None,'deadband_samples':0}
    if rows[0][1]*previous_sign<=epsilon:
        return {'valid':False,'time':None,'requested_index':None,'deadband_samples':0}
    requested_index=next((i for i,(_,v) in enumerate(rows)
                          if v*requested_sign>epsilon),None)
    if requested_index is None:
        return {'valid':False,'time':None,'requested_index':None,'deadband_samples':0}
    # Once the requested direction becomes significant, it must not bounce
    # back to significant previous-direction velocity later in the interval.
    if any(v*previous_sign>epsilon for _,v in rows[requested_index+1:]):
        return {'valid':False,'time':None,'requested_index':requested_index,'deadband_samples':0}
    crossing_time=None
    # Keep the last raw zero crossing before significant requested-direction
    # motion. Intermediate velocities inside the epsilon deadband are neutral,
    # not evidence that the transition failed.
    for i in range(1,requested_index+1):
        t0,v0=rows[i-1];t1,v1=rows[i]
        if v0*v1<0:
            crossing_time=t0+(-v0/(v1-v0))*(t1-t0)
        elif v0==0 and v1!=0:
            crossing_time=t0
        elif v1==0 and v0!=0:
            crossing_time=t1
    if crossing_time is None:
        return {'valid':False,'time':None,'requested_index':requested_index,'deadband_samples':0}
    if ((interval_start is not None and crossing_time<float(interval_start)-1e-9) or
        (interval_end is not None and crossing_time>float(interval_end)+1e-9)):
        return {'valid':False,'time':crossing_time,'requested_index':requested_index,'deadband_samples':0}
    deadband_samples=sum(abs(v)<=epsilon for _,v in rows[1:requested_index])
    return {'valid':True,'time':crossing_time,'requested_index':requested_index,
            'deadband_samples':deadband_samples}


def summarize_world_pose_history(samples,start_time,end_time):
    """Summarize actual timestamped model poses; velocity is finite difference."""
    duration=float(end_time)-float(start_time)
    ordered=sorted((dict(sample) for sample in samples
                    if all(key in sample for key in ('simulation_timestamp','world_x','world_y','world_yaw'))),
                   key=lambda row:float(row['simulation_timestamp']))
    deduplicated=[]
    for sample in ordered:
        if deduplicated and abs(float(sample['simulation_timestamp'])-
                                float(deduplicated[-1]['simulation_timestamp']))<1e-9:
            deduplicated[-1]=sample
        else:deduplicated.append(sample)
    deduplicated=[row for row in deduplicated
                  if float(start_time)-.002<=float(row['simulation_timestamp'])<=float(end_time)+.002]
    timestamps=[float(row['simulation_timestamp']) for row in deduplicated]
    intervals=[];velocities=[];angular_velocities=[]
    for a,b in zip(deduplicated,deduplicated[1:]):
        dt=float(b['simulation_timestamp'])-float(a['simulation_timestamp'])
        if dt<=0:continue
        dx=float(b['world_x'])-float(a['world_x']);dy=float(b['world_y'])-float(a['world_y'])
        yaw=float(a['world_yaw'])
        forward=dx*math.cos(yaw)+dy*math.sin(yaw)
        velocity=forward/dt
        yaw_delta=math.atan2(math.sin(float(b['world_yaw'])-float(a['world_yaw'])),
                             math.cos(float(b['world_yaw'])-float(a['world_yaw'])))
        intervals.append({'start_timestamp':float(a['simulation_timestamp']),
            'end_timestamp':float(b['simulation_timestamp']),'forward_displacement':forward})
        velocities.append({'simulation_timestamp':(float(a['simulation_timestamp'])+
            float(b['simulation_timestamp']))/2,'forward_velocity':velocity,
            'body_forward_velocity':velocity,'sample_interval':dt,
            'interval_start':float(a['simulation_timestamp']),
            'interval_end':float(b['simulation_timestamp'])})
        angular_velocity=yaw_delta/dt
        angular_velocities.append({'simulation_timestamp':(float(a['simulation_timestamp'])+
            float(b['simulation_timestamp']))/2,'angular_velocity':angular_velocity,
            'body_angular_velocity':angular_velocity,'sample_interval':dt,
            'interval_start':float(a['simulation_timestamp']),
            'interval_end':float(b['simulation_timestamp'])})
    max_gap=max((b-a for a,b in zip(timestamps,timestamps[1:])),default=None)
    fresh=bool(timestamps and timestamps[-1]>=float(end_time)-.01 and
               timestamps[-1]<=float(end_time)+.002 and timestamps[0]<=float(start_time)+.01)
    dense=bool(fresh and len(timestamps)>=3 and duration>0 and max_gap is not None and
               max_gap<=max(.02,duration*.5))
    crossing=False;crossing_time=None
    if len(velocities)>=2:
        first=float(velocities[0]['forward_velocity']);last=float(velocities[-1]['forward_velocity'])
        first_sign=1 if first>VELOCITY_DIRECTION_EPSILON else -1 if first< -VELOCITY_DIRECTION_EPSILON else 0
        last_sign=1 if last>VELOCITY_DIRECTION_EPSILON else -1 if last< -VELOCITY_DIRECTION_EPSILON else 0
        if first_sign and last_sign and first_sign!=last_sign:
            crossing_evidence=directed_velocity_zero_crossing(velocities,first_sign,last_sign,
                interval_start=start_time,interval_end=end_time)
            crossing=bool(crossing_evidence['valid'])
            crossing_time=crossing_evidence['time']
    return {'world_pose_history_available':bool(deduplicated),
        'world_pose_sample_count':len(deduplicated),
        'world_pose_sample_timestamps':timestamps,
        'world_pose_x':[float(row['world_x']) for row in deduplicated],
        'world_pose_y':[float(row['world_y']) for row in deduplicated],
        'world_pose_yaw':[float(row['world_yaw']) for row in deduplicated],
        'world_pose_receive_sequences':[row.get('receive_sequence') for row in deduplicated],
        'world_forward_displacement_samples':intervals,
        'world_velocity_sample_count':len(velocities),
        'world_forward_velocity_samples':velocities,
        'body_forward_velocity_samples':velocities,
        'world_angular_velocity_sample_count':len(angular_velocities),
        'world_angular_velocity_samples':angular_velocities,
        'body_angular_velocity_samples':angular_velocities,
        'world_start_forward_velocity':None if not velocities else velocities[0]['forward_velocity'],
        'world_end_forward_velocity':None if not velocities else velocities[-1]['forward_velocity'],
        'body_start_forward_velocity':None if not velocities else velocities[0]['forward_velocity'],
        'body_end_forward_velocity':None if not velocities else velocities[-1]['forward_velocity'],
        'world_start_angular_velocity':None if not angular_velocities else angular_velocities[0]['angular_velocity'],
        'world_end_angular_velocity':None if not angular_velocities else angular_velocities[-1]['angular_velocity'],
        'body_start_angular_velocity':None if not angular_velocities else angular_velocities[0]['angular_velocity'],
        'body_end_angular_velocity':None if not angular_velocities else angular_velocities[-1]['angular_velocity'],
        'world_start_velocity_interval':None if not intervals else [intervals[0]['start_timestamp'],intervals[0]['end_timestamp']],
        'world_end_velocity_interval':None if not intervals else [intervals[-1]['start_timestamp'],intervals[-1]['end_timestamp']],
        'world_velocity_zero_crossing':crossing,
        'world_velocity_zero_crossing_time':crossing_time,
        'world_pose_history_fresh':fresh,'world_pose_history_dense_enough':dense,
        'world_pose_history_max_gap':max_gap,
        'world_pose_source':'/world/<world>/pose/info Pose_V agent pose in world frame',
        'world_pose_timestamp_source':'Pose_V.header.stamp simulation time; contained Pose.header.stamp fallback',
        'world_pose_velocity_method':'finite_difference_adjacent_pose_samples',
        'world_pose_velocity_note':'adjacent world-pose finite difference projected onto prior body-forward axis; distinct from wheel-joint odometry'}


class GazeboEntityController:
    def __init__(self,transport,world,name='agent_marker',step_size=1.):
        self.transport,self.world,self.name,self.step_size=transport,world,name,step_size
        self.pose_topic=f'/world/{world}/pose/info'
        self.poses={}
        self.last_pose_frame_timestamp=None
        transport.subscribe(self.pose_topic,'Pose_V')

    def scene(self):return self.transport.request(f'/world/{self.world}/scene/info','Empty','Scene',{})

    def read_poses(self,min_time=-1,timeout=5):
        # SceneBroadcaster publishes model world poses, including static models.
        # Require a fresh frame for motion; never fall back to cached agent poses.
        frame=self.transport.sample(self.pose_topic,min_time,timeout)
        poses={p['name']:p for p in frame.get('pose',[]) if p.get('name')}
        self.poses=poses
        selected=poses.get(self.name)
        # Harmonic SceneBroadcaster puts the simulation stamp on Pose_V itself;
        # contained Pose messages are not required to carry their own stamp.
        self.last_pose_frame_timestamp=stamp(frame)
        if self.last_pose_frame_timestamp==0 and selected is not None:
            self.last_pose_frame_timestamp=stamp({'header':selected.get('header',{})})
        return poses

    def pose_history_after(self,sequence,start_time,end_time):
        """Read already-buffered Pose_V frames for this entity; advances no physics."""
        if not hasattr(self.transport,'messages_after'):
            return []
        frames=self.transport.messages_after(self.pose_topic,sequence,timeout=0)
        result=[]
        for receive_sequence,frame in frames:
            frame_timestamp=stamp(frame)
            for pose in frame.get('pose',[]):
                if pose.get('name')!=self.name:continue
                timestamp=frame_timestamp or stamp({'header':pose.get('header',{})})
                if float(start_time)-.002<=timestamp<=float(end_time)+.002:
                    decoded=self.decode_pose(pose)
                    result.append({'receive_sequence':receive_sequence,'simulation_timestamp':timestamp,'world_x':decoded['x'],
                                   'world_y':decoded['y'],'world_yaw':decoded['yaw']})
        return result

    @staticmethod
    def decode_pose(pose):
        p,q=pose.get('position',{}),pose.get('orientation',{})
        x,y,z,w=(float(q.get(k,1. if k=='w' else 0.)) for k in ('x','y','z','w'))
        return {'x':float(p.get('x',0)),'y':float(p.get('y',0)),'z':float(p.get('z',0)),
                'orientation':q,'yaw':math.atan2(2*(w*z+x*y),1-2*(y*y+z*z))}

    def get_pose(self,min_time=-1,timeout=5):
        poses=self.read_poses(min_time,timeout)
        if self.name not in poses:raise RuntimeError('Expected Gazebo entity not found in pose frame: '+self.name)
        return self.decode_pose(poses[self.name])

    def spawn_agent(self,sdf: str | None=None):
        if sdf:
            self.transport.request(f'/world/{self.world}/create','EntityFactory','Boolean',{'sdf':sdf,'name':self.name,'allow_renaming':False})
        return self.get_pose()

    def reset_agent_pose(self,x,y,z=.25,yaw=0.):
        x,y,z,yaw=map(float,(x,y,z,yaw))
        if not self.name or not all(math.isfinite(v) for v in (x,y,z,yaw)):
            raise ValueError('set_pose requires an entity name and finite position/yaw')
        payload={'name':self.name,'position':{'x':x,'y':y,'z':z},
                 'orientation':{'x':0.,'y':0.,'z':math.sin(yaw/2),'w':math.cos(yaw/2)}}
        self.last_pose_request={'payload':payload,'accepted':False}
        result=self.transport.request(f'/world/{self.world}/set_pose','Pose','Boolean',payload)
        if result.get('data') is not True:raise RuntimeError('Gazebo rejected set_pose for '+self.name)
        self.last_pose_request.update(accepted=True,response=result)
        return result

    def apply_action(self,action):
        action={'forward':'up','backward':'down'}.get(action.lower(),action.lower())
        delta={'up':(0,-1),'down':(0,1),'left':(-1,0),'right':(1,0),'stop':(0,0)}
        if action not in delta:raise ValueError('Unsupported Gazebo action')
        pose=self.get_pose()
        dx,dy=delta[action]
        self.reset_agent_pose(pose['x']+dx*self.step_size,pose['y']+dy*self.step_size,pose['z'],0.)

    def stop_agent(self):
        # Kinematic entity has no velocity command to latch; STOP holds its current pose.
        self.apply_action('stop')
