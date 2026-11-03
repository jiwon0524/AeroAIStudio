"""Headless-first native validation. Missing runtime is NOT AVAILABLE, never PASS."""
from pathlib import Path
import argparse
import xml.etree.ElementTree as ET
from aero_ai_studio.core.storage import write_json,read_json
from aero_ai_studio.gazebo.diagnostics import diagnose,gazebo_status
from aero_ai_studio.gazebo.environment import GazeboEnvironment
from aero_ai_studio.gazebo.world_generator import GazeboWorldGenerator
from aero_ai_studio.scenario.models import ScenarioSpec,SceneObject
from aero_ai_studio.explainability.brain_map import record_step


def rule_action(observation):
    return rule_decision(observation)['action']


def rule_decision(observation):
    import math
    s=observation.sensor_state
    dx,dy=s['goal_delta']
    front=s['canonical']['front_clearance']
    if front<.6:
        return {'action':'right','policy':'front_clearance_turn','observable_inputs':{
            'front_clearance':front,'threshold':.6,'goal_delta':[dx,dy]}}
    bearing=math.atan2(-dx,-dy)
    if abs(bearing)>.15:
        action='left' if bearing>0 else 'right'
        reason='goal bearing exceeds turn threshold'
    else:
        action='up';reason='goal bearing is within forward threshold'
    return {'action':action,'policy':reason,'observable_inputs':{
        'goal_delta':[dx,dy],'bearing_rad':bearing,'turn_threshold_rad':.15,
        'front_clearance':front,'threshold':.6}}


def target_geometry(pose,target):
    """World +X/+Y, CCW yaw about +Z; independent of policy observations."""
    import math
    dx,dy=target['x']-pose['x'],target['y']-pose['y']
    bearing=math.atan2(dy,dx)
    return {'distance':math.hypot(dx,dy),'bearing':bearing,
            'yaw_error':math.atan2(math.sin(bearing-pose['yaw']),math.cos(bearing-pose['yaw']))}


