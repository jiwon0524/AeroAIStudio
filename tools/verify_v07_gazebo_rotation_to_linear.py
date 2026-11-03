#!/usr/bin/env python3
"""Run bounded fresh-process ROTATION_TO_LINEAR trials through production validation."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))

from aero_ai_studio.core.storage import write_json
from aero_ai_studio.gazebo.environment import GazeboEnvironment
from aero_ai_studio.training.gazebo_dqn import dqn_validation_scenario


def _run_trial(output:Path,trial_index:int,*,gui=False,env_factory=None):
    output=Path(output)/f'trial_{trial_index:02d}';output.mkdir(parents=True,exist_ok=True)
    if env_factory is None:env_factory=GazeboEnvironment
    report={"trial":trial_index,"status":"NOT_STARTED","control_mode":"PHYSICS",
        "action_sequence":["right","right","right","down"],"target_transition":"ROTATION_TO_LINEAR",
        "uses_production_environment_step":True,"uses_production_pose_validator":True,"actions":[]}
    env=None
    try:
        env=env_factory(dqn_validation_scenario(),max_steps=4,root=output/'worlds',gui=gui,
            control_mode='PHYSICS',max_sensor_age_ms=20,allow_geometric_fallback=False)
        launch=env.launch()
        if not launch.get('available',True) or env.injected or env.control_mode!='PHYSICS':
            raise RuntimeError('Verifier requires actual Gazebo PHYSICS transport')
        env.reset(seed=42)
        report.update(status='RUNNING',actual_world=env.world_name,
            process=env.manager.status(),partition=env.manager.partition,
            reset_initialization=dict(env.initialization_checks),
            sensor_contract={'freshness_limit_ms':20,'initial_sensor_age_ms':
                env.sensors.frame.age_ms if getattr(env.sensors,'frame',None) else None},
            contact_topic=env.contact_topic)
        for index,action in enumerate(report['action_sequence']):
            entry={'index':index,'action':action,'before_pose':dict(env.pose),
                'before_simulation_time':float(env.stepper.time)}
            try:
                result=env.step(action)
                entry['result']={'terminated':result.terminated,'truncated':result.truncated,
                    'reason':result.reason,'reward':result.reward}
            except Exception as error:
                entry['exception']={'type':type(error).__name__,'message':str(error)}
            entry['action_transition']=env.telemetry.get('action_transition')
            entry['pose_validation']=env.telemetry.get('pose_validation')
            entry['sensor_age_ms']=env.telemetry.get('sensor_age_ms')
            entry['contact_state']=env.telemetry.get('contacts')
            entry['step_evidence']=dict(getattr(env.stepper,'last_verification',{}))
            entry['after_pose']=None if env.pose is None else dict(env.pose)
            entry['after_simulation_time']=float(env.stepper.time)
            report['actions'].append(entry)
            if 'exception' in entry:break
            if result.terminated or result.truncated:break
        target=next((row for row in report['actions'] if
            (row.get('action_transition') or {}).get('command_mode_transition')==
            'ROTATION_TO_LINEAR'),None)
        report['target_transition_found']=target is not None
        report['target_pose_validation']=None if target is None else target.get('pose_validation')
        report['target_body_history']=(None if target is None else
            (target.get('action_transition') or {}).get('world_pose_history_summary'))
        report['target_world_pose_history']=(None if target is None else
            (target.get('action_transition') or {}).get('world_pose_history'))
        report['collision_free']=not any(
            (row.get('pose_validation') or {}).get('collision_may_block_motion') is True or
            (row.get('contact_state') or {}).get('new_contact_event') is True or
            'collision' in str((row.get('result') or {}).get('reason',''))
            for row in report['actions'])
        validation=target.get('pose_validation') or {} if target else {}
        report['production_pose_validation_pass']=validation.get('valid') is True
        report['collision']=not report['collision_free']
        body_history=report.get('target_body_history') or {}
        report['world_pose_evidence_pass']=bool(
            body_history.get('world_pose_history_available') is True and
            body_history.get('world_pose_history_fresh') is True and
            body_history.get('world_pose_history_dense_enough') is True and
            int(body_history.get('world_pose_sample_count',0))>=3)
        report['transient_subtype_used']=validation.get('discrepancy_classification')==\
            'validated_rotation_to_linear_transient'
        if target is None:report['status']='TARGET_TRANSITION_NOT_FOUND'
        elif target.get('exception') or validation.get('valid') is not True or not report['collision_free']:
            report['status']='PRODUCTION_VALIDATOR_REJECTED_TRANSITION'
        elif report['transient_subtype_used']:
            report['status']='PRODUCTION_VALIDATOR_ACCEPTED_R2L_TRANSIENT'
        else:
            report['status']='PRODUCTION_VALIDATOR_ACCEPTED_NORMAL'
        report['acceptance_path']=('ROTATION_TO_LINEAR_TRANSIENT' if report['transient_subtype_used'] and
            validation.get('valid') is True and report['collision_free'] else
            'NORMAL' if validation.get('valid') is True and report['collision_free'] else 'NONE')
        report['final_process']=env.manager.status()
    except Exception as error:
        report.update(status='INFRASTRUCTURE_FAILURE',
            error={'type':type(error).__name__,'message':str(error)})
    finally:
        if env is not None:
            try:env.close();report['shutdown']='PASS'
            except Exception as error:
                report['shutdown']='FAIL';report['shutdown_error']=str(error)
        report['evidence_file']=str(output/'trial.json')
        write_json(output/'trial.json',report)
    return report


def run_verifier(output:Path,*,gui=False,trials=3,env_factory=None):
    if not 1<=int(trials)<=5:raise ValueError('trials must be between 1 and 5')
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    trial_reports=[_run_trial(output,index+1,gui=gui,env_factory=env_factory)
        for index in range(int(trials))]
    accepted=[trial for trial in trial_reports if trial.get('acceptance_path') in
        ('NORMAL','ROTATION_TO_LINEAR_TRANSIENT')]
    transient=any(trial.get('acceptance_path')=='ROTATION_TO_LINEAR_TRANSIENT' for trial in accepted)
    normal=any(trial.get('acceptance_path')=='NORMAL' for trial in accepted)
    failed=any(trial.get('status')=='PRODUCTION_VALIDATOR_REJECTED_TRANSITION' for trial in trial_reports)
    infra=any(trial.get('status') in ('INFRASTRUCTURE_FAILURE','TARGET_TRANSITION_NOT_FOUND')
        for trial in trial_reports)
    if (failed or infra) and (normal or transient):status='PARTIAL_TRIAL_FAILURE'
    elif transient:status='PRODUCTION_VALIDATOR_ACCEPTED_R2L_TRANSIENT'
    elif normal and not failed and not infra:status='NORMAL_ACTUAL_VERIFIED_R2L_TRANSIENT_NOT_REPRODUCED'
    elif normal:status='PARTIAL_TRIAL_FAILURE'
    elif infra:status='INFRASTRUCTURE_FAILURE'
    else:status='PRODUCTION_VALIDATOR_REJECTED_TRANSITION'
    report={'schema_version':'0.7.1','verifier':'production ROTATION_TO_LINEAR PHYSICS action validation',
        'status':status,'control_mode':'PHYSICS','trials_requested':int(trials),'trials_completed':len(trial_reports),
        'action_sequence':['right','right','right','down'],'target_transition':'ROTATION_TO_LINEAR',
        'uses_production_environment_step':True,'uses_production_pose_validator':True,
        'dqn_used':False,'training_used':False,'reset_semantics_changed':False,
        'acceptance_paths':[trial.get('acceptance_path','NONE') for trial in trial_reports],
        'trials':trial_reports,
        'evidence_file':str(output/'rotation_to_linear_production_verifier.json')}
    write_json(output/'rotation_to_linear_production_verifier.json',report)
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--gui',action='store_true')
    parser.add_argument('--trials',type=int,default=3,choices=range(1,6))
    args=parser.parse_args(argv)
    report=run_verifier(args.output,gui=args.gui,trials=args.trials)
    print('ROTATION_TO_LINEAR production verifier: '+report['status'])
    for trial in report['trials']:
        print(f"trial {trial['trial']}: production pose validation: "
            f"{'PASS' if trial.get('production_pose_validation_pass') else 'FAIL'}; "
            f"acceptance path: {trial.get('acceptance_path','NONE')}; "
            f"collision: {trial.get('collision',False)}; "
            f"world pose evidence: {'PASS' if trial.get('world_pose_evidence_pass') else 'FAIL'}")
    print('evidence: '+report['evidence_file'])
    return 0 if report['status'] in (
        'PRODUCTION_VALIDATOR_ACCEPTED_R2L_TRANSIENT',
        'NORMAL_ACTUAL_VERIFIED_R2L_TRANSIENT_NOT_REPRODUCED') else 1


if __name__=='__main__':raise SystemExit(main())
