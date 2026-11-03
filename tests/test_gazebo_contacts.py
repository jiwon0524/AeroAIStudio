"""Event-only Contact system fixtures; never instantiate a Gazebo Node."""
from pathlib import Path
from collections import deque
from threading import Condition
from types import SimpleNamespace
import importlib.util
import math
import xml.etree.ElementTree as ET
import pytest
from aero_ai_studio.gazebo.contact_provider import ContactProvider
from aero_ai_studio.gazebo.contracts import parse_contacts
from aero_ai_studio.gazebo.transport import HarmonicTransport
from aero_ai_studio.gazebo.environment import GazeboEnvironment
from aero_ai_studio.gazebo.world_generator import GazeboWorldGenerator
from aero_ai_studio.core.storage import read_json
from test_v06 import FakeTransport,tiny


def contact(timestamp,other='static_obstacle_2::body::collision',agent='simple_agent::body::body_collision'):
    stamp={'sec':int(timestamp),'nsec':int(round((timestamp%1)*1e9))}
    return {'header':{'stamp':stamp},'contact':[{'header':{'stamp':stamp},
            'collision1':{'id':'42','name':agent},'collision2':{'id':'75','name':other},
            'position':[{'x':3.05,'y':1.5,'z':.16}],'normal':[{'x':-1.}]}]}


class EventTransport(FakeTransport):
    def __init__(self):
        super().__init__();self.frames=[];self.ready=True
    def emit(self,message):self.frames.append((len(self.frames)+1,message))
    def cursor(self,topic):return len(self.frames)
    def messages_after(self,topic,sequence,timeout=0):return [(seq,m) for seq,m in self.frames if seq>sequence]
    def wait_for_topic(self,topic,message_type,timeout=None):
        if not self.ready:raise TimeoutError('Contact publisher unavailable')
        return super().wait_for_topic(topic,message_type,timeout)


def test_event_silence_is_allowed_but_missing_publisher_is_not():
    t=EventTransport();p=ContactProvider(t,'/contacts','simple_agent')
    p.reset(.1)
    assert p.poll(.2)==[] and p.poll(.3)==[]
    assert p.state['assessment']=='no_new_contact_event' and not p.state['silence_is_health_proof']
    t.ready=False
    with pytest.raises(TimeoutError):p.poll(.4)


def test_msgs10_contacts_entity_schema_and_exact_names():
    Contacts=pytest.importorskip('gz.msgs10.contacts_pb2').Contacts
    from google.protobuf.json_format import ParseDict,MessageToDict
    frame=MessageToDict(ParseDict(contact(2),Contacts()),preserving_proto_field_name=True)
    event=parse_contacts(frame,'simple_agent')[0]
    assert event.agent_collision=='simple_agent::body::body_collision'
    assert event.other_entity=='static_obstacle_2::body::collision'
    assert event.collision1['id']=='42' and event.timestamp==2
    reverse=contact(2)
    reverse['contact'][0]['collision1'],reverse['contact'][0]['collision2']=reverse['contact'][0]['collision2'],reverse['contact'][0]['collision1']
    assert parse_contacts(reverse,'simple_agent')[0].other_entity==event.other_entity
    assert not parse_contacts(contact(2,agent='not_simple_agent::body::body_collision'),'simple_agent')
    assert not parse_contacts(contact(2,other='world::ground::body::collision'),'simple_agent')
    assert not parse_contacts(contact(2,other='simple_agent::left_wheel::collision'),'simple_agent')
    malformed=contact(2);del malformed['contact'][0]['collision1']['name']
    with pytest.raises(ValueError):parse_contacts(malformed,'simple_agent')


def test_reset_discards_buffered_and_late_previous_episode_events_but_accepts_late_current_event():
    t=EventTransport();p=ContactProvider(t,'/contacts','simple_agent')
    t.emit(contact(.2));p.reset(.3)
    assert not p.poll(.4)
    t.emit(contact(.25))  # old packet arriving after reset's sequence barrier
    assert not p.poll(.5) and p.state['ignored_pre_reset']==1
    t.emit(contact(.41))  # delayed >one step; must still stop the episode
    events=p.poll(.8)
    assert len(events)==1 and events[0]['timestamp']==pytest.approx(.41)
    assert p.evidence[0]['receive_sequence']==3
    assert p.evidence[0]['delivery_lag_sim_seconds']==pytest.approx(.39)
    assert not p.poll(.9)  # receive sequence prevents replay
    p.reset(1.)
    assert not p.poll(1.1) and not p.evidence


def test_invalid_contact_time_and_receive_history_loss_fail_closed():
    t=EventTransport();p=ContactProvider(t,'/contacts','simple_agent')
    t.emit(contact(3.))
    with pytest.raises(RuntimeError,match='ahead'):p.poll(2.)
    with pytest.raises(RuntimeError,match='rewound'):
        p.reset(2.);p.poll(1.)
    native=HarmonicTransport.__new__(HarmonicTransport)
    native.condition=Condition();native.closed=False
    native.sequenced_history={'/contacts':deque([(3,contact(.1))])}
    with pytest.raises(RuntimeError,match='overflow'):native.messages_after('/contacts',0)


def test_contact_topic_type_readiness_without_native_node():
    native=HarmonicTransport.__new__(HarmonicTransport)
    native.message=lambda name:SimpleNamespace(DESCRIPTOR=SimpleNamespace(full_name='gz.msgs.Contacts'))
    native.node=SimpleNamespace(topic_info=lambda topic:([SimpleNamespace(msg_type_name='gz.msgs.Contacts')],[]))
    assert native.wait_for_topic('/contacts','Contacts',0)['message_type']=='gz.msgs.Contacts'
    native.node.topic_info=lambda topic:([SimpleNamespace(msg_type_name='gz.msgs.Pose')],[])
    with pytest.raises(RuntimeError,match='schema mismatch'):native.wait_for_topic('/contacts','Contacts',0)


def test_generated_contact_plugin_collision_and_harmonic_topic(tmp_path):
    world=GazeboWorldGenerator().generate(tiny(),tmp_path,True,'PHYSICS')
    root=ET.parse(world)
    assert root.find("world/plugin[@name='gz::sim::systems::Contact']") is not None
    sensor=root.find("world/model[@name='simple_agent']/link[@name='body']/sensor[@type='contact']")
    assert sensor.find('always_on').text=='true' and sensor.find('update_rate').text=='1000'
    assert sensor.find('contact/collision').text=='body_collision'
    assert sensor.find('contact/topic').text==read_json(world.with_name('metadata.json'))['contact_topic']
    assert root.find("world/model[@name='simple_agent']/link[@name='body']/collision[@name='body_collision']") is not None


def load_verifier():
    source=Path(__file__).parents[1]/'tools'/'verify_v07_runtime.py'
    spec=importlib.util.spec_from_file_location('contact_verifier_fixture',source)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('drift,yaw_drift,expect_error',[(0.,0.,False),(.031,0.,True),(0.,.051,True)])
