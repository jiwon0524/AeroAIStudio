"""AN-P offline source and synthetic packet contracts. Runtime localization remains HOST_REQUIRED."""
import copy
import inspect
import json
import math
from pathlib import Path
import pytest
from tools import diagnose_v07_gazebo_ecm_hierarchy_freshness as p
from test_gazebo_natural_q_phase_correspondence import fixture as natural_fixture


@pytest.fixture(autouse=True)
def no_runtime(monkeypatch):
    from aero_ai_studio.gazebo.process_manager import GazeboProcessManager
    def fail(*a,**k):raise AssertionError('offline tests prohibit Gazebo/Host')
    monkeypatch.setattr(GazeboProcessManager,'launch',fail)
    monkeypatch.setattr(p.g.ab,'_run_case',fail)
    monkeypatch.setattr(p.g,'run',fail)
    monkeypatch.setattr(p.legacy,'run',fail)


def component(value,frame='WORLD',flag=0):
    return {'present':value is not None,'value':copy.deepcopy(value),'component_change_state':flag,
      'component_change_label':'NoChange' if not flag else 'PeriodicChange','changed_since_previous_observation':None,
      'producer_timestamp_ns':None,'coordinate_frame':frame,'freshness':'ECM_VALUE_AT_CALLBACK'}


def compact(value):
    c=p.canonical_pose(value)
    return {'position_m':copy.deepcopy(c['position_world_m']),'orientation_xyzw':copy.deepcopy(c['orientation_world_xyzw'])}


def relative(parent,child):
    a=p.canonical_pose(parent);b=p.canonical_pose(child);inv=p.g.dm.qinverse(a['orientation_world_xyzw'])
    d=[y-x for x,y in zip(a['position_world_m'],b['position_world_m'])]
    v=p.g.dm.qmul(p.g.dm.qmul(inv,[*d,0.]),a['orientation_world_xyzw'])[:3]
    return {'position_m':v,'orientation_xyzw':p.g.dm.qmul(inv,b['orientation_world_xyzw'])}


def hierarchy(packet):
    ids={name:i+1 for i,name in enumerate(p.ENTITIES)};identity={'position_m':[0.,0.,0.],'orientation_xyzw':[0.,0.,0.,1.]}
    body=packet['links']['body']['ECM_pose'];h={}
    parents={'world':None,'model':'world','body':'model','left_wheel':'model','right_wheel':'model','front_caster':'model','rear_caster':'model',
      'body_collision':'body','left_collision':'left_wheel','right_collision':'right_wheel','front_collision':'front_caster','rear_collision':'rear_caster'}
    local={key:copy.deepcopy(identity) for key in ids};local['world']=None;local['model']=compact(body)
    for side in ['left','right']:local[side+'_wheel']=relative(body,packet['links'][side+'_wheel']['ECM_pose'])
    for key in ids:
        parent=parents[key];wp=None
        if key in ('body_collision','left_collision','right_collision'):
            link={'body_collision':'body','left_collision':'left_wheel','right_collision':'right_wheel'}[key]
            wp=compact(packet['links'][link]['engine_derived_collision_pose'])
        h[key]={'entity_id':ids[key],'resolved':True,'graph_parent_entity':ids[parent] if parent else 0,
          'Pose':component(local[key],'PARENT_ENTITY_FRAME'),'WorldPose':component(wp),
          'ParentEntity':component(ids[parent] if parent else None,'ENTITY_ID'),'reconstructed_world_pose':None,
          'reconstruction_provenance':'synthetic parent-local fixture'}
    def world(key):
        if key=='world':return p.canonical_pose(identity)
        parent=parents[key];return p.compose(world(parent),local[key])
    for key in ids:h[key]['reconstructed_world_pose']=world(key)
    return h


