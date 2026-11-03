"""AN-L offline contracts. No runtime target/isolation proof is mocked as fact."""
import copy
import inspect
import json
import math
from pathlib import Path
from types import SimpleNamespace
import pytest
from tools import diagnose_v07_gazebo_phase_isolation_qualification as q


@pytest.fixture(autouse=True)
def forbid_runtime(monkeypatch):
    from aero_ai_studio.gazebo.process_manager import GazeboProcessManager
    def fail(*a,**k):raise AssertionError('offline tests forbid Gazebo launch')
    monkeypatch.setattr(GazeboProcessManager,'launch',fail)
    monkeypatch.setattr(q.g.ab,'_run_case',fail)


@pytest.mark.parametrize('arm,sign',[('SHAM',0),('PLUS_DELTA',1),('MINUS_DELTA',-1)])
def test_exact_targets_actual_coordinate_not_phase(arm,sign):
    assert q.DELTA==4.868844349914525e-8
    assert q.target(123.456,arm)==123.456+sign*q.DELTA
    assert q.target(123.456,arm)!=q.target(1.004,arm)


@pytest.mark.parametrize('value',[math.nan,math.inf,None])
def test_nonfinite_actual_coordinate_rejected(value):
    with pytest.raises(ValueError):q.target(value,'PLUS_DELTA')


def make_record(arm,base=.75):
    amount=q.target(0.,arm);packets=[]
    for i,code in enumerate([0,0,0,q.ARMS.index(arm)+1,0,0,0]):
        moved=i>=3;right=base+(amount if moved else 0)
        def pose(angle=0):
            return {'position_world_m':[0.,0.,.1],
                'orientation_world_xyzw':q.g.dm.qmul([0.,math.sin(angle/2),0.,math.cos(angle/2)],[math.sqrt(.5),0.,0.,math.sqrt(.5)])}
        body={'position_world_m':[0.,0.,.1],'orientation_world_xyzw':[0.,0.,0.,1.]}
        links={}
        for name,p in [('body',body),('left_wheel',pose(.5)),('right_wheel',pose(right))]:
            links[name]={'ECM_pose':copy.deepcopy(p),'engine_derived_collision_pose':copy.deepcopy(p),
                **{key:[0.,0.,0.] for key in ('engine_derived_linear_velocity','engine_derived_angular_velocity','ECM_linear_velocity','ECM_angular_velocity')}}
        packets.append({'request_id':i+1,'operation_code':code,'error':'','paused':True,'iteration':3600,'sim_time_ns':3600000000,
            'postupdate_count':i+10,'apply_callback':i+10,'advancing_callback_count':3600,'last_advancing_iteration':3600,'last_advancing_time_ns':3600000000,
            'WorldPoseCmd_active':0,'WorldPoseCmd_observations':20,'ResetPosition_invoked':i==3,
            'q_actual_pre':base if i==3 or not moved else right,'left_actual_pre':.5,
            'requested_target':base+amount if i==3 else right,'requested_delta':amount if i==3 else 0.,
            'target_numerically_differs':amount!=0 if i==3 else False,'target_bitwise_differs':amount!=0 if i==3 else False,
            'generalized_q':{'right':right,'left':.5},'links':links,
            'joint_wrench':{s:{'actual_velocity_rad_s':0.,'force_xyz_N':[0.,0.,1.],'torque_xyz_N_m':[0.,0.,0.]} for s in ('left','right')},
            'supports':{s:{'state':'VALID_CONTACTS','component_available':True,'contacts':[],'component_producer_stamp_ns':3600000000} for s in ('left_wheel','right_wheel','front_caster','rear_caster')}})
    marker={'iteration':3600,'sim_time_ns':3600000000,'paused':True,'stats_source':'transport_snapshot',
        'observed_snapshot':{'iterations_normalized':3600,'paused':True,'sim_time':{'sec':3,'nsec':600000000}}}
    e={'qualification_completed':True,'packets':packets,'PRE_marker':marker,'POST_marker':copy.deepcopy(marker),
        'window_start':0,'window_end':7,'host_PRE':{'cursor':20},'host_POST':{'cursor':20},
        'stopped_chunk':{'phase':'BRAKE_LINEAR','iterations_contract_pass':True,'world_pose_history_contract':{'pass':True},
          'body_stopped_contract':{'pass':True},'collision_events':[],'simulation_end':3.6},
        'completed_brake':{'active_physics_transactions':0}}
    return {'phase_qualification':e,'command_audit':[{'kind':'RPC','request_type':'Int32','service':'/test/phase_qualification/request'} for _ in packets],
        'events':[{'canonical_index':i,'exception':None,'terminated':False} for i in range(8,24)]+[{'canonical_index':24,'exception':{'message':q.STOP}}],
        'terminal_entry_history':{'production_plan':{'request':{'previous_command':q.g.dm.gazebo_physics_twist('down'),'transition_type':'LINEAR_REVERSAL'},
            'phases':[{'kind':'BRAKE_LINEAR'},{'kind':'ACQUIRE_LINEAR'}]}}}


