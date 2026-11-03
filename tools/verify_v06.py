from __future__ import annotations
from pathlib import Path
import argparse
from dataclasses import asdict
from aero_ai_studio.scenario.models import ScenarioSpec,SceneObject
from aero_ai_studio.scenario.generator import generate_scenario
from aero_ai_studio.training.trainer import Trainer,TrainingConfig
from aero_ai_studio.evaluation.evaluator import Evaluator,EvaluationConfig
from aero_ai_studio.evaluation.suites import evaluation_scenario
from aero_ai_studio.models.registry import ModelRegistry
from aero_ai_studio.core.storage import read_json,write_json


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--baseline-root',type=Path,default=Path('work/v05-validation'))
    args=p.parse_args()
    root=args.output.resolve()
    results={'scope':'Single-seed measurements, 20 evaluation episodes per dynamic cell; no tuned target success rate','training':{},'evaluations':[]}
    basic=ScenarioSpec(objects=[SceneObject('wall',(8,y)) for y in range(4,16)])
    spec=generate_scenario(20,73,'hard',moving_count=3,danger_count=0)
    spec.randomization={'obstacle_position':True,'moving_speed':True}
    configs=[('Basic_regression',basic,TrainingConfig(episodes=1000)),
             ('Compact_curriculum',spec,TrainingConfig(episodes=600,max_steps=150,seed=4242,observation_mode='sensor',state_encoder='compact',
                                                       reward_version='v2',curriculum_enabled=True,curriculum_interval=100)),
             ('DQN2_curriculum',spec,TrainingConfig(episodes=600,max_steps=150,seed=4242,algorithm='dqn',observation_mode='sensor',
                                                   learning_rate=.001,epsilon_decay=.995,epsilon_end=.05,double_dqn=True,warmup_steps=256,
                                                   reward_clip=10,reward_version='v2',curriculum_enabled=True,curriculum_interval=100)),
             ('DQN2_direct_hard',spec,TrainingConfig(episodes=600,max_steps=150,seed=4242,algorithm='dqn',observation_mode='sensor',
                                                   learning_rate=.001,epsilon_decay=.995,epsilon_end=.05,double_dqn=True,warmup_steps=256,
                                                   reward_clip=10,reward_version='v2',curriculum_enabled=False))]
    models={}
    for name,s,cfg in configs:
        print('START',name,flush=True)
        def progress(row):
            if row['episode']%100==0:print(name,row['episode'],row['success_rate'],flush=True)
        run,agent,meta=Trainer(s,cfg).run(root/name/'runs',progress)
        model=ModelRegistry.save(root/name/'models',name,agent,meta)
        models[name]=model
        results['training'][name]={'episodes':cfg.episodes,'success_rate':meta['success_rate'],'config':asdict(cfg),
                                  'curriculum':read_json(run/'curriculum.json') if (run/'curriculum.json').exists() else []}
        if name=='Basic_regression':
            _,evaluation=Evaluator(s,EvaluationConfig(100,200,100000)).run(model,root/name/'evaluations')
            results['regression']={k:evaluation[k] for k in ('success_rate','average_steps','collision_count','timeout_count')}
        write_json(root/'performance_v06.json',results)
    for label,directory in [('Compact_V05','C_compact_sensor'),('DQN_V05','D_dqn_sensor')]:
        paths=list((args.baseline_root/directory/'models').glob('*/metadata.json'))
        if paths:models[label]=paths[0].parent
    for name,model in models.items():
        suites=('static_known','static_unseen') if name=='Basic_regression' else ('static_unseen','dynamic_easy','dynamic_normal','dynamic_hard')
        for suite in suites:
            for safety in (False,True):
                current=evaluation_scenario(basic,suite,99173)
                if suite=='static_unseen':
                    current=generate_scenario(20,73,'normal',density=.1,moving_count=0,danger_count=0)
                    current.randomization={'obstacle_position':True}
                cfg=EvaluationConfig(20,150,100000,safety_enabled=safety,reward_version='v2',suite=suite)
                output,summary=Evaluator(current,cfg).run(model,root/'evaluations'/name)
                row={'agent':name,'environment':suite,'safety':safety,**{k:summary[k] for k in
                    ('episodes_completed','success_rate','collision_rate','timeout_rate','average_steps','average_reward','average_minimum_clearance','safety_override_count')}}
                results['evaluations'].append(row)
                print('EVAL',row,flush=True)
                write_json(root/'performance_v06.json',results)
    print('COMPLETE',root/'performance_v06.json',flush=True)


if __name__=='__main__':main()
