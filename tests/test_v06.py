from __future__ import annotations
from pathlib import Path
from threading import Event
import math
import pytest
from aero_ai_studio.observation.models import Observation
from aero_ai_studio.observation.canonical import CanonicalSensorObservation,ContinuousDistanceDiscretizer
from aero_ai_studio.observation.prediction import predict_motion
from aero_ai_studio.safety.layer import SafetyLayer
from aero_ai_studio.training.rewards import reward_components
from aero_ai_studio.training.curriculum import CurriculumSchedule
from aero_ai_studio.training.trainer import Trainer,TrainingConfig
from aero_ai_studio.evaluation.evaluator import Evaluator,EvaluationConfig
from aero_ai_studio.scenario.models import ScenarioSpec,SceneObject,DynamicObject
from aero_ai_studio.simulation.grid_world import GridWorld
from aero_ai_studio.models.registry import ModelRegistry
from aero_ai_studio.core.storage import read_json,write_json
from aero_ai_studio.replay.trajectory import trajectory
from aero_ai_studio.gazebo.environment import GazeboEnvironment
from aero_ai_studio.gazebo.sensor_provider import RangeSensorProvider
from aero_ai_studio.gazebo.entity_controller import GazeboEntityController
from aero_ai_studio.gazebo.stepping import GazeboStepper


def tiny():return ScenarioSpec(width=4,height=4,goal=(3,3))


def test_canonical_conversion_and_discretization():
    env=GridWorld(tiny())
    c=CanonicalSensorObservation.from_observation(env.get_agent_observation('sensor'))
    assert c.front_clearance==pytest.approx(.3) and c.goal_direction=='SE'
    d=ContinuousDistanceDiscretizer()
    assert [d.distance(x) for x in (.2,.5,2,4,8)]==['VERY_NEAR','NEAR','MEDIUM','FAR','CLEAR']
    assert len(d.encode(c))==6
    from aero_ai_studio.agents.q_learning import QLearningAgent
    agent=QLearningAgent(encoder='canonical',observation_mode='sensor')
    agent.select_action(env.get_agent_observation('sensor'),0)
    assert len(agent.get_decision_info()['encoded_state'])==6
    with pytest.raises(ValueError):d.distance(float('nan'))


def test_safety_allow_override_stop():
    obs=GridWorld(tiny()).get_agent_observation('sensor')
    scores={'up':20,'down':3,'left':10,'right':4}
    shield=SafetyLayer(True)
    assert not shield.check('down',obs,scores).override
    result=shield.check('up',obs,scores)
    assert result.override and result.final_action=='right'
    assert not SafetyLayer(False).check('up',obs,scores).override
    env=GridWorld(ScenarioSpec(width=4,height=4,goal=(3,3),objects=[SceneObject('wall',(1,0)),SceneObject('wall',(0,1))],randomization={'obstacle_position':True}))
    blocked=Observation('sensor',(0,0),(3,3),sensor_state={'front_distance':1,'back_distance':1,'left_distance':1,'right_distance':1,'goal_direction':'SE','goal_distance':4})
    assert shield.check('up',blocked,scores).final_action=='stop'


def test_prediction_ttc_and_crossing():
    old={'agent':[0,0],'dynamic_objects':[{'position':[3,0]}]}
    result=predict_motion((0,0),[(2,0)],old)
    assert result['motion']=='APPROACHING' and result['ttc']==2
    assert result['objects'][0]['predicted_position']==[1,0]
    cross=predict_motion((0,0),[(2,1)],{'agent':[0,0],'dynamic_objects':[{'position':[2,0]}]})
    assert cross['motion']=='CROSSING'


def test_reward_components_and_grid_logging():
    env=GridWorld(tiny())
    env.reward_version='v2'
    r=env.step('right')
    parts=env.get_metrics()['reward_components']
    assert sum(parts.values())==r.reward and parts['progress']==2 and parts['time']==-.1
    assert env.get_metrics()['minimum_clearance']>=0
    env.reset()
    assert env.step('stop').reason=='moving'


