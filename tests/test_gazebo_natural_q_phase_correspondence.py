"""AN-N offline contracts. Synthetic packets test logic, never establish runtime facts."""
import copy
import inspect
import json
import math
from pathlib import Path
import pytest
from tools import diagnose_v07_gazebo_natural_q_phase_correspondence as n
from test_gazebo_phase_isolation_qualification import make_record


@pytest.fixture(autouse=True)
def no_server(monkeypatch):
    from aero_ai_studio.gazebo.process_manager import GazeboProcessManager
    def refuse(*a,**k):raise AssertionError('offline tests prohibit Gazebo')
    monkeypatch.setattr(GazeboProcessManager,'launch',refuse)
    monkeypatch.setattr(n.g.ab,'_run_case',refuse)


def fixture(spec,legacy=True):
    r=make_record('SHAM');e=r['phase_qualification'];e['spec']=spec
    e['before_optional_tick_stats']=copy.deepcopy(e['PRE_marker'])
    e['pause_synchronization']={'marker':copy.deepcopy(e['POST_marker'])}
    e['host_PRE']=e['host_POST']={'logical':{'env_previous_action':'down','adapter_previous_action':'down','publish_sequence':42,'controller_command':{'linear':{'x':0.},'angular':{'z':0.}}},
      'production_sensor':{'sequence':36,'previous_timestamp':3.6,'cached_observation_identity':123},'production_step_tracker':{'active_depth':0}}
    for i,p in enumerate(e['packets']):
        p['operation_code']=[0,0,0,1,0,0,0][i];p['WorldPoseCmd_active_PRE']=0
        p['event']='armed_readback' if i==3 else 'readback'
        for key in ('ResetPosition_invoked','requested_delta','requested_target','q_actual_pre','left_actual_pre','target_numerically_differs','target_bitwise_differs'):p.pop(key,None)
        post=i>=4;delta=n.DELTA if post and spec['iterations'] else 0.
        p['generalized_q']['right']+=delta
        if delta:
            pose=p['links']['right_wheel']['engine_derived_collision_pose']
            pose['orientation_world_xyzw']=n.g.dm.qmul([0.,math.sin((.75+delta)/2),0.,math.cos((.75+delta)/2)],[math.sqrt(.5),0.,0.,math.sqrt(.5)])
            pose['position_world_m'][2]+=n.HEIGHT_REFERENCE_M
            if legacy:p['links']['right_wheel']['ECM_pose']=copy.deepcopy(pose)
        if post:
            p['iteration']+=spec['iterations'];p['sim_time_ns']+=spec['sim_time_delta_ns'];p['advancing_callback_count']+=spec['iterations']
        n.decorate(p)
    e['advancing_observations']=[]
    if spec['iterations']:
        p=copy.deepcopy(e['packets'][4]);p.update(paused=False,event='advancing_observation',request_id=0,operation_code=2)
        e['advancing_observations']=[n.decorate(p)]
        marker=e['POST_marker'];marker['iteration']+=1;marker['sim_time_ns']+=1_000_000
        marker['observed_snapshot']['iterations_normalized']+=1;marker['observed_snapshot']['sim_time']['nsec']+=1_000_000
    e['pause_synchronization']['marker']=copy.deepcopy(e['POST_marker'])
    def rpc(kind,payload):return {'kind':'RPC','request_type':kind,'service':'/test/natural_q_phase/request' if kind=='Int32' else '/world/test/control',
      'payload':payload,'response':{'data':True},'transport_evidence':{'attempts':[{'attempt':1}]}}
    r['command_audit']=[rpc('Int32',{'data':c}) for c in (0,0,0,1)]
    if spec['iterations']:r['command_audit'].append(rpc('WorldControl',{'pause':True,'multi_step':1}))
    r['command_audit'].append(rpc('WorldControl',{'pause':True}))
    r['command_audit'] +=[rpc('Int32',{'data':0}) for _ in range(3)];e['window_end']=len(r['command_audit'])
    return r


def result(spec,legacy=True):return n.analyze(fixture(spec,legacy),spec)


def test_frozen_balanced_schedule():
    s=n.schedule();assert len(s)==10 and len({x['case_id'] for x in s})==10
    assert [x['ordinal'] for x in s]==list(range(1,11))
    assert [x['arm'] for x in s]==[n.ZERO,n.ONE,n.ONE,n.ZERO,n.ZERO,n.ONE,n.ONE,n.ZERO,n.ZERO,n.ONE]
    assert sum(x['arm']==n.ZERO for x in s)==sum(x['arm']==n.ONE for x in s)==5
    assert n.DELTA==-4.868844349914525e-8


