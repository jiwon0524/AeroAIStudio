from pathlib import Path
from threading import Event
import xml.etree.ElementTree as ET
import pytest
from aero_ai_studio.gazebo.contracts import ObservationFrame,SensorTimeoutError,parse_contacts,SimulationState
from aero_ai_studio.gazebo.discovery import parse_names,launch_arguments
from aero_ai_studio.gazebo.sensor_provider import RangeSensorProvider
from aero_ai_studio.gazebo.physics_controller import PhysicsEntityController
from aero_ai_studio.gazebo.stepping import GazeboStepper
from aero_ai_studio.gazebo.world_generator import GazeboWorldGenerator
from aero_ai_studio.gazebo.environment import GazeboEnvironment
from aero_ai_studio.training.curriculum import CurriculumSchedule
from aero_ai_studio.training.trainer import Trainer,TrainingConfig
from aero_ai_studio.core.storage import read_json
from aero_ai_studio.evaluation.safety_metrics import safety_step_metrics
from aero_ai_studio.safety.layer import SafetyLayer
from aero_ai_studio.simulation.grid_world import GridWorld
from test_v06 import FakeTransport,tiny


def test_runtime_discovery_parsers_and_options(monkeypatch,tmp_path):
    assert parse_names('DEBUG log\n /world/test/control\n/world/test/scene/info\n')==['/world/test/control','/world/test/scene/info']
    class Result:
        returncode=0;stdout='--server-only --headless-rendering --run';stderr=''
    monkeypatch.setattr('aero_ai_studio.gazebo.discovery.subprocess.run',lambda *a,**k:Result())
    args,help_text=launch_arguments('gz',tmp_path/'world.sdf',False,True)
    assert '--server-only' in args and '--headless-rendering' in args
    Result.stdout='unsupported'
    with pytest.raises(RuntimeError):launch_arguments('gz',tmp_path/'world.sdf')


def test_sensor_frame_freshness_age_sequence():
    t=FakeTransport()
    provider=RangeSensorProvider(t,'test',(3.5,3.5),max_sensor_age_ms=10)
    provider.start()
    obs=provider.get_range_observation(t.poses['agent_marker'],simulation_time=0)
    assert obs.sensor_state['sequence']==1
    with pytest.raises(SensorTimeoutError):provider.get_range_observation(t.poses['agent_marker'])
    t.time=.1
    with pytest.raises(SensorTimeoutError):provider.get_range_observation(t.poses['agent_marker'],simulation_time=.2)
    obs=provider.get_range_observation(t.poses['agent_marker'],simulation_time=.1)
    assert obs.sensor_state['sequence']==2 and provider.frame.age_ms==0
    assert obs.sensor_state['sensor_timestamp']>0


def test_contact_event_and_ground_filter():
    data={'header':{'stamp':{'sec':2}},'contact':[
        {'collision1':'simple_agent::body::body_collision','collision2':'wall::collision','position':[{'x':1}]},
        {'collision1':'simple_agent::wheel','collision2':'ground::collision'}]}
    events=parse_contacts(data,'simple_agent')
    assert len(events)==1 and events[0].timestamp==2 and events[0].other_entity=='wall::collision'


def test_physics_publish_no_teleport_and_pose_validation():
    t=FakeTransport();published=[]
    t.publish=lambda *args:published.append(args)
    controller=PhysicsEntityController(t,'test')
    before={'x':1,'y':1,'yaw':0}
    controller.apply_action('forward')
    assert published[-1][1]=='Twist' and published[-1][2]['linear']['x']>0
    assert not t.calls
    odom0={'timestamp':1.,'linear_x':0.,'angular_z':0.}
    odom1={'timestamp':1.1,'linear_x':.5,'angular_z':0.}
    args={'odometry_before':odom0,'odometry_after':odom1,'simulation_start_time':1.,'simulation_end_time':1.1}
    assert controller.validate_pose(before,{'x':1.05,'y':1,'yaw':0},.1,**args)['valid']
    assert not controller.validate_pose(before,{'x':5,'y':1,'yaw':0},.1,**args)['valid']
    controller.apply_action('turn_left');assert published[-1][2]['angular']['z']>0
    controller.stop_agent();assert published[-1][2]=={'linear':{'x':0},'angular':{'z':0}}