def test_closed_loop_starts_in_new_process_and_requires_zero_command_settle(tmp_path,drift,yaw_drift,expect_error):
    module=load_verifier()
    class Process:
        def __init__(self,pid):self.pid,self.exit_code=pid,None
        def poll(self):return self.exit_code
    class Transport:
        def __init__(self,partition):self.partition,self.closed=partition,False
        def close(self):self.closed=True
    class NewEnv:
        def __init__(self):
            self.manager=SimpleNamespace(status=lambda:{'pid':21,'partition':'closed-loop'})
            self.process=Process(21);self.transport=Transport('closed-loop');self.world_name='world'
            self.discovery={'worlds':['world'],'topics':['/world/world/pose/info','/scan','/contact','/world/world/stats'],
                            'services':['/world/world/control','/world/world/set_pose']}
            self.pose={'x':1.5,'y':1.5,'z':.16,'yaw':0.};self.goal=(5.,2.)
            self.sensors=SimpleNamespace(topic='/scan',frame=object(),transport=self.transport)
            self.contact_topic='/contact';self.contacts=SimpleNamespace(schema={},poll=lambda now:[],transport=self.transport)
            self.controller=SimpleNamespace(last_command={'linear':{'x':0},'angular':{'z':0}},transport=self.transport,
                stop_agent=lambda:setattr(self.controller,'last_command',{'linear':{'x':0},'angular':{'z':0}}))
            self.stepper=SimpleNamespace(time=.1,transport=self.transport,step_simulation=lambda n:setattr(self.stepper,'time',self.stepper.time+n*.1))
            self.telemetry={};self.initialization_checks={'reset_applied':'PASS'};self.initialization_phase='ready'
        def _refresh(self):self.pose={'x':1.5+drift,'y':1.5,'z':.16,'yaw':yaw_drift}
        def get_observation(self):return (1,1)
    class OldEnv:
        def __init__(self):
            self.manager=SimpleNamespace(status=lambda:{'pid':20,'partition':'collision'})
            self.process=Process(20);self.transport=Transport('collision');self.world_name='world'
            self.controller=SimpleNamespace(last_command={},stop_agent=lambda:None)
        def restart(self,seed):
            self.controller.stop_agent();self.transport.close();self.process.exit_code=0
            return NewEnv()
    env=OldEnv()
    if expect_error:
        with pytest.raises(RuntimeError,match='zero-command settle'):
            module.start_independent_closed_loop_episode(env)
    else:
        new_env,state,evidence=module.start_independent_closed_loop_episode(env)
        assert state==(1,1)
        assert new_env is not env
        assert evidence['old_process_exited'] and evidence['old_transport_closed']
        assert evidence['transport_recreated'] and evidence['topic_service_rediscovery']
        assert evidence['dependent_components_rebound']
        assert evidence['old_partition']!=evidence['new_partition']
        assert evidence['zero_command']=={'linear':{'x':0},'angular':{'z':0}}
        assert evidence['zero_command_displacement']==pytest.approx(0)
        assert evidence['zero_command_yaw_drift']==pytest.approx(0)


@pytest.mark.parametrize('outcome,initial_yaw,linear_sign,angular_sign',[
    ('contact',0.,1,1),('silence',0.,1,1),('wrong_obstacle',0.,1,1),('boundary',0.,1,1),
    ('contact',math.pi/2,1,1),('contact',-math.pi/2,1,1),
    ('reverse',0.,-1,1),('wrong_rotation',math.pi/2,1,-1)])
def test_collision_stage_requires_real_matching_contact_after_physical_approach(tmp_path,monkeypatch,outcome,initial_yaw,linear_sign,angular_sign):
    module=load_verifier()
    monkeypatch.setattr(module,'rule_action',lambda *a:pytest.fail('Collision challenge must not invoke avoidance policy'))
    monkeypatch.setattr(module,'diagnose',lambda **k:{})
    monkeypatch.setattr(module,'gazebo_status',lambda:{'available':True})
    class PhysicsFixture(EventTransport):
        command={'linear':{'x':0}}
        yaw=0.
        def sample(self,topic,*args,**kwargs):
            result=super().sample(topic,*args,**kwargs)
            if topic.endswith('/pose/info'):
                for pose in result['pose']:
                    if pose['name']=='simple_agent':pose['orientation']={'z':math.sin(self.yaw/2),'w':math.cos(self.yaw/2)}
            if topic.endswith('/odometry'):
                stamp={'sec':int(self.time),'nsec':int(round((self.time%1)*1e9))}
                return {'header':{'stamp':stamp},'twist':{'linear':{'x':self.command.get('linear',{}).get('x',0)},
                    'angular':{'z':self.command.get('angular',{}).get('z',0)}}}
            return result
        def publish(self,topic,message_type,payload):self.command=payload
        def request(self,service,request_type,response_type,payload):
            result=super().request(service,request_type,response_type,payload)
            if service.endswith('/set_pose') and payload['name']=='simple_agent':self.yaw=initial_yaw
            if service.endswith('/control') and payload.get('multi_step'):
                agent=self.poses['simple_agent'];speed=self.command.get('linear',{}).get('x',0)
                dt=payload['multi_step']*.001
                agent['x']+=linear_sign*speed*dt*math.cos(self.yaw)
                agent['y']+=linear_sign*speed*dt*math.sin(self.yaw)
                self.yaw+=angular_sign*self.command.get('angular',{}).get('z',0)*dt
                if agent['x']>=2.825:
                    agent['x']=2.825
                    if outcome!='silence':
                        other='static_obstacle_2' if outcome=='contact' else 'boundary_2' if outcome=='boundary' else 'static_obstacle_1'
                        self.emit(contact(self.time,other=other+'::body::collision'))
            return result
    def environment(scenario,**kwargs):
        t=PhysicsFixture();env=GazeboEnvironment(scenario,transport=t,**kwargs)
        env.world=GazeboWorldGenerator().generate(scenario,env.root,True,'PHYSICS');env.world_name=env.world.parent.name
        for model in ET.parse(env.world).findall('world/model'):
            xyz=[float(v) for v in model.find('pose').text.split()[:3]]
            t.poses[model.get('name')]=dict(zip(('x','y','z'),xyz))
        class Process:
            pid=123
            def poll(self):return None
        env.manager.process=Process();env.manager.close=lambda:setattr(env.manager,'process',None)
        env.launch=lambda:{}
        return env
    monkeypatch.setattr(module,'GazeboEnvironment',environment)
    report=module.run(tmp_path,stage='collision')
    assert report['checks']['world_loaded']=='PASS',report
    if outcome not in ('reverse','wrong_rotation'):assert report['checks']['no_contact']=='PASS',report
    assert report['checks']['closed_loop']=='NOT REQUESTED'
    if outcome=='contact':
        assert report['status']=='PASS' and report['checks']['collision_contact']=='PASS',report
        evidence=read_json(tmp_path/'collision.json')
        assert evidence['target_pose']['x']==3.5 and evidence['target_pose']['y']==1.5
        assert evidence['physical_travel']>1 and evidence['raw_contacts']
        assert evidence['event']['agent_collision'].endswith('body_collision')
        assert evidence['target_distance_reduction']>1
        assert evidence['physical_travel']>=evidence['net_displacement']-1e-9
        assert abs(evidence['alignment']['yaw_error'])<=evidence['yaw_tolerance']
        approach=[step for step in evidence['steps'] if step['phase']=='approach']
        assert all(step['distance_decrease']>0 for step in approach[:-1])
        if initial_yaw:
            align=[step for step in evidence['steps'] if step['phase']=='align']
            assert align and all(step['command']['linear']['x']==0 for step in align)
            assert all(step['action']==('right' if initial_yaw>0 else 'left') for step in align)
    else:
        assert report['status']=='FAIL' and report['checks']['collision_contact']=='FAIL',report
        evidence=read_json(tmp_path/'collision.json')
        assert evidence['steps']
        if outcome=='reverse':
            assert len(evidence['steps'])==1
            assert evidence['steps'][0]['distance_decrease']<0
        if outcome=='boundary':assert 'boundary_2' in report['error']
        if outcome=='wrong_rotation':assert all(step['phase']=='align' for step in evidence['steps'])


def test_old_sdf_scoped_contact_topic_is_selected_from_discovery(tmp_path,monkeypatch):
    t=EventTransport();env=GazeboEnvironment(tiny(),transport=t,root=tmp_path,control_mode='PHYSICS')
    env.world=GazeboWorldGenerator().generate(tiny(),tmp_path,True,'PHYSICS')
    env.world_name=env.world.parent.name;env.injected=False
    metadata=read_json(env.world.with_name('metadata.json'))
    scoped=f'/world/{env.world_name}/model/simple_agent/link/body/sensor/body_contacts/contact'
    discovery={'worlds':[env.world_name],'topics':[scoped,metadata['sensor_topic'],f'/world/{env.world_name}/pose/info'],'services':[]}
    monkeypatch.setattr('aero_ai_studio.gazebo.discovery.discover',lambda *a:discovery)
    monkeypatch.setattr('aero_ai_studio.gazebo.diagnostics.gazebo_status',lambda **k:{'executable':'gz'})
    env._connect();env.prepare_contacts()
    assert env.contact_topic==scoped and env.contacts.topic==scoped
    env.close()


