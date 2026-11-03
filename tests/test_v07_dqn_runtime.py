import json
from pathlib import Path
from types import SimpleNamespace
import pytest

torch=pytest.importorskip('torch')

from aero_ai_studio.agents.dqn import DQNAgent
from aero_ai_studio.core.storage import write_json,read_json
from aero_ai_studio.gazebo.dqn_runtime import DQNCheckpointError,checkpoint_contract,load_compatible_dqn
from aero_ai_studio.observation.models import Observation
from aero_ai_studio.scenario.models import ScenarioSpec
from aero_ai_studio.simulation.base import ACTIONS,StepResult
from aero_ai_studio.simulation.action_mapping import gazebo_physics_action_mapping
from tools.verify_v07_dqn import run_dqn_validation


def _scenario():
    return ScenarioSpec(width=6,height=4,start=(0,0),goal=(2,0),seed=7)


def _checkpoint(tmp_path,*,simulator='gazebo',control_mode='PHYSICS',observation_mode='sensor',action_mapping=None,
                input_size=22):
    path=tmp_path/'dqn_model';path.mkdir()
    agent=DQNAgent(seed=7,observation_mode='sensor',action_mapping=gazebo_physics_action_mapping())
    with torch.no_grad():
        for parameter in agent.network.parameters():parameter.zero_()
        agent.network[-1].bias[0]=2.
    agent.save(path/'model.pt')
    agent_meta=agent.get_metadata()
    if action_mapping is not None:agent_meta['action_mapping']=action_mapping
    agent_meta['input_size']=input_size
    write_json(path/'metadata.json',{'algorithm':'dqn','name':'fixture','version':'1',
        'training_config':{'algorithm':'dqn','simulator':simulator,'gazebo_control_mode':control_mode,
                           'observation_mode':observation_mode,'training_kind':'full','seed':7},
        'agent_metadata':agent_meta,'scenario':_scenario().to_dict()})
    return path


def test_compatible_physics_sensor_checkpoint_loads_eval_only(tmp_path):
    path=_checkpoint(tmp_path)
    contract=load_compatible_dqn(path)
    agent=contract['agent']
    assert contract['action_mapping']==agent.get_metadata()['action_mapping']
    assert contract['observation_dimension']==22 and contract['observation_mode']=='sensor'
    assert not agent.network.training and not agent.target.training
    assert all(not p.requires_grad for p in (*agent.network.parameters(),*agent.target.parameters()))


@pytest.mark.parametrize('kwargs,match',[
    ({'simulator':'grid'},'training environment'),
    ({'control_mode':'KINEMATIC'},'training environment'),
    ({'observation_mode':'local'},'training environment'),
    ({'action_mapping':[{'index':1,'action':'up','twist':{'linear_x':.5,'angular_z':0.}}]},'action mapping'),
    ({'input_size':21},'dimension'),
])
def test_incompatible_checkpoint_contract_is_rejected(tmp_path,kwargs,match):
    path=_checkpoint(tmp_path,**kwargs)
    with pytest.raises(DQNCheckpointError,match=match):checkpoint_contract(path)


def test_missing_checkpoint_is_reported_blocked_without_launch(tmp_path):
    report=run_dqn_validation(None,tmp_path/'out')
    assert report['status']=='BLOCKED'
    assert report['dqn_closed_loop_actual_gazebo']=='BLOCKED'
    assert report['reason']=='no_compatible_checkpoint'
    assert report['error']=='DQN ACTUAL VALIDATION BLOCKED: NO COMPATIBLE CHECKPOINT'
    assert (tmp_path/'out'/'dqn_runtime.json').exists()


class _Frame:
    def __init__(self,time,sequence):self.time=time;self.sequence=sequence
    def to_dict(self):return {'simulation_time':self.time,'sensor_timestamp':self.time,'sequence':self.sequence,
                              'source':'gazebo_lidar','age_ms':0.}


class _Process:
    def poll(self):return None


