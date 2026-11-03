from pathlib import Path
from statistics import mean,pstdev
import argparse
from aero_ai_studio.training.trainer import Trainer,TrainingConfig
from aero_ai_studio.scenario.generator import generate_scenario
from aero_ai_studio.models.registry import ModelRegistry
from aero_ai_studio.evaluation.evaluator import Evaluator,EvaluationConfig
from aero_ai_studio.evaluation.suites import evaluation_scenario
from aero_ai_studio.core.storage import write_json


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();root=args.output.resolve()
    results={'seeds':[],'scope':'Three training seeds; 200 paired evaluation episodes per Safety condition; stage minimums enforced'}
    spec=generate_scenario(20,73,'hard',moving_count=3,danger_count=0)
    for seed in (7,42,99):
        cfg=TrainingConfig(episodes=2000,max_steps=150,seed=seed,algorithm='dqn',learning_rate=.001,observation_mode='sensor',
               double_dqn=True,warmup_steps=256,reward_clip=10,reward_version='v2',epsilon_decay=.998,epsilon_end=.05,
               curriculum_enabled=True,curriculum_interval=50,curriculum_threshold=.8,
               curriculum_minimum_episodes=(100,100,100,100,400),curriculum_minimum_evaluations=2,checkpoint_interval=250)
        print('TRAIN',seed,flush=True)
        def progress(row):
            if row['episode']%250==0:print(seed,row['episode'],row.get('curriculum_stage'),row['success_rate'],flush=True)
        run,agent,metadata=Trainer(spec,cfg).run(root/f'seed_{seed}'/'runs',progress)
        attempts=0
        while metadata['hard_training_episodes']<400 and attempts<2:
            cfg.episodes+=1500;attempts+=1
            print('EXTEND BUDGET FOR HARD EXPOSURE',seed,cfg.episodes,flush=True)
            run,agent,metadata=Trainer(spec,cfg).run(root/f'seed_{seed}'/'runs',progress,resume=Path(metadata['last_checkpoint']))
        model=ModelRegistry.save(root/f'seed_{seed}'/'models',f'DQN2_exposure_seed_{seed}',agent,metadata)
        row={'seed':seed,'total_episodes':metadata['episodes_completed'],'hard_training_episodes':metadata['hard_training_episodes'],
             'curriculum_complete':metadata['curriculum_complete'],'curriculum_state':metadata['curriculum_state'],'evaluations':[]}
        scene=evaluation_scenario(spec,'dynamic_hard',99173)
        for safety in (False,True):
            path,summary=Evaluator(scene,EvaluationConfig(200,150,100000+seed*1000,safety_enabled=safety,reward_version='v2',suite='dynamic_hard')).run(model,root/f'seed_{seed}'/'evaluations')
            measured={'safety':safety,**{k:summary[k] for k in ('success_rate','collision_rate','timeout_rate','safety_override_count',
              'useful_override_heuristic','harmful_override_heuristic','near_collision_count','average_minimum_clearance','average_steps')}}
            row['evaluations'].append(measured)
            print('EVAL',seed,measured,flush=True)
        results['seeds'].append(row)
        results['aggregates']={}
        for safety in (False,True):
            values=[next(e for e in r['evaluations'] if e['safety']==safety) for r in results['seeds']]
            results['aggregates']['ON' if safety else 'OFF']={k:{'mean':mean(e[k] for e in values),'std':pstdev(e[k] for e in values),
                'min':min(e[k] for e in values),'max':max(e[k] for e in values)} for k in ('success_rate','collision_rate','timeout_rate')}
        write_json(root/'learning_v07.json',results)
    print('COMPLETE',root/'learning_v07.json',flush=True)


if __name__=='__main__':main()