def test_native_callback_assigns_receive_sequence_without_mutating_simulation_stamp():
    native=HarmonicTransport.__new__(HarmonicTransport)
    native.condition=Condition();native.closed=False
    native.samples={};native.history={};native.sequences={};native.sequenced_history={}
    native.topics=set();native.callbacks=[]
    native.message=lambda name:object
    native.json=SimpleNamespace(MessageToDict=lambda message,**kwargs:message)
    callbacks=[]
    native.node=SimpleNamespace(subscribe=lambda cls,topic,callback:callbacks.append(callback) or True)
    native.subscribe('/contacts','Contacts')
    # A late packet has a newer receive sequence but an older sim timestamp.
    callbacks[0](contact(.3));callbacks[0](contact(.2))
    assert native.cursor('/contacts')==2
    frames=native.messages_after('/contacts',0)
    assert [seq for seq,m in frames]==[1,2]
    assert frames[1][1]['header']['stamp']['nsec']==200000000


def test_odometry_transport_retains_timestamped_action_interval_history():
    native=HarmonicTransport.__new__(HarmonicTransport)
    native.condition=Condition();native.closed=False
    native.samples={};native.history={};native.sequences={};native.sequenced_history={}
    native.topics=set();native.callbacks=[]
    native.message=lambda name:object
    native.json=SimpleNamespace(MessageToDict=lambda message,**kwargs:message)
    callbacks=[]
    native.node=SimpleNamespace(subscribe=lambda cls,topic,callback:callbacks.append(callback) or True)
    native.subscribe('/model/simple_agent/odometry','Odometry')
    for i,velocity in enumerate((0.,.8,.8)):
        callbacks[0]({'header':{'stamp':{'sec':1,'nsec':i*50_000_000}},
                      'twist':{'linear':{'x':0.},'angular':{'z':velocity}}})
    interval=native.since('/model/simple_agent/odometry',1.)
    assert len(interval)==2
    assert [m['twist']['angular']['z'] for m in interval]==[.8,.8]
    assert [m['header']['stamp']['nsec'] for m in interval]==[50_000_000,100_000_000]


def test_sdf_resolved_wheel_axes_match_forward_and_ccw_diff_drive(tmp_path):
    sdf=pytest.importorskip('sdformat14')
    world=GazeboWorldGenerator().generate(tiny(),tmp_path,True,'PHYSICS')
    root=sdf.Root();root.load(str(world))
    robot=root.world_by_index(0).model_by_name('simple_agent')
    for name in ('left_joint','right_joint'):
        axis=robot.joint_by_name(name).axis(0).resolve_xyz('__model__')
        assert (axis.x(),axis.y(),axis.z())==pytest.approx((0,1,0))
    # Resolve the original joint-local axis in the rolled wheel frame too:
    # a data-only SDF semantic check of the actual regression, not Gazebo runtime.
    old=ET.parse(world)
    for axis in old.findall("world/model[@name='simple_agent']/joint/axis/xyz"):
        axis.attrib.clear();axis.text='0 0 1'
    original=sdf.Root();original.load_sdf_string(ET.tostring(old.getroot(),encoding='unicode'))
    bad=original.world_by_index(0).model_by_name('simple_agent').joint_by_name('left_joint').axis(0).resolve_xyz('__model__')
    assert (bad.x(),bad.y(),bad.z())==pytest.approx((0,-1,0),abs=1e-12)
    # No-slip wheel velocity with model +Y axles: v = radius * omega.
    radius=.1;separation=.42
    for linear,angular in ((.5,0),(0,.8),(0,-.8)):
        left=(linear-angular*separation/2)/radius
        right=(linear+angular*separation/2)/radius
        assert radius*(right+left)/2==pytest.approx(linear)
        assert radius*(right-left)/separation==pytest.approx(angular)


@pytest.mark.parametrize('yaw',[0.,math.pi/2,-math.pi/2,math.pi-.01,-math.pi+.01])
def test_quaternion_yaw_roundtrip_and_signed_forward_motion(yaw):
    from aero_ai_studio.gazebo.entity_controller import GazeboEntityController
    from aero_ai_studio.gazebo.physics_controller import PhysicsEntityController
    pose=GazeboEntityController.decode_pose({'position':{'x':1.5,'y':1.5},
        'orientation':{'z':math.sin(yaw/2),'w':math.cos(yaw/2)}})
    assert pose['yaw']==pytest.approx(yaw)
    t=FakeTransport();t.publish=lambda *a:None
    controller=PhysicsEntityController(t,'test');controller.apply_action('up')
    move_odom={'odometry_before':{'timestamp':1.,'linear_x':0.,'angular_z':0.},
               'odometry_after':{'timestamp':1.1,'linear_x':.5,'angular_z':0.},
               'simulation_start_time':1.,'simulation_end_time':1.1}
    after={**pose,'x':1.5+.05*math.cos(yaw),'y':1.5+.05*math.sin(yaw)}
    assert controller.validate_pose(pose,after,.1,**move_odom)['valid']
    reverse={**pose,'x':1.5-.05*math.cos(yaw),'y':1.5-.05*math.sin(yaw)}
    assert not controller.validate_pose(pose,reverse,.1,**move_odom)['valid']
    controller.apply_action('left')
    turn_odom={'odometry_before':{'timestamp':1.,'linear_x':0.,'angular_z':0.},
               'odometry_after':{'timestamp':1.1,'linear_x':0.,'angular_z':.8},
               'simulation_start_time':1.,'simulation_end_time':1.1}
    assert controller.validate_pose(pose,{**pose,'yaw':yaw+.08},.1,**turn_odom)['valid']
    assert not controller.validate_pose(pose,{**pose,'yaw':yaw-.08},.1,**turn_odom)['valid']


@pytest.mark.parametrize('action,before,after,delta_xy,delta_yaw,expected',[
    # turn -> forward: angular velocity remains, but decreases and explains yaw.
    ('up',(.0,.7),(.25,.4),(.0125,0),.055,True),
    # A clean left turn follows positive angular velocity and command integral.
    ('left',(0,0),(0,.8),(0,0),.075,True),
    # A clean right turn follows negative angular velocity and command integral.
    ('right',(0,0),(0,-.8),(0,0),-.075,True),
    # forward -> turn: linear momentum decays while angular velocity approaches target.
    ('left',(.4,0),(.2,.4),(.03,0),.045,True),
    # repeated forward: measured forward velocity accelerates toward 0.5 m/s.
    ('up',(.25,0),(.4,0),(.0325,0),0,True),
    # opposite turn: yaw may retain its old sign while odometry converges to -0.8.
    ('right',(0,.6),(0,.2),(0,0),.04,True),
    # Deceleration under a zero target is valid only when motion matches odometry.
    ('stop',(.4,0),(.2,0),(.03,0),0,True),
    # A zero-angular target must reduce existing turn velocity, not leave it latched.
    ('up',(0,.8),(.5,.8),(.025,0),.08,False),
    # A forward command with reverse pose progress remains invalid.
    ('up',(0,0),(.2,0),(-.01,0),0,False),
    # A left command with clockwise odometry/pose disagreement remains invalid.
    ('left',(0,0),(0,.5),(0,0),-.025,False),
])
def test_physics_validator_checks_command_transitions_against_odometry(action,before,after,delta_xy,delta_yaw,expected):
    from aero_ai_studio.gazebo.physics_controller import PhysicsEntityController
    transport=FakeTransport();transport.publish=lambda *a:None
    controller=PhysicsEntityController(transport,'test');controller.apply_action(action)
    pose={'x':1.5,'y':1.5,'yaw':0.}
    moved={**pose,'x':pose['x']+delta_xy[0],'y':pose['y']+delta_xy[1],'yaw':delta_yaw}
    before_odom={'linear_x':before[0],'angular_z':before[1],'timestamp':1.}
    after_odom={'linear_x':after[0],'angular_z':after[1],'timestamp':1.1}
    result=controller.validate_pose(pose,moved,.1,odometry_before=before_odom,odometry_after=after_odom,
                                    simulation_start_time=1.,simulation_end_time=1.1)
    assert result['valid'] is expected,result
    assert result['odometry_available']
    if expected:
        assert result['odometry_fresh']
        assert result['world_direction_ok'] and result['odometry_direction_ok']
        assert result['pose_odometry_consistent'] is None
    else:assert not result['valid']