def fixture(spec):
    r=natural_fixture(spec);e=r['phase_qualification'];base=copy.deepcopy(e['packets'][0]);rot=[0.,math.sin(p.DELTA/2),0.,math.cos(p.DELTA/2)]
    for i,packet in enumerate(e['packets']):
        if spec['iterations'] and i>=4:
            packet['generalized_q']['right']=base['generalized_q']['right']
            packet['links']['body']['engine_derived_collision_pose']['orientation_world_xyzw']=rot
            for link in ('left_wheel','right_wheel'):
                old=base['links'][link]['engine_derived_collision_pose']['orientation_world_xyzw']
                packet['links'][link]['engine_derived_collision_pose']['orientation_world_xyzw']=p.g.dm.qmul(rot,old)
            packet['links']['right_wheel']['ECM_pose']=copy.deepcopy(packet['links']['right_wheel']['engine_derived_collision_pose'])
            packet['postupdate_count']+=1
        h=hierarchy(packet);packet['callback_trace']=[]
        start=i*3+1+(3 if spec['iterations'] and i>=4 else 0)
        for j,stage in enumerate(['PreUpdate','Update/observer_after_Physics_Update','PostUpdate/const_ECM']):
            packet['callback_trace'].append({'stage':stage,'callback_sequence':start+j,'iteration':packet['iteration'],'sim_time_ns':packet['sim_time_ns'],
              'paused':True,'actual_generalized_q':copy.deepcopy(packet['generalized_q']),'hierarchy':copy.deepcopy(h),
              'engine_reference':{link:{'pose':compact(packet['links'][link]['engine_derived_collision_pose'])} for link in ('body','left_wheel','right_wheel')}})
        p.decorate(packet)
    e['advancing_observations']=[]
    if spec['iterations']:
        a=copy.deepcopy(e['packets'][4]);a.update(event='advancing_observation',request_id=0,operation_code=2,paused=False,postupdate_count=14)
        for j,point in enumerate(a['callback_trace']):
            point['callback_sequence']=13+j;point['paused']=False
            if j==0:
                point['hierarchy']=copy.deepcopy(e['packets'][3]['hierarchy'])
                point['engine_reference']=copy.deepcopy(e['packets'][3]['callback_trace'][-1]['engine_reference'])
        p.decorate(a);e['advancing_observations']=[a]
    for event in r['command_audit']:
        if event['request_type']=='Int32':event['service']='/test/ecm_hierarchy_freshness/request'
    return r


def result(spec):return p.analyze(fixture(spec),spec)


def test_phase_and_frozen_schedule():
    assert p.protocol()['phase']=='AN-P' and len(p.GATES)==23
    s=p.schedule();assert len(s)==6 and [v['arm'] for v in s]==[p.ZERO,p.ONE,p.ONE,p.ZERO,p.ZERO,p.ONE]
    assert [v['ordinal'] for v in s]==list(range(1,7))
    assert len({v['case_id'] for v in s})==6 and sum(v['iterations'] for v in s)==3
    assert all(v['sim_time_delta_ns']==v['iterations']*1000000 for v in s)


@pytest.mark.parametrize('spec',p.schedule(),ids=lambda s:s['case_id'])
def test_full_read_only_capture_analysis(spec):
    a=result(spec)
    assert a['phase']=='AN-P' and a['capture_valid']
    assert a['delta_iterations']==spec['iterations'] and a['delta_sim_time_ns']==spec['sim_time_delta_ns']
    assert a['classification']==('ECM_MIXED_HIERARCHY_FRESHNESS_REPRODUCED' if spec['iterations'] else 'ZERO_TICK_FRESHNESS_CONTROL_UNCHANGED')
    assert a['actual_q_guard']['matches'] and a['RIGHT_Z_guard']['matches']
    assert a['measurements']['RIGHT_actual_q_zero_guard']['expected']==0.
    assert 'actual_q.right' not in a['measurements']
    assert a['component_localization']['all_callback_parent_local_reconstructions_match']
    assert len(a['callback_timeline'])==24 if spec['iterations'] else len(a['callback_timeline'])==21


def test_matrix_mixed_freshness_not_physical_phase():
    a=result(p.schedule()[1]);m=a['reconstruction_matrix']
    assert set(m)=={'A','B','C','D'}
    for name in ('A','D'):
        assert m[name]['delta']==pytest.approx(p.DELTA,abs=1e-15)
        assert not m[name]['S1']['same_simulation_state_observationally_consistent']
        assert 'not physical' in m[name]['S1']['interpretation']
    for name in ('B','C'):assert abs(m[name]['delta'])<1e-15
    assert a['component_localization']['first_observed_mixed_stage']['stage']=='Update/observer_after_Physics_Update'
    assert 'right_wheel.Pose' in a['component_localization']['local_components_changed']
    assert 'model.Pose' in a['component_localization']['local_components_held']


