"""Scenario, performance planning, and export helpers for PHYSICS DQN training."""
from __future__ import annotations
import json
import statistics
from pathlib import Path
from aero_ai_studio.scenario.models import ScenarioSpec,SceneObject


def dqn_validation_scenario():
    """Match the Core 7 full-obstacle verifier's world geometry exactly."""
    return ScenarioSpec(name='v071_gazebo_dqn_obstacle',width=10,height=10,start=(1,1),goal=(5,2),
        objects=[SceneObject('wall',(7,7)),SceneObject('static_obstacle',(7,5)),SceneObject('static_obstacle',(3,1))],
        seed=42)


def find_actual_action_cost(validation_root:Path):
    candidates=[]
    for report_path in Path(validation_root).glob('*/runtime_v07.json'):
        try:
            report=json.loads(report_path.read_text(encoding='utf-8'))
            if report.get('status')!='PASS' or report.get('checks',{}).get('closed_loop')!='PASS':continue
            episode_path=report_path.with_name('episode.json')
            episode=json.loads(episode_path.read_text(encoding='utf-8'))
            values=[step.get('telemetry',{}).get('wall_step_seconds') for step in episode.get('steps',[])]
            values=[float(value) for value in values if isinstance(value,(int,float)) and value>0]
            if len(values)>=10:
                candidates.append((report_path.stat().st_mtime,report_path,episode,values))
        except (OSError,ValueError,json.JSONDecodeError):continue
    if not candidates:return None
    _,path,episode,values=max(candidates,key=lambda item:item[0])
    return {'source':str(path),'actions_per_episode':len(values),
            'mean_action_seconds':statistics.mean(values),'median_action_seconds':statistics.median(values),
            'episode_success':episode.get('success'),'episode_reason':episode.get('reason')}


def estimate_training_cost(episodes,max_steps,evaluation_interval,evaluation_episodes,action_cost):
    evaluation_rounds=(max(1,(episodes+evaluation_interval-1)//evaluation_interval)
                       if evaluation_episodes else 0)
    training_action_cap=episodes*max_steps
    evaluation_action_cap=evaluation_rounds*evaluation_episodes*max_steps
    reference_actions=None if action_cost is None else min(max_steps,action_cost['actions_per_episode'])
    planning_training_actions=training_action_cap if reference_actions is None else episodes*reference_actions
    reset_service_equivalents=(episodes+evaluation_rounds*evaluation_episodes)*3
    if action_cost is None:
        expected_seconds=maximum_seconds=None
    else:
        unit=action_cost['mean_action_seconds']
        expected_seconds=(planning_training_actions+evaluation_action_cap+reset_service_equivalents)*unit
        maximum_seconds=(training_action_cap+evaluation_action_cap+reset_service_equivalents)*unit
    return {'episodes':episodes,'max_steps':max_steps,'reference_actions_per_episode':reference_actions,
        'reference_action_time_source':None if action_cost is None else action_cost['source'],
        'measured_mean_action_wall_seconds':None if action_cost is None else action_cost['mean_action_seconds'],
        'estimated_training_physics_actions':planning_training_actions,
        'training_physics_action_upper_bound':training_action_cap,
        'evaluation_rounds':evaluation_rounds,'evaluation_episodes':evaluation_episodes,
        'evaluation_physics_action_upper_bound':evaluation_action_cap,
        'reset_service_equivalent_calls':reset_service_equivalents,
        'estimated_wall_seconds':expected_seconds,'upper_bound_wall_seconds':maximum_seconds,
        'wall_estimate_method':'measured Core 7 PHYSICS action wall time; each reset RPC-equivalent conservatively charged one action duration; process startup and host load can vary'}