@pytest.mark.parametrize('previous_action,action,old_v,new_v,body_delta,old_sign,new_sign',[
    ('up','down',.5,-.5,.020,1,-1),
    ('down','up',-.5,.5,-.020,-1,1),
])
def test_longitudinal_reversal_accepts_bounded_body_inertia_with_dense_wheel_crossing(
        previous_action,action,old_v,new_v,body_delta,old_sign,new_sign):
    from aero_ai_studio.gazebo.physics_controller import PhysicsEntityController
    transport=FakeTransport();transport.publish=lambda *a:None
    controller=PhysicsEntityController(transport,'test')
    controller.apply_action(previous_action)
    previous_command=dict(controller.last_published_command)
    controller.apply_action(action)
    before={'x':1.5,'y':1.5,'yaw':0.}
    after={**before,'x':before['x']+body_delta}
    # Gazebo applies the wheel target early in the action interval; the wheel
    # velocity crosses zero quickly while body inertia carries the chassis on.
    samples=[old_v]+[new_v*.76]+[new_v]*9
    history=[{'timestamp':.3+i*.01,'linear_x':value,'angular_z':0.}
             for i,value in enumerate(samples[1:-1],start=1)]
    result=controller.validate_pose(before,after,.1,odometry_before={
        'timestamp':.3,'linear_x':old_v,'angular_z':0.},odometry_after={
        'timestamp':.4,'linear_x':new_v,'angular_z':0.},odometry_history=history,
        simulation_start_time=.3,simulation_end_time=.4,previous_command=previous_command)
    assert result['valid'],result
    assert result['world_direction_raw_ok'] is False
    assert result['world_direction_ok'] is True
    assert result['command_reversal_detected'] is True
    assert result['previous_motion_sign']==old_sign
    assert result['requested_motion_sign']==new_sign
    assert result['odometry_zero_crossing'] is True
    assert result['odometry_final_direction_ok'] is True
    assert result['wheel_integral_direction_ok'] is True
    assert result['world_body_transient_direction'] is True
    assert result['reversal_transient_valid'] is True
    assert result['discrepancy_classification']=='validated_longitudinal_reversal_transient'


def _dense_reversal_validation(*,after_v=-.5,stale=False,body_delta=.02,yaw=0.,
                               previous_action='up',action='down',keep_wheels=False,
                               world_pose_history=None):
    from aero_ai_studio.gazebo.physics_controller import PhysicsEntityController
    transport=FakeTransport();transport.publish=lambda *a:None
    controller=PhysicsEntityController(transport,'test')
    controller.apply_action(previous_action);previous=dict(controller.last_published_command)
    controller.apply_action(action)
    old_v=.5 if previous_action=='up' else -.5
    requested_v=.5 if action=='up' else -.5
    if keep_wheels:after_v=old_v
    t0=.2 if stale else .3;t1=t0+.1
    samples=[old_v]+[after_v*.76]+[after_v]*9
    history=[{'timestamp':t0+i*.01,'linear_x':v,'angular_z':0.}
             for i,v in enumerate(samples[1:-1],start=1)]
    before={'x':1.5,'y':1.5,'yaw':0.}
    after={**before,'x':before['x']+body_delta,'yaw':yaw}
    result=controller.validate_pose(before,after,.1,
        odometry_before={'timestamp':t0,'linear_x':old_v,'angular_z':0.},
        odometry_after={'timestamp':t1,'linear_x':after_v,'angular_z':0.},
        odometry_history=history,simulation_start_time=.3,simulation_end_time=.4,
        previous_command=previous,world_pose_history=world_pose_history)
    return result,requested_v


def _dense_body_reversal_history(previous_sign,requested_sign,*,fresh=True,dense=True,
                                 start_direction=None,end_direction=None,crossing=True):
    start=.3;end=.4
    start_direction=previous_sign if start_direction is None else start_direction
    end_direction=requested_sign if end_direction is None else end_direction
    if crossing:
        velocities=[start_direction*.12,start_direction*.09,start_direction*.06,
            start_direction*.03,requested_sign*.03,requested_sign*.06,
            requested_sign*.075,requested_sign*.09,requested_sign*.105,end_direction*.12]
    else:
        velocities=[start_direction*(.10-i*.004) for i in range(10)]
    samples=[{'simulation_timestamp':start+.005+i*.01,'forward_velocity':v,'sample_interval':.01}
             for i,v in enumerate(velocities)]
    return {'world_pose_sample_count':11,'world_pose_history_fresh':fresh,'world_pose_history_dense_enough':dense,
        'world_pose_sample_timestamps':[start+i*.01 for i in range(11)],
        'world_velocity_sample_count':len(samples),'world_forward_velocity_samples':samples,
        'world_start_forward_velocity':velocities[0],'world_end_forward_velocity':velocities[-1],
        'world_velocity_zero_crossing':crossing,'world_velocity_zero_crossing_time':.34 if crossing else None}


def test_longitudinal_reversal_rejects_wheels_that_never_change_direction():
    result,_=_dense_reversal_validation(keep_wheels=True)
    assert not result['valid']
    assert result['command_reversal_detected'] and not result['odometry_final_direction_ok']
    assert not result['reversal_transient_valid']


def test_actual_down_to_up_low_world_progress_remains_wheel_slip_failure():
    """Recorded second smoke sample has reversal evidence but no body transient proof."""
    from aero_ai_studio.gazebo.physics_controller import PhysicsEntityController
    transport=FakeTransport();transport.publish=lambda *a:None
    controller=PhysicsEntityController(transport,'test')
    controller.apply_action('down')
    previous_command=dict(controller.last_published_command)
    controller.apply_action('up')
    samples=[-.49999999987428645,.39999999988181434,.4999999999275707,
        .49999999992736754,.4999999999272015,.49999999992706484,
        .49999999992695343,.49999999992686084,.4999999999267861,
        .4999999999267229,.4999999999266736]
    times=[.4+i*.01 for i in range(11)]
    history=[{'timestamp':t,'linear_x':v,'angular_z':0.}
             for t,v in zip(times[1:-1],samples[1:-1])]
    result=controller.validate_pose(
        {'x':1.5,'y':1.5,'yaw':0.},
        {'x':1.5017230510067412,'y':1.5,'yaw':2.69e-16},.1,
        odometry_before={'timestamp':.4,'linear_x':samples[0],'angular_z':0.},
        odometry_after={'timestamp':.5,'linear_x':samples[-1],'angular_z':0.},
        odometry_history=history,simulation_start_time=.4,simulation_end_time=.5,
        previous_command=previous_command)
    assert result['command_reversal_detected'] and result['odometry_zero_crossing']
    assert result['odometry_final_direction_ok'] and result['wheel_integral_direction_ok']
    assert result['wheel_odometry_forward']==pytest.approx(.04399999999324534)
    assert result['world_pose_forward']==pytest.approx(.0017230510067411942)
    assert result['world_direction_raw_ok'] is False
    assert result['world_body_transient_direction'] is False
    assert result['reversal_transient_valid'] is False
    assert result['reversal_body_history_available'] is False
    assert result['reversal_cancellation_valid'] is False
    assert result['discrepancy_classification']=='wheel_odometry_without_world_translation'
    assert result['valid'] is False


def test_longitudinal_reversal_rejects_stale_odometry():
    result,_=_dense_reversal_validation(stale=True)
    assert not result['valid'] and not result['odometry_fresh']
    assert not result['reversal_transient_valid']


def test_longitudinal_reversal_keeps_existing_distance_and_yaw_bounds():
    too_far,_=_dense_reversal_validation(body_delta=.14)
    too_much_yaw,_=_dense_reversal_validation(yaw=.051)
    assert not too_far['valid'] and not too_far['reversal_transient_valid']
    assert not too_much_yaw['valid'] and not too_much_yaw['reversal_transient_valid']


@pytest.mark.parametrize('previous_action,action,previous_sign,requested_sign',[
    ('up','down',1,-1),('down','up',-1,1)])