def test_domain_randomization_reproducible():
    s=tiny()
    s.dynamic_objects=[DynamicObject(position=(2,2))]
    s.randomization={'goal_position':True,'moving_speed':True}
    env=GridWorld(s)
    env.reset(92);a=env.get_state()
    env.reset(92);assert a==env.get_state()
    assert tuple(a['goal'])!=s.start


def test_curriculum_transition_and_resume(tmp_path):
    schedule=CurriculumSchedule(threshold=.8)
    assert not schedule.update(.7) and schedule.update(.8) and schedule.stage==1
    cfg=TrainingConfig(episodes=4,max_steps=10,observation_mode='sensor',state_encoder='compact',
                       curriculum_enabled=True,curriculum_interval=2,curriculum_threshold=0,checkpoint_interval=2)
    full,agent,_=Trainer(tiny(),cfg).run(tmp_path/'full')
    stop=Event()
    partial,_,meta=Trainer(tiny(),cfg).run(tmp_path/'partial',lambda r:stop.set() if r['episode']==2 else None,stop)
    cp=Path(meta['last_checkpoint'])
    run,resumed,_=Trainer(tiny(),cfg).run(tmp_path/'resume',resume=cp)
    assert resumed.table==agent.table
    assert read_json(full/'metrics.json')==read_json(run/'metrics.json')
    assert read_json(run/'curriculum.json')[-1]['next_stage']==2


class FakeTransport:
    """Protocol fixture only. This is NOT a simulation backend shipped to users."""
    def __init__(self):
        self.time=0.
        self.poses={'agent_marker':{'x':.5,'y':.5,'z':.25}}
        self.closed=False
        self.calls=[]
    def request(self,service,request_type,response_type,payload):
        self.calls.append((service,payload))
        if service.endswith('/scene/info'):
            return {'model':[{'name':name,'pose':{'position':p,'orientation':{'w':1}}} for name,p in self.poses.items()]}
        if service.endswith('/set_pose'):self.poses[payload['name']]=dict(payload['position'])
        if service.endswith('/control'):self.time+=payload.get('multi_step',0)*.001
        return {'data':True}
    def wait_for_topic(self,topic,message_type,timeout=None):return {'topic':topic,'message_type':'gz.msgs.'+message_type}
    def cursor(self,topic):return 0
    def messages_after(self,topic,sequence,timeout=0):return []
    def subscribe(self,*args):pass
    def sample(self,topic,min_time=-1,timeout=5):
        if self.time<min_time:raise TimeoutError('stale sample fixture')
        stamp={'sec':int(self.time),'nsec':int(round((self.time%1)*1e9))}
        if topic.endswith('/stats'):return {'sim_time':stamp}
        if topic.endswith('/pose/info'):
            return {'header':{'stamp':stamp},'pose':[{'name':name,'position':p,'orientation':{'w':1}} for name,p in self.poses.items()]}
        p=self.poses['agent_marker']
        return {'header':{'stamp':stamp},'ranges':[max(0.,v) for v in (4-p['x'],4-p['y'],p['x'],p['y'])],'range_max':100}
    def close(self):self.closed=True


def test_entity_controller_and_stepper_contract():
    t=FakeTransport()
    controller=GazeboEntityController(t,'fixture')
    assert controller.spawn_agent()['x']==.5
    controller.apply_action('right')
    assert controller.get_pose()['x']==1.5
    stepper=GazeboStepper(t,'fixture')
    assert stepper.step_simulation(2)==pytest.approx(.2)
    assert any(p.get('multi_step')==200 for s,p in t.calls)
    stepper.pause();stepper.resume();stepper.set_real_time_factor(2)


def test_sensor_provider_and_stale_sample():
    t=FakeTransport()
    provider=RangeSensorProvider(t,'fixture',(3.5,3.5))
    provider.start()
    obs=provider.get_range_observation(t.poses['agent_marker'])
    assert obs.sensor_state['canonical']['source']=='gazebo_lidar'
    with pytest.raises(TimeoutError):provider.get_range_observation(t.poses['agent_marker'],1)
    assert len(provider.get_lidar_scan()['ranges'])==4 and provider.get_camera_frame() is None
    provider.stop()