@pytest.mark.parametrize('arm',q.ARMS)
def test_analysis_target_mapping_and_cached_contacts_are_never_pass(arm):
    r=make_record(arm);a=q.analyze(r,arm)
    assert a['target_attained'] and a['zero_advancement']
    assert a['classification']=='PHASE_RESET_COLLATERAL_UNVERIFIABLE'
    assert a['generalized_target_and_native_mapping_qualified']
    assert a['contact_collateral']=='UNVERIFIABLE_WITH_ZERO_ADVANCEMENT'
    assert not a['causal_runtime_ready']
    assert abs(a['actual_generalized_delta_rad']-q.target(0.,arm))<1e-15
    if arm!='SHAM':assert a['mapping']['engine_derived_collision_pose']['ratio_phase_delta_to_generalized_delta']==pytest.approx(1.,abs=1e-7)
    else:assert 'SHAM_PATH_NOT_STRUCTURALLY_EQUIVALENT' in a['flags']


def test_axis_sign_and_phase_wrap():
    r=make_record('PLUS_DELTA')
    assert q.wrap(2*math.pi-1e-9)==pytest.approx(-1e-9,abs=1e-15)
    assert q.phases(r['phase_qualification']['packets'][0],'ECM_pose')['right']==pytest.approx(.75)
    assert q.analyze(r,'PLUS_DELTA')['mapping']['ECM_pose']['RIGHT_phase_delta']>0


def test_stale_ECM_not_used_as_direct_isolation_or_mapping_proof():
    r=make_record('PLUS_DELTA');rows=r['phase_qualification']['packets']
    for row in rows[3:]:row['links']['right_wheel']['ECM_pose']=copy.deepcopy(rows[0]['links']['right_wheel']['ECM_pose'])
    a=q.analyze(r,'PLUS_DELTA')
    assert a['mapping']['ECM_pose']['RIGHT_phase_delta']==0
    assert not a['legacy_phase_marker_mapping_confirmed']
    assert 'LEGACY_PHASE_MARKER_FILTERED_OR_INCOHERENT' in a['flags']
    assert a['generalized_target_and_native_mapping_qualified']


@pytest.mark.parametrize('channel',['left_q','right_center','chassis_velocity'])
def test_current_collateral_detected(channel):
    r=make_record('PLUS_DELTA')
    for row in r['phase_qualification']['packets'][3:]:
        if channel=='left_q':row['generalized_q']['left']+=1e-7
        elif channel=='right_center':row['links']['right_wheel']['engine_derived_collision_pose']['position_world_m'][2]+=29e-9
        else:row['links']['body']['engine_derived_linear_velocity'][0]=1e-6
    assert q.analyze(r,'PLUS_DELTA')['classification']=='PHASE_RESET_COLLATERAL_DETECTED'


def test_target_error_not_attained():
    r=make_record('PLUS_DELTA')
    for row in r['phase_qualification']['packets'][3:]:row['generalized_q']['right']-=1e-8
    a=q.analyze(r,'PLUS_DELTA')
    assert a['classification']=='PHASE_RESET_TARGET_NOT_ATTAINED'
    assert a['absolute_target_error_rad']==pytest.approx(1e-8,abs=1e-15)


def test_no_tick_fallback_for_advancement():
    r=make_record('PLUS_DELTA');r['phase_qualification']['POST_marker']={'iteration':3601,'sim_time_ns':3601000000,'paused':True,'stats_source':'transport_snapshot',
        'observed_snapshot':{'iterations_normalized':3601,'paused':True,'sim_time':{'sec':3,'nsec':601000000}}}
    assert q.analyze(r,'PLUS_DELTA')['classification']=='PHASE_RESET_REQUIRES_ADVANCEMENT'