def test_dense_body_trajectory_proves_low_net_reversal_cancellation(
        previous_action,action,previous_sign,requested_sign):
    body_history=_dense_body_reversal_history(previous_sign,requested_sign)
    result,_=_dense_reversal_validation(previous_action=previous_action,action=action,
        after_v=.5*requested_sign,body_delta=.001*requested_sign,
        world_pose_history=body_history)
    assert result['valid'],result
    assert result['reversal_body_history_available']
    assert result['reversal_body_history_fresh'] and result['reversal_body_history_dense']
    assert result['reversal_body_start_direction_ok']
    assert result['reversal_body_zero_crossing']
    assert result['reversal_body_zero_crossing_time']==pytest.approx(.34)
    assert result['reversal_body_end_direction_ok']
    assert result['reversal_net_translation_below_normal_minimum']
    assert result['reversal_cancellation_valid']
    assert not result['reversal_transient_valid']
    assert result['discrepancy_classification']=='validated_longitudinal_reversal_cancellation'


def test_actual_smoke_cancellation_trajectory_uses_deadband_aware_crossing():
    import json
    from pathlib import Path
    from aero_ai_studio.gazebo.physics_controller import PhysicsEntityController

    fixture=json.loads(Path('tests/fixtures/gazebo_dqn_reversal_cancellation_actual.json').read_text())
    transport=FakeTransport();transport.publish=lambda *a:None
    controller=PhysicsEntityController(transport,'test')
    controller.apply_action(fixture['previous_action'])
    previous_command=dict(controller.last_published_command)
    controller.apply_action(fixture['requested_action'])
    result=controller.validate_pose(
        fixture['before_pose'],fixture['after_pose'],fixture['duration'],
        collision=fixture['collision'],
        odometry_before=fixture['odometry_before'],odometry_after=fixture['odometry_after'],
        odometry_history=fixture['odometry_history'],
        simulation_start_time=fixture['simulation_start_time'],
        simulation_end_time=fixture['simulation_end_time'],
        previous_command=previous_command,
        world_pose_history=fixture['world_pose_history_summary'])
    summary=fixture['world_pose_history_summary']
    assert summary['world_velocity_zero_crossing'] is True
    assert result['reversal_body_zero_crossing'] is True
    assert result['reversal_body_zero_crossing_time']==pytest.approx(
        summary['world_velocity_zero_crossing_time'])
    assert result['reversal_body_deadband_sample_count']>=1
    assert result['reversal_cancellation_valid'] is True
    assert result['discrepancy_classification']=='validated_longitudinal_reversal_cancellation'
    assert result['world_pose_forward']==pytest.approx(.0017230510067411942)
    assert result['wheel_odometry_forward']==pytest.approx(.04399999999324534)
    assert result['valid'] is True


def _actual_linear_to_rotation_validation(*,fixture_name='gazebo_linear_to_rotation_actual.json',
                                          history_mutator=None,**overrides):
    import copy,json
    from pathlib import Path
    from aero_ai_studio.gazebo.physics_controller import PhysicsEntityController

    fixture=json.loads(Path('tests/fixtures/'+fixture_name).read_text())
    summary=copy.deepcopy(fixture['world_pose_history_summary'])
    if history_mutator:history_mutator(summary)
    transport=FakeTransport();transport.publish=lambda *a:None
    controller=PhysicsEntityController(transport,'test')
    controller.apply_action('up')
    previous_action_twist=dict(controller.last_published_command)
    controller.apply_action('right')
    kwargs={'collision':fixture['collision'],
        'odometry_before':fixture['odometry_before'],
        'odometry_after':fixture['odometry_after'],
        'odometry_history':fixture['odometry_history'],
        'simulation_start_time':fixture['simulation_start_time'],
        'simulation_end_time':fixture['simulation_end_time'],
        'previous_command':previous_action_twist,'world_pose_history':summary}
    kwargs.update(overrides)
    before=kwargs.pop('before',fixture['before_pose'])
    after=kwargs.pop('after',fixture['after_pose'])
    result=controller.validate_pose(before,after,
        fixture.get('simulation_duration',fixture.get('duration')),
        **kwargs)
    return fixture,result,previous_action_twist


def test_actual_forward_to_right_dense_body_trajectory_proves_transition_transient():
    fixture,result,previous_action_twist=_actual_linear_to_rotation_validation()
    assert fixture['command_mode_transition']=='LINEAR_TO_ROTATION'
    assert fixture['previous_published_twist']=={'linear':{'x':0.0},'angular':{'z':0.0}}
    assert previous_action_twist==fixture['previous_action_twist']
    assert result['command_mode_transition']=='LINEAR_TO_ROTATION'
    assert result['linear_to_rotation_body_history_available']
    assert result['linear_to_rotation_body_history_fresh']
    assert result['linear_to_rotation_body_history_dense']
    assert result['linear_to_rotation_start_forward_velocity']==pytest.approx(.49542932781528465)
    assert result['linear_to_rotation_end_forward_velocity']==pytest.approx(.04219263776589208)
    assert result['linear_to_rotation_start_angular_velocity']==pytest.approx(0.,abs=1e-9)
    assert result['linear_to_rotation_end_angular_velocity']==pytest.approx(-.6800033529857852)
    assert result['linear_to_rotation_forward_remaining_ratio']==pytest.approx(
        abs(result['linear_to_rotation_end_forward_velocity'])/
        abs(result['linear_to_rotation_start_forward_velocity']))
    assert result['linear_to_rotation_forward_decay_fraction']==pytest.approx(
        1.-result['linear_to_rotation_forward_remaining_ratio'])
    assert result['linear_to_rotation_forward_decay_valid']
    assert result['linear_to_rotation_angular_direction_valid']
    assert result['linear_to_rotation_angular_established']
    assert result['linear_to_rotation_angular_sustained']
    assert result['linear_to_rotation_wheel_linear_stopped']
    assert result['linear_to_rotation_wheel_angular_valid']
    assert result['linear_to_rotation_wheel_integral_valid']
    assert result['yaw_delta']==pytest.approx(.013664714081720765)
    assert result['yaw_delta']<result['expected_yaw']*.25
    assert result['linear_to_rotation_transient_valid']
    assert result['valid']
    assert result['discrepancy_classification']=='validated_linear_to_rotation_transient'


def test_actual_smoke_fixture_with_sixteen_poses_passes_time_based_transition_evidence():
    fixture,result,_=_actual_linear_to_rotation_validation(
        fixture_name='gazebo_linear_to_rotation_smoke_actual.json')
    assert fixture['world_pose_history_summary']['world_pose_sample_count']==16
    assert fixture['world_pose_history_summary']['world_pose_history_max_gap']==pytest.approx(.017)
    assert result['linear_to_rotation_forward_remaining_ratio']==pytest.approx(.0914656967477631)
    assert result['linear_to_rotation_forward_decay_fraction']==pytest.approx(.9085343032522369)
    assert result['linear_to_rotation_forward_decay_valid']
    assert result['linear_to_rotation_tail_sample_count']==2
    assert result['linear_to_rotation_angular_sustained_sample_count']==3
    assert result['linear_to_rotation_angular_first_established_time']==pytest.approx(.3705)
    assert result['linear_to_rotation_angular_sustained_duration']==pytest.approx(.0275)
    assert (result['linear_to_rotation_angular_sustained_duration']>=
        result['linear_to_rotation_angular_sustained_min_duration'])
    assert result['linear_to_rotation_angular_sustained']
    assert result['linear_to_rotation_transient_valid'] and result['valid']
    assert result['discrepancy_classification']=='validated_linear_to_rotation_transient'