def test_quaternion_sign_and_parent_local_composition():
    value={'position_m':[1.,2.,3.],'orientation_xyzw':[0.,0.,0.,1.]}
    rotated={'position_m':[0.,0.,0.],'orientation_xyzw':[0.,0.,1.,0.]}
    out=p.compose(rotated,value);assert out['position_world_m']==[-1.,-2.,3.]
    neg={**value,'orientation_xyzw':[0.,0.,0.,-1.]};assert p.same_pose(value,neg)
    assert p.q.wrap(2*math.pi-1e-9)==pytest.approx(-1e-9,abs=1e-15)


@pytest.mark.parametrize('bad',['cycle','parent_graph','unresolved','duplicate_id','nonfinite'])
def test_malformed_hierarchy_invalid(bad):
    r=fixture(p.schedule()[1]);h=r['phase_qualification']['packets'][0]['callback_trace'][0]['hierarchy']
    if bad=='cycle':h['model']['ParentEntity']['value']=h['body']['entity_id'];h['model']['graph_parent_entity']=h['body']['entity_id']
    if bad=='parent_graph':h['body']['graph_parent_entity']=999
    if bad=='unresolved':h['right_wheel']['resolved']=False
    if bad=='duplicate_id':h['body']['entity_id']=h['world']['entity_id']
    if bad=='nonfinite':h['model']['Pose']['value']['position_m'][0]=math.nan
    with pytest.raises(p.g.InvalidCapture):p.analyze(r,p.schedule()[1])


def test_missing_optional_WorldPose_stays_absent():
    a=result(p.schedule()[1])
    assert not a['S0'][0]['hierarchy']['body']['WorldPose']['present']
    assert a['S0'][0]['hierarchy']['body']['WorldPose']['value'] is None
    assert a['hierarchy_S0_reconstruction']['all_reconstructed_match']


def test_missing_local_component_is_partial_not_fabricated():
    r=fixture(p.schedule()[1])
    for packet in r['phase_qualification']['packets']+r['phase_qualification']['advancing_observations']:
        for point in packet['callback_trace']:point['hierarchy']['model']['Pose']=component(None,'PARENT_ENTITY_FRAME')
        p.decorate(packet)
    a=p.analyze(r,p.schedule()[1]);assert a['classification']=='ECM_HIERARCHY_FRESHNESS_PARTIALLY_LOCALIZED'
    assert not a['component_localization']['all_callback_parent_local_reconstructions_match']


@pytest.mark.parametrize('bad',['clock','missing_stage','pose_command','extra_request','retry','sensor','up'])
def test_contamination_and_capture_failure_separated(bad):
    s=p.schedule()[1];r=fixture(s);e=r['phase_qualification']
    if bad=='clock':e['packets'][-1]['sim_time_ns']+=1000000
    elif bad=='missing_stage':e['packets'][0]['callback_trace'].pop(1)
    elif bad=='pose_command':e['packets'][-1]['WorldPoseCmd_active']=1
    elif bad=='extra_request':r['command_audit'][4]['payload']['multi_step']=2
    elif bad=='retry':r['command_audit'][4]['transport_evidence']['attempts']*=2
    elif bad=='sensor':e['host_POST']=copy.deepcopy(e['host_PRE']);e['host_POST']['production_sensor']['sequence']+=1
    elif bad=='up':r['command_audit'][0].update(kind='TWIST',payload={'linear':{'x':.5}})
    with pytest.raises(p.g.InvalidCapture):p.analyze(r,s)


def test_resolution_insufficient_cannot_close_marker():
    r=fixture(p.schedule()[1])
    for x in r['phase_qualification']['packets']+r['phase_qualification']['advancing_observations']:
        x['generalized_q']['right']=1e12
        for point in x['callback_trace']:point['actual_generalized_q']['right']=1e12
    a=p.analyze(r,p.schedule()[1]);assert not a['actual_q_guard']['matches']
    assert a['classification']=='ECM_HIERARCHY_FRESHNESS_NOT_REPRODUCED'


