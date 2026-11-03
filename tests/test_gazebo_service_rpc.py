"""Adapter tests: real protobuf serialization, no native Node or Gazebo sockets."""
from types import SimpleNamespace
from pathlib import Path
import importlib.util
import subprocess
import pytest
from aero_ai_studio.gazebo.transport import HarmonicTransport
from aero_ai_studio.gazebo.entity_controller import GazeboEntityController
from aero_ai_studio.gazebo.environment import GazeboEnvironment
from aero_ai_studio.core.storage import read_json
from test_v06 import FakeTransport,tiny


@pytest.fixture
def rpc(monkeypatch):
    # Msg classes are data-only; importing them does not start Transport.
    Pose=pytest.importorskip('gz.msgs10.pose_pb2').Pose
    Boolean=pytest.importorskip('gz.msgs10.boolean_pb2').Boolean
    WorldControl=pytest.importorskip('gz.msgs10.world_control_pb2').WorldControl
    from google.protobuf import json_format,text_format
    t=HarmonicTransport.__new__(HarmonicTransport)
    t.message=lambda name:{'Pose':Pose,'Boolean':Boolean,'WorldControl':WorldControl}[name]
    t.json=json_format;t.text=text_format;t.timeout=10
    t.partition='isolated_test';t.executable='/usr/bin/gz';t.request_history=[]
    provider=SimpleNamespace(req_type_name='gz.msgs.Pose',rep_type_name='gz.msgs.Boolean')
    t.node=SimpleNamespace(service_info=lambda service:[provider],
                           request=lambda *args:pytest.fail('In-process synchronous native RPC must not be used'))
    clock=[0.]
    monkeypatch.setattr('aero_ai_studio.gazebo.transport.time.monotonic',lambda:clock[0])
    monkeypatch.setattr('aero_ai_studio.gazebo.transport.time.sleep',lambda delay:clock.__setitem__(0,clock[0]+delay))
    return t,provider,clock


def test_set_pose_cli_wire_schema_partition_and_boolean(rpc,monkeypatch):
    t,provider,clock=rpc
    calls=[]
    payload={'name':'simple_agent','position':{'x':1.5,'y':1.5,'z':.16},'orientation':{'w':1.}}
    def run(command,**kwargs):
        calls.append(command)
        assert command[:4]==['/usr/bin/gz','service','-s','/world/test/set_pose']
        assert command[command.index('--reqtype')+1]=='gz.msgs.Pose'
        assert command[command.index('--reptype')+1]=='gz.msgs.Boolean'
        request=t.text.Parse(command[command.index('--req')+1],t.message('Pose')())
        assert request.name=='simple_agent' and request.position.z==.16
        assert request.orientation.w==1 and request.orientation.z==0
        assert kwargs['env']['GZ_PARTITION']=='isolated_test'
        assert kwargs['timeout']<=10
        return subprocess.CompletedProcess(command,0,'data: true\n','')
    monkeypatch.setattr('aero_ai_studio.gazebo.transport.subprocess.run',run)
    assert t.request('/world/test/set_pose','Pose','Boolean',payload)=={'data':True}
    assert len(calls)==1 and t.request_history[0]['backend']=='gz-service-subprocess'


def test_service_readiness_wait_and_schema_mismatch(rpc,monkeypatch):
    t,p,clock=rpc
    providers=iter([[],[],[p]])
    t.node.service_info=lambda service:next(providers)
    assert t.wait_for_service('/set_pose','Pose','Boolean')['request_type']=='gz.msgs.Pose'
    assert clock[0]==pytest.approx(.15)
    p.req_type_name='gz.msgs.Empty'
    t.node.service_info=lambda service:[p]
    monkeypatch.setattr('aero_ai_studio.gazebo.transport.subprocess.run',lambda *a,**k:pytest.fail('Schema mismatch must not send RPC'))
    with pytest.raises(RuntimeError,match='schema mismatch'):t.request('/world/test/set_pose','Pose','Boolean',{})
    t.node.service_info=lambda service:[]
    with pytest.raises(TimeoutError,match='not advertised/ready'):t.wait_for_service('/missing','Pose','Boolean',.3)
    assert clock[0]==pytest.approx(.45)


@pytest.mark.parametrize('recover',[True,False])
def test_pose_timeout_retry_is_bounded_and_idempotent(rpc,monkeypatch,recover):
    t,p,clock=rpc;commands=[]
    def run(command,**kwargs):
        commands.append(command);clock[0]+=2
        return subprocess.CompletedProcess(command,0,'data: true' if recover and len(commands)==2 else '',
                                            '' if recover and len(commands)==2 else 'Service call timed out')
    monkeypatch.setattr('aero_ai_studio.gazebo.transport.subprocess.run',run)
    if recover:assert t.request('/world/test/set_pose','Pose','Boolean',{'name':'simple_agent'})['data']
    else:
        with pytest.raises(TimeoutError,match='attempts=3'):t.request('/world/test/set_pose','Pose','Boolean',{'name':'simple_agent'})
    assert len(commands)==(2 if recover else 3)
    assert all(command==commands[0] for command in commands)
    assert clock[0]<=10