def test_physics_sdf_body_inertia_contact_diff_drive(tmp_path):
    world=GazeboWorldGenerator().generate(tiny(),tmp_path,True,control_mode='PHYSICS')
    tree=ET.parse(world)
    robot=tree.find("world/model[@name='simple_agent']")
    assert robot.find('static').text=='false'
    assert robot.find('link/inertial/mass') is not None
    assert robot.find("plugin[@name='gz::sim::systems::DiffDrive']") is not None
    assert robot.find("link/sensor[@type='contact']") is not None
    assert len(robot.findall("joint[@type='revolute']"))==2
    assert read_json(world.with_name('metadata.json'))['control_mode']=='PHYSICS'


def test_step_delta_and_lifecycle_error(tmp_path):
    t=FakeTransport()
    stepper=GazeboStepper(t,'test')
    stepper.time=2.
    with pytest.raises(TimeoutError):stepper.step_simulation()
    env=GazeboEnvironment(tiny(),transport=FakeTransport(),root=tmp_path)
    env.reset()
    assert env.lifecycle==SimulationState.PAUSED
    with pytest.raises(ValueError):env.step('invalid')
    assert env.lifecycle==SimulationState.ERROR
    env.close();assert env.lifecycle==SimulationState.STOPPED


def test_stage_minimum_exposure_and_budget_validation():
    s=CurriculumSchedule(threshold=.8,minimum_episodes=(2,2,2,2,4),minimum_evaluations=2)
    s.record_episode();assert not s.update(1,remaining_budget=20)
    s.record_episode();assert s.update(1,remaining_budget=20)
    assert s.stage==1 and s.episodes_in_stage==0
    for _ in range(2):s.record_episode()
    assert not s.update(1,remaining_budget=1)
    assert not s.complete()
    with pytest.raises(ValueError,match='budget'):
        TrainingConfig(episodes=5,curriculum_enabled=True,curriculum_minimum_episodes=(2,2,2,2,4)).validate()


def test_stage_persistence_exact_resume(tmp_path):
    cfg=TrainingConfig(episodes=16,max_steps=4,curriculum_enabled=True,curriculum_interval=1,curriculum_threshold=0,
                       curriculum_minimum_episodes=(2,2,2,2,4),checkpoint_interval=2)
    run,agent,meta=Trainer(tiny(),cfg).run(tmp_path/'full')
    stop=Event()
    partial,_,m=Trainer(tiny(),cfg).run(tmp_path/'partial',lambda r:stop.set() if r['episode']==6 else None,stop)
    cp=Path(m['last_checkpoint'])
    state=read_json(cp/'checkpoint.json')['curriculum_state']
    assert {'current_stage','episodes_in_stage','stage_best_success','promotion_history','evaluation_history'}<=state.keys()
    resumed,a,m=Trainer(tiny(),cfg).run(tmp_path/'resumed',resume=cp)
    assert a.table==agent.table and read_json(run/'metrics.json')==read_json(resumed/'metrics.json')
    assert m['hard_training_episodes']>=4 and m['curriculum_complete']


def test_safety_heuristics_near_collision_are_not_causal():
    obs=GridWorld(tiny()).get_agent_observation('sensor')
    decision=SafetyLayer(True).check('up',obs,{'up':10,'right':2,'down':1,'left':0})
    metrics=safety_step_metrics(obs,decision)
    assert metrics['useful_override_heuristic'] and metrics['near_collision']
    assert 'no counterfactual' in metrics['interpretation']


def test_pose_topic_replaces_scene_and_rejects_stale_or_missing_agent():
    from aero_ai_studio.gazebo.entity_controller import GazeboEntityController
    t=FakeTransport()
    original=t.request
    def request(service,*args):
        assert not service.endswith('/scene/info'), 'Scene service must not gate poses'
        return original(service,*args)
    t.request=request
    c=GazeboEntityController(t,'test')
    assert c.get_pose()['x']==.5
    with pytest.raises(TimeoutError):c.get_pose(.1)
    t.poses={}
    with pytest.raises(RuntimeError,match='pose frame'):c.get_pose()