def test_aggregate_closure_six_valid_and_15_baseline_pairs():
    rs=[result(s) for s in p.schedule()];a=p.aggregate(rs)
    assert a['classification']=='ECM_MARKER_ARTIFACT_CLOSED' and a['status']=='QUALIFICATION_CAPTURE_COMPLETE'
    assert len(a['baseline_equivalence']['all_pairs'])==15
    assert len(a['baseline_equivalence']['hierarchy_baseline_pairs'])==15
    assert not a['causal_runtime_ready'] and not a['Action24_outcomes_tested'] and not a['next_physical_experiment_implemented']


def test_invalid_retention_prevents_closure():
    rs=[result(s) for s in p.schedule()];rs[1]={'case_id':p.schedule()[1]['case_id'],'arm':p.ONE,'capture_valid':False,'classification':'CAPTURE_INVALID'}
    a=p.aggregate(rs);assert len(a['results'])==6 and a['inventory'][p.ONE]=={'valid':2,'invalid':1}
    assert a['status']=='CAPTURE_FAILED' and a['classification']!='ECM_MARKER_ARTIFACT_CLOSED'


def test_baseline_instability_not_hidden():
    rs=[result(s) for s in p.schedule()];rs[-1]['S0'][-1]['generalized_q']['right']+=1e-7
    assert p.aggregate(rs)['classification']=='BASELINE_UNSTABLE'


def test_source_paths_read_only_current_phase():
    c=p.static_contract();assert c['phase']=='AN-P' and c['no_predecessor_runner_entrypoint']
    source=p.SOURCE.read_text()
    for token in ['ResetPosition','JointPositionReset','SetChanged(','SetParentEntity(','msgs::Twist','SetForce(']:assert token not in source
    assert 'ComponentState(e,type)' in source and 'ParentEntity' in source
    assert all(x in source for x in ['PreUpdate','PostUpdate','ISystemUpdate','setprecision(17)'])
    assert 'producer_timestamp_ns' in source and 'change flag is not a producer timestamp' in source
    assert 'orientation_xyzw' in source and 'PARENT_ENTITY_FRAME' in source
    assert 'NO_AN_G_RERUN_PATH' in p.GATES


def test_provenance_and_contact_scope():
    a=result(p.schedule()[1]);assert 'no physical branch or causal contact analysis' in a['limited_contact_scope']
    assert a['S1'][0]['contact_freshness']['supports']['right_wheel']['status']=='LAST_ADVANCING_STEP_STATE_OR_FILTERED_COMPONENT'
    for point in a['callback_timeline']:
        assert point['hierarchy']['body']['Pose']['producer_timestamp_ns'] is None


def test_hooks_replace_and_restore_only_capture_library():
    a,b=p.q.qualification_hook,p.q.instrument
    with p.read_only_capture_hooks():assert p.q.qualification_hook is p.hierarchy_hook and p.q.instrument is p.instrument
    assert (p.q.qualification_hook,p.q.instrument)==(a,b)


def test_prior_evidence_write_guard():
    for root in [p.legacy.DEFAULT_OUTPUT,p.q.DEFAULT_OUTPUT,p.g.DEFAULT_OUTPUT]:
        with pytest.raises(ValueError):p.write(root/'forbidden.json',{})


@pytest.mark.parametrize('state',['SCHEDULED','STARTED','FINALIZED'])
def test_incremental_ledger(state):
    ledger={'slots':[{'spec':s,'state':'SCHEDULED'} for s in p.schedule()]};ledger['slots'][0]['state']=state
    if state=='FINALIZED':
        with pytest.raises(ValueError):p.validate_ledger(ledger)
        ledger['slots'][0]['result']={'case_id':p.schedule()[0]['case_id'],'arm':p.ZERO,'capture_valid':False,'classification':'CAPTURE_INVALID','invalid_reason':'offline fixture','traceback':'fixture'}
    assert json.loads(json.dumps(p.validate_ledger(ledger)))==ledger


def test_real_diagnostic_codec_offline():assert p.q.codec_self_check()


