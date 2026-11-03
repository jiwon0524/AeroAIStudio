#!/usr/bin/env python3
"""Inference-only DQN closed-loop validation against actual Gazebo PHYSICS."""
from __future__ import annotations
import argparse
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))

from aero_ai_studio.core.storage import write_json
from aero_ai_studio.gazebo.dqn_runtime import DQNCheckpointError,load_compatible_dqn
from aero_ai_studio.observation.encoder import observation_vector
from aero_ai_studio.scenario.models import ScenarioSpec
from aero_ai_studio.simulation.base import ACTIONS


def _failure_reason(error):
    message=str(error).lower()
    if 'sensor' in message or 'laser' in message or 'fresh gazebo sample' in message:return 'stale_sensor'
    if 'physics movement outside validated tolerance' in message:return 'validator_failure'
    if any(term in message for term in ('gazebo service','worldcontrol','transport','service failed','timed out')):
        return 'service_failure'
    return 'service_failure'


def _sensor_evidence(observation,frame,simulation_time):
    state=observation.sensor_state
    timestamp=float(state.get('sensor_timestamp',state.get('sample_time',-1)))
    sequence=state.get('sequence')
    age=(simulation_time-timestamp)*1000
    values={key:state.get(key) for key in ('front_distance','left_distance','right_distance','back_distance',
            'goal_distance','goal_direction','goal_delta','moving_obstacle_distance','source')}
    return {'mode':observation.mode,'timestamp':timestamp,'sequence':sequence,'age_ms':age,
            'fresh':timestamp>=0 and sequence is not None and -2<=age<=20,
            'values':values,'frame':frame,'normalization':'sensor_vector_v1: clearance buckets; ray/goal distances clipped and scaled'}