@pytest.mark.parametrize('spec',n.schedule(),ids=lambda s:s['case_id'])
def test_exact_dose_analysis_and_three_representations(spec):
    a=result(spec)
    assert a['capture_valid'] and a['delta_iterations']==spec['iterations']
    assert a['delta_sim_time_ns']==spec['sim_time_delta_ns']
    assert a['command_audit']['advancing_requests']==spec['iterations']
    assert a['classification']==('NATURAL_Q_PHASE_CORRESPONDENCE_CONFIRMED' if spec['iterations'] else 'ZERO_CONTROL_UNCHANGED_OBSERVED')
    assert len(a['S0'])==len(a['S1'])==3
    assert set(a['S0'][0]['representations'])=={'ACTUAL_GENERALIZED_Q','ENGINE_DERIVED_WHEEL_ORIENTATION','LEGACY_ECM_DERIVED_PHASE_MARKER'}
    assert a['causal_interpretation'].startswith('NONE')


def test_filtered_legacy_does_not_prevent_engine_only_observation():
    a=result(n.schedule()[1],legacy=False)
    assert a['classification']=='NATURAL_Q_ENGINE_PHASE_ONLY_CONFIRMED'
    assert a['flags']==['LEGACY_MARKER_FILTERED_OR_STALE']
    assert a['measurements']['ECM_pose.phase.right']['delta']==0.
    assert a['measurements']['engine_derived_collision_pose.phase.right']['delta']==pytest.approx(n.DELTA,abs=1e-15)


@pytest.mark.parametrize('field,value',[('iteration',3602),('sim_time_ns',3602000000)])
def test_wrong_tick_clock_invalid(field,value):
    s=n.schedule()[1];r=fixture(s);r['phase_qualification']['packets'][-1][field]=value
    with pytest.raises(n.g.InvalidCapture,match='callback clock'):n.analyze(r,s)


def test_callback_progress_not_physics_advance():
    s=n.schedule()[0];r=fixture(s)
    for i,p in enumerate(r['phase_qualification']['packets']):p['postupdate_count']=1000+i*7
    a=n.analyze(r,s);assert a['delta_iterations']==0 and a['paused_callback_progress']==42


@pytest.mark.parametrize('mutation',['twist','reset_rpc','pose_rpc','extra_tick','retry','sensor','pose_component','missing_solve'])
def test_contamination_or_missing_evidence_rejected(mutation):
    s=n.schedule()[1];r=fixture(s);e=r['phase_qualification']
    if mutation in ('twist','reset_rpc','pose_rpc'):
        r['command_audit'][0].update(kind='TWIST' if mutation=='twist' else 'RPC',request_type='Empty',service='/set_pose' if mutation=='pose_rpc' else '/reset_joint')
    elif mutation=='extra_tick':r['command_audit'][4]['payload']['multi_step']=2
    elif mutation=='retry':r['command_audit'][4]['transport_evidence']['attempts']*=2
    elif mutation=='sensor':e['host_POST']=copy.deepcopy(e['host_PRE']);e['host_POST']['production_sensor']['sequence']+=1
    elif mutation=='pose_component':e['packets'][-1]['WorldPoseCmd_active']=1
    elif mutation=='missing_solve':e['advancing_observations']=[]
    with pytest.raises(n.g.InvalidCapture):n.analyze(r,s)


def test_proven_axis_sign_wrap_and_height():
    a=result(n.schedule()[1]);m=a['measurements']
    assert m['actual_q.right']['delta']<0 and m['engine_derived_collision_pose.phase.right']['delta']<0
    assert m['engine_derived_collision_pose.Z.right']['delta']==pytest.approx(n.HEIGHT_REFERENCE_M,abs=1e-17)
    assert n.numeric_delta(math.pi-1e-9,-math.pi+1e-9,True)==pytest.approx(2e-9,abs=1e-15)
    assert m['engine_derived_collision_pose.aliases']['differential_delta']>0


def test_resolution_insufficient_never_match():
    a=n.resolved_match([1e12]*3,[1e12]*3,n.DELTA,1e-11)
    assert not a['resolution_sufficient'] and not a['matches']
    a=n.resolved_match([.75,.75+1e-9,.75],[.75]*3,0.,1e-12)
    assert not a['resolution_sufficient']


def test_contact_stamp_not_callback_fabricated():
    p=fixture(n.schedule()[1])['phase_qualification']['advancing_observations'][0]
    assert p['contact_freshness']['callback_is_advancing']
    assert all(v['status']=='LAST_ADVANCING_STEP_STATE_OR_FILTERED_COMPONENT' for v in p['contact_freshness']['supports'].values())
    p['supports']['right_wheel']['component_producer_stamp_ns']=p['sim_time_ns'];n.decorate(p)
    assert p['contact_freshness']['supports']['right_wheel']['status']=='TIME_MATCHED_ADVANCING_STEP_COMPONENT'
    assert p['tangential_relative_velocity']['value'] is None