@pytest.mark.parametrize('stage,contact_failure,moving,fail_pose',[('movement',False,True,False),('full',True,True,False),('movement',False,False,False),('movement',False,True,True)])
def test_runtime_report_step_motion_independent_of_scene_and_contacts(tmp_path,monkeypatch,stage,contact_failure,moving,fail_pose):
    import importlib.util
    source=Path(__file__).parents[1]/'tools'/'verify_v07_runtime.py'
    spec=importlib.util.spec_from_file_location('runtime_fixture',source)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    monkeypatch.setattr(module,'diagnose',lambda **k:{})
    monkeypatch.setattr(module,'gazebo_status',lambda:{'available':True})
    class PhysicsTransport(FakeTransport):
        def publish(self,topic,message_type,payload):self.command=payload
        def sample(self,topic,min_time=-1,timeout=5):
            if topic.endswith('/odometry'):
                stamp={'sec':int(self.time),'nsec':int(round((self.time%1)*1e9))}
                return {'header':{'stamp':stamp},'twist':{'linear':{'x':self.command.get('linear',{}).get('x',0)},
                    'angular':{'z':self.command.get('angular',{}).get('z',0)}}}
            return super().sample(topic,min_time,timeout)
        def request(self,service,request_type,response_type,payload):
            assert not service.endswith('/scene/info')
            if fail_pose and service.endswith('/set_pose'):raise TimeoutError('set_pose fixture timeout')
            if service.endswith('/control') and payload.get('multi_step'):
                self.poses['simple_agent']['x']+=self.command['linear']['x']*payload['multi_step']*.001*int(moving)
            return super().request(service,request_type,response_type,payload)
        def latest(self,topic):return None
    def environment(scenario,**kwargs):
        t=PhysicsTransport()
        env=GazeboEnvironment(scenario,transport=t,**kwargs)
        env.world=GazeboWorldGenerator().generate(scenario,env.root,True,'PHYSICS')
        env.world_name=env.world.parent.name
        metadata=read_json(env.world.with_name('metadata.json'))
        for name in [metadata['agent_entity'],metadata['goal_entity'],*metadata['obstacle_entities']]:
            t.poses[name]={'x':7.5,'y':7.5,'z':.16}
        # Laser fixture uses agent_marker; physical pose is checked separately.
        class Process:
            pid=123
            def poll(self):return None
        env.manager.process=Process()
        env.manager.close=lambda:setattr(env.manager,'process',None)
        env.launch=lambda:{}
        return env
    monkeypatch.setattr(module,'GazeboEnvironment',environment)
    report=module.run(tmp_path,stage=stage)
    if fail_pose:
        assert report['status']=='FAIL'
        for key in ('world_loaded','agent_exists','goal_exists','obstacles_exist','pose_read','sensor_topic','shutdown'):
            assert report['checks'][key]=='PASS',report
        assert report['checks']['initialization']=='FAIL'
        assert report['checks']['set_pose']=='FAIL'
        assert report['checks']['physics_motion']=='NOT AVAILABLE'
        assert report['set_pose_request']['payload']['name']=='simple_agent'
        return
    assert report['checks']['step_progress']=='PASS',report
    assert report['checks']['shutdown']=='PASS'
    if not moving:
        assert report['status']=='FAIL' and report['checks']['physics_motion']=='FAIL',report
        return
    assert report['checks']['physics_motion']=='PASS',report
    if contact_failure:
        assert report['status']=='FAIL' and report['checks']['collision_contact']=='FAIL'
        assert report['checks']['closed_loop']=='NOT AVAILABLE'
        assert report['error']
    else:
        assert report['status']=='PASS',report
        assert report['checks']['collision_contact']=='NOT REQUESTED'
        assert report['checks']['closed_loop']=='NOT REQUESTED'


def test_native_publisher_waits_for_connection_before_command(monkeypatch):
    from types import SimpleNamespace
    from aero_ai_studio.gazebo.transport import HarmonicTransport
    # Exercise the adapter without constructing a native Node or any sockets.
    transport=HarmonicTransport.__new__(HarmonicTransport)
    connections=iter([False,False,True]);published=[];waits=[]
    publisher=SimpleNamespace(has_connections=lambda:next(connections),publish=lambda p:published.append(p) or True)
    transport.node=SimpleNamespace(advertise=lambda *a:publisher)
    transport.publishers={};transport.timeout=1
    transport.message=lambda name:dict
    transport.json=SimpleNamespace(ParseDict=lambda payload,message:payload)
    monkeypatch.setattr('aero_ai_studio.gazebo.transport.time.sleep',lambda delay:waits.append(delay))
    transport.publish('/cmd_vel','Twist',{'linear':{'x':.5}})
    assert len(waits)==2 and len(published)==1
    transport.timeout=0
    publisher.has_connections=lambda:False
    with pytest.raises(TimeoutError,match='subscriber not ready'):
        transport.publish('/cmd_vel','Twist',{})
    assert len(published)==1
