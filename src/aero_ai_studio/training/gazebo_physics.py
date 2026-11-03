"""Training adapter that keeps DQN episodes on the validated Gazebo PHYSICS path."""
from __future__ import annotations
import math
import time
from aero_ai_studio.gazebo.control_executor import (
    GazeboControlExecutor,
    GazeboDownToLeftControlExecutor,
    GazeboLeftToUpControlExecutor,
    GazeboLinearReversalControlExecutor,
    GazeboUpToRightControlExecutor,
)
from aero_ai_studio.gazebo.contracts import SensorTimeoutError
from aero_ai_studio.gazebo.physics_feedback import (
    BODY_STOPPED_EPSILON,
    PRE_RESET_QUIESCENCE_CHUNK_ITERATIONS,
    PRE_RESET_QUIESCENCE_MAX_CHUNKS,
    body_stopped_contract,
)
from aero_ai_studio.simulation.action_mapping import classify_physics_command_transition, gazebo_physics_twist
from aero_ai_studio.simulation.base import PhysicalControlFailure,StepResult
from aero_ai_studio.simulation.control_execution import (
    ControlExecutionRequest,
    ControlExecutionStatus,
    plan_control_execution,
)
from aero_ai_studio.training.temporal import (
    MacroRewardAccumulator,
    NOMINAL_DISCOUNT_TIME_UNIT_SECONDS,
)


R2L_VERIFIED_ACTION_PAIR=('right','down')
LINEAR_REVERSAL_VERIFIED_ACTION_PAIR=('down','up')
LINEAR_REVERSAL_UP_TO_DOWN_VERIFIED_ACTION_PAIR=('up','down')
LINEAR_TO_ROTATION_DOWN_TO_LEFT_VERIFIED_ACTION_PAIR=('down','left')
ROTATION_TO_LINEAR_LEFT_TO_UP_VERIFIED_ACTION_PAIR=('left','up')
LINEAR_TO_ROTATION_UP_TO_RIGHT_VERIFIED_ACTION_PAIR=('up','right')


class GazeboTrainingInfrastructureError(RuntimeError):
    training_status='infrastructure_failure'

    def __init__(self,category,message):
        super().__init__(message);self.category=category


def reset_odometry_contract(odometry,*,reset_epoch_sim_time,settle_start_sim_time,
                           settle_end_sim_time,sequence_before_reset,
                           sequence_after_reset,sequence_before_settle):
    """Evaluate stopped-wheel odometry against both receive and sim-time epochs."""
    from_sequence=None if odometry is None else odometry.get('receive_sequence')
    timestamp=None if odometry is None else odometry.get('timestamp')
    linear=None if odometry is None else odometry.get('linear_x')
    angular=None if odometry is None else odometry.get('angular_z')
    present=odometry is not None and timestamp is not None and from_sequence is not None
    seq_new=bool(present and sequence_before_settle is not None and
                 int(from_sequence)>int(sequence_before_settle))
    seq_after_epoch=bool(present and sequence_after_reset is not None and
                         int(from_sequence)>int(sequence_after_reset))
    timestamp_after_epoch=bool(present and float(timestamp)>=float(reset_epoch_sim_time)-1e-6)
    # Keep the existing 20 ms freshness bound and 2 ms future allowance.
    timestamp_fresh=bool(present and
        float(settle_end_sim_time)-.02<=float(timestamp)<=float(settle_end_sim_time)+.002 and
        float(timestamp)>=float(settle_start_sim_time)-.002)
    linear_stopped=bool(present and math.isfinite(float(linear)) and abs(float(linear))<=.02)
    angular_stopped=bool(present and math.isfinite(float(angular)) and abs(float(angular))<=.02)
    conditions={'odom_present':present,'receive_sequence_new':seq_new,
        'receive_sequence_after_epoch':seq_after_epoch,'timestamp_after_epoch':timestamp_after_epoch,
        'timestamp_fresh':timestamp_fresh,'linear_stopped':linear_stopped,
        'angular_stopped':angular_stopped}
    failures=[name for name,passed in conditions.items() if not passed]
    return {'reset_epoch_sim_time':float(reset_epoch_sim_time),
        'settle_start_sim_time':float(settle_start_sim_time),
        'settle_end_sim_time':float(settle_end_sim_time),
        'sequence_before_reset':sequence_before_reset,'sequence_after_reset':sequence_after_reset,
        'sequence_before_settle':sequence_before_settle,'receive_sequence':from_sequence,
        'timestamp':timestamp,'linear_x':linear,'angular_z':angular,
        'expected_publish_frequency_hz':100,'expected_publish_period_seconds':.01,
        'publish_frequency_source':'generated SDF DiffDrive odom_publish_frequency=100',
        **conditions,'pass':not failures,
        'failure_reason':None if not failures else ','.join(failures)}


def gazebo_dqn_reward(distance_before,distance_after,reason):
    """Reuse V0.6/V0.7 terminal/progress scale with continuous Gazebo pose distance."""
    if reason=='goal':
        parts={'goal':100.,'collision':0.,'danger':0.,'progress':0.,'time':0.,
               'smooth':0.,'near_obstacle':0.,'moving_risk':0.}
    elif 'collision' in reason:
        parts={'goal':0.,'collision':-100.,'danger':0.,'progress':0.,'time':0.,
               'smooth':0.,'near_obstacle':0.,'moving_risk':0.}
    elif reason=='danger_zone':
        parts={'goal':0.,'collision':0.,'danger':-50.,'progress':0.,'time':0.,
               'smooth':0.,'near_obstacle':0.,'moving_risk':0.}
    else:
        parts={'goal':0.,'collision':0.,'danger':0.,
               'progress':2.*(distance_before-distance_after),'time':-.1,
               'smooth':0.,'near_obstacle':0.,'moving_risk':0.}
    parts['total']=sum(parts.values())
    return parts