def collision_challenge(env,evidence):
    """Align to an observed target, then drive into it without avoidance rules."""
    import math
    env.reset(43)
    positions=env.actual_world['obstacles']
    candidates=[(name,p) for name,p in positions.items() if name.startswith('static_obstacle_')]
    if not candidates:raise RuntimeError('Forced contact requires an observed static obstacle')
    target_name,target=(('static_obstacle_2',positions['static_obstacle_2']) if 'static_obstacle_2' in positions else
                        min(candidates,key=lambda item:target_geometry(env.pose,item[1])['distance']))
    tx,ty=float(target.get('x',0)),float(target.get('y',0))
    if not 1.2<target_geometry(env.pose,target)['distance']<3.:
        env.controller.reset_agent_pose(tx-1.7,ty,.16,0.)
        env.stepper.step_simulation();env._refresh()
        if math.hypot(env.pose['x']-(tx-1.7),env.pose['y']-ty)>.02:
            raise RuntimeError('Forced-contact approach placement was not observed')
        env.contacts.reset(env.stepper.time)
    start=dict(env.pose);start_time=env.stepper.time
    yaw_tolerance=.09
    evidence.update(topic=env.contact_topic,target_entity=target_name,target_pose=target,
                    start_pose=start,start_time=start_time,initial_target_distance=target_geometry(start,target)['distance'],
                    yaw_tolerance=yaw_tolerance,no_contact='NOT VERIFIED',forced_contact='NOT VERIFIED',steps=[],
                    physical_travel=0.,approach_travel=0.,net_displacement=0.)

    def advance(action,phase):
        before=dict(env.pose);before_time=env.stepper.time;geometry=target_geometry(before,target)
        try:
            return env.step(action)
        finally:
            after=dict(env.pose);after_geometry=target_geometry(after,target)
            dx,dy=after['x']-before['x'],after['y']-before['y']
            path=math.hypot(dx,dy)
            evidence['physical_travel']+=path
            if phase=='approach':evidence['approach_travel']+=path
            evidence['net_displacement']=math.hypot(after['x']-start['x'],after['y']-start['y'])
            evidence['step_progress']=env.stepper.time>start_time
            evidence['motion_seen']=evidence['physical_travel']>.01
            evidence['steps'].append({'phase':phase,'action':action,'command':dict(env.controller.last_command),
                'before_time':before_time,'timestamp':env.stepper.time,'before':before,'pose':after,
                'target_bearing':geometry['bearing'],'yaw_error_before':geometry['yaw_error'],
                'yaw_error_after':after_geometry['yaw_error'],
                'signed_yaw_delta':math.atan2(math.sin(after['yaw']-before['yaw']),math.cos(after['yaw']-before['yaw'])),
                'target_distance_before':geometry['distance'],'target_distance_after':after_geometry['distance'],
                'distance_decrease':geometry['distance']-after_geometry['distance'],
                'toward_target_projection':dx*math.cos(geometry['bearing'])+dy*math.sin(geometry['bearing']),
                'body_forward_projection':dx*math.cos(before['yaw'])+dy*math.sin(before['yaw']),
                'contact':env.collision_event,'collision':bool(env.collision_event),'contact_state':dict(env.contacts.state)})
            if env.collision_event:evidence['event']=dict(env.collision_event)

    def check_contact():
        if env.collision_event and target_name not in env.collision_event['other_entity'].split('::'):
            raise RuntimeError('Unexpected contact: expected '+target_name+', got '+env.collision_event['other_entity'])

    def align():
        # Stop within half a discrete .08 rad turn, then allow a wider
        # approach tolerance. Re-align from measured pose if drift grows.
        for _ in range(80):
            geometry=target_geometry(env.pose,target)
            if abs(geometry['yaw_error'])<=.041:return
            action='left' if geometry['yaw_error']>0 else 'right'
            result=advance(action,'align');check_contact()
            step=evidence['steps'][-1]
            if result.terminated or result.truncated:raise RuntimeError('Episode ended while aligning to contact target')
            if (step['signed_yaw_delta']*math.copysign(1,geometry['yaw_error'])<=0 or
                    abs(step['yaw_error_after'])>=abs(geometry['yaw_error'])+.005):
                raise RuntimeError('Rotation moved away from target bearing')
        raise TimeoutError('Target yaw alignment did not converge')

    try:
        align()
        aligned=target_geometry(env.pose,target)
        if abs(aligned['yaw_error'])>yaw_tolerance:raise RuntimeError('Target yaw tolerance not met')
        evidence.update(aligned_pose=dict(env.pose),alignment=aligned,approach_start_distance=aligned['distance'])

        for i in range(100):
            geometry=target_geometry(env.pose,target)
            if abs(geometry['yaw_error'])>yaw_tolerance:
                align()
                if abs(target_geometry(env.pose,target)['yaw_error'])>yaw_tolerance:
                    raise RuntimeError('Approach heading left target yaw tolerance')
            result=advance('up','approach');check_contact()
            step=evidence['steps'][-1]
            if step['distance_decrease']<-.002 or step['toward_target_projection']<-.002:
                raise RuntimeError('Physical approach moved away from target')
            if env.collision_event:
                event=env.collision_event
                names=event['other_entity'].split('::');own=event['agent_collision'].split('::')
                distance=step['target_distance_after']
                progress=aligned['distance']-distance
                evidence.update(impact_distance_to_target=distance,target_distance_reduction=progress)
                if (evidence['no_contact']!='PASS' or 'collision' not in names
                        or env.agent_entity not in own or 'body_collision' not in own
                        or evidence['approach_travel']<.1 or progress<.1
                        or event['timestamp']<=start_time or distance>.85
                        or env.collision_source!='gazebo_contact' or not result.terminated
                        or not any(item['event']==event for item in env.contacts.evidence)):
                    raise RuntimeError('Forced-contact evidence did not match physical approach and expected collision pair')
                evidence['forced_contact']='PASS'
                return
            if step['distance_decrease']<=.0001:
                raise RuntimeError('Physical approach did not reduce target distance')
            if i==2:
                if aligned['distance']-step['target_distance_after']<.05:
                    raise RuntimeError('No-contact approach did not progress toward target')
                evidence['no_contact']='PASS'
            if result.terminated or result.truncated:raise RuntimeError('Approach ended before expected contact: '+result.reason)
        raise TimeoutError('Agent did not produce contact with the expected obstacle within 100 physical steps')
    except Exception as error:
        evidence['error']=str(error)
        raise
    finally:
        evidence['raw_contacts']=list(env.contacts.evidence)
        evidence['end_time']=env.stepper.time
        evidence['end_pose']=dict(env.pose)
        evidence['end_target_distance']=target_geometry(env.pose,target)['distance']
        evidence['contact_state']=dict(env.contacts.state)
        evidence['pose_validation']=env.telemetry.get('pose_validation')
        env.controller.stop_agent()


