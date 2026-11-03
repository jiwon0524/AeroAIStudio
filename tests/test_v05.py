from pathlib import Path
from threading import Event
import xml.etree.ElementTree as ET
import pytest
from aero_ai_studio.observation.models import Observation, Cell
from aero_ai_studio.observation.provider import observe
from aero_ai_studio.observation.encoder import CompactStateEncoder, observation_vector
from aero_ai_studio.scenario.models import ScenarioSpec, SceneObject, DynamicObject
from aero_ai_studio.simulation.grid_world import GridWorld
from aero_ai_studio.agents.base import Agent, Transition
from aero_ai_studio.agents.q_learning import QLearningAgent
from aero_ai_studio.training.trainer import Trainer, TrainingConfig
from aero_ai_studio.training.checkpoint import CheckpointStore
from aero_ai_studio.models.registry import ModelRegistry
from aero_ai_studio.agents.factory import load_agent
from aero_ai_studio.core.storage import read_json
from aero_ai_studio.evaluation.evaluator import Evaluator, EvaluationConfig
from aero_ai_studio.evaluation.generalization import GeneralizationEvaluator, GeneralizationConfig
from aero_ai_studio.explainability.brain_map import BrainEvent
from aero_ai_studio.gazebo.world_generator import GazeboWorldGenerator
from aero_ai_studio.gazebo.environment import GazeboEnvironment
from aero_ai_studio.gazebo.diagnostics import gazebo_status, diagnose


def tiny():
    return ScenarioSpec(width=4, height=4, goal=(3,3))


def test_local_observation_tiles_and_no_full_grid():
    s = tiny()
    s.objects = [SceneObject('wall',(1,0)), SceneObject('danger_zone',(1,1)), SceneObject('slow_zone',(0,2))]
    env = GridWorld(s)
    for radius in (1,2,3):
        obs = env.get_agent_observation('local',radius)
        assert len(obs.local_grid) == 2*radius+1
        assert obs.local_grid[radius][radius] == Cell.AGENT
        assert obs.local_grid[radius][radius+1] == Cell.WALL
        assert obs.local_grid[radius-1][radius] == Cell.WALL
        assert not obs.full_grid and not obs.sensor_state
    assert env.get_agent_observation('full_debug').full_grid
    assert not env.get_agent_observation('basic').sensor_state


def test_sensor_observation_and_compact_encoder():
    s = tiny()
    s.objects = [SceneObject('wall',(1,0))]
    env = GridWorld(s)
    obs = env.get_agent_observation('sensor')
    assert obs.sensor_state['front_distance'] == 1 and obs.sensor_state['right_distance'] == 1
    assert obs.sensor_state['goal_direction'] == 'SE'
    encoded = CompactStateEncoder().encode(obs)
    assert encoded == ('SE','BLOCKED','BLOCKED','BLOCKED','CLEAR',False,False)
    assert len(observation_vector(obs)) == 22
    assert not obs.full_grid and not obs.local_grid


def test_moving_observation_relative_motion():
    s = tiny()
    s.dynamic_objects = [DynamicObject(position=(3,0),movement='horizontal',direction=-1)]
    env = GridWorld(s)
    assert env.get_agent_observation('sensor').sensor_state['moving_obstacle_relative_motion'] == 'UNKNOWN'
    env.step('down')
    obs = env.get_agent_observation('sensor')
    assert obs.sensor_state['moving_obstacle_relative_motion'] == 'APPROACHING'
    assert obs.sensor_state['moving_obstacle_distance'] > 0
    # Pure provider handles leaving/static based on same object index and old agent pose.
    old = env.get_state()
    changed = {**old, 'dynamic_objects': [{'position':[3,0]}]}
    assert observe(changed,'sensor',previous=old).sensor_state['moving_obstacle_relative_motion'] == 'LEAVING'
    assert observe(old,'sensor',previous=old).sensor_state['moving_obstacle_relative_motion'] == 'STATIC'


def test_agent_interface_compact_q_and_save(tmp_path):
    agent = QLearningAgent(encoder='compact',observation_mode='sensor')
    assert isinstance(agent, Agent)
    obs = GridWorld(tiny()).get_agent_observation('sensor')
    a = agent.select_action(obs,0)
    agent.learn(Transition(obs,a,10,obs,True))
    agent.save(tmp_path/'q_table.json')
    restored = load_agent(tmp_path)
    assert restored.table == agent.table and restored.encoder.name == 'compact'


def test_dqn_forward_buffer_and_learning():
    torch = pytest.importorskip('torch')
    from aero_ai_studio.agents.dqn import DQNAgent, ReplayBuffer
    import random
    buffer = ReplayBuffer(2)
    for i in range(3): buffer.append((i,))
    assert len(buffer)==2 and len(buffer.sample(2,random.Random(1)))==2
    agent = DQNAgent(batch_size=2,buffer_size=8,target_interval=4)
    assert isinstance(agent,Agent)
    assert tuple(agent.network(torch.zeros(22)).shape)==(4,)
    obs = GridWorld(tiny()).get_agent_observation('sensor')
    agent.select_action(obs,0)
    assert len(agent.get_decision_info()['q_values'])==4
    for _ in range(8): agent.learn(Transition(obs,'right',1,obs,False))
    assert agent.last_loss is not None
    assert all(torch.equal(a,b) for a,b in zip(agent.network.parameters(),agent.target.parameters()))