@pytest.mark.parametrize('history_mutator',[
    lambda h:h.update(world_pose_history_fresh=False),
    lambda h:h.update(world_pose_history_dense_enough=False),
    lambda h:(h.update(world_pose_sample_timestamps=[h['world_pose_sample_timestamps'][0],
        h['world_pose_sample_timestamps'][-1]],world_pose_sample_count=2,
        world_forward_velocity_samples=h['world_forward_velocity_samples'][:1]+h['world_forward_velocity_samples'][-1:],
        world_velocity_sample_count=2,
        world_angular_velocity_samples=h['world_angular_velocity_samples'][:1]+h['world_angular_velocity_samples'][-1:],
        world_angular_velocity_sample_count=2,world_pose_history_max_gap=.1)),
    lambda h:h.update(world_angular_velocity_samples=[]),
    lambda h:h.update(world_pose_sample_timestamps=[h['world_pose_sample_timestamps'][0],
        h['world_pose_sample_timestamps'][0],*h['world_pose_sample_timestamps'][2:]]),
])
def test_linear_to_rotation_transient_rejects_missing_stale_sparse_or_ambiguous_history(history_mutator):
    _,result,_=_actual_linear_to_rotation_validation(history_mutator=history_mutator)
    assert not result['linear_to_rotation_transient_valid']
    assert not result['valid']


def test_linear_to_rotation_rejects_wheel_rotation_without_body_rotation():
    def mutate(history):
        for sample in history['world_angular_velocity_samples']:
            sample['angular_velocity']=sample['body_angular_velocity']=0.
        history['world_start_angular_velocity']=history['world_end_angular_velocity']=0.
    _,result,_=_actual_linear_to_rotation_validation(history_mutator=mutate)
    assert result['linear_to_rotation_wheel_angular_valid']
    assert not result['linear_to_rotation_angular_direction_valid']
    assert not result['linear_to_rotation_transient_valid'] and not result['valid']


def test_linear_to_rotation_rejects_body_rotation_opposite_requested_direction():
    def mutate(history):
        for sample in history['world_angular_velocity_samples']:
            sample['angular_velocity']=sample['body_angular_velocity']=abs(sample['angular_velocity'])
        history['world_start_angular_velocity']=0.
        history['world_end_angular_velocity']=abs(history['world_end_angular_velocity'])
    _,result,_=_actual_linear_to_rotation_validation(history_mutator=mutate)
    assert not result['linear_to_rotation_angular_direction_valid']
    assert not result['linear_to_rotation_transient_valid'] and not result['valid']


def test_linear_to_rotation_rejects_intermediate_opposite_body_angular_motion():
    def mutate(history):
        sample=history['world_angular_velocity_samples'][8]
        sample['angular_velocity']=sample['body_angular_velocity']=.1
    _,result,_=_actual_linear_to_rotation_validation(history_mutator=mutate)
    assert not result['linear_to_rotation_angular_direction_valid']
    assert not result['linear_to_rotation_transient_valid'] and not result['valid']


def test_linear_to_rotation_rejects_single_angular_spike_without_sustained_tail():
    def mutate(history):
        rows=history['world_angular_velocity_samples']
        for sample in rows[-4:-1]:
            sample['angular_velocity']=sample['body_angular_velocity']=0.
        rows[-1]['angular_velocity']=rows[-1]['body_angular_velocity']=-.8
        history['world_end_angular_velocity']=-.8
    _,result,_=_actual_linear_to_rotation_validation(history_mutator=mutate)
    assert not result['linear_to_rotation_angular_sustained']
    assert not result['linear_to_rotation_transient_valid'] and not result['valid']


def test_linear_to_rotation_rejects_requested_rotation_that_drops_to_zero_before_end():
    def mutate(history):
        sample=history['world_angular_velocity_samples'][-1]
        sample['angular_velocity']=sample['body_angular_velocity']=0.
        history['world_end_angular_velocity']=0.
    _,result,_=_actual_linear_to_rotation_validation(history_mutator=mutate)
    assert not result['linear_to_rotation_angular_sustained']
    assert not result['linear_to_rotation_angular_direction_valid']
    assert not result['linear_to_rotation_transient_valid'] and not result['valid']


def test_linear_to_rotation_rejects_forward_motion_that_does_not_decay():
    def mutate(history):
        start=history['world_forward_velocity_samples'][0]['forward_velocity']
        for sample in history['world_forward_velocity_samples']:
            sample['forward_velocity']=sample['body_forward_velocity']=start
        history['world_start_forward_velocity']=history['world_end_forward_velocity']=start
    _,result,_=_actual_linear_to_rotation_validation(history_mutator=mutate)
    assert not result['linear_to_rotation_forward_decay_valid']
    assert not result['linear_to_rotation_transient_valid'] and not result['valid']


def test_linear_to_rotation_rejects_forward_remaining_above_intended_quarter():
    def mutate(history):
        start=history['world_forward_velocity_samples'][0]['forward_velocity']
        for sample in history['world_forward_velocity_samples'][1:]:
            sample['forward_velocity']=sample['body_forward_velocity']=start*.6
        history['world_start_forward_velocity']=start
        history['world_end_forward_velocity']=start*.6
    _,result,_=_actual_linear_to_rotation_validation(history_mutator=mutate)
    assert result['linear_to_rotation_forward_remaining_ratio']==pytest.approx(.6)
    assert result['linear_to_rotation_forward_decay_fraction']==pytest.approx(.4)
    assert not result['linear_to_rotation_forward_decay_valid']
    assert not result['linear_to_rotation_transient_valid'] and not result['valid']


def test_linear_to_rotation_requires_wheel_linear_stop_and_angular_convergence():
    fixture,_,_=_actual_linear_to_rotation_validation()
    wheel_linear_failed={**fixture['odometry_after'],'linear_x':.5}
    _,not_stopped,_=_actual_linear_to_rotation_validation(odometry_after=wheel_linear_failed)
    assert not not_stopped['linear_to_rotation_wheel_linear_stopped']
    assert not not_stopped['linear_to_rotation_transient_valid'] and not not_stopped['valid']
    wheel_angular_failed={**fixture['odometry_after'],'angular_z':0.}
    _,not_converged,_=_actual_linear_to_rotation_validation(odometry_after=wheel_angular_failed)
    assert not not_converged['linear_to_rotation_wheel_angular_valid']
    assert not not_converged['linear_to_rotation_transient_valid'] and not not_converged['valid']


def test_linear_to_rotation_keeps_existing_endpoint_distance_yaw_and_contact_bounds():
    fixture,_,_=_actual_linear_to_rotation_validation()
    too_far={**fixture['after_pose'],'x':fixture['before_pose']['x']+.08}
    _,distance_failure,_=_actual_linear_to_rotation_validation(after=too_far)
    too_much_yaw={**fixture['after_pose'],'yaw':-.211}
    _,yaw_failure,_=_actual_linear_to_rotation_validation(after=too_much_yaw)
    _,contact_failure,_=_actual_linear_to_rotation_validation(collision=True)
    assert not distance_failure['linear_to_rotation_transient_valid'] and not distance_failure['valid']
    assert not yaw_failure['linear_to_rotation_transient_valid'] and not yaw_failure['valid']
    assert not contact_failure['linear_to_rotation_transient_valid']


def test_linear_to_rotation_requires_real_prior_action_not_zero_publication():
    fixture,result,_=_actual_linear_to_rotation_validation(previous_command={
        'linear':{'x':0.},'angular':{'z':0.}})
    assert fixture['previous_published_twist']['linear']['x']==0.
    assert result['command_mode_transition']=='OTHER'
    assert not result['linear_to_rotation_transient_valid'] and not result['valid']


def test_rotation_to_linear_does_not_use_linear_to_rotation_subtype():
    import json
    from pathlib import Path
    from aero_ai_studio.gazebo.physics_controller import PhysicsEntityController
    fixture=json.loads(Path('tests/fixtures/gazebo_linear_to_rotation_actual.json').read_text())
    transport=FakeTransport();transport.publish=lambda *a:None
    controller=PhysicsEntityController(transport,'test')
    controller.apply_action('right');previous=dict(controller.last_published_command)
    controller.apply_action('up')
    result=controller.validate_pose(fixture['before_pose'],fixture['after_pose'],
        fixture['simulation_duration'],odometry_before=fixture['odometry_before'],
        odometry_after=fixture['odometry_after'],odometry_history=fixture['odometry_history'],
        simulation_start_time=fixture['simulation_start_time'],
        simulation_end_time=fixture['simulation_end_time'],previous_command=previous,
        world_pose_history=fixture['world_pose_history_summary'])
    assert result['command_mode_transition']=='ROTATION_TO_LINEAR'
    assert not result['linear_to_rotation_transient_valid']