def test_gazebo_reset_closed_loop_trajectory_serialization(tmp_path):
    transport=FakeTransport()
    env=GazeboEnvironment(tiny(),transport=transport,root=tmp_path/'worlds')
    assert env.reset(1)==(0,0)
    events=[]
    from aero_ai_studio.explainability.brain_map import record_step
    for i,action in enumerate(['down']*3+['right']*3):
        before=env.get_state()
        result=env.step(action)
        step=record_step(1,i,tuple(before['agent']),dict.fromkeys(('up','down','left','right'),0),action,False,0,before,env.get_state(),result)
        step.update(pose=before['pose'],next_pose=env.get_state()['pose'],timestamp=env.get_state()['timestamp'],reward_components=env.get_metrics()['reward_components'])
        events.append(step)
    assert result.reason=='goal'
    episode={'reason':'goal','steps':events}
    path=tmp_path/'episode.json';write_json(path,episode)
    trace=trajectory(read_json(path))
    assert trace['points'][0]==[0,0] and trace['points'][-1]==[3,3]
    assert env.reset(2)==(0,0)
    assert env.step('up').reason=='collision'
    env.close();assert transport.closed


def test_safety_and_components_integrated_evaluation(tmp_path):
    run,agent,meta=Trainer(tiny(),TrainingConfig(episodes=10,max_steps=10,safety_enabled=True,reward_version='v2')).run(tmp_path/'runs')
    first=read_json(run/'episodes'/'episode_0001.json')
    assert 'safety_override_count' in first and 'reward_components' in first['steps'][0]
    model=ModelRegistry.save(tmp_path/'models','shield',agent,meta)
    output,summary=Evaluator(tiny(),EvaluationConfig(3,10,10000,safety_enabled=True)).run(model,tmp_path/'evaluations')
    assert 'average_minimum_clearance' in summary and summary['safety_override_count']>=0


def test_double_dqn_checkpoint(tmp_path):
    torch=pytest.importorskip('torch')
    from aero_ai_studio.agents.dqn import DQNAgent
    from aero_ai_studio.agents.base import Transition
    agent=DQNAgent(batch_size=2,buffer_size=20,double_dqn=True,warmup_steps=8,reward_clip=10)
    obs=GridWorld(tiny()).get_agent_observation('sensor')
    for i in range(7):agent.learn(Transition(obs,'right',100,obs,False))
    assert agent.last_loss is None
    agent.learn(Transition(obs,'right',100,obs,False))
    assert agent.last_loss is not None and agent.buffer.items[0][2]==10
    agent.save(tmp_path/'model.pt')
    restored=DQNAgent.load(tmp_path/'model.pt')
    assert restored.double_dqn and restored.warmup_steps==8
    assert all(torch.equal(a,b) for a,b in zip(agent.network.parameters(),restored.network.parameters()))


def test_double_dqn_uses_online_argmax_target_value(monkeypatch):
    torch=pytest.importorskip('torch')
    from aero_ai_studio.agents.dqn import DQNAgent
    from aero_ai_studio.agents.base import Transition
    agent=DQNAgent(gamma=.9,batch_size=2,buffer_size=10,double_dqn=True,target_interval=500)
    with torch.no_grad():
        for p in agent.network.parameters():p.zero_()
        for p in agent.target.parameters():p.zero_()
        agent.network[-1].bias.copy_(torch.tensor([1.,2.,3.,4.]))
        agent.target[-1].bias.copy_(torch.tensor([100.,2.,3.,5.]))
    expected=[]
    original=torch.nn.functional.smooth_l1_loss
    def loss(q,target):
        expected.extend(target.tolist())
        return original(q,target)
    monkeypatch.setattr(torch.nn.functional,'smooth_l1_loss',loss)
    obs=GridWorld(tiny()).get_agent_observation('sensor')
    for _ in range(4):agent.learn(Transition(obs,'right',1,obs,False))
    assert expected==pytest.approx([5.5,5.5])
