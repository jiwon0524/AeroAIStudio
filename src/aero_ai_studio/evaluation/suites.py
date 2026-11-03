from aero_ai_studio.scenario.models import ScenarioSpec
from aero_ai_studio.scenario.generator import generate_scenario

SUITES=('custom','static_known','static_unseen','dynamic_easy','dynamic_normal','dynamic_hard','gazebo_static')


def evaluation_scenario(spec: ScenarioSpec,suite: str,seed: int) -> ScenarioSpec:
    if suite not in SUITES:raise ValueError('Unknown evaluation suite')
    result=ScenarioSpec.from_dict(spec.to_dict())
    if suite=='gazebo_static':result.dynamic_objects=[]
    if suite=='static_unseen':
        result.dynamic_objects=[]
        result.randomization['obstacle_position']=True
    elif suite.startswith('dynamic_'):
        difficulty=suite.split('_',1)[1]
        result=generate_scenario(spec.width,seed,difficulty,moving_count={'easy':1,'normal':2,'hard':3}[difficulty],danger_count=0)
        result.randomization['obstacle_position']=True
    return result
