"""Generate a real SDF and attempt a bounded Gazebo process smoke if installed.

Process startup cannot automatically certify a rendered GUI frame.
"""
from pathlib import Path
import argparse
import time
from aero_ai_studio.scenario.models import ScenarioSpec, SceneObject
from aero_ai_studio.gazebo.world_generator import GazeboWorldGenerator
from aero_ai_studio.gazebo.environment import GazeboEnvironment
from aero_ai_studio.gazebo.diagnostics import gazebo_status, command
from aero_ai_studio.core.storage import write_json


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--gui',action='store_true')
    args=p.parse_args()
    scenario=ScenarioSpec(width=10,height=10,goal=(9,9),objects=[SceneObject('wall',(4,y)) for y in range(2,8)])
    world=GazeboWorldGenerator().generate(scenario,args.output/'generated_worlds')
    status=gazebo_status()
    result={'sdf_generated':True,'sdf':str(world),'gazebo':status,'actual_launch':False,'render_verified':False}
    if status['available']:
        ok,detail=command([status['executable'],'sdf','-k',str(world.resolve())],10)
        result['gz_sdf_validation']={'success':ok,'detail':detail}
        env=GazeboEnvironment(scenario,root=args.output/'generated_worlds')
        try:
            launched=env.launch(gui=args.gui)
            result['actual_launch']=env.process is not None
            time.sleep(3)
            result['process_state']=env.get_state()
        finally:
            env.close()
    write_json(args.output/'gazebo_smoke.json',result)
    print(result)


if __name__=='__main__':main()