@pytest.mark.parametrize('output,returncode,error',[('data: false',0,'Boolean false'),('',1,'exited 1'),('not a protobuf',0,None)])
def test_false_rejection_and_malformed_response_never_pass_or_retry(rpc,monkeypatch,output,returncode,error):
    t,p,clock=rpc;calls=[]
    def run(command,**kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command,returncode,output,'')
    monkeypatch.setattr('aero_ai_studio.gazebo.transport.subprocess.run',run)
    with pytest.raises(Exception,match=error):t.request('/world/test/set_pose','Pose','Boolean',{})
    assert len(calls)==1


def test_control_timeout_never_retries_and_pose_probe_can_limit_to_one(rpc,monkeypatch):
    t,p,clock=rpc;calls=[]
    def run(command,**kwargs):
        calls.append(command)
        raise subprocess.TimeoutExpired(command,kwargs['timeout'])
    monkeypatch.setattr('aero_ai_studio.gazebo.transport.subprocess.run',run)
    p.req_type_name='gz.msgs.WorldControl'
    with pytest.raises(TimeoutError):t.request('/world/test/control','WorldControl','Boolean',{'multi_step':100})
    assert len(calls)==1
    p.req_type_name='gz.msgs.Pose'
    with pytest.raises(TimeoutError):t.request('/world/test/set_pose','Pose','Boolean',{},max_attempts=1)
    assert len(calls)==2


def test_controller_rejects_invalid_pose_and_boolean_false():
    t=FakeTransport();controller=GazeboEntityController(t,'test','simple_agent')
    for bad in (float('nan'),float('inf')):
        with pytest.raises(ValueError):controller.reset_agent_pose(bad,1)
    assert not t.calls
    t.request=lambda *a:{'data':False}
    with pytest.raises(RuntimeError,match='rejected set_pose'):controller.reset_agent_pose(1.5,1.5,.16)
    assert not controller.last_pose_request['accepted']


def test_world_prepare_is_read_only_and_physics_reset_sends_one_pose(tmp_path):
    class Transport(FakeTransport):
        def publish(self,*args):pass
    t=Transport();t.poses['simple_agent']={'x':.5,'y':.5,'z':.16}
    env=GazeboEnvironment(tiny(),transport=t,root=tmp_path,control_mode='PHYSICS')
    env.prepare()
    assert not t.calls
    env.reset()
    poses=[payload for service,payload in t.calls if service.endswith('/set_pose')]
    assert len(poses)==1 and poses[0]['name']=='simple_agent' and poses[0]['position']['z']==.16
    assert env.initialization_checks['set_pose']=='PASS'
    assert env.initialization_checks['reset_applied']=='PASS'
    env.close()


def test_pose_retries_share_original_total_timeout(rpc,monkeypatch):
    t,p,clock=rpc;t.timeout=.25;calls=[]
    def run(command,**kwargs):
        calls.append(command);clock[0]+=kwargs['timeout']
        raise subprocess.TimeoutExpired(command,kwargs['timeout'])
    monkeypatch.setattr('aero_ai_studio.gazebo.transport.subprocess.run',run)
    with pytest.raises(TimeoutError):t.request('/world/test/set_pose','Pose','Boolean',{})
    assert clock[0]==pytest.approx(.25) and len(calls)==1


def test_diagnostic_requests_exactly_once_and_saves_boolean(tmp_path,monkeypatch):
    source=Path(__file__).parents[1]/'tools'/'diagnose_set_pose.py'
    spec=importlib.util.spec_from_file_location('diagnose_fixture',source)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    calls=[]
    class Transport:
        request_history=[]
        def __init__(self,partition,timeout):assert partition=='test_partition'
        def wait_for_service(self,service,req,rep):return {'request_type':'gz.msgs.Pose','response_type':'gz.msgs.Boolean'}
        def request(self,service,req,rep,payload,**kwargs):
            calls.append((service,req,rep,payload,kwargs))
            return {'data':True}
        def close(self):pass
    monkeypatch.setattr(module,'HarmonicTransport',Transport)
    output=tmp_path/'diagnosis.json'
    report=module.run('test','test_partition',output)
    assert report['status']=='PASS' and len(calls)==1
    assert calls[0][4]=={'max_attempts':1}
    assert calls[0][3]['name']=='simple_agent'
    assert read_json(output)['response']=={'data':True}
    assert report['pose_applied']=='NOT VERIFIED'


def test_prepare_waits_for_agent_in_initial_pose_frames(tmp_path,monkeypatch):
    class Transport(FakeTransport):
        reads=0
        def sample(self,topic,*args,**kwargs):
            if topic.endswith('/pose/info'):
                self.reads+=1
                if self.reads==1:return {'pose':[]}
            return super().sample(topic,*args,**kwargs)
    t=Transport();waits=[]
    monkeypatch.setattr('aero_ai_studio.gazebo.environment.time.sleep',waits.append)
    env=GazeboEnvironment(tiny(),transport=t,root=tmp_path)
    assert env.prepare()['x']==.5
    assert t.reads==2 and waits==[.05] and not t.calls
    env.close()