def test_dqn_checkpoint_model_and_evaluation(tmp_path):
    pytest.importorskip('torch')
    from aero_ai_studio.agents.dqn import DQNAgent
    cfg = TrainingConfig(episodes=6,max_steps=12,algorithm='dqn',observation_mode='sensor',
                         batch_size=2,buffer_size=30,target_interval=4,checkpoint_interval=3)
    full, full_agent, _ = Trainer(tiny(),cfg).run(tmp_path/'full')
    stop=Event()
    def progress(row):
        if row['episode']==3:stop.set()
    first,_,meta = Trainer(tiny(),cfg).run(tmp_path/'partial',progress,stop)
    cp = Path(meta['last_checkpoint'])
    assert (cp/'model.pt').exists()
    saved = CheckpointStore.load(cp)
    assert isinstance(CheckpointStore.restore_agent(saved),DQNAgent)
    resumed,agent,meta = Trainer(tiny(),cfg).run(tmp_path/'resumed',resume=cp)
    import torch
    assert all(torch.equal(a,b) for a,b in zip(agent.network.parameters(),full_agent.network.parameters()))
    assert read_json(full/'metrics.json')==read_json(resumed/'metrics.json')
    model = ModelRegistry.save(tmp_path/'models','DQN',agent,meta)
    assert (model/'model.pt').exists() and read_json(model/'metadata.json')['algorithm']=='dqn'
    restored = load_agent(model)
    assert restored.learn_steps==agent.learn_steps and len(restored.buffer)==len(agent.buffer)
    before=(model/'model.pt').read_bytes()
    path,result=Evaluator(tiny(),EvaluationConfig(2,12,10000)).run(model,tmp_path/'evals')
    assert (model/'model.pt').read_bytes()==before
    step = read_json(next((path/'episodes').glob('*.json')))['steps'][0]
    assert 'Network output Q-values' in BrainEvent(step).text()
    assert step['observation']['mode']=='sensor' and step['agent_decision']['q_values']==step['q_values']


def test_evaluation_seed_overlap_rejected(tmp_path):
    _,agent,meta=Trainer(tiny(),TrainingConfig(episodes=5)).run(tmp_path/'runs')
    model=ModelRegistry.save(tmp_path/'models','seed',agent,meta)
    with pytest.raises(ValueError,match='overlap'):
        Evaluator(tiny(),EvaluationConfig(2,20,42)).run(model,tmp_path/'evals')


def test_generalization_evaluation(tmp_path):
    _,agent,meta=Trainer(tiny(),TrainingConfig(episodes=30)).run(tmp_path/'runs')
    model=ModelRegistry.save(tmp_path/'models','generalize',agent,meta)
    root,result=GeneralizationEvaluator(tiny(),EvaluationConfig(3,15,10000),GeneralizationConfig(moving_obstacles=True)).run(model,tmp_path/'evals')
    assert 'training_scenario_success' in result and 'unseen_scenario_success' in result
    assert result['generalization_gap']==result['training_scenario_success']-result['unseen_scenario_success']
    assert len(list((root/'episodes').glob('*.json')))==3


def test_scenario_sdf_structure(tmp_path):
    s=tiny()
    s.objects=[SceneObject('wall',(1,1)),SceneObject('danger_zone',(2,2))]
    path=GazeboWorldGenerator().generate(s,tmp_path)
    document=ET.parse(path)
    world=document.find('world')
    assert document.getroot().attrib['version']=='1.9'
    assert len(world.findall('plugin'))==3 and world.find('physics') is not None
    names=[m.attrib['name'] for m in world.findall('model')]
    assert len(names)==len(set(names)) and {'ground','goal_marker','agent_marker','wall_0'}<=set(names)
    assert world.find('light') is not None
    assert GazeboWorldGenerator().generate(s,tmp_path)==path


def test_gazebo_unavailable_graceful(monkeypatch,tmp_path):
    monkeypatch.setattr('aero_ai_studio.gazebo.diagnostics.shutil.which',lambda name:None)
    assert not gazebo_status()['available']
    env=GazeboEnvironment(tiny(),root=tmp_path)
    assert env.launch()['status']=='Unavailable'
    assert env.capabilities.supports_3d and not env.training_available
    with pytest.raises(NotImplementedError):env.step('right')
    env.close()
    assert diagnose()['Gazebo']['status']=='Unavailable'


def test_environment_diagnostics():
    result=diagnose()
    assert {'OS','Python','PyTorch','Gazebo','ROS2','ros_gz_bridge','CUDA','GPU'}<=set(result)
