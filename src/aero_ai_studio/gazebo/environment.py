from __future__ import annotations
from pathlib import Path
import math
import random
import time
from aero_ai_studio.gazebo.diagnostics import gazebo_status
from aero_ai_studio.gazebo.world_generator import GazeboWorldGenerator
from aero_ai_studio.gazebo.process_manager import GazeboProcessManager
from aero_ai_studio.gazebo.transport import HarmonicTransport
from aero_ai_studio.gazebo.stepping import GazeboStepper
from aero_ai_studio.gazebo.entity_controller import GazeboEntityController,summarize_world_pose_history
from aero_ai_studio.gazebo.sensor_provider import RangeSensorProvider
from aero_ai_studio.simulation.base import PhysicalControlFailure,SimulationCapabilities,StepResult
from aero_ai_studio.observation.models import Observation
from aero_ai_studio.observation.canonical import CanonicalSensorObservation
from aero_ai_studio.training.rewards import reward_components
from aero_ai_studio.gazebo.contracts import SimulationState
from aero_ai_studio.core.storage import read_json
from aero_ai_studio.simulation.action_mapping import (
    classify_physics_command_transition,
    physics_transition_requires_world_pose_history,
)


class GazeboEnvironment:
    """Actual Gazebo service/laser loop; no surrogate GridWorld or invented sensor fallback."""
    capabilities=SimulationCapabilities(True,True,True,True)

    def __init__(self,scenario,max_steps=200,root: Path | None=None,*,transport=None,
                 gui=False,dt=.1,step_size=1.,goal_radius=.45,timeout=10,control_mode='KINEMATIC',max_sensor_age_ms=20,
                 allow_geometric_fallback=True,capture_world_pose_history=False,
                 retain_world_pose_history=False):
        scenario.validate()
        if dt<=0 or step_size<=0 or goal_radius<=0:raise ValueError('Invalid Gazebo timing/geometry')
        self.scenario,self.max_steps=scenario,max_steps
        self.root=root or Path.cwd()/'generated_worlds'
        self.transport=transport
        self.injected=transport is not None
        self.manager=GazeboProcessManager()
        self.detected=gazebo_status(probe=False)
        self.gui,self.dt,self.step_size,self.goal_radius,self.timeout=gui,dt,step_size,goal_radius,timeout
        self.world=None
        self.world_name=None
        self.pose=None
        self.observation=None
        self.steps=0
        self.done=False
        self.closed=False
        self.reward_version='legacy'
        self.last_reward_components={}
        self.minimum_clearance=float('inf')
        self.previous_action=None
        self.goal=(scenario.goal[0]+.5,scenario.goal[1]+.5)
        self.dynamic=[]
        self.distance=0.
        if control_mode not in ('KINEMATIC','PHYSICS'):raise ValueError('Unknown control mode')
        if control_mode=='PHYSICS' and scenario.dynamic_objects:raise ValueError('V0.7 physics smoke is static-only until actual runtime validation passes')
        self.control_mode=control_mode
        self.max_sensor_age_ms=max_sensor_age_ms
        self.allow_geometric_fallback=allow_geometric_fallback
        self.capture_world_pose_history=bool(capture_world_pose_history)
        self.retain_world_pose_history=bool(retain_world_pose_history)
        self.lifecycle=SimulationState.STOPPED
        self.last_error=None
        self.collision_event=None
        self.contact_topic=None
        self.discovery={}
        self.telemetry={}
        self.actual_world={}

    @property
    def process(self):return self.manager.process
    @property
    def training_available(self):return self.injected or self.detected['available']

    def launch(self,gui=None):
        try:return self._launch(gui)
        except Exception as error:
            self.lifecycle=SimulationState.ERROR;self.last_error=str(error)
            raise

    def _launch(self,gui=None):
        status=gazebo_status()
        self.detected=status
        if not status['available']:return status
        if self.process and self.process.poll() is None:return self.get_state()
        self.lifecycle=SimulationState.STARTING
        self.world=GazeboWorldGenerator().generate(self.scenario,self.root,closed_loop=True,control_mode=self.control_mode)
        self.world_name=self.world.parent.name
        self.manager.launch(self.world,self.gui if gui is None else gui,paused=True)
        return self.get_state()

    def _connect(self):
        if not self.world:
            if self.injected:
                self.world=GazeboWorldGenerator().generate(self.scenario,self.root,closed_loop=True,control_mode=self.control_mode)
                self.world_name=self.world.parent.name
            else:
                status=self.launch()
                if not status.get('available'):raise RuntimeError(status['detail'])
        if self.transport is None:self.transport=HarmonicTransport(self.manager.partition,self.timeout)
        metadata=read_json(self.world.with_name('metadata.json'))
        self.agent_entity=metadata['agent_entity']
        if not self.injected:
            from aero_ai_studio.gazebo.discovery import discover
            from aero_ai_studio.gazebo.diagnostics import gazebo_status
            deadline=time.monotonic()+self.timeout
            while True:
                self.discovery=discover(gazebo_status(probe=False)['executable'],self.manager.partition)
                if self.world_name in self.discovery['worlds'] and f'/world/{self.world_name}/pose/info' in self.discovery['topics']:break
                if time.monotonic()>=deadline:raise TimeoutError('Expected generated world/control service/pose topic not discovered')
                time.sleep(.1)
        if self.control_mode=='PHYSICS':
            from aero_ai_studio.gazebo.physics_controller import PhysicsEntityController
            self.controller=PhysicsEntityController(self.transport,self.world_name,self.agent_entity,topic=metadata['command_topic'])
            self.odometry_topic=f'/model/{self.agent_entity}/odometry'
            self.transport.subscribe(self.odometry_topic,'Odometry')
            # Capture the process-local receive epoch at subscription setup,
            # before reset/set-pose progression can produce episode samples.
            self.odometry_sequence_at_subscription=self.transport.cursor(self.odometry_topic)
            self.odometry_epoch_source='fresh_process_initialization'
            self.contact_topic=metadata['contact_topic']
            # Older SDF used sensor/topic, ignored by Sim 8 Contact. Accept its
            # actually discovered scoped topic instead of subscribing blindly.
            scoped=f'/world/{self.world_name}/model/{self.agent_entity}/link/body/sensor/body_contacts/contact'
            if not self.injected and self.contact_topic not in self.discovery['topics'] and scoped in self.discovery['topics']:
                self.contact_topic=scoped

        else:self.controller=GazeboEntityController(self.transport,self.world_name,self.agent_entity,step_size=self.step_size)
        self.stepper=GazeboStepper(self.transport,self.world_name,dt=self.dt,timeout=self.timeout)
        self.sensors=RangeSensorProvider(self.transport,self.world_name,self.goal,self.timeout,physics=self.control_mode=='PHYSICS',
                                         max_sensor_age_ms=self.max_sensor_age_ms,topic=metadata['sensor_topic'])
        self.sensors.start()
        # prepare() checks entity readiness from the paused-world pose stream.
        # Reset application is checked again after its first fixed step.

    def prepare_contacts(self):
        if self.contact_topic and not hasattr(self,'contacts'):
            from aero_ai_studio.gazebo.contact_provider import ContactProvider
            self.contacts=ContactProvider(self.transport,self.contact_topic,self.agent_entity,self.timeout)

    def prepare(self):
        """Observe the loaded world before any reset mutation or physics step."""
        if self.closed:raise RuntimeError('Closed Gazebo environment; create a new instance')
        if not hasattr(self,'controller'):self._connect()
        deadline=time.monotonic()+self.timeout
        delay=.05
        while True:
            try:return self.controller.get_pose(timeout=max(0,deadline-time.monotonic()))
            except RuntimeError as error:
                if 'Expected Gazebo entity not found in pose frame:' not in str(error):raise
                remaining=deadline-time.monotonic()
                if remaining<=0:raise TimeoutError('World pose stream did not contain '+self.agent_entity) from error
                time.sleep(min(delay,remaining));delay=min(delay*2,.2)

    def reset(self,seed=None):
        try:return self._reset(seed)
        except Exception as error:
            self.lifecycle=SimulationState.ERROR;self.last_error=str(error)
            raise

    def _reset(self,seed=None):
        if self.closed:raise RuntimeError('Closed Gazebo environment; create a new instance')
        self.initialization_phase='world_ready'
        self.initialization_checks={}
        self.prepare()
        self.last_reset_trace={'seed':seed,'pre_reset_body_pose':dict(getattr(self,'pose',{}) or {})}
        self.initialization_phase='contact_channel'
        try:self.prepare_contacts()
        except Exception:
            self.initialization_checks['contact_channel']='FAIL'
            raise
        if self.contact_topic:self.initialization_checks['contact_channel']='PASS'
        self.initialization_phase='pause'
        self.stepper.pause()
        self.steps=0
        self.done=False
        self.previous_action=None
        self.minimum_clearance=float('inf')
        self.distance=0.
        rng=random.Random(self.scenario.seed if seed is None else seed)
        self.goal=(self.scenario.goal[0]+.5,self.scenario.goal[1]+.5)
        if self.scenario.randomization.get('goal_position'):
            blocked={o.position for o in self.scenario.objects}
            choices=[(x+.5,y+.5) for x in range(self.scenario.width) for y in range(self.scenario.height)
                     if (x,y) not in blocked|{self.scenario.start}]
            self.goal=rng.choice(choices)
            GazeboEntityController(self.transport,self.world_name,'goal_marker').reset_agent_pose(*self.goal,.05)
        self.sensors.goal=self.goal
        if self.control_mode=='PHYSICS':
            self.initialization_phase='stop_agent'
            self.controller.stop_agent()
        self.initialization_phase='set_pose'
        self.controller.reset_agent_pose(self.scenario.start[0]+.5,self.scenario.start[1]+.5,
                                         .16 if self.control_mode=='PHYSICS' else .25)
        self.last_reset_trace['set_pose_response']=dict(getattr(self.controller,'last_pose_request',{}))
        self.last_reset_trace['requested_pose']=dict(
            getattr(self.controller,'last_pose_request',{}).get('payload',{}))
        self.initialization_checks['set_pose']='PASS'
        self.collision_event=None
        self.dynamic=[]
        for i,o in enumerate(self.scenario.dynamic_objects):
            controller=GazeboEntityController(self.transport,self.world_name,f'moving_proxy_{i}')
            controller.reset_agent_pose(o.position[0]+.5,o.position[1]+.5,.5)
            self.dynamic.append({'controller':controller,'movement':o.movement,'direction':o.direction})
        self.initialization_phase='step_progress'
        self.stepper.step_simulation()
        self.initialization_checks['step_progress']='PASS'
        self.initialization_phase='reset_applied'
        self._refresh()
        self.last_reset_trace['post_set_pose_body_pose']=dict(self.pose)
        self.last_reset_trace['post_set_pose_simulation_time']=self.stepper.time
        if math.hypot(self.pose['x']-(self.scenario.start[0]+.5),self.pose['y']-(self.scenario.start[1]+.5))>.02:
            raise RuntimeError('Gazebo reset pose was not applied')
        self.collision_source='not_evaluated'
        if hasattr(self,'contacts'):
            self.contacts.reset(self.stepper.time)
            self.telemetry.update(collision_event=None,collision_source=self.collision_source,contacts=dict(self.contacts.state))
        self.telemetry.pop('pose_validation',None)
        self.initialization_checks['reset_applied']='PASS'
        self.initialization_phase='ready'
        self.last_reward_components={}
        self.lifecycle=SimulationState.PAUSED
        self.last_error=None
        return self.get_observation()

    def _refresh(self):
        started=time.perf_counter()
        self.pose=self.controller.get_pose(self.stepper.time-.002,self.timeout)
        models={name:p.get('position',{}) for name,p in self.controller.poses.items()}
        metadata=read_json(self.world.with_name('metadata.json'))
        self.actual_world={'source':'gazebo_pose_topic','pose_semantics':'simulated_body_world_pose_ground_truth',
                           'odometry_semantics':'diff_drive_wheel_joint_dead_reckoning',
                           'agent_pose':dict(self.pose),
                           'goal_pose':models.get(metadata['goal_entity']),
                           'obstacles':{n:models[n] for n in metadata['obstacle_entities'] if n in models}}
        self.observation=self.sensors.get_range_observation(self.pose,self.stepper.time-.002,simulation_time=self.stepper.time)
        c=CanonicalSensorObservation.from_observation(self.observation)
        self.minimum_clearance=min(self.minimum_clearance,c.front_clearance,c.back_clearance,c.left_clearance,c.right_clearance)
        self.telemetry.update(observation_latency_seconds=time.perf_counter()-started,sensor_age_ms=self.sensors.frame.age_ms)

    def read_odometry(self,min_time=None,timeout=.15):
        """Return a timestamped DiffDrive velocity sample, or None if unavailable."""
        if not getattr(self,'odometry_topic',None):return None
        try:
            sample=self.transport.sample(self.odometry_topic,self.stepper.time-.02 if min_time is None else min_time,timeout)
            if 'twist' not in sample:return None
            twist=sample.get('twist',{})
            stamp=sample.get('header',{}).get('stamp',{})
            timestamp=float(stamp.get('sec',0))+float(stamp.get('nsec',0))*1e-9
            return {'timestamp':timestamp,
                    'linear_x':float(twist.get('linear',{}).get('x',0)),
                    'angular_z':float(twist.get('angular',{}).get('z',0))}
        except (TimeoutError,RuntimeError):return None

    def read_odometry_after_sequence(self,sequence,min_time,max_time,timeout=.15):
        """Read odometry received after an explicit sequence and within one sim epoch."""
        if not getattr(self,'odometry_topic',None) or not hasattr(self.transport,'sample_after_sequence'):
            return None
        try:
            sample,received_sequence=self.transport.sample_after_sequence(
                self.odometry_topic,sequence,min_time=min_time,max_time=max_time,timeout=timeout)
            if 'twist' not in sample:return None
            header=sample.get('header',{}).get('stamp',{})
            timestamp=float(header.get('sec',0))+float(header.get('nsec',0))*1e-9
            twist=sample.get('twist',{})
            return {'timestamp':timestamp,
                    'linear_x':float(twist.get('linear',{}).get('x',0)),
                    'angular_z':float(twist.get('angular',{}).get('z',0)),
                    'receive_sequence':int(received_sequence)}
        except (TimeoutError,RuntimeError):return None

    def read_odometry_interval(self,start_time,end_time):
        """Return all buffered DiffDrive samples within one fixed-step interval."""
        if not getattr(self,'odometry_topic',None) or not hasattr(self.transport,'since'):return []
        result=[]
        for sample in self.transport.since(self.odometry_topic,start_time-1e-9):
            if 'twist' not in sample:continue
            header=sample.get('header',{}).get('stamp',{})
            timestamp=float(header.get('sec',0))+float(header.get('nsec',0))*1e-9
            if start_time-1e-6<=timestamp<=end_time+1e-6:
                twist=sample.get('twist',{})
                result.append({'timestamp':timestamp,
                    'linear_x':float(twist.get('linear',{}).get('x',0)),
                    'angular_z':float(twist.get('angular',{}).get('z',0))})
        return result

    def step(self,action):
        started=time.perf_counter()
        try:
            result=self._step(action)
            self.telemetry.update(wall_step_seconds=time.perf_counter()-started,simulation_time=self.stepper.time,
                                  wall_time=time.time(),sensor_frame=self.sensors.frame.to_dict(),
                                  stepping=dict(self.stepper.last_verification),collision_event=self.collision_event,
                                  collision_source=self.collision_source,
                                  command=getattr(self.controller,'last_command',None),goal_pose={'x':self.goal[0],'y':self.goal[1]},
                                  control_mode=self.control_mode,discovery=self.discovery)
            self.telemetry.update(step_throughput=1/max(self.telemetry['wall_step_seconds'],1e-9),
                                  measured_real_time_factor=self.dt/max(self.telemetry['wall_step_seconds'],1e-9),
                                  actual_world=self.actual_world)
            return result
        except Exception as error:
            if hasattr(self,'stepper'):
                self.telemetry['stepping']=dict(self.stepper.last_verification)
                if getattr(error,'step_recovery',None):
                    self.telemetry['step_recovery']=dict(error.step_recovery)
            self.lifecycle=SimulationState.ERROR
            self.last_error=str(error)
            raise

    def _step(self,action):
        if not hasattr(self,'controller'):
            if not self.training_available:raise NotImplementedError('Gazebo unavailable; closed loop requires Ubuntu Harmonic and native Python bindings')
            raise RuntimeError('reset must be called before step')
        if self.closed or self.done:raise RuntimeError('Environment closed or episode finished')
        self.telemetry.pop('action_transition',None)
        self.telemetry.pop('pose_validation',None)
        self.lifecycle=SimulationState.RUNNING
        action={'forward':'up','backward':'down'}.get(action.lower(),action.lower())
        before=self.get_state()
        oldpose=dict(self.pose)
        pre=CanonicalSensorObservation.from_observation(self.observation)
        odometry_before=self.read_odometry(self.stepper.time-.002) if self.control_mode=='PHYSICS' else None
        prior_published_command=dict(self.controller.last_published_command) if self.control_mode=='PHYSICS' and self.controller.last_published_command else None
        # apply_action() is followed by a zero Twist after each paused physics
        # interval. last_command retains the prior discrete action for transition
        # validation; last_published_command correctly reflects the zero Twist.
        prior_action_command=dict(self.controller.last_command) if self.control_mode=='PHYSICS' and self.controller.last_command else None
        prior_publish_sequence=self.controller.publish_sequence if self.control_mode=='PHYSICS' else None
        for item in self.dynamic:
            p=item['controller'].get_pose()
            dx,dy=(item['direction'],0) if item['movement']=='horizontal' else (0,item['direction'])
            if item['movement']=='random':dx,dy=random.Random(self.steps+int(p['x']*100)).choice([(1,0),(-1,0),(0,1),(0,-1)])
            x,y=p['x']+dx*.25,p['y']+dy*.25
            if not .4<x<self.scenario.width-.4 or not .4<y<self.scenario.height-.4:
                item['direction']*=-1
                x,y=p['x']-dx*.25,p['y']-dy*.25
            item['controller'].reset_agent_pose(x,y,p['z'])
        self.controller.apply_action(action)
        action_command=dict(self.controller.last_published_command) if self.control_mode=='PHYSICS' else None
        action_publish_sequence=self.controller.publish_sequence if self.control_mode=='PHYSICS' else None
        pose_topic=getattr(self.controller,'pose_topic',None)
        command_mode_transition=classify_physics_command_transition(
            prior_action_command,action_command)
        validator_requires_pose_history=physics_transition_requires_world_pose_history(
            prior_action_command,action_command,capture_all=False)
        capture_pose_history=(validator_requires_pose_history or self.capture_world_pose_history or
                              self.retain_world_pose_history)
        pose_history_sequence=(self.transport.cursor(pose_topic)
                               if self.control_mode=='PHYSICS' and capture_pose_history and pose_topic and
                               hasattr(self.transport,'cursor') else None)
        self.stepper.step_simulation()
        self.steps+=1
        self._refresh()
        pose_history=[]
        pose_history_summary=None
        pose_history_sequence_after=(self.transport.cursor(pose_topic)
                                     if pose_history_sequence is not None and
                                     hasattr(self.transport,'cursor') else None)
        if self.control_mode=='PHYSICS' and pose_history_sequence is not None:
            try:
                pose_history=self.controller.pose_history_after(
                    pose_history_sequence,before['timestamp'],self.stepper.time)
                pose_history_summary=summarize_world_pose_history(
                    pose_history,before['timestamp'],self.stepper.time)
            except (RuntimeError,TimeoutError) as error:
                pose_history_summary=summarize_world_pose_history(
                    [],before['timestamp'],self.stepper.time)
                pose_history_summary['world_pose_history_error']=str(error)
        odometry_after=self.read_odometry(self.stepper.time-.002) if self.control_mode=='PHYSICS' else None
        odometry_history=(self.read_odometry_interval(before['timestamp'],self.stepper.time)
                          if self.control_mode=='PHYSICS' else [])
        if self.control_mode=='PHYSICS':
            commanded=self.controller.last_command
            self.controller.stop_agent()
            zero_command=dict(self.controller.last_published_command)
            zero_publish_sequence=self.controller.publish_sequence
            self.controller.last_command=commanded
            self.telemetry['action_transition']={'action':action,'commanded_twist':action_command,
                'command_mode_transition':command_mode_transition,
                'previous_published_twist':prior_published_command,'zero_twist_after_step':zero_command,
                'previous_action_twist':prior_action_command,
                'command_publish_sequence_before':prior_publish_sequence,
                'action_publish_sequence':action_publish_sequence,'zero_publish_sequence':zero_publish_sequence,
                'action_command_sim_time':before['timestamp'],'zero_command_sim_time':self.stepper.time,
                'simulation_duration':self.stepper.time-before['timestamp'],
                'odometry_before':odometry_before,'odometry_after':odometry_after,
                'odometry_history':odometry_history,
                'before_pose':oldpose,'after_pose':dict(self.pose),
                'pose_topic_sequence_before':pose_history_sequence,
                'pose_topic_sequence_after':pose_history_sequence_after,
                'world_pose_history':pose_history,
                'world_pose_history_summary':pose_history_summary}
        dx,dy={'up':(0,-1),'down':(0,1),'left':(-1,0),'right':(1,0),'stop':(0,0)}[action]
        if self.control_mode=='KINEMATIC' and math.hypot(self.pose['x']-(oldpose['x']+dx*self.step_size),self.pose['y']-(oldpose['y']+dy*self.step_size))>.02:
            raise RuntimeError('Gazebo commanded pose was not observed after stepping')
        self.distance+=math.hypot(self.pose['x']-oldpose['x'],self.pose['y']-oldpose['y'])
        ray={'up':'front','down':'back','left':'left','right':'right'}.get(action)
        collision=ray is not None and getattr(pre,ray+'_clearance')<self.step_size-.01
        collision=collision or not .2<=self.pose['x']<=self.scenario.width-.2 or not .2<=self.pose['y']<=self.scenario.height-.2
        dynamic_collision=any(math.hypot(self.pose['x']-d['controller'].get_pose()['x'],self.pose['y']-d['controller'].get_pose()['y'])<.5 for d in self.dynamic)
        self.collision_source='geometric_fallback'
        if self.contact_topic:
            if not hasattr(self,'contacts'):raise RuntimeError('Contact channel not initialized')
            events=self.contacts.poll(self.stepper.time)
            self.collision_event=events[0] if events else None
            collision=bool(events)
            dynamic_collision=False
            self.collision_source='gazebo_contact' if events else 'gazebo_contact_event_stream'
            self.telemetry['contacts']=dict(self.contacts.state)
        if self.control_mode=='PHYSICS':
            # Range-based pre-command distance is not a physics contact: do not call it contact evidence.
            if self.collision_source=='geometric_fallback':
                collision=not .2<=self.pose['x']<=self.scenario.width-.2 or not .2<=self.pose['y']<=self.scenario.height-.2
            validation=self.controller.validate_pose(oldpose,self.pose,self.stepper.time-before['timestamp'],collision or dynamic_collision,
                                                    odometry_before,odometry_after,
                                                    self.telemetry['action_transition']['odometry_history'],
                                                    simulation_start_time=before['timestamp'],
                                                    simulation_end_time=self.stepper.time,
                                                    previous_command=prior_action_command,
                                                    world_pose_history=(pose_history_summary
                                                        if validator_requires_pose_history or
                                                        self.capture_world_pose_history else None))
            # Diagnostic-only world trajectory evidence. It never changes the
            # physical validator's inputs or acceptance decision.
            if pose_history_summary is not None:
                validation['world_pose_history_summary']=pose_history_summary
                validation['world_pose_history']=pose_history
            if not validation['valid'] and hasattr(self,'contacts') and not collision:
                events=self.contacts.poll(self.stepper.time,timeout=min(.5,self.timeout))
                if events:
                    self.collision_event=events[0];collision=True
                    self.collision_source='gazebo_contact'
                    validation=self.controller.validate_pose(oldpose,self.pose,self.dt,True,odometry_before,odometry_after,
                        self.telemetry['action_transition']['odometry_history'],
                        simulation_start_time=before['timestamp'],simulation_end_time=self.stepper.time,
                        previous_command=prior_action_command,world_pose_history=(pose_history_summary
                            if validator_requires_pose_history or self.capture_world_pose_history else None))
                self.telemetry['contacts']=dict(self.contacts.state)
            self.telemetry['pose_validation']=validation
            if not validation['valid']:
                reason='Physics movement outside validated tolerance'
                evidence={
                    'requested_action':action,
                    'previous_command':prior_action_command,
                    'requested_command':action_command,
                    'transition_type':command_mode_transition,
                    'validator_evidence':dict(validation),
                    'action_transition':dict(self.telemetry['action_transition']),
                    'collision':bool(collision or dynamic_collision),
                    'collision_event':(None if self.collision_event is None else
                        self.collision_event.to_dict()),
                    'contact_state':dict(self.telemetry.get('contacts',{})),
                }
                raise PhysicalControlFailure(reason,evidence=evidence)
        success=math.hypot(self.pose['x']-self.goal[0],self.pose['y']-self.goal[1])<=self.goal_radius
        danger=any(o.type=='danger_zone' and math.hypot(self.pose['x']-(o.position[0]+.5),self.pose['y']-(o.position[1]+.5))<.5 for o in self.scenario.objects)
        reason='moving_obstacle_collision' if dynamic_collision else 'collision' if collision else 'danger_zone' if danger else 'goal' if success else 'timeout' if self.steps>=self.max_steps else 'moving'
        terminated=collision or dynamic_collision or danger or success
        truncated=not terminated and self.steps>=self.max_steps
        self.done=terminated or truncated
        self.last_reward_components=reward_components(before,self.get_state(),reason,version=self.reward_version,
                previous_action=self.previous_action,action=action,clearance=self.minimum_clearance)
        self.previous_action=action
        self.lifecycle=SimulationState.PAUSED
        return StepResult(self.get_observation(),sum(self.last_reward_components.values()),terminated,truncated,reason)

    def get_observation(self):
        if self.pose is None:raise RuntimeError('No Gazebo observation; reset first')
        return (math.floor(self.pose['x']),math.floor(self.pose['y']))

    def get_agent_observation(self,mode='sensor',radius=2):
        if self.observation is None:raise RuntimeError('No Gazebo sensor sample')
        if mode=='basic':
            if self.control_mode=='PHYSICS':raise ValueError('PHYSICS differential drive requires body-relative SENSOR observations; Basic policy semantics differ')
            return Observation('basic',self.get_observation(),(int(self.goal[0]),int(self.goal[1])))
        if mode!='sensor':raise ValueError('Gazebo supports BASIC/SENSOR; LOCAL requires a sensor occupancy mapper')
        return self.observation

    def get_state(self):
        status=self.manager.status()
        data={**status,'world_file':str(self.world) if self.world else None,'training_available':self.training_available,'render_verified':False,
              'simulation_state':self.lifecycle,'error':self.last_error,'control_mode':self.control_mode,'telemetry':dict(self.telemetry),
              'sensor_frame':self.sensors.frame.to_dict() if hasattr(self,'sensors') and self.sensors.frame else None}
        if self.pose is None:return data
        return {**data,'agent':list(self.get_observation()),'goal':[int(self.goal[0]),int(self.goal[1])],
                'width':self.scenario.width,'height':self.scenario.height,'steps':self.steps,'pose':dict(self.pose),
                'timestamp':self.stepper.time,'obstacles':[list(o.position) for o in self.scenario.objects if o.type not in ('danger_zone','slow_zone')],
                'dynamic_objects':[{'position':[d['controller'].get_pose()['x']-.5,d['controller'].get_pose()['y']-.5]} for d in self.dynamic],
                'mission':self.scenario.mission,'danger_zones':[list(o.position) for o in self.scenario.objects if o.type=='danger_zone'],
                'slow_zones':[list(o.position) for o in self.scenario.objects if o.type=='slow_zone']}

    def get_metrics(self):
        return {'steps':self.steps,'distance':self.distance,'done':self.done,'shortest_path_distance':None,
                'minimum_clearance':None if math.isinf(self.minimum_clearance) else self.minimum_clearance,
                'reward_components':dict(self.last_reward_components)}

    def render(self):return self.get_state()

    def close(self):
        if self.closed:return
        self.closed=True
        self.lifecycle=SimulationState.STOPPING
        try:
            if hasattr(self,'sensors'):self.sensors.stop()
            if self.transport:self.transport.close()
        finally:
            self.manager.close()
            self.lifecycle=SimulationState.STOPPED

    def restart(self,seed=None):
        """Start a new Gazebo process/partition, clearing all simulator-owned state.

        `/world/<name>/set_pose` applies a world pose command; it does not promise
        to clear rigid-body velocities, DiffDrive wheel state, or plugin commands.
        A process restart is the supported hard episode boundary for PHYSICS.
        """
        stop_error=None
        if not self.closed and hasattr(self,'controller') and self.control_mode=='PHYSICS':
            try:self.controller.stop_agent()
            except Exception as error:stop_error=error
        self.close()
        if self.process and self.process.poll() is None:
            raise RuntimeError('Old Gazebo process did not exit during restart')
        if stop_error:raise RuntimeError('Could not publish zero command before simulator restart') from stop_error
        options=dict(gui=self.gui,dt=self.dt,step_size=self.step_size,goal_radius=self.goal_radius,timeout=self.timeout,
                     control_mode=self.control_mode,max_sensor_age_ms=self.max_sensor_age_ms,allow_geometric_fallback=self.allow_geometric_fallback)
        # Do not reinitialize self: that leaves old controller/provider attributes
        # attached to the object and can route reset through a closed transport.
        fresh=type(self)(self.scenario,self.max_steps,self.root,**options)
        try:fresh.reset(seed)
        except Exception as error:
            error.new_environment=fresh
            raise
        return fresh