def test_steady_rotation_below_existing_minimum_yaw_still_fails():
    from aero_ai_studio.gazebo.physics_controller import PhysicsEntityController
    transport=FakeTransport();transport.publish=lambda *a:None
    controller=PhysicsEntityController(transport,'test')
    controller.apply_action('right');previous=dict(controller.last_published_command)
    controller.apply_action('right')
    result=controller.validate_pose({'x':1.5,'y':1.5,'yaw':0.},
        {'x':1.5,'y':1.5,'yaw':-.01},.1,
        odometry_before={'timestamp':.2,'linear_x':0.,'angular_z':-.8},
        odometry_after={'timestamp':.3,'linear_x':0.,'angular_z':-.8},
        odometry_history=[{'timestamp':.2+i*.01,'linear_x':0.,'angular_z':-.8}
                          for i in range(1,10)],
        simulation_start_time=.2,simulation_end_time=.3,previous_command=previous)
    assert result['command_mode_transition']=='STEADY_ROTATION'
    assert not result['linear_to_rotation_transient_valid']
    assert not result['valid']


def test_forward_to_rotation_with_pose_history_remains_strict_failure():
    from aero_ai_studio.gazebo.physics_controller import PhysicsEntityController
    from aero_ai_studio.gazebo.entity_controller import summarize_world_pose_history
    from aero_ai_studio.simulation.action_mapping import classify_physics_command_transition

    transport=FakeTransport();transport.publish=lambda *a:None
    controller=PhysicsEntityController(transport,'test')
    controller.apply_action('up');previous=dict(controller.last_published_command)
    controller.apply_action('right')
    samples=[{'simulation_timestamp':.8+i*.005,'world_x':1.5+.0255*(1-i/20),
              'world_y':1.5,'world_yaw':-.0124*i/20} for i in range(21)]
    summary=summarize_world_pose_history(samples,.8,.9)
    before={'x':1.5255,'y':1.5,'yaw':0.}
    after={'x':1.55105755,'y':1.5,'yaw':-.012437653205}
    result=controller.validate_pose(before,after,.1,
        odometry_before={'timestamp':.8,'linear_x':.5,'angular_z':0.},
        odometry_after={'timestamp':.9,'linear_x':.05,'angular_z':-.8},
        odometry_history=[{'timestamp':.81+i*.01,'linear_x':(.05 if i else .05),
                           'angular_z':(-.72 if i==0 else -.8)} for i in range(8)],
        simulation_start_time=.8,simulation_end_time=.9,
        previous_command=previous,world_pose_history=summary)
    assert classify_physics_command_transition(previous,controller.last_published_command)=="LINEAR_TO_ROTATION"
    assert summary['world_pose_history_fresh'] and summary['world_pose_history_dense_enough']
    assert summary['world_angular_velocity_sample_count']>0
    assert result['valid'] is False
    assert result['discrepancy_classification']=='world_pose_exceeds_wheel_odometry'
    assert result['reversal_cancellation_valid'] is False


def test_deadband_crossing_requires_significant_requested_motion_after_neutral():
    from aero_ai_studio.gazebo.entity_controller import directed_velocity_zero_crossing
    def samples(values):
        return [{'simulation_timestamp':.3+i*.01,'forward_velocity':v}
                for i,v in enumerate(values)]

    good=directed_velocity_zero_crossing(samples([-.12,-.035,.004,.027,.08]),-1,1,
        interval_start=.3,interval_end=.4)
    ends_neutral=directed_velocity_zero_crossing(samples([-.12,-.035,.004,.019]),-1,1,
        interval_start=.3,interval_end=.4)
    noise_only=directed_velocity_zero_crossing(samples([-.12,.006,-.009,.012,-.004]),-1,1,
        interval_start=.3,interval_end=.4)
    requested_spike_then_old=directed_velocity_zero_crossing(
        samples([-.12,-.01,.03,.01,-.04]),-1,1,interval_start=.3,interval_end=.4)
    assert good['valid'] and good['deadband_samples']==1
    assert not ends_neutral['valid']
    assert not noise_only['valid']
    assert not requested_spike_then_old['valid']


def test_cancellation_without_reversal_or_body_history_remains_strict():
    from aero_ai_studio.gazebo.physics_controller import PhysicsEntityController
    transport=FakeTransport();transport.publish=lambda *a:None
    controller=PhysicsEntityController(transport,'test');controller.apply_action('up')
    result=controller.validate_pose({'x':1.5,'y':1.5,'yaw':0.},
        {'x':1.501,'y':1.5,'yaw':0.},.1,
        odometry_before={'timestamp':.3,'linear_x':0.,'angular_z':0.},
        odometry_after={'timestamp':.4,'linear_x':.5,'angular_z':0.},
        odometry_history=[{'timestamp':.3+i*.01,'linear_x':.5,'angular_z':0.}
                          for i in range(1,10)],
        simulation_start_time=.3,simulation_end_time=.4)
    assert not result['valid'] and not result['reversal_cancellation_valid']
    assert result['discrepancy_classification']=='wheel_odometry_without_world_translation'


@pytest.mark.parametrize('action,sign', [('up',1),('down',-1)])
def test_normal_forward_and_reverse_motion_keep_existing_pass_semantics(action,sign):
    from aero_ai_studio.gazebo.physics_controller import PhysicsEntityController
    transport=FakeTransport();transport.publish=lambda *a:None
    controller=PhysicsEntityController(transport,'test');controller.apply_action(action)
    result=controller.validate_pose({'x':1.5,'y':1.5,'yaw':0.},
        {'x':1.5+.047*sign,'y':1.5,'yaw':0.},.1,
        odometry_before={'timestamp':.3,'linear_x':0.,'angular_z':0.},
        odometry_after={'timestamp':.4,'linear_x':.5*sign,'angular_z':0.},
        odometry_history=[{'timestamp':.3+i*.01,'linear_x':.5*sign,'angular_z':0.}
                          for i in range(1,10)],
        simulation_start_time=.3,simulation_end_time=.4)
    assert result['valid'],result
    assert not result['reversal_cancellation_valid']


def test_actual_diagnostic_up_to_down_body_transient_remains_existing_subtype():
    velocities=[.50113]*19+[.05,-.047,-.02713]
    times=[.302+i*.0045 for i in range(19)]+[.3905,.395,.397]
    body_history={'world_pose_sample_count':23,'world_pose_history_fresh':True,'world_pose_history_dense_enough':True,
        'world_pose_sample_timestamps':[.3+i*.0045 for i in range(23)],
        'world_velocity_sample_count':len(velocities),
        'world_forward_velocity_samples':[{'simulation_timestamp':t,'forward_velocity':v,'sample_interval':.0045}
            for t,v in zip(times,velocities)],
        'world_start_forward_velocity':.50113,'world_end_forward_velocity':-.02713,
        'world_velocity_zero_crossing':True,'world_velocity_zero_crossing_time':.39277}
    result,_=_dense_reversal_validation(body_delta=.02443903741,
        world_pose_history=body_history)
    assert result['valid'],result
    assert result['reversal_transient_valid']
    assert not result['reversal_cancellation_valid']
    assert result['discrepancy_classification']=='validated_longitudinal_reversal_transient'


@pytest.mark.parametrize('history_options',[
    {'crossing':False},
    {'fresh':False},
    {'dense':False},
    {'start_direction':-1},
    {'end_direction':1},
])
def test_cancellation_requires_fresh_dense_body_direction_crossing(history_options):
    history=_dense_body_reversal_history(1,-1,**history_options)
    result,_=_dense_reversal_validation(body_delta=.001,world_pose_history=history)
    assert not result['valid'],result
    assert not result['reversal_cancellation_valid']


def test_cancellation_obeys_existing_yaw_and_physical_distance_bounds():
    history=_dense_body_reversal_history(1,-1)
    too_far,_=_dense_reversal_validation(body_delta=.14,world_pose_history=history)
    too_much_yaw,_=_dense_reversal_validation(body_delta=.001,yaw=.051,world_pose_history=history)
    assert not too_far['valid'] and not too_far['reversal_cancellation_valid']
    assert not too_much_yaw['valid'] and not too_much_yaw['reversal_cancellation_valid']