class GazeboPhysicsTrainingEnvironment:
    """Verified PHYSICS adapter with exact-pair verified control macros."""
    def __init__(self,scenario,max_steps,*,root,gui=False,max_sensor_age_ms=20,goal_radius=.45,gamma=.95):
        from aero_ai_studio.gazebo.environment import GazeboEnvironment
        self.scenario=scenario;self.max_steps=max_steps;self.root=root;self.gui=gui
        self.max_sensor_age_ms=max_sensor_age_ms;self.goal_radius=goal_radius;self.gamma=float(gamma)
        self.env=GazeboEnvironment(scenario,max_steps,root=root,gui=gui,control_mode='PHYSICS',
            max_sensor_age_ms=max_sensor_age_ms,goal_radius=goal_radius,allow_geometric_fallback=False,
            retain_world_pose_history=True)
        self.reward_version='v2';self.last_reward_components={};self.last_reset_evidence={}
        self.reset_evidence=[];self.restart_fallbacks=0;self.last_step_seconds=0.
        self.episodes_started=0;self._active_reset_attempt=None

    def __getattr__(self,name):return getattr(self.env,name)

    def _require_actual_sensor(self,observation,previous_sequence=None):
        from aero_ai_studio.observation.encoder import observation_vector
        state=observation.sensor_state if observation is not None else {}
        frame=getattr(self.env.sensors,'frame',None)
        timestamp=state.get('sensor_timestamp',state.get('sample_time'))
        sequence=state.get('sequence')
        now=float(self.env.stepper.time)
        age_ms=None if timestamp is None else (now-float(timestamp))*1000.
        if (observation.mode!='sensor' or state.get('source')!='gazebo_lidar' or frame is None or
            frame.source!='gazebo_lidar' or timestamp is None or sequence is None or
            (previous_sequence is not None and int(sequence)<=int(previous_sequence)) or
            age_ms is None or age_ms < -2. or age_ms > self.max_sensor_age_ms):
            raise GazeboTrainingInfrastructureError('stale_sensor',
                f'Gazebo training requires a fresh, advancing native SENSOR sample: '
                f'mode={getattr(observation,"mode",None)}, source={state.get("source")}, '
                f'timestamp={timestamp}, sequence={sequence}, age_ms={age_ms}')
        vector=observation_vector(observation)
        if len(vector)!=22:
            raise GazeboTrainingInfrastructureError('incompatible_observation',
                f'Gazebo SENSOR encoder produced {len(vector)} values, expected 22')
        return {'mode':'sensor','source':'gazebo_lidar','timestamp':float(timestamp),
                'sequence':int(sequence),'age_ms':age_ms,'dimension':len(vector)}

    def _pre_reset_quiescence(self):
        """Boundedly stop the live rigid body before a persistent MODEL_ONLY reset."""
        from aero_ai_studio.gazebo.entity_controller import summarize_world_pose_history
        env=self.env
        env.controller.stop_agent()
        start_time=float(env.stepper.time)
        start_pose=dict(env.controller.get_pose(start_time-.002,env.timeout))
        evidence={'zero_twist_sent':True,
            'zero_twist':dict(env.controller.last_published_command or {}),
            'zero_twist_publish_sequence':getattr(env.controller,'publish_sequence',None),
            'fixed_physics_stepper_used':True,'wall_clock_sleep_used_for_settling':False,
            'chunk_iterations':PRE_RESET_QUIESCENCE_CHUNK_ITERATIONS,
            'max_chunks':PRE_RESET_QUIESCENCE_MAX_CHUNKS,'settle_chunks':[],
            'start_simulation_time':start_time,'start_pose':start_pose,
            'world_body_is_primary_authority':True}
        if (evidence['zero_twist'].get('linear',{}).get('x')!=0. or
            evidence['zero_twist'].get('angular',{}).get('z')!=0.):
            evidence.update(world_body_stopped=False,
                failure_reason='zero_twist_not_published')
            evidence['pass']=False
            error=GazeboTrainingInfrastructureError('reset_isolation',
                'Persistent reset quiescence failed: zero Twist was not published')
            error.reset_failure_reasons=('pre_reset_quiescence_failed:zero_twist_not_published',)
            error.pre_reset_quiescence=evidence
            raise error
        stopped=False
        for index in range(PRE_RESET_QUIESCENCE_MAX_CHUNKS):
            if not env.process or env.process.poll() is not None:
                evidence['process_alive']=False
                break
            chunk_start=float(env.stepper.time)
            pose_cursor=env.transport.cursor(env.controller.pose_topic)
            odom_cursor=env.transport.cursor(env.odometry_topic)
            pose_before=dict(env.pose)
            env.stepper.step_simulation()
            env._refresh()
            chunk_end=float(env.stepper.time)
            pose_after=dict(env.pose)
            samples=env.controller.pose_history_after(pose_cursor,chunk_start,chunk_end)
            summary=summarize_world_pose_history(samples,chunk_start,chunk_end)
            body_contract=body_stopped_contract(summary)
            step_evidence=dict(getattr(env.stepper,'last_verification',{}))
            observed_iterations=step_evidence.get('iteration_delta')
            expected_iterations=step_evidence.get('expected_iteration_delta',
                PRE_RESET_QUIESCENCE_CHUNK_ITERATIONS)
            iterations_ok=(observed_iterations==PRE_RESET_QUIESCENCE_CHUNK_ITERATIONS and
                           expected_iterations==PRE_RESET_QUIESCENCE_CHUNK_ITERATIONS)
            odometry=None
            odometry_error=None
            try:
                if hasattr(env,'read_odometry_after_sequence'):
                    odometry=env.read_odometry_after_sequence(odom_cursor,
                        chunk_end-.02,chunk_end+.002,timeout=.5)
                else:
                    odometry=env.read_odometry(chunk_end-.02,timeout=.5)
            except Exception as error:
                odometry_error={'type':type(error).__name__,'message':str(error)}
            displacement=math.hypot(pose_after['x']-pose_before['x'],
                                    pose_after['y']-pose_before['y'])
            row={'index':index+1,'simulation_start':chunk_start,
                'simulation_end':chunk_end,'iterations':observed_iterations,
                'expected_iterations':expected_iterations,'iterations_contract_pass':iterations_ok,
                'pose_before':pose_before,'pose_after':pose_after,
                'displacement_during_chunk':displacement,
                'world_pose_history':summary,'body_stopped_contract':body_contract,
                'odometry':odometry,'odometry_error':odometry_error,
                'step_evidence':step_evidence}
            evidence['settle_chunks'].append(row)
            if body_contract['pass'] and iterations_ok:
                stopped=True
                break
        end_pose=dict(env.pose)
        evidence.update(end_simulation_time=float(env.stepper.time),
            total_iterations=sum(int(row['iterations'] or 0) for row in evidence['settle_chunks']),
            simulation_time_spent=float(env.stepper.time)-start_time,
            end_pose=end_pose,
            displacement_during_quiescence=math.hypot(end_pose['x']-start_pose['x'],
                                                       end_pose['y']-start_pose['y']),
            final_body_history=(evidence['settle_chunks'][-1]['world_pose_history']
                                if evidence['settle_chunks'] else None),
            final_body_stopped_contract=(evidence['settle_chunks'][-1]['body_stopped_contract']
                                         if evidence['settle_chunks'] else None),
            final_odometry=(evidence['settle_chunks'][-1]['odometry']
                            if evidence['settle_chunks'] else None),
            world_body_stopped=stopped,
            failure_reason=None if stopped else 'pre_reset_quiescence_failed')
        evidence['pass']=stopped
        if not stopped:
            error=GazeboTrainingInfrastructureError('reset_isolation',
                'Persistent reset quiescence failed: world body did not meet strict stop contract '
                'within 20 physics chunks / 2.0 simulation seconds')
            error.reset_failure_reasons=('pre_reset_quiescence_failed',)
            error.pre_reset_quiescence=evidence
            raise error
        return evidence

    def _contact_readiness(self,phase):
        """Check publisher/schema only; event silence is not used as a health signal."""
        env=self.env
        topic=getattr(env,'contact_topic',None)
        record={'phase':phase,'required':True,'timeout_seconds':1.0,
                'expected_schema':'gz.msgs.Contacts','topic':topic}
        try:
            if not topic:
                raise RuntimeError('Contact topic is not configured')
            if not env.process or env.process.poll() is not None:
                raise RuntimeError('Gazebo process is not alive during Contact readiness')
            advertised=env.transport.wait_for_topic(topic,'Contacts',timeout=1.0)
            alive=bool(env.process and env.process.poll() is None)
            record.update(result=advertised,process_alive=alive,
                event_packet_required=False)
            record['pass']=alive and advertised.get('message_type')=='gz.msgs.Contacts'
            if not record['pass']:
                raise RuntimeError('Contact publisher/schema readiness failed')
        except Exception as error:
            record.update(failure_reason=f'{type(error).__name__}: {error}',
                          process_alive=bool(env.process and env.process.poll() is None),
                          event_packet_required=False)
            record['pass']=False
            if self._active_reset_attempt is not None:
                self._active_reset_attempt.setdefault('contact_readiness',{})[phase]=record
            raise GazeboTrainingInfrastructureError('reset_isolation',
                f'Contact publisher/schema not ready at {phase}: {record}') from error
        if self._active_reset_attempt is not None:
            self._active_reset_attempt.setdefault('contact_readiness',{})[phase]=record
        return record

    def launch(self):
        result=self.env.launch()
        if not result.get('available',True):raise GazeboTrainingInfrastructureError('service_failure','Gazebo launch unavailable')
        if not self.env.process or self.env.process.poll() is not None:
            raise GazeboTrainingInfrastructureError('service_failure','Gazebo server process is not alive')
        return result

    def _reset_once(self,seed):
        self.env.reset(seed)
        if self.env.control_mode!='PHYSICS' or self.env.injected:
            raise GazeboTrainingInfrastructureError('incompatible_environment','Training requires native PHYSICS Gazebo, not injected transport')
        if not self.env.process or self.env.process.poll() is not None:
            raise GazeboTrainingInfrastructureError('service_failure','Gazebo process exited during episode reset')
        if self.env.controller.last_command.get('linear',{}).get('x')!=0 or self.env.controller.last_command.get('angular',{}).get('z')!=0:
            raise GazeboTrainingInfrastructureError('reset_isolation','Reset did not leave a zero Twist command')
        reset_attempt=self._active_reset_attempt or {}
        persistent_reset=bool(reset_attempt.get('persistent_reset'))
        if persistent_reset:
            self._contact_readiness('after_progression')
        epoch_type=reset_attempt.get('reset_method',
            getattr(self.env,'odometry_epoch_source','fresh_process_initialization'))
        if epoch_type=='fresh_process_initialization' and reset_attempt.get('odometry_sequence_after_reset') is None:
            # _connect subscribes before GazeboEnvironment.reset publishes its
            # first physics step. This cursor is the explicit fresh-process
            # epoch boundary; it is never inferred from the selected sample.
            baseline=getattr(self.env,'odometry_sequence_at_subscription',None)
            if baseline is not None:
                reset_attempt['odometry_sequence_after_reset']=int(baseline)
                reset_attempt['odometry_epoch_source']='fresh_process_subscription'
        before=dict(self.env.pose);time_before=self.env.stepper.time
        pose_topic=getattr(self.env.controller,'pose_topic',None)
        pose_sequence_before=(self.env.transport.cursor(pose_topic)
            if pose_topic and hasattr(self.env.transport,'cursor') else None)
        odometry_topic=getattr(self.env,'odometry_topic',None)
        odometry_sequence_before=(self.env.transport.cursor(odometry_topic)
            if odometry_topic and hasattr(self.env.transport,'cursor') else None)
        sequence_before=self.env.sensors.sequence
        self.env.stepper.step_simulation()
        self.env._refresh()
        after=dict(self.env.pose);duration=self.env.stepper.time-time_before
        displacement=math.hypot(after['x']-before['x'],after['y']-before['y'])
        yaw_drift=abs(math.atan2(math.sin(after['yaw']-before['yaw']),math.cos(after['yaw']-before['yaw'])))
        start=(self.scenario.start[0]+.5,self.scenario.start[1]+.5)
        start_error=math.hypot(after['x']-start[0],after['y']-start[1])
        frame=self.env.sensors.frame
        sensor_fresh=(frame is not None and frame.source=='gazebo_lidar' and
            frame.sequence>sequence_before and frame.age_ms<=self.max_sensor_age_ms)
        if odometry_sequence_before is not None and hasattr(self.env,'read_odometry_after_sequence'):
            # Select a post-boundary sample that is also fresh at settle end;
            # accepting the first post-reset packet can return t=0.11 after a
            # settle through t=0.20, which is epoch-new but no longer current.
            odometry=self.env.read_odometry_after_sequence(odometry_sequence_before,
                self.env.stepper.time-.02,self.env.stepper.time+.002,timeout=.5)
        else:
            odometry=self.env.read_odometry(self.env.stepper.time-.02)
        reset_epoch_time=float(reset_attempt.get('reset_epoch_sim_time',0.))
        sequence_before_reset=reset_attempt.get('odometry_sequence_before_reset')
        sequence_after_reset=reset_attempt.get('odometry_sequence_after_reset')
        odometry_contract=reset_odometry_contract(odometry,
            reset_epoch_sim_time=reset_epoch_time,settle_start_sim_time=time_before,
            settle_end_sim_time=self.env.stepper.time,
            sequence_before_reset=sequence_before_reset,
            sequence_after_reset=sequence_after_reset,
            sequence_before_settle=odometry_sequence_before)
        odometry_fresh=odometry_contract['pass']
        if persistent_reset:
            self._contact_readiness('after_settle')
        contacts=self.env.contacts.poll(self.env.stepper.time) if hasattr(self.env,'contacts') else []
        body_history_summary=None
        if pose_sequence_before is not None:
            try:
                from aero_ai_studio.gazebo.entity_controller import summarize_world_pose_history
                history=self.env.controller.pose_history_after(pose_sequence_before,time_before,self.env.stepper.time)
                full=summarize_world_pose_history(history,time_before,self.env.stepper.time)
                forward=[float(item['forward_velocity']) for item in full.get('world_forward_velocity_samples',())]
                angular=[float(item['angular_velocity']) for item in full.get('world_angular_velocity_samples',())]
                body_history_summary={key:full.get(key) for key in (
                    'world_pose_history_available','world_pose_history_fresh','world_pose_history_dense_enough',
                    'world_pose_sample_count','world_pose_history_max_gap','world_start_forward_velocity',
                    'world_end_forward_velocity','world_start_angular_velocity','world_end_angular_velocity',
                    'world_velocity_zero_crossing','world_velocity_zero_crossing_time')}
                body_history_summary.update(
                    world_max_abs_forward_velocity=max(map(abs,forward),default=0.),
                    world_max_abs_angular_velocity=max(map(abs,angular),default=0.),
                    source=full.get('world_pose_source'),
                    velocity_method=full.get('world_pose_velocity_method'))
            except Exception as telemetry_error:
                body_history_summary={'world_pose_history_available':False,
                                      'error':str(telemetry_error)}
        body_history_ok=bool(body_history_summary and
            body_history_summary.get('world_pose_history_fresh') and
            body_history_summary.get('world_pose_history_dense_enough'))
        body_end_forward=(None if not body_history_summary else
            body_history_summary.get('world_end_forward_velocity'))
        body_end_angular=(None if not body_history_summary else
            body_history_summary.get('world_end_angular_velocity'))
        from aero_ai_studio.gazebo.entity_controller import VELOCITY_DIRECTION_EPSILON
        body_residual_velocity_stopped=bool(body_history_ok and
            body_end_forward is not None and body_end_angular is not None and
            math.isfinite(float(body_end_forward)) and math.isfinite(float(body_end_angular)) and
            abs(float(body_end_forward))<=VELOCITY_DIRECTION_EPSILON and
            abs(float(body_end_angular))<=VELOCITY_DIRECTION_EPSILON)
        reset_trace=dict(getattr(self.env,'last_reset_trace',{}))
        reset_trace.update(post_settle_body_pose=after,post_settle_simulation_time=self.env.stepper.time,
            body_settle_translation=displacement,body_settle_yaw=yaw_drift,
            body_residual_motion=body_history_summary,
            wheel_odometry_after_reset=odometry,sensor_fresh=sensor_fresh,
            odometry_contract=odometry_contract,
            contact_state=dict(getattr(getattr(self.env,'contacts',None),'state',{})))
        evidence={'seed':seed,'zero_command':dict(self.env.controller.last_published_command or {}),
            'settle_simulation_duration':duration,'pose_before_settle':before,'pose_after_settle':after,
            'start_pose_error':start_error,'zero_command_displacement':displacement,'zero_command_yaw_drift':yaw_drift,
            'sensor_sequence_before':sequence_before,'sensor_sequence_after':None if frame is None else frame.sequence,
            'sensor_timestamp':None if frame is None else frame.sensor_timestamp,
            'sensor_age_ms':None if frame is None else frame.age_ms,'sensor_fresh':sensor_fresh,
            'odometry':odometry,'odometry_fresh_and_stopped':odometry_fresh,
            'odometry_contract':odometry_contract,
            'odometry_epoch':{
                'epoch_type':epoch_type,
                'baseline_receive_sequence':sequence_after_reset,
                'selected_receive_sequence':None if odometry is None else odometry.get('receive_sequence'),
                'receive_sequence_after_epoch':odometry_contract['receive_sequence_after_epoch'],
                'baseline_source':reset_attempt.get('odometry_epoch_source',
                    'world_reset_all_cursor' if epoch_type=='world_control_reset_all' else None)},
            'wheel_odometry_after_reset':odometry,
            'body_settle_translation':displacement,'body_settle_yaw':yaw_drift,
            'body_residual_motion':body_history_summary,
            'world_pose_history_sufficient':body_history_ok,
            'body_end_forward_velocity':body_end_forward,
            'body_end_angular_velocity':body_end_angular,
            'body_residual_velocity_stopped':body_residual_velocity_stopped,
            'contact':contacts[0].to_dict() if contacts else None,
            'contact_state':dict(getattr(getattr(self.env,'contacts',None),'state',{})),
            'process_reused':self.episodes_started>0,
            'restart_fallback_count':self.restart_fallbacks,
            'restart_fallback_used':False,
            'normal_reset_pass':False,
            'normal_reset_failure_reason':None,
            'reset_method':('world_control_reset_model_only_after_quiescence'
                if persistent_reset else 'fresh_process_initialization'),
            'reset_rpc':(None if self._active_reset_attempt is None else
                self._active_reset_attempt.get('model_only_reset_evidence',
                    self._active_reset_attempt.get('world_reset_evidence'))),
            'pre_reset_quiescence':(None if not persistent_reset else
                reset_attempt.get('pre_reset_quiescence')),
            'contact_readiness':(None if not persistent_reset else
                dict(reset_attempt.get('contact_readiness',{}))),
            'odometry_epoch_policy':('preserve_monotonic_sim_time_and_require_new_receive_sequence'
                if persistent_reset else 'fresh_process_subscription_epoch'),
            'set_pose_response':dict(getattr(self.env.controller,'last_pose_request',{})),
            'reset_trace':reset_trace}
        if hasattr(self.env,'last_reset_trace'):
            self.env.last_reset_trace=dict(reset_trace)
        if self._active_reset_attempt is not None:
            self._active_reset_attempt['settle_evidence']=dict(evidence)
        reset_failures=[]
        if displacement>.02 or yaw_drift>.02 or start_error>.02:
            reset_failures.append('pose_or_body_settle_outside_existing_tolerance')
        if not sensor_fresh:reset_failures.append('fresh_sensor_required')
        if not odometry_fresh:reset_failures.append('odometry:'+str(odometry_contract['failure_reason']))
        if not body_history_ok or not body_residual_velocity_stopped:
            reset_failures.append('actual_world_body_residual_velocity_unavailable_or_moving')
        if contacts:reset_failures.append('contact_during_zero_command_reset_settle')
        evidence['normal_reset_pass']=not reset_failures
        evidence['normal_reset_failure_reason']=None if not reset_failures else '; '.join(reset_failures)
        if reset_failures:
            if self._active_reset_attempt is not None:
                self._active_reset_attempt['settle_evidence']=dict(evidence)
            category='stale_sensor' if 'fresh_sensor_required' in reset_failures else 'reset_isolation'
            error=GazeboTrainingInfrastructureError(category,
                f'Gazebo normal reset failed ({evidence["normal_reset_failure_reason"]}): {evidence}')
            error.reset_failure_reasons=tuple(reset_failures)
            raise error
        if hasattr(self.env,'contacts'):self.env.contacts.reset(self.env.stepper.time)
        observation=self.env.get_agent_observation('sensor',2)
        evidence['observation_contract']=self._require_actual_sensor(observation)
        if self._active_reset_attempt is not None:
            evidence['primary_reset_attempt']=dict(self._active_reset_attempt)
        self.last_reset_evidence=evidence;self.reset_evidence.append(evidence)
        self.episodes_started+=1
        return self.env.get_observation()

    def reset(self,seed=None):
        attempt={'seed':seed,'attempted':True,'reset_method':None,'normal_reset_pass':False,
                 'normal_reset_failure_reason':None,'restart_fallback_used':False,
                 'pre_reset_body_pose':dict(getattr(self.env,'pose',{}) or {}),
                 'pre_reset_simulation_time':getattr(getattr(self.env,'stepper',None),'time',None),
                 'reset_epoch_sim_time':0.}
        if hasattr(self.env,'controller') and hasattr(self.env,'transport'):
            topic=getattr(self.env.controller,'pose_topic',None)
            attempt['pose_sequence_before']=self.env.transport.cursor(topic) if topic and hasattr(self.env.transport,'cursor') else None
            odom_topic=getattr(self.env,'odometry_topic',None)
            attempt['odometry_sequence_before_reset']=(self.env.transport.cursor(odom_topic)
                if odom_topic and hasattr(self.env.transport,'cursor') else None)
        self._active_reset_attempt=attempt
        try:
            if self.episodes_started>0:
                attempt['persistent_reset']=True
                attempt['reset_method']='world_control_reset_model_only_after_quiescence'
                attempt['pre_reset_quiescence']=self._pre_reset_quiescence()
                # Settle with world-body evidence before pausing. Do not use
                # reset.all: actual host validation showed it loses Contact.
                self.env.stepper.pause()
                attempt['odometry_sequence_before_reset']=self.env.transport.cursor(
                    self.env.odometry_topic)
                attempt['sensor_sequence_before_reset']=self.env.transport.cursor(
                    self.env.sensors.topic)
                attempt['reset_epoch_sim_time']=float(self.env.stepper.time)
                attempt['model_only_reset_evidence']=self.env.stepper.reset_model_only()
                attempt['reset_epoch_sim_time']=float(
                    attempt['model_only_reset_evidence']['after_sim_time'])
                odom_topic=getattr(self.env,'odometry_topic',None)
                attempt['odometry_sequence_after_reset']=(self.env.transport.cursor(odom_topic)
                    if odom_topic and hasattr(self.env.transport,'cursor') else None)
                attempt['odometry_epoch_source']='world_reset_model_only_cursor'
                attempt['sensor_epoch_policy']='simulation_time_preserved; require advancing native sensor sample'
                if hasattr(self.env,'contacts'):
                    self.env.contacts.reset(self.env.stepper.time)
                attempt['contact_epoch_after_model_only']=dict(
                    getattr(self.env.contacts,'state',{}))
                self._contact_readiness('after_model_only')
            else:
                attempt['reset_method']='fresh_process_initialization'
                attempt['odometry_sequence_after_reset']=attempt.get('odometry_sequence_before_reset')
                attempt['odometry_epoch_source']='pre-reset-subscription-cursor'
            observation=self._reset_once(seed)
            attempt['normal_reset_pass']=True
            self.last_reset_evidence['primary_reset_attempt']=dict(attempt)
            self.last_reset_evidence['normal_reset_pass']=True
            self.reset_evidence[-1].update(self.last_reset_evidence)
            self._active_reset_attempt=None
            return observation
        except Exception as primary:
            exact_failures=getattr(primary,'reset_failure_reasons',None)
            attempt['normal_reset_failure_reason']=('; '.join(exact_failures) if exact_failures else
                f'{type(primary).__name__}: {primary}')
            attempt['normal_reset_pass']=False
            if getattr(primary,'pre_reset_quiescence',None) is not None:
                attempt['pre_reset_quiescence']=primary.pre_reset_quiescence
            attempt['failure_initialization_phase']=getattr(self.env,'initialization_phase',None)
            attempt['failure_initialization_checks']=dict(getattr(self.env,'initialization_checks',{}))
            attempt['set_pose_response']=dict(getattr(getattr(self.env,'controller',None),'last_pose_request',{}))
            attempt['published_command']=dict(getattr(getattr(self.env,'controller',None),'last_published_command',{}) or {})
            attempt['step_evidence']=dict(getattr(getattr(self.env,'stepper',None),'last_verification',{}))
            attempt['post_failure_body_pose']=dict(getattr(self.env,'pose',{}) or {})
            attempt['post_failure_simulation_time']=getattr(getattr(self.env,'stepper',None),'time',None)
            frame=getattr(getattr(self.env,'sensors',None),'frame',None)
            attempt['sensor_after_failure']=(None if frame is None else {
                'source':frame.source,'sequence':frame.sequence,'timestamp':frame.sensor_timestamp,
                'age_ms':frame.age_ms})
            attempt['contact_state_after_failure']=dict(getattr(getattr(self.env,'contacts',None),'state',{}))
            if getattr(primary,'category',None)=='incompatible_environment':
                self._active_reset_attempt=None
                raise
            try:
                attempt['wheel_odometry_after_failure']=self.env.read_odometry(
                    self.env.stepper.time-.02,timeout=.05)
            except Exception as telemetry_error:
                attempt['wheel_odometry_after_failure']={'error':str(telemetry_error)}
            try:
                cursor=attempt.get('pose_sequence_before')
                if cursor is not None:
                    end=float(attempt.get('post_failure_simulation_time') or 0.)
                    start=(float(attempt.get('reset_epoch_sim_time') or 0.)
                           if attempt.get('model_only_reset_evidence') else
                           (0. if attempt.get('world_reset_evidence') else
                            float(attempt.get('pre_reset_simulation_time') or 0.)))
                    history=self.env.controller.pose_history_after(cursor,start,end)
                    from aero_ai_studio.gazebo.entity_controller import summarize_world_pose_history
                    attempt['body_residual_motion']=summarize_world_pose_history(history,start,end)
            except Exception as telemetry_error:
                attempt['body_residual_motion']={'available':False,'error':str(telemetry_error)}
            # Reuse the same simulator for normal episodes. Hard restart is only
            # a bounded fallback after reset/settle evidence fails.
            try:
                self.env=self.env.restart(seed);self.restart_fallbacks+=1
                attempt['restart_fallback_used']=True
                attempt['restart_fallback_reason']=attempt['normal_reset_failure_reason']
                observation=self._reset_once_after_restart(seed)
                self.last_reset_evidence['primary_reset_attempt']=dict(attempt)
                self.last_reset_evidence['normal_reset_pass']=False
                self.last_reset_evidence['normal_reset_failure_reason']=attempt['normal_reset_failure_reason']
                self.last_reset_evidence['restart_fallback_used']=True
                self.last_reset_evidence['restart_fallback_reason']=attempt['restart_fallback_reason']
                self.reset_evidence[-1].update(self.last_reset_evidence)
                self.episodes_started+=1
                return observation
            except Exception as fallback:
                raise GazeboTrainingInfrastructureError('reset_isolation',
                    f'Episode reset failed and one process-restart fallback also failed: first={primary}; fallback={fallback}') from fallback
            finally:
                self._active_reset_attempt=None

    def _reset_once_after_restart(self,seed):
        # restart(seed) already performed the validated Environment.reset once;
        # the adapter still checks zero-command settle evidence below.
        return self._check_settle_after_base_reset(seed)

    def _check_settle_after_base_reset(self,seed):
        if self.env.controller.last_command.get('linear',{}).get('x')!=0 or self.env.controller.last_command.get('angular',{}).get('z')!=0:
            raise GazeboTrainingInfrastructureError('reset_isolation','Restart reset did not leave zero command')
        before=dict(self.env.pose);time_before=self.env.stepper.time;sequence_before=self.env.sensors.sequence
        pose_topic=getattr(self.env.controller,'pose_topic',None)
        pose_sequence_before=(self.env.transport.cursor(pose_topic)
            if pose_topic and hasattr(self.env.transport,'cursor') else None)
        odometry_topic=getattr(self.env,'odometry_topic',None)
        odometry_sequence_before=(self.env.transport.cursor(odometry_topic)
            if odometry_topic and hasattr(self.env.transport,'cursor') else None)
        self.env.stepper.step_simulation();self.env._refresh();after=dict(self.env.pose)
        displacement=math.hypot(after['x']-before['x'],after['y']-before['y'])
        yaw_drift=abs(math.atan2(math.sin(after['yaw']-before['yaw']),math.cos(after['yaw']-before['yaw'])))
        frame=self.env.sensors.frame
        if odometry_sequence_before is not None and hasattr(self.env,'read_odometry_after_sequence'):
            odom=self.env.read_odometry_after_sequence(odometry_sequence_before,
                self.env.stepper.time-.02,self.env.stepper.time+.002,timeout=.5)
        else:odom=self.env.read_odometry(self.env.stepper.time-.02)
        contacts=self.env.contacts.poll(self.env.stepper.time) if hasattr(self.env,'contacts') else []
        start=(self.scenario.start[0]+.5,self.scenario.start[1]+.5)
        start_error=math.hypot(after['x']-start[0],after['y']-start[1])
        sensor_fresh=frame is not None and frame.sequence>sequence_before and frame.source=='gazebo_lidar' and frame.age_ms<=self.max_sensor_age_ms
        odom_contract=reset_odometry_contract(odom,reset_epoch_sim_time=0.,
            settle_start_sim_time=time_before,settle_end_sim_time=self.env.stepper.time,
            sequence_before_reset=None,sequence_after_reset=odometry_sequence_before,
            sequence_before_settle=odometry_sequence_before)
        odom_ok=odom_contract['pass']
        body_history_summary=None
        if pose_sequence_before is not None:
            try:
                from aero_ai_studio.gazebo.entity_controller import summarize_world_pose_history
                history=self.env.controller.pose_history_after(pose_sequence_before,time_before,self.env.stepper.time)
                full=summarize_world_pose_history(history,time_before,self.env.stepper.time)
                body_history_summary={key:full.get(key) for key in (
                    'world_pose_history_available','world_pose_history_fresh','world_pose_history_dense_enough',
                    'world_pose_sample_count','world_pose_history_max_gap','world_start_forward_velocity',
                    'world_end_forward_velocity','world_start_angular_velocity','world_end_angular_velocity')}
            except Exception as telemetry_error:
                body_history_summary={'world_pose_history_available':False,'error':str(telemetry_error)}
        from aero_ai_studio.gazebo.entity_controller import VELOCITY_DIRECTION_EPSILON
        body_history_ok=bool(body_history_summary and body_history_summary.get('world_pose_history_fresh') and
                             body_history_summary.get('world_pose_history_dense_enough'))
        body_end_forward=None if not body_history_summary else body_history_summary.get('world_end_forward_velocity')
        body_end_angular=None if not body_history_summary else body_history_summary.get('world_end_angular_velocity')
        body_stopped=bool(body_history_ok and body_end_forward is not None and body_end_angular is not None and
            math.isfinite(float(body_end_forward)) and math.isfinite(float(body_end_angular)) and
            abs(float(body_end_forward))<=VELOCITY_DIRECTION_EPSILON and
            abs(float(body_end_angular))<=VELOCITY_DIRECTION_EPSILON)
        evidence={'seed':seed,'zero_command':dict(self.env.controller.last_published_command or {}),
            'settle_simulation_duration':self.env.stepper.time-time_before,'pose_before_settle':before,'pose_after_settle':after,
            'start_pose_error':start_error,'zero_command_displacement':displacement,'zero_command_yaw_drift':yaw_drift,
            'sensor_sequence_before':sequence_before,'sensor_sequence_after':None if frame is None else frame.sequence,
            'sensor_timestamp':None if frame is None else frame.sensor_timestamp,'sensor_age_ms':None if frame is None else frame.age_ms,
            'sensor_fresh':sensor_fresh,'odometry':odom,'odometry_fresh_and_stopped':odom_ok,
            'odometry_contract':odom_contract,
            'body_residual_motion':body_history_summary,'world_pose_history_sufficient':body_history_ok,
            'body_end_forward_velocity':body_end_forward,'body_end_angular_velocity':body_end_angular,
            'body_residual_velocity_stopped':body_stopped,
            'set_pose_response':dict(getattr(self.env.controller,'last_pose_request',{})),
            'contact_state':dict(getattr(getattr(self.env,'contacts',None),'state',{})),
            'contact':contacts[0].to_dict() if contacts else None,'process_reused':False,
            'restart_fallback_count':self.restart_fallbacks,'restart_fallback_used':True,
            'reset_method':'fresh_process_restart','normal_reset_pass':False,
            'normal_reset_failure_reason':(None if self._active_reset_attempt is None else
                self._active_reset_attempt.get('normal_reset_failure_reason'))}
        if (displacement>.02 or yaw_drift>.02 or start_error>.02 or not sensor_fresh or
            not odom_ok or not body_history_ok or not body_stopped or contacts):
            raise GazeboTrainingInfrastructureError('reset_isolation',f'Restart fallback did not produce isolated episode: {evidence}')
        if hasattr(self.env,'contacts'):self.env.contacts.reset(self.env.stepper.time)
        observation=self.env.get_agent_observation('sensor',2)
        evidence['observation_contract']=self._require_actual_sensor(observation)
        self.last_reset_evidence=evidence;self.reset_evidence.append(evidence)
        return self.env.get_observation()

    def step(self,action):
        started=time.perf_counter();before=dict(self.env.pose)
        before_observation=self.env.get_agent_observation('sensor',2)
        before_evidence=self._require_actual_sensor(before_observation)
        d0=math.dist((before['x'],before['y']),self.env.goal)
        controller=getattr(self.env,'controller',None)
        previous_command=dict(getattr(controller,'last_command',{}) or {})
        requested_command=gazebo_physics_twist(action)
        transition=classify_physics_command_transition(previous_command,requested_command)
        previous_verified_action,requested_verified_action=R2L_VERIFIED_ACTION_PAIR
        r2l_macro_supported=(controller is not None and transition=='ROTATION_TO_LINEAR' and
            action==requested_verified_action and
            previous_command==gazebo_physics_twist(previous_verified_action))
        previous_reversal_action,requested_reversal_action=LINEAR_REVERSAL_VERIFIED_ACTION_PAIR
        reversal_macro_supported=(controller is not None and transition=='LINEAR_REVERSAL' and
            action==requested_reversal_action and
            previous_command==gazebo_physics_twist(previous_reversal_action))
        forward_reversal_previous,forward_reversal_requested=(
            LINEAR_REVERSAL_UP_TO_DOWN_VERIFIED_ACTION_PAIR)
        forward_reversal_macro_supported=(controller is not None and
            transition=='LINEAR_REVERSAL' and action==forward_reversal_requested and
            previous_command==gazebo_physics_twist(forward_reversal_previous))
        if r2l_macro_supported:
            return self._step_r2l_macro(action,started,before,before_observation,
                                         before_evidence,d0,previous_command,requested_command,
                                         float(self.env.stepper.time))
        if reversal_macro_supported:
            return self._step_linear_reversal_macro(action,started,before,before_observation,
                before_evidence,d0,previous_command,requested_command,float(self.env.stepper.time))
        if forward_reversal_macro_supported:
            return self._step_linear_reversal_macro(action,started,before,before_observation,
                before_evidence,d0,previous_command,requested_command,float(self.env.stepper.time),
                activation_pair='UP_TO_DOWN',previous_action=forward_reversal_previous)
        l2r_previous,l2r_requested=LINEAR_TO_ROTATION_DOWN_TO_LEFT_VERIFIED_ACTION_PAIR
        down_to_left_macro_supported=(controller is not None and
            transition=='LINEAR_TO_ROTATION' and action==l2r_requested and
            previous_command==gazebo_physics_twist(l2r_previous))
        if down_to_left_macro_supported:
            return self._step_down_to_left_macro(action,started,before,before_observation,
                before_evidence,d0,previous_command,requested_command,float(self.env.stepper.time))
        l2r_previous,l2r_requested=LINEAR_TO_ROTATION_UP_TO_RIGHT_VERIFIED_ACTION_PAIR
        up_to_right_macro_supported=(controller is not None and
            transition=='LINEAR_TO_ROTATION' and action==l2r_requested and
            previous_command==gazebo_physics_twist(l2r_previous))
        if up_to_right_macro_supported:
            return self._step_up_to_right_macro(action,started,before,before_observation,
                before_evidence,d0,previous_command,requested_command,float(self.env.stepper.time))
        r2l_previous,r2l_requested=ROTATION_TO_LINEAR_LEFT_TO_UP_VERIFIED_ACTION_PAIR
        left_to_up_macro_supported=(controller is not None and
            transition=='ROTATION_TO_LINEAR' and action==r2l_requested and
            previous_command==gazebo_physics_twist(r2l_previous))
        if left_to_up_macro_supported:
            return self._step_left_to_up_macro(action,started,before,before_observation,
                before_evidence,d0,previous_command,requested_command,float(self.env.stepper.time))
        result=self._step_direct(action,started,before,before_observation,before_evidence,d0,
                                 (float(self.env.stepper.time) if hasattr(self.env,'stepper') else None))
        if transition in ('ROTATION_TO_LINEAR','LINEAR_REVERSAL','LINEAR_TO_ROTATION'):
            self.env.telemetry.setdefault('gazebo_dqn_training',{})['control_executor_activation']={
                'transition_type':transition,'active':False,
                'reason':('command pair is outside the actual-verified exact ROTATION_TO_LINEAR pairs'
                    if transition=='ROTATION_TO_LINEAR' else
                    'command pair is outside the actual-verified exact LINEAR_REVERSAL pairs'
                    if transition=='LINEAR_REVERSAL' else
                    'command pair is outside the actual-verified exact DOWN-to-LEFT L2R boundary')}
        return result

    def _step_direct(self,action,started,before,before_observation,before_evidence,d0,start_sim):
        """Unchanged one-step production path for every non-R2L transition."""
        try:result=self.env.step(action)
        except SensorTimeoutError as error:
            raise GazeboTrainingInfrastructureError('stale_sensor',str(error)) from error
        except PhysicalControlFailure:
            # Preserve the typed physical outcome and its actual validator,
            # command, odometry, and contact evidence for the trainer/CLI.
            raise
        except Exception as error:
            raise GazeboTrainingInfrastructureError('service_failure',str(error)) from error
        after=dict(self.env.pose);d1=math.dist((after['x'],after['y']),self.env.goal)
        after_observation=self.env.get_agent_observation('sensor',2)
        after_evidence=self._require_actual_sensor(after_observation,before_evidence['sequence'])
        if 'collision' in result.reason and self.env.collision_event is None:
            raise GazeboTrainingInfrastructureError('contact_evidence','Gazebo PHYSICS collision was reported without an actual contact event')
        self.last_reward_components=gazebo_dqn_reward(d0,d1,result.reason)
        reward=self.last_reward_components['total']
        elapsed=(float(self.env.stepper.time)-float(start_sim)
                 if start_sim is not None and hasattr(self.env,'stepper') else
                 float(self.env.telemetry.get('action_transition',{}).get('simulation_duration',
                     NOMINAL_DISCOUNT_TIME_UNIT_SECONDS)))
        if not math.isfinite(elapsed) or elapsed<=0.:
            elapsed=float(self.env.telemetry.get('action_transition',{}).get('simulation_duration',
                NOMINAL_DISCOUNT_TIME_UNIT_SECONDS))
        elapsed_units=elapsed/NOMINAL_DISCOUNT_TIME_UNIT_SECONDS
        self.env.last_reward_components=dict(self.last_reward_components)
        self.env.telemetry['gazebo_dqn_training']={'goal_distance_before':d0,'goal_distance_after':d1,
            'reward_components':dict(self.last_reward_components),'training_action_wall_seconds':time.perf_counter()-started,
            'sensor_before':before_evidence,'sensor_after':after_evidence,
            'physics_validation':self.env.telemetry.get('pose_validation'),
            'contact':None if self.env.collision_event is None else self.env.collision_event.to_dict()}
        self.last_step_seconds=time.perf_counter()-started
        return StepResult(result.observation,reward,result.terminated,result.truncated,result.reason,
                          elapsed_execution_time=elapsed,elapsed_discount_units=elapsed_units)

    def _step_down_to_left_macro(self,action,started,before,before_observation,before_evidence,d0,
                                 previous_command,requested_command,start_sim):
        """Execute the exact actual-verified DOWN→LEFT L2R macro as one decision."""
        return self._step_executor_macro(action,started,before,before_observation,
            before_evidence,d0,previous_command,requested_command,start_sim,
            executor_type=GazeboDownToLeftControlExecutor,transition_type='LINEAR_TO_ROTATION',
            activation_pair='DOWN_TO_LEFT',braking_phase='BRAKE_LINEAR',
            acquisition_phase='ACQUIRE_ANGULAR')

    def _step_left_to_up_macro(self,action,started,before,before_observation,before_evidence,d0,
                               previous_command,requested_command,start_sim):
        """Execute the exact actual-verified LEFT→UP R2L macro as one decision."""
        return self._step_executor_macro(action,started,before,before_observation,
            before_evidence,d0,previous_command,requested_command,start_sim,
            executor_type=GazeboLeftToUpControlExecutor,transition_type='ROTATION_TO_LINEAR',
            activation_pair='LEFT_TO_UP',braking_phase='BRAKE_ANGULAR',
            acquisition_phase='ACQUIRE_LINEAR')

    def _step_up_to_right_macro(self,action,started,before,before_observation,before_evidence,d0,
                                previous_command,requested_command,start_sim):
        """Execute the exact actual-verified UP→RIGHT L2R macro as one decision."""
        return self._step_executor_macro(action,started,before,before_observation,
            before_evidence,d0,previous_command,requested_command,start_sim,
            executor_type=GazeboUpToRightControlExecutor,transition_type='LINEAR_TO_ROTATION',
            activation_pair='UP_TO_RIGHT',braking_phase='BRAKE_LINEAR',
            acquisition_phase='ACQUIRE_ANGULAR')

    def _step_r2l_macro(self,action,started,before,before_observation,before_evidence,d0,
                       previous_command,requested_command,start_sim):
        return self._step_executor_macro(action,started,before,before_observation,
            before_evidence,d0,previous_command,requested_command,start_sim,
            executor_type=GazeboControlExecutor,transition_type='ROTATION_TO_LINEAR',
            activation_pair='RIGHT_TO_DOWN',braking_phase='BRAKE_ANGULAR')

    def _step_linear_reversal_macro(self,action,started,before,before_observation,before_evidence,d0,
                                    previous_command,requested_command,start_sim,*,
                                    activation_pair='DOWN_TO_UP',previous_action='down'):
        """Execute one exact-pair actual-verified linear reversal macro."""
        return self._step_executor_macro(action,started,before,before_observation,
            before_evidence,d0,previous_command,requested_command,start_sim,
            executor_type=GazeboLinearReversalControlExecutor,transition_type='LINEAR_REVERSAL',
            activation_pair=activation_pair,braking_phase='BRAKE_LINEAR',
            executor_kwargs={'previous_action':previous_action,'requested_action':action})

    def _step_executor_macro(self,action,started,before,before_observation,before_evidence,d0,
                             previous_command,requested_command,start_sim,*,executor_type,
                             transition_type,activation_pair,braking_phase,
                             acquisition_phase='ACQUIRE_LINEAR',
                             executor_kwargs=None):
        """Adapt a verified ControlExecutor plan into one RL macro transition."""
        from aero_ai_studio.gazebo.entity_controller import summarize_world_pose_history

        action_transition=dict(self.env.telemetry.get('action_transition') or {})
        prehistory=action_transition.get('world_pose_history_summary')
        if prehistory is None:
            prehistory=summarize_world_pose_history([],float(self.env.stepper.time)-.1,
                                                    float(self.env.stepper.time))
        request=ControlExecutionRequest(action,previous_command,requested_command,
                                        transition_type=transition_type)
        plan=plan_control_execution(request)
        accumulator=MacroRewardAccumulator(self.gamma,NOMINAL_DISCOUNT_TIME_UNIT_SECONDS)
        reward_chunks=[]
        prior_sequence=before_evidence['sequence']

        def record_braking_chunk(row):
            nonlocal prior_sequence
            pose_before=dict(row['pose_before']);pose_after=dict(row['pose_after'])
            d_before=math.dist((pose_before['x'],pose_before['y']),self.env.goal)
            d_after=math.dist((pose_after['x'],pose_after['y']),self.env.goal)
            self.env.distance+=math.hypot(pose_after['x']-pose_before['x'],
                                          pose_after['y']-pose_before['y'])
            contacts=list(row.get('collision_events') or [])
            if hasattr(self.env,'contacts'):
                self.env.telemetry['contacts']=dict(self.env.contacts.state)
            if contacts:
                self.env.collision_event=contacts[0]
            observation=self.env.get_agent_observation('sensor',2)
            sensor_contract=self._require_actual_sensor(observation,prior_sequence)
            prior_sequence=sensor_contract['sequence']
            reason=self._task_reason_after_chunk(pose_after,contacts)
            components=gazebo_dqn_reward(d_before,d_after,reason)
            duration=float(row['simulation_end'])-float(row['simulation_start'])
            terminal=reason in ('goal','danger_zone') or 'collision' in reason
            accumulator.add_chunk(components['total'],duration,terminal=terminal)
            chunk={'phase':braking_phase,'simulation_start':row['simulation_start'],
                'simulation_end':row['simulation_end'],'elapsed_execution_time':duration,
                'reward_components':components,'reward':components['total'],'reason':reason,
                'terminated':terminal,'truncated':False,'sensor_contract':sensor_contract,
                'collision_events':contacts}
            reward_chunks.append(chunk)
            return {'reason':reason,'terminated':terminal,'truncated':False,
                    'collision':bool(contacts),'collision_events':contacts,
                    'reward':components['total'],'reward_components':components,
                    'elapsed_execution_time':duration,'sensor_contract':sensor_contract}

        executor=executor_type(self,pre_braking_history=prehistory,
                               **(executor_kwargs or {}))
        try:
            execution=executor.execute_plan(plan,on_braking_chunk=record_braking_chunk)
        except SensorTimeoutError as error:
            raise GazeboTrainingInfrastructureError('stale_sensor',str(error)) from error
        except GazeboTrainingInfrastructureError:
            raise
        except PhysicalControlFailure:
            raise
        except Exception as error:
            raise GazeboTrainingInfrastructureError('service_failure',str(error)) from error

        # The acquisition phase uses _step_direct through executor.step(),
        # because braking has set the controller's previous action to zero.
        acquisition=execution.step_result
        if acquisition is not None:
            acquisition_duration=float(acquisition.elapsed_execution_time or 0.)
            accumulator.add_chunk(acquisition.reward,acquisition_duration,
                terminal=bool(acquisition.terminated or acquisition.truncated))
            reward_chunks.append({'phase':acquisition_phase,
                'simulation_start':start_sim+sum(x['elapsed_execution_time'] for x in reward_chunks),
                'simulation_end':float(self.env.stepper.time),
                'elapsed_execution_time':acquisition_duration,'reward':acquisition.reward,
                'reward_components':dict(self.last_reward_components),
                'reason':acquisition.reason,'terminated':acquisition.terminated,
                'truncated':acquisition.truncated})
        elif execution.status in (ControlExecutionStatus.PHYSICAL_CONTROL_FAILURE,
                                   ControlExecutionStatus.INFRASTRUCTURE_FAILURE):
            evidence=execution.to_dict()
            if execution.status is ControlExecutionStatus.PHYSICAL_CONTROL_FAILURE:
                raise PhysicalControlFailure(execution.reason or f'{transition_type} physical execution failed',
                    evidence={'execution_evidence':evidence})
            raise GazeboTrainingInfrastructureError(execution.failure_category or 'control_executor',
                execution.reason or f'{transition_type} executor infrastructure failure')
        elif execution.status is ControlExecutionStatus.INCONCLUSIVE:
            raise PhysicalControlFailure(execution.reason or f'{transition_type} physical precondition was inconclusive',
                evidence={'execution_evidence':execution.to_dict()})
        elif execution.status is ControlExecutionStatus.EXECUTED and acquisition is None:
            raise GazeboTrainingInfrastructureError('control_executor_contract',
                f'{transition_type} executor reported success without the production acquisition StepResult')

        macro=accumulator.result()
        # Terminal collision/goal/danger during braking ends the one agent
        # decision without sending ACQUIRE_LINEAR.
        if acquisition is None:
            reason=execution.reason or 'task_terminal_during_braking'
            terminated=execution.status in (ControlExecutionStatus.COLLISION,
                                             ControlExecutionStatus.TASK_TERMINAL)
            truncated=False
            self.env.steps+=1
            self.env.done=terminated or truncated
            if hasattr(self.env.lifecycle.__class__,'PAUSED'):
                self.env.lifecycle=self.env.lifecycle.__class__.PAUSED
            self.last_reward_components={'macro_reward':macro.reward,'total':macro.reward,
                                         'chunks':[dict(x['reward_components']) for x in reward_chunks]}
            self.env.last_reward_components=dict(self.last_reward_components)
            observation=self.env.get_observation()
        else:
            reason=acquisition.reason;terminated=acquisition.terminated;truncated=acquisition.truncated
            observation=acquisition.observation
            self.last_reward_components={'macro_reward':macro.reward,'total':macro.reward,
                                         'chunks':[dict(x['reward_components']) for x in reward_chunks]}
            self.env.last_reward_components=dict(self.last_reward_components)

        elapsed=float(self.env.stepper.time)-start_sim
        elapsed_units=elapsed/NOMINAL_DISCOUNT_TIME_UNIT_SECONDS
        execution_evidence=execution.to_dict()
        verified_pairs={'RIGHT_TO_DOWN':R2L_VERIFIED_ACTION_PAIR,
            'DOWN_TO_UP':LINEAR_REVERSAL_VERIFIED_ACTION_PAIR,
            'UP_TO_DOWN':LINEAR_REVERSAL_UP_TO_DOWN_VERIFIED_ACTION_PAIR,
            'DOWN_TO_LEFT':LINEAR_TO_ROTATION_DOWN_TO_LEFT_VERIFIED_ACTION_PAIR,
            'LEFT_TO_UP':ROTATION_TO_LINEAR_LEFT_TO_UP_VERIFIED_ACTION_PAIR,
            'UP_TO_RIGHT':LINEAR_TO_ROTATION_UP_TO_RIGHT_VERIFIED_ACTION_PAIR}
        verified_pair=verified_pairs[activation_pair]
        previous_action=verified_pair[0]
        execution_evidence.update(agent_intent=action,previous_action=previous_action,
            transition_type=transition_type,
            previous_command=dict(previous_command),requested_command=dict(requested_command),
            production_macro=True,activation_pair=activation_pair,
            execution_phases=execution_evidence.get('execution_evidence',{}).get('phase_evidence',[]),
            macro_reward=macro.reward,reward_chunks=reward_chunks,
            elapsed_execution_time=elapsed,elapsed_discount_units=elapsed_units,
            control_chunk_count=len(reward_chunks),physical_status=execution.status.value,
            collision=execution.status is ControlExecutionStatus.COLLISION,
            decision_reference=None)
        training_telemetry=dict(self.env.telemetry.get('gazebo_dqn_training') or {})
        training_telemetry.update(agent_intent=action,previous_action=previous_action,
            production_macro=True,transition_type=transition_type,
            activation_pair=activation_pair,
            control_executor_activation={'transition_type':transition_type,'active':True,
                'activation_pair':activation_pair,'verified_action_pair':list(verified_pair)},
            macro_reward=macro.reward,elapsed_execution_time=elapsed,
            elapsed_discount_units=elapsed_units,control_chunk_count=len(reward_chunks),
            execution_evidence=execution_evidence)
        self.env.telemetry['gazebo_dqn_training']=training_telemetry
        self.last_step_seconds=time.perf_counter()-started
        return StepResult(observation,macro.reward,terminated,truncated,reason,
            elapsed_execution_time=elapsed,elapsed_discount_units=elapsed_units,
            execution_evidence=execution_evidence)

    def _task_reason_after_chunk(self,pose,contacts):
        if contacts:
            return 'collision'
        if math.dist((pose['x'],pose['y']),self.env.goal)<=self.goal_radius:
            return 'goal'
        danger=any(o.type=='danger_zone' and
            math.hypot(pose['x']-(o.position[0]+.5),pose['y']-(o.position[1]+.5))<.5
            for o in self.scenario.objects)
        return 'danger_zone' if danger else 'moving'

    def get_metrics(self):
        result=self.env.get_metrics();result['reward_components']=dict(self.last_reward_components)
        result['reset_evidence']=dict(self.last_reset_evidence)
        return result

    def get_observation(self):return self.env.get_observation()
    def get_agent_observation(self,mode='sensor',radius=2):return self.env.get_agent_observation(mode,radius)
    def get_state(self):return self.env.get_state()
    def close(self):
        try:
            if hasattr(self.env,'controller') and self.env.process and self.env.process.poll() is None:
                self.env.controller.stop_agent()
        finally:self.env.close()