def run_dqn_validation(checkpoint:Path|None,output:Path,*,gui=False,max_steps=250,environment_factory=None):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    report={'schema_version':'0.7.1','validation':'DQN Closed Loop Actual Gazebo',
        'status':'BLOCKED','dqn_closed_loop_actual_gazebo':'BLOCKED','reason':'incompatible_checkpoint',
        'control_mode':'PHYSICS','policy_mode':'dqn','inference_mode':'deterministic_greedy',
        'training_enabled':False,'epsilon':0.0,'online_learning':False,'weight_updates':False,
        'Safety':'OFF','checkpoint':None if checkpoint is None else str(Path(checkpoint).resolve()),
        'checks':{},'episode':{'started':False,'success':False,'actions_attempted':0,'actions_completed':0,
                               'termination_reason':'no_compatible_checkpoint'},'action_trace':[]}
    trace=[];env=None;agent=None
    inference_snapshot=None
    try:
        if checkpoint is None:
            raise DQNCheckpointError('DQN ACTUAL VALIDATION BLOCKED: NO COMPATIBLE CHECKPOINT')
        contract=load_compatible_dqn(checkpoint)
        agent=contract['agent'];metadata=contract['metadata'];scenario=ScenarioSpec.from_dict(contract['scenario'])
        config=contract['config'];artifact=contract['artifact']
        report.update(checkpoint=str(artifact),checkpoint_metadata=str(contract['metadata_path']),
            checkpoint_architecture={'network':'22 -> 128 ReLU -> 128 ReLU -> 4','encoder':'sensor_vector_v1',
                                     'observation_mode':'sensor','observation_dimension':22},
            training_provenance={'simulator':config['simulator'],'control_mode':config['gazebo_control_mode'],
                                 'observation_mode':config['observation_mode'],'action_mapping':contract['action_mapping'],
                                 'scenario':scenario.to_dict()},
            action_mapping={str(index):{'action':action,'physics_semantics':{
                'up':'linear.x=+0.5 m/s','down':'linear.x=-0.5 m/s',
                'left':'angular.z=+0.8 rad/s','right':'angular.z=-0.8 rad/s'}[action]}
                for index,action in enumerate(ACTIONS)},
            reason='running',checks={'checkpoint':'PASS','compatibility':'PASS'})
        import torch
        agent.network.eval();agent.target.eval()
        for parameter in (*agent.network.parameters(),*agent.target.parameters()):parameter.requires_grad_(False)
        agent.rng.seed(int(config.get('seed',42)))
        weights_before=[parameter.detach().clone() for parameter in agent.network.parameters()]
        target_before=[parameter.detach().clone() for parameter in agent.target.parameters()]
        learned_before=agent.learn_steps;buffer_before=len(agent.buffer)
        inference_snapshot=(weights_before,target_before,learned_before,buffer_before)
        if environment_factory is None:
            from aero_ai_studio.gazebo.environment import GazeboEnvironment
            environment_factory=lambda spec: GazeboEnvironment(spec,max_steps=max_steps,root=output/'worlds',gui=gui,
                control_mode='PHYSICS',max_sensor_age_ms=20,allow_geometric_fallback=False)
        env=environment_factory(scenario)
        launched=env.launch()
        if not launched.get('available',True):raise RuntimeError('Gazebo service/world launch unavailable')
        if getattr(env,'control_mode',None)!='PHYSICS':raise RuntimeError('DQN actual validation requires PHYSICS control mode')
        if getattr(env,'injected',False):raise RuntimeError('Actual validation cannot use an injected/fake transport')
        env.reset(seed=int(config.get('seed',42)))
        if not env.process or env.process.poll() is not None:raise RuntimeError('Gazebo server process is not alive')
        report['checks'].update(world='PASS',physics='PASS',checkpoint_loaded='PASS')
        report['episode'].update(started=True,termination_reason='timeout/max_steps')
        report['status']='RUNNING';report['dqn_closed_loop_actual_gazebo']='RUNNING';report['reason']='timeout/max_steps'
        report['observation_contract']={'mode':'sensor','dimension':22,'normalization':'sensor_vector_v1',
            'input_source':'actual Gazebo LaserScan plus Gazebo pose-derived relative goal features'}
        previous_sensor_sequence=0;success=False;termination='timeout/max_steps'
        for index in range(max_steps):
            before=env.get_state();before_pose=dict(env.pose);before_time=float(env.stepper.time)
            goal_before=math.dist((before_pose['x'],before_pose['y']),env.goal)
            observation=env.get_agent_observation('sensor',agent.local_radius)
            sensor=_sensor_evidence(observation,env.sensors.frame.to_dict(),before_time)
            if observation.mode!='sensor' or sensor['values']['source']!='gazebo_lidar':
                termination='incompatible_observation';raise DQNCheckpointError('Actual DQN observation is not Gazebo SENSOR data')
            if not sensor['fresh'] or sensor['sequence']<=previous_sensor_sequence:
                termination='stale_sensor';raise RuntimeError('Stale or non-advancing actual Gazebo sensor sequence')
            vector=observation_vector(observation)
            if len(vector)!=contract['agent_metadata']['input_size']:
                termination='incompatible_observation';raise DQNCheckpointError(
                    f'Gazebo observation vector dimension {len(vector)} != checkpoint {contract["agent_metadata"]["input_size"]}')
            with torch.inference_mode():action=agent.select_action(observation,epsilon=0.)
            decision=agent.get_decision_info();q_values=decision.get('q_values',{})
            if action not in ACTIONS or len(q_values)!=len(ACTIONS):
                termination='incompatible_checkpoint';raise DQNCheckpointError('DQN inference returned incompatible action/Q-value shape')
            action_index=ACTIONS.index(action);previous_sensor_sequence=int(sensor['sequence'])
            entry={'index':index,'simulation_time':before_time,'observation':observation.to_dict(),
                'observation_vector':vector,'sensor':sensor,'goal_relative_features':{
                    'direction':sensor['values']['goal_direction'],'delta':sensor['values']['goal_delta'],
                    'distance':sensor['values']['goal_distance']},'q_values':q_values,
                'selected_action_index':action_index,'selected_action':action,'epsilon':0.,
                'inference_mode':'deterministic_greedy','Safety':'OFF','before_pose':before_pose,
                'goal_distance_before':goal_before,'command_twist':None,'odometry_before':None,
                'odometry_after':None,'physical_validator':None,'collision_contact':None,
                'after_pose':None,'goal_distance_after':None,'reward':None,'done':False,'termination_reason':None}
            report['episode']['actions_attempted']+=1
            try:
                result=env.step(action)
                report['episode']['actions_completed']+=1
                after_pose=dict(env.pose);goal_after=math.dist((after_pose['x'],after_pose['y']),env.goal)
                transition=env.telemetry.get('action_transition',{})
                event=getattr(env,'collision_event',None)
                entry.update(after_pose=after_pose,goal_distance_after=goal_after,
                    command_twist=transition.get('commanded_twist'),odometry_before=transition.get('odometry_before'),
                    odometry_after=transition.get('odometry_after'),physical_validator=env.telemetry.get('pose_validation'),
                    collision_contact=None if event is None else (event.to_dict() if hasattr(event,'to_dict') else event),
                    reward=result.reward,done=bool(result.terminated or result.truncated),
                    termination_reason=result.reason,simulation_time_after=env.stepper.time)
                if result.reason=='goal' and result.terminated:
                    success=True;termination='goal';trace.append(entry);break
                if result.reason in ('collision','moving_obstacle_collision'):
                    termination='collision';trace.append(entry);break
                if result.reason=='timeout' or result.truncated:
                    termination='timeout/max_steps';trace.append(entry);break
                if result.terminated:
                    termination=result.reason;trace.append(entry);break
            except Exception as error:
                entry.update(after_pose=dict(env.pose) if env.pose else None,
                    goal_distance_after=None if env.pose is None else math.dist((env.pose['x'],env.pose['y']),env.goal),
                    command_twist=env.telemetry.get('action_transition',{}).get('commanded_twist'),
                    odometry_before=env.telemetry.get('action_transition',{}).get('odometry_before'),
                    odometry_after=env.telemetry.get('action_transition',{}).get('odometry_after'),
                    physical_validator=env.telemetry.get('pose_validation'),
                    collision_contact=getattr(env,'collision_event',None),termination_reason=_failure_reason(error),error=str(error),
                    step_recovery=env.telemetry.get('stepping'))
                termination=entry['termination_reason'];trace.append(entry);raise
            trace.append(entry)
        inference_unchanged=(agent.learn_steps==learned_before and len(agent.buffer)==buffer_before and
            all(torch.equal(a,b) for a,b in zip(weights_before,agent.network.parameters())) and
            all(torch.equal(a,b) for a,b in zip(target_before,agent.target.parameters())) and
            all(parameter.grad is None for parameter in (*agent.network.parameters(),*agent.target.parameters())))
        report['inference_integrity']={'model_eval':not agent.network.training and not agent.target.training,
            'gradients_disabled':all(not p.requires_grad for p in (*agent.network.parameters(),*agent.target.parameters())),
            'learn_steps_before':learned_before,'learn_steps_after':agent.learn_steps,
            'replay_size_before':buffer_before,'replay_size_after':len(agent.buffer),
            'weights_and_target_unchanged':inference_unchanged,'online_learning':False}
        if not inference_unchanged:raise RuntimeError('Inference-only DQN state changed during actual episode')
        report['checks'].update(sensor='PASS',observation='PASS',inference='PASS',action_execution='PASS' if len(trace)>1 else 'FAIL',
            physical_trajectory='PASS' if len(trace)>1 and any(e.get('after_pose') for e in trace) else 'FAIL',
            no_collision='PASS' if termination!='collision' else 'FAIL',goal='PASS' if success else 'FAIL',
            inference_integrity='PASS')
        report['episode'].update(success=success,termination_reason=termination,actions_completed=sum(e.get('reward') is not None for e in trace),
            final_pose=None if env.pose is None else dict(env.pose),goal={'x':env.goal[0],'y':env.goal[1]},
            final_goal_distance=None if env.pose is None else math.dist((env.pose['x'],env.pose['y']),env.goal))
        report['status']='PASS' if success and report['episode']['actions_attempted']>1 and report['episode']['actions_completed']>1 else 'FAIL'
        report['dqn_closed_loop_actual_gazebo']=report['status'];report['reason']=termination
    except DQNCheckpointError as error:
        message=str(error)
        reason=('no_compatible_checkpoint' if 'NO COMPATIBLE CHECKPOINT' in message else
                'incompatible_observation' if 'observation' in message.lower() else 'incompatible_checkpoint')
        status='FAIL' if reason=='incompatible_observation' else 'BLOCKED'
        report['status']=status;report['dqn_closed_loop_actual_gazebo']=status
        report['reason']=reason
        report['error']=message
    except Exception as error:
        report['status']='FAIL';report['dqn_closed_loop_actual_gazebo']='FAIL'
        report['reason']=_failure_reason(error);report['error']=str(error)
        report['episode']['termination_reason']=report['reason']
        if report['episode']['started']:
            report['episode']['actions_completed']=sum(e.get('reward') is not None for e in trace)
            report['episode']['final_pose']=None if env is None or env.pose is None else dict(env.pose)
    finally:
        if agent is not None and inference_snapshot is not None:
            weights_before,target_before,learned_before,buffer_before=inference_snapshot
            unchanged=(agent.learn_steps==learned_before and len(agent.buffer)==buffer_before and
                all(torch.equal(a,b) for a,b in zip(weights_before,agent.network.parameters())) and
                all(torch.equal(a,b) for a,b in zip(target_before,agent.target.parameters())) and
                all(parameter.grad is None for parameter in (*agent.network.parameters(),*agent.target.parameters())))
            report['inference_integrity']={'model_eval':not agent.network.training and not agent.target.training,
                'gradients_disabled':all(not p.requires_grad for p in (*agent.network.parameters(),*agent.target.parameters())),
                'learn_steps_before':learned_before,'learn_steps_after':agent.learn_steps,
                'replay_size_before':buffer_before,'replay_size_after':len(agent.buffer),
                'weights_and_target_unchanged':unchanged,'online_learning':False}
            if not unchanged:report.update(status='FAIL',dqn_closed_loop_actual_gazebo='FAIL',reason='inference_integrity_failure')
        report['action_trace']=trace
        write_json(output/'dqn_action_trace.json',trace)
        if env is not None:
            try:env.close()
            except Exception as error:
                report['shutdown_error']=str(error);report['status']='FAIL';report['dqn_closed_loop_actual_gazebo']='FAIL'
            alive=bool(env.process and env.process.poll() is None)
            report['checks']['shutdown']='FAIL' if alive else 'PASS'
            if alive:report['status']='FAIL';report['dqn_closed_loop_actual_gazebo']='FAIL'
        write_json(output/'dqn_runtime.json',report)
    return report


def main():
    parser=argparse.ArgumentParser(description='Inference-only DQN closed loop in actual Gazebo PHYSICS mode')
    parser.add_argument('--checkpoint',type=Path,help='Compatible DQN model directory or model.pt with provenance metadata')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--gui',action='store_true')
    parser.add_argument('--max-steps',type=int,default=250)
    args=parser.parse_args()
    report=run_dqn_validation(args.checkpoint,args.output,gui=args.gui,max_steps=args.max_steps)
    print(report)
    if report['status']!='PASS':raise SystemExit(2 if report['status']=='BLOCKED' else 1)


if __name__=='__main__':main()
