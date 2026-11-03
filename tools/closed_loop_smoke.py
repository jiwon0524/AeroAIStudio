"""Actual native Gazebo loop or an explicit NOT VERIFIED result; no fake fallback."""
from pathlib import Path
import argparse
from aero_ai_studio.core.storage import write_json
from aero_ai_studio.gazebo.diagnostics import gazebo_status,diagnose
from aero_ai_studio.gazebo.environment import GazeboEnvironment
from aero_ai_studio.scenario.models import ScenarioSpec
from aero_ai_studio.explainability.brain_map import record_step
from aero_ai_studio.observation.canonical import CanonicalSensorObservation


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--gui',action='store_true')
    args=parser.parse_args()
    status=gazebo_status()
    report={'status':'NOT VERIFIED','diagnostics':diagnose(),'checks':{},'render_verified':False}
    args.output.mkdir(parents=True,exist_ok=True)
    if status['available']:
        env=GazeboEnvironment(ScenarioSpec(width=10,height=10,goal=(3,3)),root=args.output/'worlds',gui=args.gui)
        try:
            state=env.reset(42)
            report['checks'].update(world_loaded=True,agent_exists=True,sensor_received=True)
            events=[]
            # Deterministic world-coordinate rule navigation in an empty generated world.
            for i,action in enumerate(['right']*3+['down']*3):
                before=env.get_state()
                observation=env.get_agent_observation('sensor')
                result=env.step(action)
                after=env.get_state()
                event=record_step(1,i,state,dict.fromkeys(('up','down','left','right'),0),action,False,0,before,after,result)
                event.update(observation=observation.to_dict(),pose=before['pose'],next_pose=after['pose'],timestamp=after['timestamp'],
                             proposed_action=action,final_action=action,reward_components=env.get_metrics()['reward_components'])
                events.append(event)
                state=result.observation
                if result.terminated or result.truncated:break
            report['checks'].update(entity_moved=any(s['pose']!=s['next_pose'] for s in events),goal_reached=result.reason=='goal',sensor_updated=events[-1]['timestamp']>events[0]['timestamp'])
            write_json(args.output/'episode.json',{'episode':1,'success':result.reason=='goal','reason':result.reason,'steps':events})
            env.reset(43)
            report['checks']['reset']=env.get_observation()==(0,0)
            report['checks']['collision']=env.step('up').reason=='collision'
            report['status']='PASSED' if all(report['checks'].values()) else 'FAILED'
        except Exception as error:
            report.update(status='FAILED',error=str(error))
        finally:
            env.close()
            report['checks']['clean_shutdown']=env.process is None or env.process.poll() is not None
    write_json(args.output/'closed_loop_smoke.json',report)
    print(report)
    if report['status']=='FAILED':raise SystemExit(1)


if __name__=='__main__':main()
