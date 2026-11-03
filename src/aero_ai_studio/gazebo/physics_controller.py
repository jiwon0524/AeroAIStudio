import math
from aero_ai_studio.gazebo.entity_controller import (
    GazeboEntityController,
    VELOCITY_DIRECTION_EPSILON,
    directed_velocity_zero_crossing,
)
from aero_ai_studio.simulation.action_mapping import (
    classify_physics_command_transition,
    gazebo_physics_twist,
)


def _sample_interval_union(samples,start,end):
    """Return exact represented finite-difference coverage clipped to [start,end]."""
    try:start=float(start);end=float(end)
    except (TypeError,ValueError):return False,0.
    if not math.isfinite(start) or not math.isfinite(end) or end<=start:return False,0.
    intervals=[]
    for sample in samples or ():
        try:
            a=float(sample['interval_start']);b=float(sample['interval_end'])
            midpoint=float(sample['simulation_timestamp']);dt=float(sample['sample_interval'])
        except (KeyError,TypeError,ValueError):return False,0.
        if not all(math.isfinite(value) for value in (a,b,midpoint,dt)) or b<=a or dt<=0:
            return False,0.
        if abs((b-a)-dt)>1e-9 or abs(midpoint-(a+b)/2)>1e-9:return False,0.
        left=max(start,a);right=min(end,b)
        if right>left:intervals.append((left,right))
    intervals.sort()
    if not intervals:return False,0.
    cursor=start;covered=0.
    for left,right in intervals:
        if left>cursor+1e-9:return False,covered
        if right>cursor:
            covered+=right-max(left,cursor)
            cursor=right
    return cursor>=end-1e-9,covered

