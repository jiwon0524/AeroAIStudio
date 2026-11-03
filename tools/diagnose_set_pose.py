"""Host-only, one-request set_pose probe against an already running world.

Does not reset/step a simulation, subscribe to sensors, or launch Gazebo.
"""
from pathlib import Path
import argparse
import json
from aero_ai_studio.core.storage import write_json
from aero_ai_studio.gazebo.transport import HarmonicTransport


def run(world,partition,output,timeout=10):
    service=f'/world/{world}/set_pose'
    payload={'name':'simple_agent','position':{'x':1.5,'y':1.5,'z':.16},
             'orientation':{'x':0.,'y':0.,'z':0.,'w':1.}}
    report={'status':'FAIL','service':service,'partition':partition,'payload':payload,
            'request_type':'gz.msgs.Pose','response_type':'gz.msgs.Boolean',
            'pose_applied':'NOT VERIFIED','step_progress':'NOT REQUESTED','physics_motion':'NOT REQUESTED'}
    transport=None
    try:
        transport=HarmonicTransport(partition,timeout)
        report['schema']=transport.wait_for_service(service,'Pose','Boolean')
        # Exactly one RPC: deliberately disable the adapter's set_pose retry.
        report['response']=transport.request(service,'Pose','Boolean',payload,max_attempts=1)
        report['status']='PASS' if report['response'].get('data') is True else 'FAIL'
    except Exception as error:
        report['error']=str(error)
    finally:
        if transport is not None:
            report['service_requests']=transport.request_history
            transport.close()
        write_json(output,report)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--world',required=True)
    parser.add_argument('--partition',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=run(args.world,args.partition,args.output)
    print(json.dumps(report,indent=2))
    if report['status']!='PASS':raise SystemExit(1)


if __name__=='__main__':main()