def test_production_SHA_exact():
    assert p.protocol()['production_sha256']=='92def637ff4da2be1348502d345a30721cc845c34704f0b125d4ff1a26fdcc55'


@pytest.mark.parametrize('field',['q','engine','legacy'])
def test_same_callback_channels_must_be_coherent(field):
    r=fixture(p.schedule()[1]);packet=r['phase_qualification']['packets'][4];point=packet['callback_trace'][-1]
    if field=='q':point['actual_generalized_q']['right']+=1e-6
    elif field=='engine':point['engine_reference']['body']['pose']['position_m'][2]+=1e-6
    else:point['hierarchy']['body']['reconstructed_world_pose']['position_world_m'][2]+=1e-6
    p.decorate(packet)
    with pytest.raises(p.g.InvalidCapture,match='incoherent'):p.analyze(r,p.schedule()[1])


def test_change_state_flags_are_not_freshness_proof():
    a=result(p.schedule()[1])
    assert a['hierarchy_component_deltas']['right_wheel']['Pose']['value_changed']
    assert a['hierarchy_component_deltas']['right_wheel']['Pose']['S1']['component_change_label']=='NoChange'
    assert 'not producer times' in a['component_localization']['limits']


@pytest.mark.parametrize('shutdown_unproven',[False,True])
def test_fresh_process_six_slots_shutdown_gate_no_rerun(tmp_path,monkeypatch,shutdown_unproven):
    """Synthetic lifecycle control-flow test; runtime process isolation remains Host-required."""
    monkeypatch.setattr(p,'DEFAULT_OUTPUT',tmp_path)
    library=tmp_path/'builds/observer.so';library.parent.mkdir();library.write_bytes(b'offline fixture')
    p.write(tmp_path/'protocol.json',p.protocol())
    pf={'status':'PREFLIGHT_PASS','runner_sha256':p.g.sha(p.__file__),'protocol_sha256':p.g.sha(tmp_path/'protocol.json'),
      'guard_manifest':{},'library':str(library),'observer_build':{'library_sha256':p.g.sha(library)},
      'production_sha_before':p.g.EXPECTED_SHA,'production_sha_after':p.g.EXPECTED_SHA}
    p.write(tmp_path/'hierarchy_preflight.json',pf)
    monkeypatch.setattr(p,'safety',lambda output:None)
    monkeypatch.setattr(p.q,'codec_self_check',lambda:True)
    monkeypatch.setattr(p.g.history,'source',lambda path:({},43,None))
    monkeypatch.setattr(p.g.ab,'_build_all',lambda path:({},{}))
    monkeypatch.setattr(p.g,'verify_static_builds',lambda _:None)
    calls=[]
    def capture(case,scenario,directory,libraries,seed,namespace,library):
        index=len(calls);calls.append(case);spec=p.schedule()[index]
        if index:assert json.loads((tmp_path/calls[-2]/'process_lifecycle.json').read_text())['shutdown_proven']
        shutdown=not (shutdown_unproven and index==2)
        life={'shutdown_proven':shutdown,'fresh_single_server':True,'events':[
          {'event':'launch','wall_monotonic_s':index*10.,'status':{'pid':1000+index}},
          {'event':'close','wall_monotonic_s':index*10.+5,'pid':1000+index,'exit_code':0,'shutdown_proven':shutdown}]}
        p.write(directory/'process_lifecycle.json',life)
        r=fixture(spec);r.update(shutdown_completed=shutdown,runtime_identity={'partition':namespace,'topic':'/AN-P/'+namespace})
        if index==1:r['phase_qualification']['qualification_completed']=False
        return r
    monkeypatch.setattr(p,'capture',capture)
    a=p.run(tmp_path);slots=a['original_slots'];assert len(slots)==6
    assert calls==[s['case_id'] for s in p.schedule()[:len(calls)]]
    assert slots[1]['result']['classification']=='CAPTURE_INVALID'
    if shutdown_unproven:assert len(calls)==3 and all(s['state']=='SCHEDULED' for s in slots[3:])
    else:assert len(calls)==6 and all(s['state']=='FINALIZED' for s in slots)
    assert not a['causal_runtime_ready']
    with pytest.raises(FileExistsError):p.run(tmp_path)