def start_independent_closed_loop_episode(env,seed=42):
    """Discard collision physics state, then prove the new episode stays still at zero input."""
    old_env=env
    old=old_env.manager.status()
    old_world=old_env.world_name
    old_transport=old_env.transport
    try:new_env=old_env.restart(seed)
    except Exception as error:
        failed_env=getattr(error,'new_environment',None)
        failed_status=failed_env.manager.status() if failed_env else {}
        error.lifecycle_evidence={'old_partition':old.get('partition'),'old_world':old_world,
                                  'old_process':old.get('pid'),
                                  'old_process_exited':old_env.process.poll() is not None if old_env.process else True,
                                  'old_transport_closed':bool(getattr(old_transport,'closed',False)),
                                  'new_instance_created':failed_env is not None,
                                  'new_partition':failed_status.get('partition'),'new_world':failed_env.world_name if failed_env else None,
                                  'new_process':failed_status.get('pid'),'new_process_alive':bool(failed_env and failed_env.process and failed_env.process.poll() is None),
                                  'transport_recreated':bool(failed_env and failed_env.transport is not old_transport),
                                  'closed_loop_started':False,'setup_error':str(error)}
        raise
    try:return _finish_independent_closed_loop_episode(old_env,new_env,old,old_world,old_transport)
    except Exception as error:
        if not getattr(error,'lifecycle_evidence',None):
            new_status=new_env.manager.status()
            error.lifecycle_evidence={'old_partition':old.get('partition'),'old_world':old_world,
                'old_process':old.get('pid'),'old_process_exited':old_env.process.poll() is not None if old_env.process else True,
                'old_transport_closed':bool(getattr(old_transport,'closed',False)),
                'new_partition':new_status.get('partition'),'new_world':new_env.world_name,
                'new_process':new_status.get('pid'),'new_process_alive':bool(new_env.process and new_env.process.poll() is None),
                'transport_recreated':new_env.transport is not old_transport,'closed_loop_started':False,
                'setup_error':str(error)}
        error.new_environment=new_env
        raise