class PhysicsObservationFixture:
    def __init__(self,scenario,outcome='goal'):
        self.scenario=scenario;self.goal=(scenario.goal[0]+.5,scenario.goal[1]+.5)
        self.pose={'x':.5,'y':.5,'z':.16,'yaw':0.};self.stepper=SimpleNamespace(time=0.)
        self.control_mode='PHYSICS';self.injected=False;self.process=_Process();self.closed=False
        self.telemetry={};self.collision_event=None;self.sensors=SimpleNamespace(frame=None)
        self.sensor_sequence=0;self.outcome=outcome;self.agent_observation=None;self.max_steps=100

    def launch(self):return {'available':True}
    def _refresh_observation(self):
        self.sensor_sequence+=1
        self.sensors.frame=_Frame(self.stepper.time,self.sensor_sequence)
        state={'front_distance':10.,'left_distance':10.,'right_distance':10.,'back_distance':10.,
            'goal_distance':((self.goal[0]-self.pose['x'])**2+(self.goal[1]-self.pose['y'])**2)**.5,
            'goal_direction':'E','goal_delta':[self.goal[0]-self.pose['x'],self.goal[1]-self.pose['y']],
            'moving_obstacle_distance':None,'moving_obstacle_relative_motion':'UNKNOWN',
            'source':'gazebo_lidar','sensor_timestamp':self.stepper.time,'sequence':self.sensor_sequence}
        self.agent_observation=Observation('sensor',(int(self.pose['x']),int(self.pose['y'])),
            (int(self.goal[0]),int(self.goal[1])),sensor_state=state)
    def reset(self,seed=None):self._refresh_observation();return (0,0)
    def get_state(self):return {'pose':dict(self.pose),'timestamp':self.stepper.time,'telemetry':dict(self.telemetry)}
    def get_agent_observation(self,mode='sensor',radius=2):
        assert mode=='sensor';return self.agent_observation
    def step(self,action):
        before=dict(self.pose);self.pose['x']+=1.;self.stepper.time+=.1;self._refresh_observation()
        self.telemetry={'action_transition':{'commanded_twist':{'linear':{'x':.5},'angular':{'z':0.}},
            'odometry_before':{'linear_x':0.},'odometry_after':{'linear_x':.5}},
            'pose_validation':{'valid':True,'world_direction_ok':True,'odometry_direction_ok':True}}
        if self.outcome=='validator':raise RuntimeError('Physics movement outside validated tolerance')
        reason='collision' if self.outcome=='collision' else 'goal' if self.pose['x']>=self.goal[0] else 'moving'
        if self.outcome=='timeout':reason='timeout'
        return StepResult((int(self.pose['x']),int(self.pose['y'])),1.,reason in ('goal','collision'),
                          reason=='timeout',reason)
    def close(self):self.closed=True;self.process=None


@pytest.mark.parametrize('outcome,expected_status,reason,steps',[
    ('goal','PASS','goal',2),('collision','FAIL','collision',1),('timeout','FAIL','timeout/max_steps',1),
    ('validator','FAIL','validator_failure',1)])
def test_physics_closed_loop_outcomes_and_trace_serialization(tmp_path,outcome,expected_status,reason,steps):
    checkpoint=_checkpoint(tmp_path)
    output=tmp_path/'validation'
    def factory(scenario):
        env=PhysicsObservationFixture(scenario,outcome);env.max_steps=steps;return env
    report=run_dqn_validation(checkpoint,output,max_steps=steps,environment_factory=factory)
    assert report['status']==expected_status
    assert report['reason']==reason
    assert report['episode']['actions_attempted']==steps
    assert report['Safety']=='OFF' and report['training_enabled'] is False and report['epsilon']==0
    saved=read_json(output/'dqn_action_trace.json')
    assert len(saved)==steps
    assert saved[0]['selected_action_index']==0 and saved[0]['selected_action']=='up'
    assert saved[0]['q_values']['up']>saved[0]['q_values']['down']
    assert saved[0]['sensor']['fresh'] and saved[0]['sensor']['sequence']==1
    assert saved[0]['physical_validator'] is not None if outcome!='validator' else True
    assert report['inference_integrity']['weights_and_target_unchanged']
    if outcome=='goal':assert report['episode']['success'] and report['episode']['actions_completed']==2
    else:assert not report['episode']['success']


def test_stale_sensor_fails_before_policy_action(tmp_path):
    checkpoint=_checkpoint(tmp_path);output=tmp_path/'stale'
    def factory(scenario):
        env=PhysicsObservationFixture(scenario)
        original=env.get_agent_observation
        def stale(*args,**kwargs):
            result=original(*args,**kwargs);result.sensor_state['sensor_timestamp']=-1;return result
        env.get_agent_observation=stale
        return env
    report=run_dqn_validation(checkpoint,output,max_steps=5,environment_factory=factory)
    assert report['status']=='FAIL' and report['reason']=='stale_sensor'
    assert report['episode']['actions_attempted']==0


@pytest.mark.parametrize('action,linear,angular',[('up',.5,0.),('down',-.5,0.),('left',0.,.8),('right',0.,-.8)])
def test_dqn_action_order_maps_to_existing_physics_twist(action,linear,angular):
    from aero_ai_studio.gazebo.physics_controller import PhysicsEntityController
    from test_v06 import FakeTransport
    transport=FakeTransport();transport.publish=lambda *args:None
    controller=PhysicsEntityController(transport,'test');controller.apply_action(action)
    command=controller.last_published_command
    assert command['linear']['x']==linear and command['angular']['z']==angular


def test_gazebo_sensor_vector_is_22_dimensional_and_normalized(tmp_path):
    from aero_ai_studio.observation.encoder import observation_vector
    env=PhysicsObservationFixture(_scenario());env.reset()
    vector=observation_vector(env.get_agent_observation())
    assert len(vector)==22 and all(0.<=value<=1. for value in vector if value>=0)

