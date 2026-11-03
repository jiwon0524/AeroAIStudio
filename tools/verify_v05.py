"""Reproducible A/B/C/D/E measurements; no target success rate or privileged policy data."""
from pathlib import Path
from dataclasses import asdict
import argparse
import time
from aero_ai_studio.scenario.models import ScenarioSpec, SceneObject
from aero_ai_studio.scenario.generator import generate_scenario
from aero_ai_studio.training.trainer import Trainer, TrainingConfig
from aero_ai_studio.models.registry import ModelRegistry
from aero_ai_studio.evaluation.evaluator import Evaluator, EvaluationConfig
from aero_ai_studio.evaluation.generalization import GeneralizationEvaluator, GeneralizationConfig
from aero_ai_studio.gazebo.world_generator import GazeboWorldGenerator
from aero_ai_studio.gazebo.diagnostics import diagnose, gazebo_status
from aero_ai_studio.core.storage import write_json, read_json


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    root=args.output.resolve()
    basic=ScenarioSpec(objects=[SceneObject('wall',(8,y)) for y in range(4,16)])
    random_spec=generate_scenario(20,73,'normal',density=.10,moving_count=0,danger_count=0)
    random_spec.randomization={'obstacle_position':True}
    results={}
    cases=[('A_basic_fixed',basic,TrainingConfig(episodes=1000),100),
           ('B_basic_random',random_spec,TrainingConfig(episodes=3000,checkpoint_interval=500),200),
           ('C_compact_sensor',random_spec,TrainingConfig(episodes=3000,observation_mode='sensor',state_encoder='compact',checkpoint_interval=500),200),
           ('D_dqn_sensor',random_spec,TrainingConfig(episodes=1000,algorithm='dqn',observation_mode='sensor',learning_rate=.001,
                                                   epsilon_decay=.997,epsilon_end=.05,checkpoint_interval=250),200)]
    for name,scenario,config,evaluation_episodes in cases:
        print('START',name,flush=True)
        def progress(row):
            if row['episode']%500==0:
                print(name,row['episode'],'train success',row['success_rate'],flush=True)
        run,agent,meta=Trainer(scenario,config).run(root/name/'runs',progress)
        model=ModelRegistry.save(root/name/'models',name,agent,meta)
        output,info=Evaluator(scenario,EvaluationConfig(evaluation_episodes,200,10042)).run(model,root/name/'evaluations')
        ModelRegistry.attach_evaluation(model,output,info)
        rows=read_json(run/'metrics.json')
        results[name]={'config':asdict(config),'training_success':meta['success_rate'],
                        'last_100_training_success':sum(r['success'] for r in rows[-100:])/100,
                        'training_seconds':meta['training_seconds'],
                        'model_bytes':sum(f.stat().st_size for f in model.iterdir() if f.is_file()),
                        'evaluation':{key:info[key] for key in ('episodes_completed','success_rate','average_reward','average_steps',
                                                        'collision_count','timeout_count','path_efficiency')},
                        'evaluation_reset_seeds':[10043,10042+evaluation_episodes],
                        'training_reset_seeds':[43,42+config.episodes]}
        print('RESULT',name,results[name],flush=True)
        write_json(root/'performance_v05.json',results)
        if name=='C_compact_sensor':
            _,g=GeneralizationEvaluator(scenario,EvaluationConfig(50,200,30042),GeneralizationConfig(moving_obstacles=True,different_difficulty=True)).run(model,root/name/'generalization')
            results['generalization']={k:g[k] for k in ('training_scenario_success','unseen_scenario_success','generalization_gap')}
    world=GazeboWorldGenerator().generate(basic,root/'generated_worlds')
    results['E_gazebo']={'world_generated':True,'sdf':str(world),'availability':gazebo_status(),
                         'actual_launch':False,'render_verified':False}
    results['diagnostics']=diagnose(full=True)
    write_json(root/'performance_v05.json',results)
    print('COMPLETE',root/'performance_v05.json',flush=True)


if __name__=='__main__':main()