@pytest.mark.parametrize('operation',['TWIST','WorldControl','poseRPC'])
def test_treatment_audit_rejects_forbidden_operations(operation):
    r=make_record('SHAM');r['command_audit'][3]={'kind':'TWIST'} if operation=='TWIST' else {'kind':'RPC','request_type':operation,'service':'/world/x/set_pose' if operation=='poseRPC' else '/world/x/control'}
    with pytest.raises(q.g.InvalidCapture):q.analyze(r,'SHAM')


def test_production_sensor_cursor_must_not_move():
    r=make_record('SHAM');r['phase_qualification']['host_POST']['cursor']+=1
    with pytest.raises(q.g.InvalidCapture,match='cursor'):q.analyze(r,'SHAM')


def test_precision_failure_and_stale_read_are_not_isolation_pass():
    assert q.measurement([1.,1.],[1.,1.],1e-18)['status']=='MEASUREMENT_RESOLUTION_INSUFFICIENT'
    assert q.measurement([1.,1.],[1.,1.],1e-8,fresh=False)['status']=='UNVERIFIABLE_WITH_ZERO_ADVANCEMENT'
    assert q.measurement([0.,0.],[0.,0.],1e-11)['status']=='VERIFIED_WITHIN_NUMERICAL_CAP'


def test_source_no_forbidden_paths_and_REAL_ResetPosition():
    assert q.static_contract()['runtime_target_attainment']=='HOST_REQUIRED'
    text=q.SOURCE.read_text()
    assert text.count('.ResetPosition(ecm,{target})')==1
    assert 'std::memcmp' in text and 'target!=qPre' in text
    assert 'if(code!=0)mutationAccepted=true' in text and 'if(!info.paused)' in text
    assert 'WorldPoseCmd_active' in text  # const observation only
    assert 'CreateComponent(e,gz::sim::components::WorldPose())' in text
    assert 'WorldPose(' not in text.split('// Sole physical-state mutation.')[1].split('public: void PostUpdate')[0]


def test_provenance_and_decoration():
    packet=q.decorate_packet(make_record('SHAM')['phase_qualification']['packets'][0])
    assert packet['supports']['right_wheel']['provenance']=='LAST_ADVANCING_STEP_STATE'
    assert packet['supports']['right_wheel']['Fn_N']==0
    assert 'CACHED_OR_STALE_POSSIBLE' in q.LABELS.values()
    assert 'engine_derived_collision_pose_derived_phase' in packet
    assert packet['tangential_relative_velocity']['value'] is None


def test_protocol_frozen_three_fresh_cases_no_causal_outcomes():
    p=q.protocol()
    assert [s['arm'] for s in p['arms']]==list(q.ARMS)
    assert p['no_replacements'] and p['intervention_iteration_delta']==0 and p['intervention_sim_time_delta_ns']==0
    assert 'before fresh Action24 UP' in p['context']
    source=inspect.getsource(q)
    assert 'classify_candidate(' not in source and 'analyze_case(' not in source
    assert 'step_simulation(' not in source and '._refresh(' not in source


def prepare_fake_run(tmp_path,monkeypatch):
    output=tmp_path/'block';output.mkdir();lib=tmp_path/'plugin.so';lib.write_text('static fixture')
    q.write(output/'protocol.json',q.protocol());q.write(output/'qualification_preflight.json',{
        'status':'PREFLIGHT_PASS','runner_sha256':q.g.sha(q.__file__),'protocol_sha256':q.g.sha(output/'protocol.json'),
        'guard_manifest':{},'library':str(lib),'qualification_build':{'library_sha256':q.g.sha(lib)}})
    monkeypatch.setattr(q,'safety',lambda _:None)
    monkeypatch.setattr(q.g.history,'source',lambda _: (None,43,None))
    monkeypatch.setattr(q.g.ab,'_build_all',lambda _: ({},{}))
    monkeypatch.setattr(q.g,'verify_static_builds',lambda _:None)
    return output