class PhysicsEntityController(GazeboEntityController):
    def __init__(self,transport,world,name='simple_agent',step_size=1.,linear_speed=.5,angular_speed=.8,topic=None):
        super().__init__(transport,world,name,step_size)
        self.linear_speed,self.angular_speed=linear_speed,angular_speed
        self.topic=topic or f'/aero/{world}/cmd_vel'
        self.last_command={}
        self.last_published_command=None
        self.publish_sequence=0

    def apply_action(self,action):
        action=action.lower()
        aliases={'forward':'up','backward':'down','turn_left':'left','turn_right':'right'}
        action=aliases.get(action,action)
        self.last_command=({'linear':{'x':0.},'angular':{'z':0.}} if action=='stop' else
                           gazebo_physics_twist(action,self.linear_speed,self.angular_speed))
        self.transport.publish(self.topic,'Twist',self.last_command)
        self.last_published_command={
            'linear':{'x':float(self.last_command['linear']['x'])},
            'angular':{'z':float(self.last_command['angular']['z'])}}
        self.publish_sequence+=1

    def stop_agent(self):self.apply_action('stop')

    def validate_pose(self,before,after,dt,collision=False,odometry_before=None,odometry_after=None,
                      odometry_history=None,simulation_start_time=None,simulation_end_time=None,
                      previous_command=None,world_pose_history=None):
        distance=math.hypot(after['x']-before['x'],after['y']-before['y'])
        signed_yaw=math.atan2(math.sin(after['yaw']-before['yaw']),math.cos(after['yaw']-before['yaw']))
        yaw=abs(signed_yaw)
        forward=(after['x']-before['x'])*math.cos(before['yaw'])+(after['y']-before['y'])*math.sin(before['yaw'])
        linear=self.last_command.get('linear',{}).get('x',0)
        angular=self.last_command.get('angular',{}).get('z',0)
        expected=abs(linear)*dt
        rotation=abs(angular)*dt
        odometry_available=odometry_before is not None and odometry_after is not None
        odometry_fresh=False
        predicted_linear=predicted_yaw=None
        linear_response=angular_response=None
        integration_method='unavailable';sample_times=[];sample_count=0
        points=[]
        discrepancy_classification='odometry_unavailable'
        max_distance=expected*2+.03
        max_yaw=rotation*2+.05
        command_integrated_forward=linear*dt
        command_integrated_yaw=angular*dt
        previous_linear=float((previous_command or {}).get('linear',{}).get('x',0.))
        previous_angular=float((previous_command or {}).get('angular',{}).get('z',0.))
        previous_motion_sign=1 if previous_linear>.02 else -1 if previous_linear<-.02 else 0
        requested_motion_sign=1 if linear>.02 else -1 if linear<-.02 else 0
        command_mode_transition=classify_physics_command_transition(previous_command,self.last_command)
        command_reversal_detected=bool(previous_motion_sign and requested_motion_sign and
                                       previous_motion_sign!=requested_motion_sign)
        odometry_zero_crossing=False
        odometry_zero_crossing_time=None
        odometry_final_direction_ok=(linear==0)
        wheel_integral_direction_ok=(linear==0)
        world_body_transient_direction=False
        reversal_transient_valid=False
        reversal_body_history_available=bool(world_pose_history and
            int(world_pose_history.get('world_pose_sample_count',0))>0 and
            world_pose_history.get('world_pose_sample_timestamps'))
        reversal_body_history_fresh=bool((world_pose_history or {}).get('world_pose_history_fresh',False))
        reversal_body_history_dense=bool((world_pose_history or {}).get('world_pose_history_dense_enough',False))
        reversal_body_start_direction_ok=False
        reversal_body_zero_crossing=False
        reversal_body_zero_crossing_time=None
        reversal_body_deadband_sample_count=0
        reversal_body_end_direction_ok=False
        reversal_net_translation_below_normal_minimum=False
        reversal_cancellation_valid=False
        linear_to_rotation_transient_valid=False
        linear_to_rotation_forward_decay_valid=False
        linear_to_rotation_angular_direction_valid=False
        linear_to_rotation_angular_established=False
        linear_to_rotation_angular_sustained=False
        linear_to_rotation_body_angular_bounded=False
        linear_to_rotation_wheel_linear_stopped=False
        linear_to_rotation_wheel_angular_started_neutral=False
        linear_to_rotation_wheel_angular_valid=False
        linear_to_rotation_wheel_integral_valid=False
        linear_to_rotation_body_history_available=bool((world_pose_history or {}).get(
            'world_pose_history_available',False))
        linear_to_rotation_body_history_fresh=bool((world_pose_history or {}).get(
            'world_pose_history_fresh',False))
        linear_to_rotation_body_history_dense=bool((world_pose_history or {}).get(
            'world_pose_history_dense_enough',False))
        linear_to_rotation_body_history_interval_ok=False
        linear_to_rotation_tail_sample_count=0
        linear_to_rotation_forward_remaining_ratio=None
        linear_to_rotation_forward_decay_fraction=None
        linear_to_rotation_angular_tail_window=None
        linear_to_rotation_angular_first_established_time=None
        linear_to_rotation_angular_sustained_duration=0.
        linear_to_rotation_angular_sustained_min_duration=0.
        linear_to_rotation_angular_tail_fresh=False
        linear_to_rotation_angular_sustained_sample_count=0
        rotation_to_linear_transient_valid=False
        rotation_to_linear_body_history_available=bool((world_pose_history or {}).get(
            'world_pose_history_available',False))
        rotation_to_linear_body_history_fresh=bool((world_pose_history or {}).get(
            'world_pose_history_fresh',False))
        rotation_to_linear_body_history_dense=bool((world_pose_history or {}).get(
            'world_pose_history_dense_enough',False))
        rotation_to_linear_body_history_interval_ok=False
        rotation_to_linear_start_angular_velocity=None
        rotation_to_linear_end_angular_velocity=None
        rotation_to_linear_angular_remaining_ratio=None
        rotation_to_linear_angular_decay_fraction=None
        rotation_to_linear_angular_decay_valid=False
        rotation_to_linear_angular_stopped=False
        rotation_to_linear_angular_tail_coverage_seconds=0.
        rotation_to_linear_angular_tail_coverage_valid=False
        rotation_to_linear_angular_tail_sustained=False
        rotation_to_linear_start_forward_velocity=None
        rotation_to_linear_end_forward_velocity=None
        rotation_to_linear_requested_direction_established=False
        rotation_to_linear_final_direction_ok=False
        world_direction_raw_ok=False
        current_reversal_command_valid=False
        if odometry_available:
            v0=float(odometry_before['linear_x']);v1=float(odometry_after['linear_x'])
            w0=float(odometry_before['angular_z']);w1=float(odometry_after['angular_z'])
            t0=float(odometry_before['timestamp']);t1=float(odometry_after['timestamp'])
            points=[{'timestamp':t0,'linear_x':v0,'angular_z':w0},*(odometry_history or ()),
                    {'timestamp':t1,'linear_x':v1,'angular_z':w1}]
            unique={float(p['timestamp']):p for p in points}
            points=sorted(unique.values(),key=lambda p:float(p['timestamp']))
            sample_times=[float(p['timestamp']) for p in points];sample_count=len(points)
            interval_duration=max(0.,t1-t0)
            gaps=[b-a for a,b in zip(sample_times,sample_times[1:]) if b>a]
            max_gap=max(gaps,default=interval_duration)
            freshness_tolerance=.01
            odometry_fresh=(simulation_start_time is not None and simulation_end_time is not None and
                t0>=simulation_start_time-freshness_tolerance and t0<=simulation_start_time+.002 and
                t1>=simulation_end_time-freshness_tolerance and t1<=simulation_end_time+.002 and
                abs(interval_duration-dt)<=.01)
            def converges(before_velocity,after_velocity,target):
                old_error=abs(before_velocity-target);new_error=abs(after_velocity-target)
                return new_error<=.02 if old_error<=.02 else new_error<old_error-1e-4
            linear_response=converges(v0,v1,linear)
            angular_response=converges(w0,w1,angular)
            dense=(sample_count>=3 and interval_duration>0 and
                   sample_times[0]<=t0+max(.002,interval_duration*.05) and
                   sample_times[-1]>=t1-max(.002,interval_duration*.05) and
                   max_gap<=max(.02,interval_duration*.5))
            if dense:
                def interpolate(at,key):
                    if at<=sample_times[0]:return float(points[0][key])
                    if at>=sample_times[-1]:return float(points[-1][key])
                    for left,right in zip(points,points[1:]):
                        a,b=float(left['timestamp']),float(right['timestamp'])
                        if a<=at<=b:
                            fraction=(at-a)/(b-a)
                            return float(left[key])+(float(right[key])-float(left[key]))*fraction
                    return float(points[-1][key])
                clipped=[t0,*[t for t in sample_times if t0<t<t1],t1]
                predicted_linear=predicted_yaw=0.
                for a,b in zip(clipped,clipped[1:]):
                    predicted_linear+=(interpolate(a,'linear_x')+interpolate(b,'linear_x'))*.5*(b-a)
                    predicted_yaw+=(interpolate(a,'angular_z')+interpolate(b,'angular_z'))*.5*(b-a)
                integration_method='history_piecewise'
            else:
                integration_method='endpoint_bounds'
            if linear!=0:
                odometry_final_direction_ok=(v1*linear>0 and abs(v1)>.02)
                wheel_integral_direction_ok=(predicted_linear is not None and
                    predicted_linear*linear>=max(.01,abs(command_integrated_forward)*.25))
            if command_reversal_detected and odometry_available:
                # Require an observed sign crossing in the timestamped history,
                # from the old wheel direction into the newly requested direction.
                for left,right in zip(points,points[1:]):
                    va=float(left['linear_x']);vb=float(right['linear_x'])
                    ta=float(left['timestamp']);tb=float(right['timestamp'])
                    old_side=va*previous_motion_sign>0
                    new_side=vb*requested_motion_sign>0
                    if old_side and new_side and va*vb<0 and tb>ta:
                        odometry_zero_crossing=True
                        odometry_zero_crossing_time=ta+(-va/(vb-va))*(tb-ta)
                        break
                    if old_side and abs(vb)<=.02 and tb>ta:
                        # A sampled near-zero velocity is a crossing candidate;
                        # a later sample must still prove requested-direction travel.
                        later=next((p for p in points if float(p['timestamp'])>tb and
                                    float(p['linear_x'])*requested_motion_sign>0),None)
                        if later is not None:
                            odometry_zero_crossing=True
                            odometry_zero_crossing_time=tb
                            break
            world_translation_ok=(linear==0 or forward*math.copysign(1,linear)>=max(.01,abs(command_integrated_forward)*.25)-1e-9)
            world_turn_ok=(angular==0 or
                signed_yaw*math.copysign(1,angular)>=max(.01,abs(command_integrated_yaw)*.25)-1e-9)
            if angular!=0 and w0*angular<0 and angular_response and signed_yaw*w0>=-.002:
                world_turn_ok=True
            if angular==0 and w0*w1>0 and abs(signed_yaw)>.002:
                world_turn_ok=signed_yaw*w0>0
            world_direction_raw_ok=world_translation_ok and world_turn_ok
            world_direction_ok=world_direction_raw_ok
            if collision:world_direction_ok=True
            max_distance=max(max_distance,max(abs(v0),abs(v1),abs(linear))*dt+.02)
            max_yaw=max(max_yaw,max(abs(w0),abs(w1),abs(angular))*dt+.01)
            odometry_direction_ok=(
                (linear==0 or v1*linear>=-.002) and
                (angular==0 or w1*angular>=-.002 or (w0*angular<0 and angular_response)))
            # The two channels describe different physical layers. Pose topic is
            # the simulated body pose; DiffDrive odometry is wheel-joint dead reckoning.
            if abs(forward)<.005 and abs(predicted_linear or 0.)>.01:
                discrepancy_classification='wheel_odometry_without_world_translation'
            elif abs(forward)>1e-6 and predicted_linear is not None:
                if forward*predicted_linear<0:
                    discrepancy_classification='world_pose_odometry_direction_disagreement'
                else:
                    ratio=abs(predicted_linear/forward)
                    discrepancy_classification=('wheel_odometry_exceeds_world_pose' if ratio>1.25 else
                        'world_pose_exceeds_wheel_odometry' if ratio<.75 else 'translation_signals_close')
            else:discrepancy_classification='direction_and_velocity_only'
        else:
            world_direction_ok=False
            odometry_direction_ok=False
            discrepancy_classification='odometry_unavailable_or_stale'
        contact_blocked_world_motion=bool(collision and
            abs(forward)<max(.01,abs(command_integrated_forward)*.25) and
            abs(signed_yaw)<max(.01,abs(command_integrated_yaw)*.25))
        angular_direction_ok=(angular==0 or signed_yaw*math.copysign(1,angular)>0)
        if odometry_available and angular!=0 and odometry_before['angular_z']*angular<0 and angular_response:
            # A genuine reversal may spend one interval shedding old wheel speed.
            angular_direction_ok=angular_response
        world_body_transient_direction=bool(command_reversal_detected and linear!=0 and
            forward*requested_motion_sign<max(.01,abs(command_integrated_forward)*.25) and
            forward*previous_motion_sign>=max(.01,abs(command_integrated_forward)*.25))
        current_reversal_command_valid=bool(command_reversal_detected and
            abs(abs(linear)-self.linear_speed)<=1e-9 and abs(angular)<=1e-9 and
            abs(abs(previous_linear)-self.linear_speed)<=1e-9 and
            abs(previous_angular)<=1e-9 and odometry_before is not None and
            float(odometry_before['linear_x'])*previous_motion_sign>VELOCITY_DIRECTION_EPSILON)
        reversal_transient_valid=bool(world_body_transient_direction and current_reversal_command_valid and
            odometry_available and odometry_fresh and integration_method=='history_piecewise' and
            odometry_zero_crossing and odometry_final_direction_ok and wheel_integral_direction_ok and
            linear_response and angular_response and not collision and
            distance<=max_distance+1e-9 and yaw<=max_yaw+1e-9)

        body_velocity_samples=(world_pose_history or {}).get('world_forward_velocity_samples',())
        body_velocity_samples=list(body_velocity_samples or ())
        body_start=(None if not body_velocity_samples else
                    float(body_velocity_samples[0].get('forward_velocity',0.)))
        body_end=(None if not body_velocity_samples else
                  float(body_velocity_samples[-1].get('forward_velocity',0.)))
        reversal_body_start_direction_ok=bool(command_reversal_detected and body_start is not None and
            body_start*previous_motion_sign>VELOCITY_DIRECTION_EPSILON)
        reversal_body_end_direction_ok=bool(command_reversal_detected and body_end is not None and
            body_end*requested_motion_sign>VELOCITY_DIRECTION_EPSILON)
        if reversal_body_start_direction_ok and reversal_body_end_direction_ok:
            body_crossing=directed_velocity_zero_crossing(
                body_velocity_samples, previous_motion_sign, requested_motion_sign,
                interval_start=simulation_start_time, interval_end=simulation_end_time)
            reversal_body_zero_crossing=bool(body_crossing['valid'])
            reversal_body_zero_crossing_time=body_crossing['time']
            reversal_body_deadband_sample_count=body_crossing['deadband_samples']
        normal_minimum_translation=max(.01,abs(command_integrated_forward)*.25)
        reversal_net_translation_below_normal_minimum=bool(
            command_reversal_detected and abs(forward)<normal_minimum_translation)
        body_pose_times=[float(t) for t in
            (world_pose_history or {}).get('world_pose_sample_timestamps',())]
        body_velocity_times=[float(sample.get('simulation_timestamp',float('nan')))
            for sample in body_velocity_samples]
        body_pose_gaps=[b-a for a,b in zip(body_pose_times,body_pose_times[1:])]
        body_history_interval_ok=bool(world_pose_history and simulation_start_time is not None and
            simulation_end_time is not None and len(body_pose_times)>=3 and len(body_velocity_samples)>=2 and
            all(math.isfinite(t) for t in body_pose_times+body_velocity_times) and
            body_pose_times==sorted(body_pose_times) and body_velocity_times==sorted(body_velocity_times) and
            body_pose_times[0]>=simulation_start_time-.002 and
            body_pose_times[0]<=simulation_start_time+.01 and
            body_pose_times[-1]>=simulation_end_time-.01 and
            body_pose_times[-1]<=simulation_end_time+.002 and
            body_pose_gaps and max(body_pose_gaps)<=max(.02,dt*.5) and
            all(simulation_start_time-.002<=t<=simulation_end_time+.002 for t in body_velocity_times))
        body_angular_samples=list((world_pose_history or {}).get(
            'world_angular_velocity_samples',()) or ())
        body_angular_times=[float(sample.get('simulation_timestamp',float('nan')))
            for sample in body_angular_samples]
        linear_to_rotation_body_history_interval_ok=bool(body_history_interval_ok and
            len(body_angular_samples)>=2 and all(math.isfinite(t) for t in body_angular_times) and
            body_angular_times==sorted(body_angular_times) and
            all(b>a for a,b in zip(body_pose_times,body_pose_times[1:])) and
            all(b>a for a,b in zip(body_velocity_times,body_velocity_times[1:])) and
            all(b>a for a,b in zip(body_angular_times,body_angular_times[1:])) and
            len(body_pose_times)==int((world_pose_history or {}).get('world_pose_sample_count',-1)) and
            len(body_velocity_samples)==int((world_pose_history or {}).get('world_velocity_sample_count',-1)) and
            len(body_angular_samples)==int((world_pose_history or {}).get('world_angular_velocity_sample_count',-1)) and
            all(simulation_start_time-.002<=t<=simulation_end_time+.002 for t in body_angular_times))

        # This subtype is deliberately limited to the observed LINEAR_TO_ROTATION
        # primitive. The previous discrete action Twist is passed by Environment;
        # the zero Twist published after its physics interval is not used here.
        body_angular_start=(None if not body_angular_samples else
            float(body_angular_samples[0].get('angular_velocity',float('nan'))))
        body_angular_end=(None if not body_angular_samples else
            float(body_angular_samples[-1].get('angular_velocity',float('nan'))))
        previous_is_linear_only=bool(abs(previous_linear)>VELOCITY_DIRECTION_EPSILON and
            abs(previous_angular)<=VELOCITY_DIRECTION_EPSILON)
        requested_is_rotation_only=bool(abs(linear)<=VELOCITY_DIRECTION_EPSILON and
            abs(angular)>VELOCITY_DIRECTION_EPSILON)
        linear_to_rotation_command_valid=bool(
            command_mode_transition=='LINEAR_TO_ROTATION' and previous_is_linear_only and
            requested_is_rotation_only and
            abs(abs(previous_linear)-self.linear_speed)<=1e-9 and
            abs(abs(angular)-self.angular_speed)<=1e-9 and
            simulation_start_time is not None and simulation_end_time is not None and
            simulation_end_time>simulation_start_time and
            abs((simulation_end_time-simulation_start_time)-dt)<=.01)
        body_tail_start=(None if simulation_end_time is None else simulation_end_time-dt*.2)
        body_linear_tail=[float(sample.get('forward_velocity',float('nan')))
            for sample in body_velocity_samples
            if body_tail_start is not None and
            float(sample.get('simulation_timestamp',float('nan')))>=body_tail_start-1e-9]
        body_angular_tail=[float(sample.get('angular_velocity',float('nan')))
            for sample in body_angular_samples
            if body_tail_start is not None and
            float(sample.get('simulation_timestamp',float('nan')))>=body_tail_start-1e-9]
        linear_to_rotation_tail_sample_count=min(len(body_linear_tail),len(body_angular_tail))
        linear_to_rotation_angular_tail_window=(None if body_tail_start is None or simulation_end_time is None
            else [body_tail_start,simulation_end_time])
        if (body_start is not None and math.isfinite(body_start) and
            abs(body_start)>VELOCITY_DIRECTION_EPSILON and body_end is not None and math.isfinite(body_end)):
            linear_to_rotation_forward_remaining_ratio=abs(body_end)/abs(body_start)
            linear_to_rotation_forward_decay_fraction=1.-linear_to_rotation_forward_remaining_ratio
            linear_to_rotation_forward_decay_valid=bool(
                body_start*previous_motion_sign>VELOCITY_DIRECTION_EPSILON and
                linear_to_rotation_forward_remaining_ratio<=.25 and
                linear_to_rotation_forward_decay_fraction>=.75 and
                body_end*previous_motion_sign>=-VELOCITY_DIRECTION_EPSILON and
                bool(body_linear_tail) and all(math.isfinite(v) for v in body_linear_tail) and
                all(float(sample.get('forward_velocity',float('nan')))*previous_motion_sign>=
                    -VELOCITY_DIRECTION_EPSILON for sample in body_velocity_samples) and
                all(abs(v)<=abs(body_start)*.25 for v in body_linear_tail))
        if odometry_available and body_angular_start is not None and body_angular_end is not None and angular!=0 and \
                math.isfinite(body_angular_start) and math.isfinite(body_angular_end):
            old_body_angular_error=abs(body_angular_start-angular)
            new_body_angular_error=abs(body_angular_end-angular)
            linear_to_rotation_angular_established=bool(
                new_body_angular_error<=VELOCITY_DIRECTION_EPSILON
                if old_body_angular_error<=VELOCITY_DIRECTION_EPSILON
                else new_body_angular_error<old_body_angular_error-1e-4)
            linear_to_rotation_angular_direction_valid=bool(
                abs(body_angular_start)<=VELOCITY_DIRECTION_EPSILON and
                body_angular_end*angular>=max(VELOCITY_DIRECTION_EPSILON,abs(angular)*.25) and
                all(float(sample.get('angular_velocity',float('nan')))*angular>=-
                    VELOCITY_DIRECTION_EPSILON for sample in body_angular_samples))
            first_established_index=next((i for i,sample in enumerate(body_angular_samples)
                if float(sample.get('angular_velocity',float('nan')))*angular>
                    VELOCITY_DIRECTION_EPSILON),None)
            if first_established_index is not None:
                angular_run=body_angular_samples[first_established_index:]
                run_times=[float(sample.get('simulation_timestamp',float('nan')))
                    for sample in angular_run]
                run_values=[float(sample.get('angular_velocity',float('nan')))
                    for sample in angular_run]
                linear_to_rotation_angular_first_established_time=run_times[0]
                linear_to_rotation_angular_sustained_duration=(run_times[-1]-run_times[0]
                    if len(run_times)>=2 else 0.)
                linear_to_rotation_angular_sustained_min_duration=max(0.,dt*.2)
                linear_to_rotation_angular_tail_fresh=bool(
                    simulation_end_time is not None and run_times and
                    simulation_end_time-.01<=run_times[-1]<=simulation_end_time+.002)
                linear_to_rotation_angular_sustained_sample_count=len(angular_run)
                # Once significant requested-direction body rotation is established,
                # it must remain significant through the final fresh sample. Duration,
                # rather than callback count, proves sustained motion.
                linear_to_rotation_angular_sustained=bool(
                    run_times and all(math.isfinite(t) for t in run_times) and
                    all(math.isfinite(v) and v*angular>VELOCITY_DIRECTION_EPSILON
                        for v in run_values) and
                    linear_to_rotation_angular_sustained_duration>=
                        linear_to_rotation_angular_sustained_min_duration and
                    linear_to_rotation_angular_tail_fresh)
            linear_to_rotation_body_angular_bounded=bool(
                all(abs(float(sample.get('angular_velocity',float('nan'))))<=
                    max(abs(float(odometry_before['angular_z'])),
                        abs(float(odometry_after['angular_z'])),abs(angular))+
                    VELOCITY_DIRECTION_EPSILON for sample in body_angular_samples))
        if odometry_available:
            linear_to_rotation_wheel_linear_stopped=bool(
                linear_response and float(odometry_before['linear_x'])*previous_motion_sign>VELOCITY_DIRECTION_EPSILON and
                abs(float(odometry_after['linear_x']))<=VELOCITY_DIRECTION_EPSILON)
            linear_to_rotation_wheel_angular_started_neutral=bool(
                abs(float(odometry_before['angular_z']))<=VELOCITY_DIRECTION_EPSILON)
            linear_to_rotation_wheel_angular_valid=bool(
                angular_response and linear_to_rotation_wheel_angular_started_neutral and
                float(odometry_after['angular_z'])*angular>VELOCITY_DIRECTION_EPSILON)
            linear_to_rotation_wheel_integral_valid=bool(
                predicted_yaw is not None and predicted_linear is not None and
                predicted_yaw*angular>=max(.01,abs(command_integrated_yaw)*.25) and
                abs(predicted_linear)<=max_distance+1e-9 and
                abs(predicted_yaw)<=max_yaw+1e-9)
        linear_to_rotation_transient_valid=bool(
            linear_to_rotation_command_valid and odometry_available and odometry_fresh and
            integration_method=='history_piecewise' and dense and
            linear_to_rotation_wheel_linear_stopped and
            linear_to_rotation_wheel_angular_started_neutral and linear_to_rotation_wheel_angular_valid and
            linear_to_rotation_wheel_integral_valid and odometry_direction_ok and
            linear_to_rotation_body_history_available and linear_to_rotation_body_history_fresh and
            linear_to_rotation_body_history_dense and linear_to_rotation_body_history_interval_ok and
            len(body_velocity_samples)>=3 and len(body_angular_samples)>=3 and
            body_start is not None and body_start*previous_motion_sign>VELOCITY_DIRECTION_EPSILON and
            body_angular_start is not None and abs(body_angular_start)<=VELOCITY_DIRECTION_EPSILON and
            linear_to_rotation_forward_decay_valid and linear_to_rotation_angular_direction_valid and
            linear_to_rotation_angular_established and linear_to_rotation_angular_sustained and
            linear_to_rotation_body_angular_bounded and
            not collision and distance<=max_distance+1e-9 and yaw<=max_yaw+1e-9 and
            angular_direction_ok)

        # Actual body-history exception for the observed ROTATION_TO_LINEAR
        # dynamics. Wheel odometry corroborates the command response, while
        # world-pose finite differences establish both body motion trends.
        rotation_to_linear_body_history_interval_ok=bool(
            body_history_interval_ok and len(body_angular_samples)>=3 and
            all(b>a for a,b in zip(body_pose_times,body_pose_times[1:])) and
            all(math.isfinite(t) for t in body_angular_times) and
            body_angular_times==sorted(body_angular_times) and
            all(b>a for a,b in zip(body_angular_times,body_angular_times[1:])) and
            all(b>a for a,b in zip(body_velocity_times,body_velocity_times[1:])) and
            len(body_pose_times)==int((world_pose_history or {}).get('world_pose_sample_count',-1)) and
            len(body_velocity_samples)==int((world_pose_history or {}).get('world_velocity_sample_count',-1)) and
            len(body_angular_samples)==int((world_pose_history or {}).get('world_angular_velocity_sample_count',-1)) and
            all(simulation_start_time-.002<=t<=simulation_end_time+.002 for t in body_angular_times))
        body_pose_values=[]
        for key in ('world_pose_x','world_pose_y','world_pose_yaw'):
            try:body_pose_values.extend(float(v) for v in (world_pose_history or {}).get(key,()))
            except (TypeError,ValueError):body_pose_values.append(float('nan'))
        rotation_to_linear_body_history_interval_ok=bool(
            rotation_to_linear_body_history_interval_ok and
            len(body_pose_values)==3*len(body_pose_times) and
            all(math.isfinite(v) for v in body_pose_values) and
            len(body_angular_samples)==len(body_angular_times))
        rotation_to_linear_linear_values=[float(s.get('forward_velocity',float('nan')))
            for s in body_velocity_samples]
        rotation_to_linear_angular_values=[float(s.get('angular_velocity',float('nan')))
            for s in body_angular_samples]
        if (rotation_to_linear_linear_values and rotation_to_linear_angular_values and
            all(math.isfinite(v) for v in rotation_to_linear_linear_values+rotation_to_linear_angular_values)):
            rotation_to_linear_start_forward_velocity=rotation_to_linear_linear_values[0]
            rotation_to_linear_end_forward_velocity=rotation_to_linear_linear_values[-1]
            rotation_to_linear_start_angular_velocity=rotation_to_linear_angular_values[0]
            rotation_to_linear_end_angular_velocity=rotation_to_linear_angular_values[-1]
        previous_is_rotation_only=bool(abs(previous_angular)>VELOCITY_DIRECTION_EPSILON and
            abs(previous_linear)<=VELOCITY_DIRECTION_EPSILON)
        requested_is_linear_only=bool(abs(linear)>VELOCITY_DIRECTION_EPSILON and
            abs(angular)<=VELOCITY_DIRECTION_EPSILON)
        rotation_to_linear_command_valid=bool(
            command_mode_transition=='ROTATION_TO_LINEAR' and previous_is_rotation_only and
            requested_is_linear_only and
            abs(abs(previous_angular)-self.angular_speed)<=1e-9 and
            abs(abs(linear)-self.linear_speed)<=1e-9 and
            simulation_start_time is not None and simulation_end_time is not None and
            simulation_end_time>simulation_start_time and
            abs((simulation_end_time-simulation_start_time)-dt)<=.01)
        if rotation_to_linear_start_angular_velocity is not None:
            previous_angular_sign=1 if previous_angular>VELOCITY_DIRECTION_EPSILON else -1
            requested_linear_sign=1 if linear>VELOCITY_DIRECTION_EPSILON else -1
            angular_start_abs=abs(rotation_to_linear_start_angular_velocity)
            angular_end_abs=abs(rotation_to_linear_end_angular_velocity)
            if angular_start_abs>VELOCITY_DIRECTION_EPSILON:
                rotation_to_linear_angular_remaining_ratio=angular_end_abs/angular_start_abs
                rotation_to_linear_angular_decay_fraction=1.-rotation_to_linear_angular_remaining_ratio
                angular_tail_start=simulation_end_time-dt*.2
                angular_tail_samples=[]
                for sample in body_angular_samples:
                    try:
                        overlaps=(float(sample['interval_end'])>angular_tail_start and
                            float(sample['interval_start'])<simulation_end_time)
                    except (KeyError,TypeError,ValueError):overlaps=False
                    if overlaps:angular_tail_samples.append(sample)
                angular_tail=[float(s.get('angular_velocity',float('nan')))
                    for s in angular_tail_samples]
                rotation_to_linear_angular_tail_coverage_valid,rotation_to_linear_angular_tail_coverage_seconds=(
                    _sample_interval_union(body_angular_samples,angular_tail_start,simulation_end_time))
                tail_coverage=bool(rotation_to_linear_angular_tail_coverage_valid and
                    rotation_to_linear_angular_tail_coverage_seconds>=dt*.2-1e-9)
                rotation_to_linear_angular_stopped=bool(angular_end_abs<=VELOCITY_DIRECTION_EPSILON)
                rotation_to_linear_angular_decay_valid=bool(
                    rotation_to_linear_start_angular_velocity*previous_angular_sign>VELOCITY_DIRECTION_EPSILON and
                    rotation_to_linear_end_angular_velocity*previous_angular_sign>=-VELOCITY_DIRECTION_EPSILON and
                    rotation_to_linear_angular_remaining_ratio<=.25 and
                    rotation_to_linear_angular_decay_fraction>=.75 and
                    all(math.isfinite(v) and abs(v)<=angular_start_abs+VELOCITY_DIRECTION_EPSILON and
                        v*previous_angular_sign>=-VELOCITY_DIRECTION_EPSILON
                        for v in rotation_to_linear_angular_values) and
                    rotation_to_linear_angular_stopped and tail_coverage and angular_tail and
                    all(math.isfinite(v) and abs(v)<=VELOCITY_DIRECTION_EPSILON
                        for v in angular_tail) and
                    all(math.isfinite(v) and abs(v)<=angular_start_abs*.25+
                        VELOCITY_DIRECTION_EPSILON for v in angular_tail))
            established_index=next((i for i,v in enumerate(rotation_to_linear_linear_values)
                if v*requested_linear_sign>VELOCITY_DIRECTION_EPSILON),None)
            if established_index is not None:
                rotation_to_linear_requested_direction_established=bool(
                    all(v*requested_linear_sign>=-VELOCITY_DIRECTION_EPSILON
                        for v in rotation_to_linear_linear_values[established_index:]))
            rotation_to_linear_final_direction_ok=bool(
                rotation_to_linear_end_forward_velocity*requested_linear_sign>
                    max(VELOCITY_DIRECTION_EPSILON,abs(linear)*.5) and
                abs(rotation_to_linear_end_forward_velocity-linear)<
                    abs(rotation_to_linear_start_forward_velocity-linear))
        if (odometry_available and rotation_to_linear_start_angular_velocity is not None and
            rotation_to_linear_end_forward_velocity is not None and predicted_linear is not None):
            rotation_to_linear_wheel_response_valid=bool(
                odometry_fresh and integration_method=='history_piecewise' and dense and
                angular_response and linear_response and odometry_direction_ok and
                float(odometry_before['angular_z'])*previous_angular>VELOCITY_DIRECTION_EPSILON and
                abs(float(odometry_after['angular_z']))<=VELOCITY_DIRECTION_EPSILON and
                float(odometry_after['linear_x'])*linear>VELOCITY_DIRECTION_EPSILON and
                predicted_linear*linear>=max(.01,abs(command_integrated_forward)*.25) and
                abs(predicted_linear)<=max_distance+1e-9 and
                abs(predicted_yaw or 0.)<=max_yaw+1e-9)
        else:
            rotation_to_linear_wheel_response_valid=False
        rotation_to_linear_transient_valid=bool(
            rotation_to_linear_command_valid and
            rotation_to_linear_body_history_available and rotation_to_linear_body_history_fresh and
            rotation_to_linear_body_history_dense and rotation_to_linear_body_history_interval_ok and
            len(body_velocity_samples)>=3 and len(body_angular_samples)>=3 and
            rotation_to_linear_start_angular_velocity is not None and
            rotation_to_linear_start_angular_velocity*previous_angular_sign>VELOCITY_DIRECTION_EPSILON and
            rotation_to_linear_angular_decay_valid and rotation_to_linear_angular_stopped and
            rotation_to_linear_requested_direction_established and rotation_to_linear_final_direction_ok and
            rotation_to_linear_wheel_response_valid and not world_direction_raw_ok and not collision and
            distance<=max_distance+1e-9 and yaw<=max_yaw+1e-9)
        reversal_cancellation_valid=bool(
            not reversal_transient_valid and reversal_net_translation_below_normal_minimum and
            current_reversal_command_valid and odometry_available and odometry_fresh and
            integration_method=='history_piecewise' and odometry_zero_crossing and
            odometry_final_direction_ok and wheel_integral_direction_ok and
            linear_response and angular_response and odometry_direction_ok and
            reversal_body_history_available and reversal_body_history_fresh and
            reversal_body_history_dense and body_history_interval_ok and
            (world_pose_history or {}).get('world_velocity_zero_crossing') is True and
            reversal_body_start_direction_ok and reversal_body_zero_crossing and
            reversal_body_end_direction_ok and not collision and
            distance<=max_distance+1e-9 and yaw<=max_yaw+1e-9)
        if reversal_transient_valid:
            world_direction_ok=True
            discrepancy_classification='validated_longitudinal_reversal_transient'
        elif reversal_cancellation_valid:
            world_direction_ok=True
            discrepancy_classification='validated_longitudinal_reversal_cancellation'
        elif linear_to_rotation_transient_valid:
            world_turn_ok=True
            world_direction_ok=world_translation_ok and world_turn_ok
            discrepancy_classification='validated_linear_to_rotation_transient'
        elif rotation_to_linear_transient_valid:
            world_direction_ok=True
            discrepancy_classification='validated_rotation_to_linear_transient'
        valid=(distance<=max_distance+1e-9 and yaw<=max_yaw+1e-9 and odometry_fresh and
               world_direction_ok and odometry_direction_ok and linear_response and angular_response)
        return {'valid':valid,'distance':distance,'expected_distance':expected,'yaw_delta':yaw,'expected_yaw':rotation,
                'body_forward_displacement':forward,'signed_yaw_delta':signed_yaw,
                'collision_may_block_motion':collision,'control_mode':'PHYSICS',
                'odometry_available':odometry_available,'odometry_fresh':odometry_fresh,'odometry_before':odometry_before,
                'odometry_after':odometry_after,'odometry_predicted_forward':predicted_linear,
                'odometry_predicted_yaw':predicted_yaw,'linear_velocity_converging':linear_response,
                'angular_velocity_converging':angular_response,'pose_odometry_consistent':None,
                'odometry_sample_count':sample_count,'odometry_sample_timestamps':sample_times,
                'odometry_sample_linear_x':[float(p['linear_x']) for p in points],
                'odometry_sample_angular_z':[float(p['angular_z']) for p in points],
                'odometry_integration_method':integration_method,
                'odometry_integration_note':('timestamped piecewise integral' if integration_method=='history_piecewise' else
                    'sparse endpoint bounds; no trapezoidal integral reported' if integration_method=='endpoint_bounds' else 'unavailable'),
                'command_integrated_forward':linear*dt,
                'command_integrated_yaw':angular*dt,
                'odometry_integrated_forward':predicted_linear,'odometry_integrated_yaw':predicted_yaw,
                'wheel_odometry_forward':predicted_linear,'wheel_odometry_yaw':predicted_yaw,
                'pose_measured_forward':forward,'pose_measured_yaw':signed_yaw,
                'world_pose_forward':forward,
                'world_pose_source':'gazebo_pose_topic_physical_body_pose',
                'odometry_source':'gazebo_diff_drive_wheel_joint_dead_reckoning',
                'world_direction_ok':world_direction_ok,'odometry_direction_ok':odometry_direction_ok,
                'world_direction_raw_ok':world_direction_raw_ok,
                'command_reversal_detected':command_reversal_detected,
                'previous_motion_sign':previous_motion_sign,
                'requested_motion_sign':requested_motion_sign,
                'previous_command_twist':previous_command,
                'previous_action_twist':previous_command,
                'requested_command_twist':dict(self.last_command),
                'command_mode_transition':command_mode_transition,
                'odometry_zero_crossing':odometry_zero_crossing,
                'odometry_zero_crossing_time':odometry_zero_crossing_time,
                'odometry_final_direction_ok':odometry_final_direction_ok,
                'wheel_integral_direction_ok':wheel_integral_direction_ok,
                'world_body_transient_direction':world_body_transient_direction,
                'reversal_current_command_valid':current_reversal_command_valid,
                'reversal_transient_valid':reversal_transient_valid,
                'reversal_body_history_available':reversal_body_history_available,
                'reversal_body_history_fresh':reversal_body_history_fresh,
                'reversal_body_history_dense':reversal_body_history_dense,
                'reversal_body_history_interval_ok':body_history_interval_ok,
                'reversal_body_start_forward_velocity':body_start,
                'reversal_body_end_forward_velocity':body_end,
                'reversal_body_start_direction_ok':reversal_body_start_direction_ok,
                'reversal_body_zero_crossing':reversal_body_zero_crossing,
                'reversal_body_zero_crossing_time':reversal_body_zero_crossing_time,
                'reversal_body_deadband_sample_count':reversal_body_deadband_sample_count,
                'reversal_body_end_direction_ok':reversal_body_end_direction_ok,
                'reversal_net_translation_below_normal_minimum':reversal_net_translation_below_normal_minimum,
                'reversal_normal_minimum_translation':normal_minimum_translation,
                'reversal_cancellation_valid':reversal_cancellation_valid,
                'linear_to_rotation_body_history_available':linear_to_rotation_body_history_available,
                'linear_to_rotation_body_history_fresh':linear_to_rotation_body_history_fresh,
                'linear_to_rotation_body_history_dense':linear_to_rotation_body_history_dense,
                'linear_to_rotation_body_history_interval_ok':linear_to_rotation_body_history_interval_ok,
                'linear_to_rotation_start_forward_velocity':body_start,
                'linear_to_rotation_end_forward_velocity':body_end,
                'linear_to_rotation_forward_remaining_ratio':linear_to_rotation_forward_remaining_ratio,
                'linear_to_rotation_forward_decay_fraction':linear_to_rotation_forward_decay_fraction,
                # Backward-compatible evidence alias: this is the fraction decayed,
                # not the remaining velocity ratio.
                'linear_to_rotation_forward_decay_ratio':linear_to_rotation_forward_decay_fraction,
                'linear_to_rotation_forward_decay_ratio_definition':'1 - abs(end_forward_velocity) / abs(start_forward_velocity)',
                'linear_to_rotation_forward_decay_valid':linear_to_rotation_forward_decay_valid,
                'linear_to_rotation_start_angular_velocity':body_angular_start,
                'linear_to_rotation_end_angular_velocity':body_angular_end,
                'linear_to_rotation_angular_direction_valid':linear_to_rotation_angular_direction_valid,
                'linear_to_rotation_angular_established':linear_to_rotation_angular_established,
                'linear_to_rotation_angular_sustained':linear_to_rotation_angular_sustained,
                'linear_to_rotation_body_angular_bounded':linear_to_rotation_body_angular_bounded,
                'linear_to_rotation_angular_tail_window':linear_to_rotation_angular_tail_window,
                'linear_to_rotation_tail_sample_count':linear_to_rotation_tail_sample_count,
                'linear_to_rotation_angular_first_established_time':linear_to_rotation_angular_first_established_time,
                'linear_to_rotation_angular_sustained_duration':linear_to_rotation_angular_sustained_duration,
                'linear_to_rotation_angular_sustained_min_duration':linear_to_rotation_angular_sustained_min_duration,
                'linear_to_rotation_angular_tail_fresh':linear_to_rotation_angular_tail_fresh,
                'linear_to_rotation_angular_sustained_sample_count':linear_to_rotation_angular_sustained_sample_count,
                'linear_to_rotation_wheel_linear_stopped':linear_to_rotation_wheel_linear_stopped,
                'linear_to_rotation_wheel_angular_started_neutral':linear_to_rotation_wheel_angular_started_neutral,
                'linear_to_rotation_wheel_angular_valid':linear_to_rotation_wheel_angular_valid,
                'linear_to_rotation_wheel_integral_valid':linear_to_rotation_wheel_integral_valid,
                'linear_to_rotation_transient_valid':linear_to_rotation_transient_valid,
                'rotation_to_linear_body_history_available':rotation_to_linear_body_history_available,
                'rotation_to_linear_body_history_fresh':rotation_to_linear_body_history_fresh,
                'rotation_to_linear_body_history_dense':rotation_to_linear_body_history_dense,
                'rotation_to_linear_body_history_interval_ok':rotation_to_linear_body_history_interval_ok,
                'rotation_to_linear_start_angular_velocity':rotation_to_linear_start_angular_velocity,
                'rotation_to_linear_end_angular_velocity':rotation_to_linear_end_angular_velocity,
                'rotation_to_linear_angular_remaining_ratio':rotation_to_linear_angular_remaining_ratio,
                'rotation_to_linear_angular_decay_fraction':rotation_to_linear_angular_decay_fraction,
                'rotation_to_linear_angular_decay_valid':rotation_to_linear_angular_decay_valid,
                'rotation_to_linear_angular_stopped':rotation_to_linear_angular_stopped,
                'rotation_to_linear_angular_tail_coverage_seconds':rotation_to_linear_angular_tail_coverage_seconds,
                'rotation_to_linear_angular_tail_coverage_valid':rotation_to_linear_angular_tail_coverage_valid,
                'rotation_to_linear_start_forward_velocity':rotation_to_linear_start_forward_velocity,
                'rotation_to_linear_end_forward_velocity':rotation_to_linear_end_forward_velocity,
                'rotation_to_linear_requested_direction_established':rotation_to_linear_requested_direction_established,
                'rotation_to_linear_final_direction_ok':rotation_to_linear_final_direction_ok,
                'rotation_to_linear_wheel_response_valid':rotation_to_linear_wheel_response_valid,
                'rotation_to_linear_transient_valid':rotation_to_linear_transient_valid,
                'contact_blocked_world_motion':contact_blocked_world_motion,
                'odometry_pose_delta':None if predicted_linear is None else predicted_linear-forward,
                'odometry_pose_ratio':None if predicted_linear is None or abs(forward)<1e-9 else abs(predicted_linear/forward),
                'discrepancy_classification':discrepancy_classification,
                'consistency_reason':'world pose and wheel odometry are validated by separate semantics; magnitude discrepancy is telemetry',
                'angular_direction_ok':angular_direction_ok,
                'distance_limit_from_command_or_odometry':max_distance,'yaw_limit_from_command_or_odometry':max_yaw}
