from types import SimpleNamespace

from aero_ai_studio.core.storage import read_json
from tools import diagnose_v07_gazebo_motion_transition as diagnostic


def test_transition_diagnostic_captures_up_to_right_even_when_strict_validator_fails(tmp_path, monkeypatch):
    constructed={}

    class FakeEnvironment:
        def __init__(self,scenario,**kwargs):
            constructed.update(kwargs)
            self.injected=False
            self.control_mode=kwargs['control_mode']
            self.world_name='fixture_world'
            self.manager=SimpleNamespace(partition='fixture_partition',status=lambda:{'status':'Running'})
            self.controller=SimpleNamespace(pose_topic='/world/fixture_world/pose/info')
            self.initialization_checks={'reset_applied':'PASS'}
            self.pose={'x':1.5,'y':1.5,'yaw':0.}
            self.stepper=SimpleNamespace(time=0.)
            self.telemetry={}
            self.actions=[]

        def launch(self):
            return {'available':True}

        def reset(self,seed=None):
            return None

        def step(self,action):
            self.actions.append(action)
            self.stepper.time+=.1
            self.pose={'x':1.5+.025*len(self.actions),'y':1.5,
                       'yaw':0. if action=='up' else -.012}
            transition='OTHER' if action=='up' else 'LINEAR_TO_ROTATION'
            history=[{'simulation_timestamp':self.stepper.time-.02+i*.01,
                      'world_x':1.5+.005*i,'world_y':1.5,'world_yaw':-.001*i}
                     for i in range(3)]
            summary={'world_pose_sample_count':3,'world_pose_history_fresh':True,
                'world_pose_history_dense_enough':True,'world_pose_history_max_gap':.01,
                'world_velocity_sample_count':2,'world_angular_velocity_sample_count':2,
                'world_forward_velocity_samples':[
                    {'simulation_timestamp':self.stepper.time-.015,'forward_velocity':.5},
                    {'simulation_timestamp':self.stepper.time-.005,'forward_velocity':.5}],
                'world_angular_velocity_samples':[
                    {'simulation_timestamp':self.stepper.time-.015,'angular_velocity':0.},
                    {'simulation_timestamp':self.stepper.time-.005,'angular_velocity':-.1}]}
            twist={'linear':{'x':.5 if action=='up' else 0.},
                   'angular':{'z':0. if action=='up' else -.8}}
            self.telemetry={'action_transition':{
                'action':action,'command_mode_transition':transition,
                'commanded_twist':twist,'world_pose_history':history,
                'world_pose_history_summary':summary},
                'pose_validation':{'valid':action!='right'}}
            if action=='right':
                raise RuntimeError('Physics movement outside validated tolerance')
            return SimpleNamespace(reward=0.,terminated=False,truncated=False,reason='moving')

        def close(self):
            return None

    monkeypatch.setattr(diagnostic,'GazeboEnvironment',FakeEnvironment)
    report=diagnostic.run_diagnostic(tmp_path)
    saved=read_json(tmp_path/'motion_transition_diagnostic.json')
    assert report['status']=='CAPTURED_WITH_VALIDATOR_FAILURE'
    assert saved['status']==report['status']
    assert report['target_transition_found']
    assert report['world_pose_history_sufficient']
    assert constructed['control_mode']=='PHYSICS'
    assert constructed['capture_world_pose_history'] is True
    assert report['action_sequence']==['up','right']
    target=report['actions'][1]
    assert target['action_transition']['command_mode_transition']=='LINEAR_TO_ROTATION'
    assert target['pose_validation']['valid'] is False
    assert target['action_transition']['world_pose_history']