def test_baseline_all_pairs_and_instability():
    rs=[result(s) for s in n.schedule()]
    b=n.baseline_equivalence(rs);assert b['status']=='OBSERVED_BASELINE_EQUIVALENT' and len(b['all_pairs'])==45
    rs[-1]['S0'][-1]['generalized_q']['right']+=1e-8
    b=n.baseline_equivalence(rs);assert b['status']=='BASELINE_STATE_UNSTABLE'
    assert n.schedule()[-1]['case_id'] in b['unstable_case_ids']
    assert n.aggregate(rs)['classification']=='BASELINE_STATE_UNSTABLE'


def test_invalid_retained_not_physical_failure_or_replaced():
    rs=[result(s) for s in n.schedule()]
    rs[1]={'case_id':n.schedule()[1]['case_id'],'arm':n.ONE,'capture_valid':False,'classification':'CAPTURE_INVALID'}
    a=n.aggregate(rs)
    assert len(a['results'])==10 and a['inventory'][n.ONE]=={'valid':4,'invalid':1}
    assert a['status']=='CAPTURE_FAILED' and not a['causal_runtime_ready']
    assert a['baseline_equivalence']['valid_cases_compared']==9


def test_aggregate_strong_correspondence_requires_replication():
    rs=[result(s) for s in n.schedule()]
    assert n.aggregate(rs)['classification']=='NATURAL_Q_PHASE_CORRESPONDENCE_CONFIRMED'
    rs=[result(s,False) for s in n.schedule()]
    assert n.aggregate(rs)['classification']=='NATURAL_Q_ENGINE_PHASE_ONLY_CONFIRMED'


@pytest.mark.parametrize('state',['SCHEDULED','STARTED','FINALIZED'])
def test_incremental_ledger(state):
    ledger={'slots':[{'spec':s,'state':'SCHEDULED'} for s in n.schedule()]}
    ledger['slots'][0]['state']=state
    if state=='FINALIZED':
        with pytest.raises(ValueError,match='incomplete finalized'):n.validate_ledger(ledger)
        ledger['slots'][0]['result']={'case_id':n.schedule()[0]['case_id'],'arm':n.ZERO,'capture_valid':False,'classification':'CAPTURE_INVALID','invalid_reason':'synthetic capture error','traceback':'offline fixture'}
    assert json.loads(json.dumps(n.validate_ledger(ledger)))==ledger


def test_no_setter_or_mutating_plugin_in_new_paths():
    assert n.static_contract()['read_only_source']
    source=n.SOURCE.read_text()
    assert '.Position(ecm)' in source and 'EnablePositionCheck(ecm)' in source
    assert 'ResetPosition' not in source and 'JointPositionReset' not in source
    assert 'PhaseIsolationQualification' not in source
    assert 'engine_derived_collision_pose' in source and 'ECM_pose' in source
    assert 'setprecision(17)' in source


def test_reuse_only_read_only_hook_and_restore():
    a,b=n.q.qualification_hook,n.q.instrument
    with n.read_only_capture_hooks():
        assert n.q.qualification_hook is n.natural_hook and n.q.instrument is n.instrument
    assert (n.q.qualification_hook,n.q.instrument)==(a,b)


def test_shutdown_freshness_and_no_rerun_contract():
    code=inspect.getsource(n.run)
    assert 'if not previous_shutdown:' in code and 'previous_close' in code
    assert "identity['partition'] in partitions" in code and "identity['topic'] in topics" in code
    assert 'directory.mkdir(parents=True)' in code
    assert 'cannot resume or overwrite' in code
    assert code.count('record=capture(')==1
    assert not n.protocol()['automatic_reruns']


def test_write_guard_preserves_previous_evidence():
    with pytest.raises(ValueError,match='outside new AN-N'):n.write(n.q.DEFAULT_OUTPUT/'forbidden.json',{})


def test_real_diagnostic_codec_without_node():
    checked=n.q.codec_self_check()
    assert checked
    assert n.q.DIAGNOSTIC_TYPES=={'StringMsg':'stringmsg','Int32':'int32'}


def test_preflight_runtime_facts_host_required_and_production_hash():
    p=n.protocol();assert p['runtime_facts'].startswith('HOST_REQUIRED')
    assert p['production_sha256']=='92def637ff4da2be1348502d345a30721cc845c34704f0b125d4ff1a26fdcc55'
    assert len(n.GATES)==17 and not p['causal_efficacy_testing']