@pytest.mark.parametrize('shutdown',[True,False])
def test_invalid_arms_retained_no_rerun_shutdown_fence(tmp_path,monkeypatch,shutdown):
    output=prepare_fake_run(tmp_path,monkeypatch);calls=[]
    def fail(arm,scenario,directory,*args):
        calls.append(arm);q.write(directory/'process_lifecycle.json',{'shutdown_proven':shutdown})
        raise q.g.InvalidCapture('fixture capture unavailable')
    monkeypatch.setattr(q,'capture',fail)
    report=q.run(output)
    assert calls==list(q.ARMS)[:3 if shutdown else 1]
    assert len(report['original_slots'])==3
    assert all(r['classification']=='CAPTURE_INVALID' for r in report['results'])
    assert report['status']=='CAPTURE_FAILED'
    if not shutdown:assert report['original_slots'][1]['state']=='SCHEDULED'
    with pytest.raises(FileExistsError):q.run(output)


def test_mocked_fresh_process_orchestration_and_three_distinct_identities(tmp_path,monkeypatch):
    output=prepare_fake_run(tmp_path,monkeypatch);calls=[]
    def capture(arm,scenario,directory,*args):
        calls.append(arm);r=make_record(arm)
        life={'shutdown_proven':True,'fresh_single_server':True,'events':[
          {'event':'launch','wall_monotonic_s':2*len(calls),'status':{'pid':100+len(calls)}},
          {'event':'close','wall_monotonic_s':2*len(calls)+1}]}
        q.write(directory/'process_lifecycle.json',life)
        r.update(shutdown_completed=True,runtime_identity={'partition':arm,'topic':arm})
        return r
    monkeypatch.setattr(q,'capture',capture)
    report=q.run(output)
    assert calls==list(q.ARMS) and report['status']=='QUALIFICATION_CAPTURE_COMPLETE'
    assert len({s['runtime_identity']['partition'] for s in report['original_slots']})==3
    assert not report['causal_runtime_ready']


def test_production_and_preserved_evidence_paths_unchanged():
    assert q.g.EXPECTED_SHA=='92def637ff4da2be1348502d345a30721cc845c34704f0b125d4ff1a26fdcc55'
    p=next((q.d.DEFAULT_OUTPUT/'TICK_0_R1/world').glob('*/world.sdf'))
    assert q.g.sha(p)==q.g.EXPECTED_SHA
    with pytest.raises(FileExistsError):q.ensure_output(q.d.DEFAULT_OUTPUT)


def test_hook_stops_before_UP_and_never_calls_step_or_sensor(monkeypatch):
    r=make_record('PLUS_DELTA');rows=iter(r['phase_qualification']['packets']);evidence={};audit={'phase':'prior','events':[]}
    transport=offline_transport()
    adapter=SimpleNamespace(env=SimpleNamespace(transport=transport,timeout=1.))
    monkeypatch.setattr(q.g.y,'stopped_chunk',lambda _:None)
    monkeypatch.setattr(q.g.y,'completed_brake_checkpoint',lambda *a:{'active_physics_transactions':0})
    monkeypatch.setattr(q.g.dm,'physics_mark',lambda _:r['phase_qualification']['PRE_marker'])
    monkeypatch.setattr(q,'fresh_paused_stats',lambda _:r['phase_qualification']['POST_marker'])
    monkeypatch.setattr(q,'boundary_state',lambda _:{'sensor_cursor':10,'logical_command':'DOWN/braked'})
    def read(*args):
        row=next(rows);audit['events'].append({'kind':'RPC','request_type':'Int32'})
        return row,row['request_id']
    monkeypatch.setattr(q,'read_packet',read)
    hook=q.qualification_hook('PLUS_DELTA',evidence,None)
    with pytest.raises(q.g.InvalidCapture,match=q.STOP):hook(adapter,'PLUS_DELTA',SimpleNamespace(topic='/native'),{}, {},audit)
    assert evidence['qualification_completed'] and evidence['window_end']==7
    assert audit['phase']=='qualification_finished_no_acquisition'
    assert evidence['host_PRE']==evidence['host_POST']