def _finish_independent_closed_loop_episode(old_env,new_env,old,old_world,old_transport):
    old_exit=old_env.process.poll() is not None if old_env.process else True
    new=new_env.manager.status()
    if not new.get('pid') or new_env.process is None or new_env.process.poll() is not None or new.get('partition')==old.get('partition'):
        raise RuntimeError('Closed-loop reset did not create an independent Gazebo process/partition')
    topics=set(new_env.discovery.get('topics',[]));services=set(new_env.discovery.get('services',[]))
    required_topics={f'/world/{new_env.world_name}/pose/info',new_env.sensors.topic,new_env.contact_topic,
                     f'/world/{new_env.world_name}/stats'}
    required_services={f'/world/{new_env.world_name}/control',f'/world/{new_env.world_name}/set_pose'}
    rediscovered=required_topics<=topics and required_services<=services and new_env.world_name in new_env.discovery.get('worlds',[])
    bound=new_env.transport is not old_transport
    partition_matches=new_env.transport.partition==new.get('partition')
    # Old transport is expected to be permanently closed; all active components
    # in the new Environment must point at the replacement transport.
    old_transport_closed=bool(getattr(old_transport,'closed',False))
    dependencies_bound=(new_env.controller.transport is new_env.transport and
                        new_env.sensors.transport is new_env.transport and
                        new_env.stepper.transport is new_env.transport and
                        new_env.contacts.transport is new_env.transport)
    if not old_exit or not old_transport_closed or not bound or not partition_matches or not rediscovered or not dependencies_bound:
        error=RuntimeError('Gazebo restart lifecycle evidence failed: '+str({'old_process_exited':old_exit,
            'old_transport_closed':old_transport_closed,'transport_recreated':bound,'rediscovered':rediscovered,
            'transport_partition_matches_process':partition_matches,
            'dependencies_bound':dependencies_bound,'required_topics':sorted(required_topics-topics),
            'required_services':sorted(required_services-services)}))
        error.lifecycle_evidence={'old_partition':old.get('partition'),'old_world':old_world,
            'old_process':old.get('pid'),'old_process_exited':old_exit,'old_transport_closed':old_transport_closed,
            'new_partition':new.get('partition'),'new_world':new_env.world_name,'new_process':new.get('pid'),
            'new_process_alive':bool(new_env.process and new_env.process.poll() is None),
            'transport_recreated':bound,'transport_partition_matches_process':partition_matches,
            'world_reloaded':new_env.world_name in new_env.discovery.get('worlds',[]),
            'topic_service_rediscovery':rediscovered,
            'dependent_components_rebound':dependencies_bound,'closed_loop_started':False}
        raise error
    reset_pose=dict(new_env.pose)
    new_env.controller.stop_agent()
    new_env.stepper.step_simulation(3)
    new_env._refresh()
    settled_pose=dict(new_env.pose)
    import math
    drift=math.hypot(settled_pose['x']-reset_pose['x'],settled_pose['y']-reset_pose['y'])
    yaw_drift=abs(math.atan2(math.sin(settled_pose['yaw']-reset_pose['yaw']),
                             math.cos(settled_pose['yaw']-reset_pose['yaw'])))
    contacts=new_env.contacts.poll(new_env.stepper.time) if hasattr(new_env,'contacts') else []
    odometry={'status':'NOT AVAILABLE'}
    if getattr(new_env,'odometry_topic',None):
        try:
            sample=new_env.transport.sample(new_env.odometry_topic,new_env.stepper.time-.02,timeout=.5)
            twist=sample.get('twist',{})
            linear=twist.get('linear',{});angular=twist.get('angular',{})
            odometry={'status':'PASS','timestamp':sample.get('header',{}).get('stamp'),
                      'linear_x_m_s':float(linear.get('x',0)),'angular_z_rad_s':float(angular.get('z',0))}
        except Exception as error:
            odometry={'status':'NOT AVAILABLE','error':str(error)}
    evidence={'state_isolation':'new_environment_process_partition_and_transport',
              'old_partition':old.get('partition'),'old_world':old_world,'old_process':old.get('pid'),
              'old_process_exited':old_exit,'old_transport_closed':old_transport_closed,
              'new_partition':new.get('partition'),'new_world':new_env.world_name,'new_process':new.get('pid'),
              'new_process_alive':bool(new_env.process and new_env.process.poll() is None),
              'transport_recreated':bound,'transport_partition_matches_process':partition_matches,
              'world_reloaded':new_env.world_name in new_env.discovery.get('worlds',[]),
              'topic_service_rediscovery':rediscovered,'rediscovered_topics':sorted(required_topics & topics),
              'rediscovered_services':sorted(required_services & services),'dependent_components_rebound':dependencies_bound,
              'sensor_subscription_ready':new_env.sensors.frame is not None,
              'contact_subscription_ready':new_env.contacts.schema is not None,
              'reset_applied':new_env.initialization_checks.get('reset_applied')=='PASS',
              'readiness_complete_before_settle':new_env.initialization_phase=='ready',
              'zero_command_settle_executed':True,'closed_loop_started':False,
              'reset_pose':reset_pose,'reset_yaw':reset_pose.get('yaw'),
              'zero_command':dict(new_env.controller.last_command),'settle_steps':3,
              'settle_simulation_time':new_env.stepper.time,'settled_pose':settled_pose,
              'zero_command_displacement':drift,'zero_command_yaw_drift':yaw_drift,
              'contact_during_settle':contacts,'odometry':odometry}
    new_env.telemetry['closed_loop_reset_evidence']=evidence
    if (drift>.03 or yaw_drift>.05 or contacts or
            (odometry['status']=='PASS' and (abs(odometry['linear_x_m_s'])>.02 or abs(odometry['angular_z_rad_s'])>.02))):
        error=RuntimeError('Fresh closed-loop episode failed zero-command settle check: '+str(evidence))
        error.lifecycle_evidence=evidence
        raise error
    return new_env,new_env.get_observation(),evidence