@pytest.mark.parametrize('stop_after_unproven',[False,True])
def test_offline_orchestrator_retains_invalid_and_proves_shutdown_before_next(tmp_path,monkeypatch,stop_after_unproven):
    """Synthetic lifecycle records exercise control flow; not runtime isolation evidence."""
    monkeypatch.setattr(n,'DEFAULT_OUTPUT',tmp_path)
    library=tmp_path/'builds/observer.so';library.parent.mkdir();library.write_bytes(b'offline test only')
    n.write(tmp_path/'protocol.json',n.protocol())
    pf={'status':'PREFLIGHT_PASS','runner_sha256':n.g.sha(n.__file__),'protocol_sha256':n.g.sha(tmp_path/'protocol.json'),
        'guard_manifest':{},'library':str(library),'observer_build':{'library_sha256':n.g.sha(library)},
        'production_sha_before':n.g.EXPECTED_SHA,'production_sha_after':n.g.EXPECTED_SHA}
    n.write(tmp_path/'natural_preflight.json',pf)
    monkeypatch.setattr(n,'safety',lambda output:None)
    monkeypatch.setattr(n.q,'codec_self_check',lambda:True)
    monkeypatch.setattr(n.g.history,'source',lambda path:({},43,None))
    monkeypatch.setattr(n.g.ab,'_build_all',lambda path:({},{}))
    monkeypatch.setattr(n.g,'verify_static_builds',lambda builds:None)
    called=[]
    def fake_capture(case,scenario,directory,libraries,seed,namespace,library):
        spec=next(x for x in n.schedule() if x['case_id']==case);idx=len(called);called.append(case)
        if idx:
            prior=json.loads((tmp_path/called[idx-1]/'process_lifecycle.json').read_text())
            assert prior['shutdown_proven']
        shutdown=not(stop_after_unproven and idx==2)
        life={'shutdown_proven':shutdown,'fresh_single_server':True,'events':[
          {'event':'launch','wall_monotonic_s':idx*10.,'status':{'pid':1000+idx}},
          {'event':'close','wall_monotonic_s':idx*10.+5,'pid':1000+idx,'exit_code':0,'shutdown_proven':shutdown}]}
        n.write(directory/'process_lifecycle.json',life)
        r=fixture(spec);r.update(shutdown_completed=shutdown,runtime_identity={'partition':namespace,'topic':'/test/'+namespace})
        # Preserve an invalid original slot and continue only after proven shutdown.
        if idx==1:r['phase_qualification']['qualification_completed']=False
        return r
    monkeypatch.setattr(n,'capture',fake_capture)
    a=n.run(tmp_path)
    slots=a['original_slots'];assert len(slots)==10
    assert called==[s['case_id'] for s in n.schedule()[:len(called)]]
    assert slots[1]['result']['classification']=='CAPTURE_INVALID'
    if stop_after_unproven:
        assert len(called)==3 and all(s['state']=='SCHEDULED' for s in slots[3:])
    else:assert len(called)==10 and all(s['state']=='FINALIZED' for s in slots)
    assert not a['causal_runtime_ready']
    with pytest.raises(FileExistsError):n.run(tmp_path)


def test_zero_observation_detects_chassis_and_contact_evidence_changes():
    s=n.schedule()[0];r=fixture(s)
    for p in r['phase_qualification']['packets'][4:]:p['links']['body']['engine_derived_linear_velocity'][0]=1e-7
    a=n.analyze(r,s)
    assert a['classification']=='NATURAL_Q_PHASE_CORRESPONDENCE_NOT_REPRODUCED'
    assert not a['zero_observer_state_audit']['observed_unchanged']


def test_binary64_subtraction_no_decimal_rounding():
    x=1.0039999999756914;y=x+n.DELTA
    a=n.resolved_match([x]*3,[y]*3,n.DELTA,1e-11)
    assert a['delta']==y-x and a['delta']==n.DELTA
    assert a['error']==0. and a['matches']


def test_generalized_coordinate_is_not_orientation_alias():
    s=n.schedule()[1];r=fixture(s)
    for p in r['phase_qualification']['packets'][4:]:p['generalized_q']['right']=.75
    a=n.analyze(r,s)
    assert a['measurements']['actual_q.right']['delta']==0.
    assert a['measurements']['engine_derived_collision_pose.phase.right']['delta']<0.
    assert a['classification']=='NATURAL_Q_PHASE_CORRESPONDENCE_NOT_REPRODUCED'


def test_nonfinite_coordinate_invalid():
    r=fixture(n.schedule()[0]);r['phase_qualification']['packets'][0]['generalized_q']['right']=math.nan
    with pytest.raises(n.g.InvalidCapture,match='nonfinite'):n.analyze(r,n.schedule()[0])