def test_recorded_diagnostic_reverse_to_forward_progress_remains_normal_pass():
    result,_=_dense_reversal_validation(previous_action='down',action='up',after_v=.5,
        body_delta=.02032)
    assert result['valid'],result
    assert not result['reversal_cancellation_valid']
    assert result['discrepancy_classification']=='wheel_odometry_exceeds_world_pose'


def test_opposite_world_motion_without_command_reversal_still_fails():
    result,_=_dense_reversal_validation(body_delta=-.02,previous_action='up',action='up',
                                         after_v=.5)
    assert not result['valid']
    assert not result['command_reversal_detected']
    assert not result['reversal_transient_valid']


def test_physics_controller_records_twist_replacement_and_zero_command_publish():
    from aero_ai_studio.gazebo.physics_controller import PhysicsEntityController
    transport=FakeTransport();published=[];transport.publish=lambda topic,kind,payload:published.append(dict(payload))
    controller=PhysicsEntityController(transport,'test')
    controller.apply_action('left');turn=controller.last_published_command
    controller.stop_agent();zero=controller.last_published_command
    controller.apply_action('up');forward=controller.last_published_command
    assert turn=={'linear':{'x':0},'angular':{'z':.8}}
    assert zero=={'linear':{'x':0},'angular':{'z':0}}
    assert forward=={'linear':{'x':.5},'angular':{'z':0}}
    assert controller.publish_sequence==3 and published==[turn,zero,forward]


def test_sparse_endpoint_odometry_does_not_assume_trapezoidal_acceleration():
    from aero_ai_studio.gazebo.physics_controller import PhysicsEntityController
    transport=FakeTransport();transport.publish=lambda *a:None
    controller=PhysicsEntityController(transport,'test');controller.apply_action('left')
    before={'x':0.,'y':0.,'yaw':0.};after={**before,'yaw':.07472749596526108}
    result=controller.validate_pose(before,after,.1,odometry_before={
        'timestamp':1.,'linear_x':0.,'angular_z':0.},odometry_after={
        'timestamp':1.1,'linear_x':0.,'angular_z':.8},
        simulation_start_time=1.,simulation_end_time=1.1)
    assert result['valid'],result
    assert result['odometry_integration_method']=='endpoint_bounds'
    assert result['odometry_integrated_yaw'] is None
    assert result['command_integrated_yaw']==pytest.approx(.08)
    assert result['pose_measured_yaw']==pytest.approx(.07472749596526108)
    assert result['odometry_integration_note']=='sparse endpoint bounds; no trapezoidal integral reported'
    assert result['discrepancy_classification']=='direction_and_velocity_only'


def test_dense_odometry_history_is_integrated_piecewise():
    from aero_ai_studio.gazebo.physics_controller import PhysicsEntityController
    transport=FakeTransport();transport.publish=lambda *a:None
    controller=PhysicsEntityController(transport,'test');controller.apply_action('left')
    history=[{'timestamp':1.+i*.01,'linear_x':0.,'angular_z':.8} for i in range(1,10)]
    before={'x':0.,'y':0.,'yaw':0.};after={**before,'yaw':.076}
    result=controller.validate_pose(before,after,.1,odometry_before={
        'timestamp':1.,'linear_x':0.,'angular_z':0.},odometry_after={
        'timestamp':1.1,'linear_x':0.,'angular_z':.8},odometry_history=history,
        simulation_start_time=1.,simulation_end_time=1.1)
    assert result['valid'],result
    assert result['odometry_integration_method']=='history_piecewise'
    assert result['odometry_sample_count']==11
    assert result['odometry_integrated_yaw']==pytest.approx(.076)
    assert result['pose_odometry_consistent'] is None
    assert 'magnitude discrepancy is telemetry' in result['consistency_reason']


@pytest.mark.parametrize('world_forward,after_velocity,collision,expected,classification',[
    (.047,.5,False,True,'translation_signals_close'),
    (.026386304842561215,.5,False,True,'wheel_odometry_exceeds_world_pose'),
    (-.026,.5,False,False,'world_pose_odometry_direction_disagreement'),
    (0.,.5,False,False,'wheel_odometry_without_world_translation'),
    (0.,.5,True,True,'wheel_odometry_without_world_translation'),
    (.047,-.5,False,False,'world_pose_odometry_direction_disagreement'),
])
def test_wheel_odometry_and_world_pose_are_separate_signal_layers(world_forward,after_velocity,collision,expected,classification):
    from aero_ai_studio.gazebo.physics_controller import PhysicsEntityController
    transport=FakeTransport();transport.publish=lambda *a:None
    controller=PhysicsEntityController(transport,'test');controller.apply_action('up')
    before={'x':1.5,'y':1.5,'yaw':0.}
    after={**before,'x':before['x']+world_forward}
    before_odom={'timestamp':.2,'linear_x':0.,'angular_z':0.}
    after_odom={'timestamp':.3,'linear_x':after_velocity,'angular_z':0.}
    history=[{'timestamp':.21,'linear_x':.45,'angular_z':0.}]
    history.extend({'timestamp':round(.22+i*.01,8),'linear_x':.5 if after_velocity>0 else -.5,'angular_z':0.}
                   for i in range(8))
    result=controller.validate_pose(before,after,.1,collision,before_odom,after_odom,history,
                                    simulation_start_time=.2,simulation_end_time=.3)
    assert result['valid'] is expected,result
    assert result['odometry_integration_method']=='history_piecewise'
    assert result['odometry_fresh']
    assert result['odometry_direction_ok'] is (after_velocity>0)
    assert result['discrepancy_classification']==classification
    assert result['pose_odometry_consistent'] is None
    if world_forward==pytest.approx(.026386304842561215):
        assert result['wheel_odometry_forward']==pytest.approx(.047)
        assert result['world_pose_forward']==pytest.approx(world_forward)
        assert result['odometry_pose_ratio']==pytest.approx(.047/world_forward)
    if collision:assert result['contact_blocked_world_motion']


def test_stale_odometry_fails_closed_and_wrong_turn_pose_fails():
    from aero_ai_studio.gazebo.physics_controller import PhysicsEntityController
    transport=FakeTransport();transport.publish=lambda *a:None
    controller=PhysicsEntityController(transport,'test');controller.apply_action('up')
    pose={'x':1.5,'y':1.5,'yaw':0.};forward={**pose,'x':1.55}
    stale=controller.validate_pose(pose,forward,.1,odometry_before={'timestamp':.1,'linear_x':0.,'angular_z':0.},
        odometry_after={'timestamp':.2,'linear_x':.5,'angular_z':0.},simulation_start_time=.2,simulation_end_time=.3)
    assert not stale['valid'] and not stale['odometry_fresh']
    controller.apply_action('left')
    wrong_turn=controller.validate_pose(pose,{**pose,'yaw':-.07},.1,
        odometry_before={'timestamp':.2,'linear_x':0.,'angular_z':0.},
        odometry_after={'timestamp':.3,'linear_x':0.,'angular_z':.8},
        simulation_start_time=.2,simulation_end_time=.3)
    assert not wrong_turn['valid'] and not wrong_turn['world_direction_ok']


def test_target_bearing_and_wrapped_yaw_error():
    geometry=load_verifier().target_geometry
    assert geometry({'x':1.5,'y':1.5,'yaw':0.},{'x':3.5,'y':1.5})=={'distance':2.,'bearing':0.,'yaw_error':0.}
    assert geometry({'x':1.5,'y':1.5,'yaw':math.pi/2},{'x':3.5,'y':1.5})['yaw_error']==pytest.approx(-math.pi/2)
    assert geometry({'x':1.5,'y':1.5,'yaw':-math.pi/2},{'x':3.5,'y':1.5})['yaw_error']==pytest.approx(math.pi/2)
    wrapped=geometry({'x':0.,'y':0.,'yaw':math.pi-.01},{'x':-1.,'y':-.001})
    assert 0<wrapped['yaw_error']<.02