def run(output: Path,gui=False,obstacle=False,stage='full'):
    if stage not in ('full','movement','collision'):raise ValueError('Unknown runtime stage')
    if stage=='collision':obstacle=True
    spec=ScenarioSpec(width=10,height=10,start=(1,1),goal=(4,1),objects=[SceneObject('wall',(7,7)),SceneObject('static_obstacle',(7,5))])
    if obstacle:
        spec.objects.append(SceneObject('static_obstacle',(3,1)));spec.goal=(5,2)
    output.mkdir(parents=True,exist_ok=True)
    names=('sdf_generated','xml_valid','server_alive','world_loaded','agent_exists','goal_exists','obstacles_exist','sensor_topic',
           'sensor_received','pose_read','initialization','set_pose','reset_applied','step_progress','physics_motion','contact_channel','no_contact','collision_contact','closed_loop','shutdown')
    report={'status':'NOT VERIFIED','control_mode':'PHYSICS','diagnostics':diagnose(full=True),
            'checks':{n:'NOT AVAILABLE' for n in names},'render_verified':False,'validation_stage':stage}
    report['physical_signal_semantics']={'world_pose_source':'gazebo_pose_topic / simulated body world pose',
        'odometry_source':'/model/simple_agent/odometry / DiffDrive wheel-joint dead reckoning',
        'comparison':'validate directions and freshness separately; retain magnitude discrepancy as telemetry'}
    if stage=='full':
        report['closed_loop_execution']={'status':'NOT RUN','started':False,'actions_attempted':0,'actions_completed':0}
        report['closed_loop_action_trace']=[]
    if stage=='movement':
        for key in ('no_contact','collision_contact','closed_loop'):report['checks'][key]='NOT REQUESTED'
    if stage=='collision':report['checks']['closed_loop']='NOT REQUESTED'
    world=GazeboWorldGenerator().generate(spec,output/'worlds',True,'PHYSICS')
    report['checks']['sdf_generated']='PASS'
    ET.parse(world);report['checks']['xml_valid']='PASS'
    if not gazebo_status()['available']:
        write_json(output/'runtime_v07.json',report);return report
    env=GazeboEnvironment(spec,root=output/'worlds',gui=gui,control_mode='PHYSICS',allow_geometric_fallback=stage=='movement')
    active='server_alive'
    try:
        status=env.launch()
        if not env.process or env.process.poll() is not None:raise RuntimeError('Gazebo server exited')
        report['checks'][active]='PASS'
        active='world_loaded';env.prepare()
        report['checks'][active]='PASS';report['discovery']=env.discovery
        metadata=read_json(env.world.with_name('metadata.json'))
        models=set(env.controller.poses)
        for key,required in [('agent_exists',[metadata['agent_entity']]),('goal_exists',[metadata['goal_entity']]),('obstacles_exist',metadata['obstacle_entities'])]:
            active=key
            if not set(required)<=models:raise RuntimeError('Expected entities missing: '+str(required))
            report['checks'][key]='PASS'
        report['checks']['pose_read']='PASS'
        active='sensor_topic'
        if not env.injected and metadata['sensor_topic'] not in env.discovery['topics']:
            raise RuntimeError('Expected sensor topic not discovered: '+metadata['sensor_topic'])
        report['checks'][active]='PASS'
        active='initialization'
        try:
            state=env.reset(42)
        finally:
            report['checks'].update(getattr(env,'initialization_checks',{}))
            report['initialization_phase']=getattr(env,'initialization_phase','unknown')
            pose_request=getattr(env.controller,'last_pose_request',None)
            report['set_pose_request']=pose_request
            if pose_request is not None and not pose_request['accepted']:
                report['checks']['set_pose']='FAIL'
        report['checks']['initialization']='PASS'
        report['checks']['sensor_received']='PASS'
        if stage in ('collision','full'):
            active='collision_contact'
            evidence={};report['collision_evidence']=evidence
            try:
                collision_challenge(env,evidence)
                report['checks']['collision_contact']='PASS'
                report['checks']['step_progress']='PASS'
                report['checks']['physics_motion']='PASS'
            finally:
                report['checks']['no_contact']=evidence.get('no_contact','NOT AVAILABLE')
                if evidence.get('step_progress'):report['checks']['step_progress']='PASS'
                if evidence.get('motion_seen'):report['checks']['physics_motion']='PASS'
                write_json(output/'collision.json',evidence)
            if stage=='full':
                active='initialization'
                env,state,reset_evidence=start_independent_closed_loop_episode(env,42)
                report['restart_lifecycle']=reset_evidence
        if stage!='collision':
            events=[];avoid_turns=avoid_forward=0
            initial_time=env.stepper.time
            motion_seen=False
            for i in range(5 if stage=='movement' else 250):
                active='physics_motion' if stage=='movement' else 'closed_loop'
                before=env.get_state();obs=env.get_agent_observation('sensor')
                if obstacle and obs.sensor_state['canonical']['front_clearance']<.6 and not avoid_turns and not avoid_forward:
                    avoid_turns=20;avoid_forward=25
                if avoid_turns:
                    action='left';avoid_turns-=1
                    decision={'action':action,'policy':'obstacle_avoidance_turn_override',
                              'observable_inputs':{'front_clearance':obs.sensor_state['canonical']['front_clearance'],
                                                   'threshold':.6,'remaining_turn_actions':avoid_turns}}
                elif avoid_forward:
                    action='up';avoid_forward-=1
                    decision={'action':action,'policy':'obstacle_avoidance_forward_override',
                              'observable_inputs':{'remaining_forward_actions':avoid_forward}}
                elif stage=='movement':
                    action='up';decision={'action':action,'policy':'movement_stage_fixed_forward','observable_inputs':{}}
                else:
                    decision=rule_decision(obs);action=decision['action']
                trace_entry={'index':i,'action':action,'decision':decision,'before_pose':dict(before['pose']),
                             'before_simulation_time':before['timestamp'],
                             'observation':{'goal_delta':obs.sensor_state.get('goal_delta'),
                                 'front_clearance':obs.sensor_state.get('canonical',{}).get('front_clearance'),
                                 'sensor_timestamp':obs.sensor_state.get('sensor_timestamp'),
                                 'sensor_sequence':obs.sensor_state.get('sequence')}}
                if stage=='full':
                    report['closed_loop_execution']['status']='RUNNING'
                    report['closed_loop_execution']['started']=True
                    report['restart_lifecycle']['closed_loop_started']=True
                    report['closed_loop_execution']['actions_attempted']+=1
                try:
                    result=env.step(action)
                    if stage=='full':report['closed_loop_execution']['actions_completed']+=1
                except Exception as error:
                    if stage=='full':
                        report['closed_loop_execution'].update(status='ABORTED_BEFORE_GOAL',error=str(error))
                    raise
                finally:
                    if stage=='full':
                        transition=env.telemetry.get('action_transition',{})
                        trace_entry.update(command_transition=transition,
                            before_odometry=transition.get('odometry_before'),after_pose=dict(env.pose) if env.pose else None,
                            after_odometry=transition.get('odometry_after'),
                            simulation_duration=transition.get('simulation_duration'),
                            validation=env.telemetry.get('pose_validation'),
                            step_recovery=dict(env.stepper.last_verification))
                        if env.pose:
                            import math
                            trace_entry['displacement']=math.hypot(env.pose['x']-before['pose']['x'],env.pose['y']-before['pose']['y'])
                            trace_entry['yaw_delta']=math.atan2(math.sin(env.pose['yaw']-before['pose']['yaw']),
                                                               math.cos(env.pose['yaw']-before['pose']['yaw']))
                        report['closed_loop_action_trace'].append(trace_entry)
                    # Preserve independent evidence even if contact/closed-loop fails.
                    if env.stepper.time>initial_time:
                        report['checks']['step_progress']='PASS'
                    validation=(env.telemetry.get('pose_validation') or
                                env.controller.validate_pose(before['pose'],env.pose,env.dt)) if env.stepper.time>before['timestamp'] and env.pose is not None else {}
                    if validation.get('valid') and (validation.get('distance',0)>1e-6 or validation.get('yaw_delta',0)>1e-6):
                        motion_seen=True
                        report['checks']['physics_motion']='PASS'
                    report['progress']={'simulation_time':env.stepper.time,'stepping':dict(env.stepper.last_verification),
                                        'pose_validation':validation,'actual_world':env.actual_world}
                    if env.stepper.last_verification.get('service_timeout'):
                        report['step_recovery']=dict(env.stepper.last_verification)
                after=env.get_state()
                event=record_step(1,i,state,dict.fromkeys(('up','down','left','right'),0.),action,False,0,before,after,result)
                event.update(schema_version='0.7',observation=obs.to_dict(),pose=before['pose'],next_pose=after['pose'],timestamp=after['timestamp'],
                             proposed_action=action,final_action=action,telemetry=after['telemetry'],reward_components=env.get_metrics()['reward_components'])
                events.append(event);state=result.observation
                if result.terminated or result.truncated:break
            report['checks']['step_progress']='PASS' if after['timestamp']>initial_time else 'FAIL'
            report['checks']['physics_motion']='PASS' if motion_seen else 'FAIL'
            if stage=='full':
                report['checks']['closed_loop']='PASS' if result.reason=='goal' else 'FAIL'
                report['closed_loop_execution'].update(status='PASS' if result.reason=='goal' else 'FAIL_GOAL_NOT_REACHED',
                                                       reason=result.reason,final_pose=dict(env.pose),
                                                       final_goal={'x':env.goal[0],'y':env.goal[1]})
            write_json(output/'episode.json',{'schema_version':'0.7','episode':1,'success':result.reason=='goal','reason':result.reason,'steps':events})
    except Exception as error:
        report['checks'][active]='FAIL';report['error']=str(error)
        if getattr(error,'lifecycle_evidence',None):report['restart_lifecycle']=error.lifecycle_evidence
        if getattr(error,'new_environment',None):env=error.new_environment
    finally:
        if stage=='full':write_json(output/'closed_loop_action_trace.json',report.get('closed_loop_action_trace',[]))
        report['service_requests']=getattr(env.transport,'request_history',[])
        if hasattr(env,'discovery'):report['discovery']=env.discovery
        env.close();report['checks']['shutdown']='PASS' if env.process is None or env.process.poll() is not None else 'FAIL'
    report['status']='PASS' if all(v in ('PASS','NOT REQUESTED') for v in report['checks'].values()) else 'FAIL'
    write_json(output/'runtime_v07.json',report)
    return report


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--gui',action='store_true');p.add_argument('--obstacle',action='store_true')
    p.add_argument('--stage',choices=('full','movement','collision'),default='full',help='movement: physical motion; collision: free approach and real obstacle impact; full: collision evidence then rule goal completion')
    args=p.parse_args();result=run(args.output,args.gui,args.obstacle,args.stage);print(result)
    if result['status']=='FAIL':raise SystemExit(1)


if __name__=='__main__':main()