def test_unchanged_production_executor_honors_abort_before_acquisition():
    import importlib.util
    spec=importlib.util.spec_from_file_location('linear_fixture',Path(__file__).with_name('test_gazebo_linear_reversal_executor.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    executor,adapter,physics=module._executor()
    def callback(row):
        if row['body_stopped_contract']['pass']:raise q.g.InvalidCapture(q.STOP)
        return {}
    result=executor.execute_plan(executor.plan(module._request()),on_braking_chunk=callback)
    assert result.status is module.ControlExecutionStatus.INFRASTRUCTURE_FAILURE
    assert q.STOP in result.reason and adapter.actions==[] and not physics.acquisition


def test_new_stats_publication_without_control_or_step():
    calls=[]
    raw={'iterations_normalized':3600,'sim_time':{'sec':3,'nsec':600000000},'paused':True}
    transport=SimpleNamespace(cursor=lambda _:7,messages_after=lambda *a,**k: calls.append(a) or [(8,raw)])
    adapter=SimpleNamespace(env=SimpleNamespace(transport=transport,timeout=1.,stepper=SimpleNamespace(topic='/stats')))
    marker=q.fresh_paused_stats(adapter)
    assert marker['observed_snapshot']==raw and marker['stats_receive_sequence']==8
    assert calls[0]==('/stats',7)


def test_expected_reset_request_and_callback_provenance_are_required():
    r=make_record('PLUS_DELTA');r['phase_qualification']['packets'][3]['requested_delta']=0.
    with pytest.raises(q.g.InvalidCapture,match='requested delta'):q.analyze(r,'PLUS_DELTA')
    r=make_record('PLUS_DELTA');r['phase_qualification']['packets'][3]['apply_callback']=0
    with pytest.raises(q.g.InvalidCapture,match='callback provenance'):q.analyze(r,'PLUS_DELTA')


def test_explicit_prohibited_cursors_distinguish_qualification_RPC_from_pose_or_Twist():
    audit={'events':[{'kind':'TWIST','published':True},{'kind':'RPC','service':'/world/w/set_pose'},
        {'kind':'RPC','service':'/native/phase_qualification/request'}]}
    assert q.prohibited_cursors(audit)=={'Twist_publication_cursor':1,'pose_RPC_cursor':1}
    audit['events'].append({'kind':'RPC','service':'/native/phase_qualification/request'})
    assert q.prohibited_cursors(audit)=={'Twist_publication_cursor':1,'pose_RPC_cursor':1}


@pytest.mark.parametrize('arm,base',[('PLUS_DELTA',math.pi-1e-8),('MINUS_DELTA',-math.pi+1e-8)])
def test_actual_phase_wrap_crossing_does_not_create_spurious_collateral(arm,base):
    r=make_record(arm,base)
    result=q.analyze(r,arm)
    assert result['classification']=='PHASE_RESET_COLLATERAL_UNVERIFIABLE'
    assert result['target_attained'] and result['legacy_phase_marker_mapping_confirmed']
    assert abs(result['mapping']['ECM_pose']['RIGHT_phase_delta']-q.target(0.,arm))<1e-14


def test_unavailable_contact_component_is_not_reported_as_zero_force():
    packet=make_record('SHAM')['phase_qualification']['packets'][0]
    packet['supports']['right_wheel'].update(component_available=False,state='UNAVAILABLE')
    decorated=q.decorate_packet(packet)
    assert decorated['supports']['right_wheel']['Fn_N'] is None
    assert decorated['supports']['right_wheel']['provenance']=='LAST_ADVANCING_STEP_STATE'


class OfflineNode:
    """In-memory protobuf endpoint; never constructs gz.transport.Node."""
    def __init__(self):self.subscriptions={};self.topic_schema='gz.msgs.StringMsg'
    def subscribe(self,cls,topic,callback):
        self.subscriptions[topic]=(cls,callback);return True
    def topic_info(self,topic):return [SimpleNamespace(msg_type_name=self.topic_schema)],[]
    def service_info(self,service):return [SimpleNamespace(req_type_name='gz.msgs.Int32',rep_type_name='gz.msgs.Boolean')]
    def unsubscribe(self,topic):self.subscriptions.pop(topic,None)
    def emit(self,topic,packet):
        cls,callback=self.subscriptions[topic];msg=cls();msg.data=json.dumps(packet);callback(msg)


def offline_transport():
    import threading
    from google.protobuf import json_format,text_format
    from aero_ai_studio.gazebo.transport import HarmonicTransport
    t=object.__new__(HarmonicTransport)
    t.node=OfflineNode();t.json=json_format;t.text=text_format;t.timeout=1.;t.executable='/OFFLINE_ONLY/gz'
    t.partition='OFFLINE_PROTOBUF_FIXTURE';t.condition=threading.Condition();t.request_history=[]
    t.callbacks=[];t.topics=set();t.closed=False;t.samples={};t.received_at={};t.history={};t.sequences={};t.sequenced_history={}
    return t


@pytest.mark.parametrize('name',['StringMsg','Int32'])
def test_exact_Host1_real_production_resolver_failure(name):
    t=offline_transport()
    with pytest.raises(KeyError) as error:t.message(name)
    assert str(error.value)==repr(name)
    assert not t.node.subscriptions and not t.request_history


def test_exact_Host1_subscription_fails_before_native_registration():
    t=offline_transport()
    with pytest.raises(KeyError,match='StringMsg'):t.subscribe('/phase_qualification','StringMsg')
    assert not t.node.subscriptions and not t.topics and not t.request_history


def test_diagnostic_codec_instance_only_and_restored_on_exception():
    from aero_ai_studio.gazebo.transport import HarmonicTransport
    original=HarmonicTransport.TYPES;before=dict(original);t=offline_transport()
    with pytest.raises(RuntimeError):
        with q.diagnostic_codec(t) as descriptors:
            assert descriptors=={'StringMsg':'gz.msgs.StringMsg','Int32':'gz.msgs.Int32'}
            assert HarmonicTransport.TYPES is original and original==before
            assert t.message('WorldControl').DESCRIPTOR.full_name=='gz.msgs.WorldControl'
            raise RuntimeError('injected qualification failure')
    assert 'TYPES' not in vars(t) and HarmonicTransport.TYPES==before
    with pytest.raises(KeyError):t.message('StringMsg')


def test_diagnostic_codec_preserves_existing_instance_registry():
    t=offline_transport();t.TYPES=dict(t.TYPES);original=t.TYPES
    with q.diagnostic_codec(t):assert t.TYPES is not original
    assert t.TYPES is original


@pytest.mark.parametrize('arm',q.ARMS)
def test_repaired_hook_real_message_resolver_subscribe_RPC_encode_and_readback(arm,monkeypatch):
    """Real production methods/protobufs, fake Node and CLI. Not a runtime proof."""
    import aero_ai_studio.gazebo.transport as transport_module
    r=make_record(arm);rows=iter(r['phase_qualification']['packets']);t=offline_transport()
    adapter=SimpleNamespace(env=SimpleNamespace(transport=t,timeout=1.));evidence={};audit={'events':[]};commands=[]
    monkeypatch.setattr(q.g.y,'stopped_chunk',lambda _:None)
    monkeypatch.setattr(q.g.y,'completed_brake_checkpoint',lambda *a:{'active_physics_transactions':0})
    monkeypatch.setattr(q.g.dm,'physics_mark',lambda _:r['phase_qualification']['PRE_marker'])
    monkeypatch.setattr(q,'fresh_paused_stats',lambda _:r['phase_qualification']['POST_marker'])
    monkeypatch.setattr(q,'boundary_state',lambda _:{'sensor_cursor':10,'logical_command':'braked'})
    def fake_cli(command,**kwargs):
        commands.append(command)
        assert command[command.index('--reqtype')+1]=='gz.msgs.Int32'
        assert command[command.index('--reptype')+1]=='gz.msgs.Boolean'
        row=next(rows);message=t.message('Int32')();t.text.Parse(command[command.index('--req')+1],message)
        assert message.data==row['operation_code']
        audit['events'].append({'kind':'RPC','request_type':'Int32','service':'/native/phase_qualification/request'})
        t.node.emit('/native/phase_qualification',row)
        return SimpleNamespace(returncode=0,stdout='data: true\n',stderr='')
    monkeypatch.setattr(transport_module.subprocess,'run',fake_cli)
    with pytest.raises(q.g.InvalidCapture,match=q.STOP):
        q.qualification_hook(arm,evidence,None)(adapter,arm,SimpleNamespace(topic='/native'),{}, {},audit)
    assert len(commands)==7 and len(evidence['packets'])==7
    assert evidence['qualification_completed'] and evidence['current_stage']=='QUALIFICATION_CAPTURE_COMPLETE'
    assert evidence['publisher_readiness']['message_type']=='gz.msgs.StringMsg'
    assert evidence['service_readiness']['request_type']=='gz.msgs.Int32'
    assert 'TYPES' not in vars(t) and 'StringMsg' not in transport_module.HarmonicTransport.TYPES
    assert audit['phase']=='qualification_finished_no_acquisition'
    assert all(cmd[cmd.index('-s')+1]=='/native/phase_qualification/request' for cmd in commands)
    t.close();assert t.closed and not t.node.subscriptions


def test_subscription_readiness_failure_retains_root_cause_before_any_request(monkeypatch):
    t=offline_transport();t.node.topic_schema='gz.msgs.WrongType';evidence={};audit={'events':[]}
    adapter=SimpleNamespace(env=SimpleNamespace(transport=t,timeout=1.));marker=make_record('SHAM')['phase_qualification']['PRE_marker']
    monkeypatch.setattr(q.g.y,'stopped_chunk',lambda _:None)
    monkeypatch.setattr(q.g.y,'completed_brake_checkpoint',lambda *a:{'active_physics_transactions':0})
    monkeypatch.setattr(q.g.dm,'physics_mark',lambda _:marker)
    monkeypatch.setattr(q,'boundary_state',lambda _:{'cursor':1})
    with pytest.raises(RuntimeError,match='schema mismatch'):
        q.qualification_hook('SHAM',evidence,None)(adapter,'SHAM',SimpleNamespace(topic='/native'),{}, {},audit)
    assert evidence['failed_stage']=='QUALIFICATION_PUBLISHER_DISCOVERY'
    assert evidence['qualification_error']['type']=='RuntimeError'
    assert evidence['packets']==[] and not t.request_history
    assert audit['phase']=='qualification_finished_no_acquisition' and 'TYPES' not in vars(t)


def test_legacy_generic_incomplete_guard_reproduced_and_new_error_preserves_cause():
    import types
    snapshot=q.FORENSICS/'runner_before_repair.py'
    legacy=types.ModuleType('ANL_legacy_runner_snapshot');legacy.__file__=str(snapshot)
    exec(compile(snapshot.read_text(),str(snapshot),'exec'),legacy.__dict__)
    r={'phase_qualification':{}}
    with pytest.raises(q.g.InvalidCapture,match='^qualification incomplete; no physical interpretation$'):legacy.analyze(r,'SHAM')
    r['phase_qualification'].update(qualification_error={'type':'KeyError','message':"'StringMsg'"},failed_stage='QUALIFICATION_SUBSCRIPTION')
    with pytest.raises(q.g.InvalidCapture,match="stage=QUALIFICATION_SUBSCRIPTION; KeyError: 'StringMsg'"):q.analyze(r,'SHAM')


def test_real_codec_preflight_and_Host1_immutable_Host2_fresh_protocol():
    assert q.codec_self_check()['legacy_errors_reproduced']=={'StringMsg':"'StringMsg'",'Int32':"'Int32'"}
    assert q.DEFAULT_OUTPUT.name.endswith('host2') and q.DEFAULT_OUTPUT!=q.HOST1
    assert json.loads((q.HOST1/'protocol.json').read_text())==q.protocol()
    with pytest.raises(FileExistsError):q.ensure_output(q.HOST1)
    with pytest.raises(FileExistsError):q.write(q.HOST1/'never_write.json',{})
    inventory=json.loads((q.FORENSICS/'inventory.json').read_text())
    q.g.history.verify_manifest({x['path']:x['sha256'] for x in inventory})
    findings=json.loads((q.FORENSICS/'findings.json').read_text())
    assert findings['primary_classification']=='QUALIFICATION_CAPTURE_INFRASTRUCTURE_FAILURE'
    assert all(not a['reset_request_sent'] and a['PRE_RIGHT_q'] is None for a in findings['per_arm'])


def test_Host1_latent_Int32_failure_after_StringMsg_only_fix(monkeypatch):
    import aero_ai_studio.gazebo.transport as production_transport
    t=offline_transport();t.TYPES={**t.TYPES,'StringMsg':'stringmsg'}
    t.subscribe('/native/phase_qualification','StringMsg')
    monkeypatch.setattr(production_transport.subprocess,'run',lambda *a,**k:pytest.fail('CLI must not run'))
    with pytest.raises(KeyError,match='Int32'):
        t.request('/native/phase_qualification/request','Int32','Boolean',{'data':0},max_attempts=1)
    assert not t.request_history


def test_codec_failure_blocks_Host_before_any_arm_launch(tmp_path,monkeypatch):
    output=prepare_fake_run(tmp_path,monkeypatch)
    def codec_failure():raise ValueError('diagnostic codec unavailable')
    monkeypatch.setattr(q,'codec_self_check',codec_failure)
    monkeypatch.setattr(q,'capture',lambda *a:pytest.fail('must not launch'))
    with pytest.raises(ValueError,match='codec unavailable'):q.run(output)
    assert not (output/'qualification_ledger.json').exists()
