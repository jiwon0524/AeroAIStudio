"""AN-T synthetic/offline tests. No static test establishes runtime neutrality."""
import copy,inspect,json,math
from pathlib import Path
import pytest
from tools import diagnose_v07_gazebo_contact_surface_event as t
from test_gazebo_physical_microstate_ordering import fixture as microstate_fixture

@pytest.fixture(autouse=True)
def no_runtime(monkeypatch):
    from aero_ai_studio.gazebo.process_manager import GazeboProcessManager
    def refuse(*a,**k):raise AssertionError('offline tests prohibit Gazebo and Host')
    monkeypatch.setattr(GazeboProcessManager,'launch',refuse)
    monkeypatch.setattr(t.q,'capture',refuse)
    monkeypatch.setattr(t.g.ab,'_run_case',refuse)


def physical(spec):
    record=microstate_fixture(spec)
    packets=record['phase_qualification']['packets']+record['phase_qualification']['advancing_observations']
    for packet in packets:
        for state in [packet['microstate']]+[x['microstate'] for x in packet['callback_trace']]:
            for i,side in enumerate(t.r.SUPPORTS):state['supports'][side]['collision_entity_id']=47+i
    return record,t.r.analyze(record,spec)


def event_rows(spec,record,result):
    rows=[];seq=0;ordinal=0;count=int(spec['listener'])
    def add(kind,stage,cycle,it,ns,paused,**extra):
        nonlocal seq
        seq+=1;x={'kind':kind,'stage':stage,'cycle':cycle,'callback_sequence':seq,'iteration':it,'sim_time_ns':ns,'paused':paused,'listener_count':count,'listener_enabled':spec['listener'],**extra};rows.append(x)
    total=0
    ids={side:47+i for i,side in enumerate(t.r.SUPPORTS)}
    def lifecycle(complete=True):
        n=4 if spec['listener'] and complete else 0
        return dict(opt_in_lifecycle_schema=2,identities_resolved=5 if complete else 0,
          opt_in_creation_attempt_count=total,opt_in_creation_returned_true_count=total,
          opt_in_present_after_resolve=n,opt_in_before_mask=0,opt_in_attempt_mask=15 if n else 0,
          opt_in_returned_true_mask=15 if n else 0,opt_in_after_mask=15 if n else 0,
          opt_in_first_activation_iteration=0 if n else None,opt_in_latest_attempt_iteration=current if n else 0,
          opt_in_entities=ids if complete else {})
    current=0
    add('health','configure',0,0,0,True,prior_listener_count=0,**lifecycle(False))
    # Initial paused callback reproduces Host1's first activation at iteration 0.
    for stage in t.r.STAGES:
        if stage=='PreUpdate':total+=4 if spec['listener'] else 0
        add('stage',stage,1,0,0,True,**lifecycle(),opt_in_present_after_physics_mask=0)
    e=record['phase_qualification'];packets=[*e['packets'][:4],*e['advancing_observations'],*e['packets'][4:]]
    for p in packets:
        meta=(p['postupdate_count'],p['iteration'],p['sim_time_ns'],p['paused'])
        for stage in t.r.STAGES:
            current=p['iteration']
            if stage=='PreUpdate':total+=4 if spec['listener'] else 0
            add('stage',stage,*meta,**lifecycle(),opt_in_present_after_physics_mask=0)
            if stage=='Update/before_Physics_Update' and not p['paused'] and spec['listener']:
                s0=result['S0'][-1]['microstate'];s1=result['S1'][0]['microstate']
                for i,side in enumerate(t.r.SUPPORTS):
                    pt=t.contact_points(s1,side)[0];ordinal+=1
                    read={'engine_collision_pose':{k:copy.deepcopy(v['collision_pose']) for k,v in s0['geometry'].items()},'supports':copy.deepcopy(s0['supports']),'joint_wrench':copy.deepcopy(s0['joint_wrench'])}
                    add('contact_event','CollectContactSurfaceProperties',*meta,event_sequence=ordinal,inside_physics_window=True,
                      collision1=47+i,collision2=7,collision1_identity=side,collision2_identity='ground',point_world_m=pt['position_world_m'],normal_world=pt['normal_world'],
                      depth_argument_m=pt['depth_m'],force_argument=[0.,0.,0.],force_semantics='PRE_SOLVE_NONPHYSICAL_FORCE_ARGUMENT',surface_properties={'frictionCoeff':None},readback=read,producer_timestamp_ns=None)
    add('health','shutdown',0,0,0,True,event_count=ordinal,surface_mutation_count=0,outside_window_count=0,io_failed=False)
    return rows


def result(spec,tmp_path):
    record,a=physical(spec);directory=tmp_path/spec['case_id'];directory.mkdir()
    (directory/'contact_surface_events.ndjson').write_text('\n'.join(json.dumps(x) for x in event_rows(spec,record,a))+'\n')
    a.update(listener=spec['listener'],stage=spec['stage'],event_capture=t.event_capture(directory,a,spec),classification='CONTACT_EVENT_LISTENER_NEUTRALITY_UNRESOLVED' if spec['stage']=='A' else 'CONTACT_EVENT_TIMING_UNRESOLVED')
    return a


def test_documented_semantics_and_installed_feature():
    a=t.api_semantics();assert a['classification']=='DOCUMENTED_API_SEMANTICS'
    assert 'mutable' in str(a['payload']) and 'params' in a['signature']
    assert a['force_semantics']=='PRE_SOLVE_NONPHYSICAL_FORCE_ARGUMENT'
    assert all(v['callback_feature_present'] for v in a['installed_symbols'].values())
    assert 'HOST_REQUIRED' in a['runtime_observation'] and 'NOT established' in a['opt_in_neutrality']


def test_listener_const_sink_no_parameter_write_command_or_private_access():
    a=t.static_contract();assert a['listener_const_only'] and a['surface_assignments']==a['listener_commands']==a['physics_advancement_calls']==0
    source=t.SOURCE.read_text();body=source[source.index(' void Observe('):source.index(' public: ~ContactSurfaceEventObserver')]
    assert 'const SurfaceParams &params' in body and source.count('const SurfaceParams &params')==2
    for token in ('params.','const_cast','SetForce(','SetVelocity(','ResetPosition','JointPositionReset','publish(','Request('):assert token not in body
    assert '#include "gazebo_physical_microstate_observer.cc"' in source


@pytest.mark.parametrize('stage',['A','B'])
def test_frozen_balanced_interleaved_schedules(stage):
    s=t.schedule(stage);arms=(t.CONTROL,t.LISTENER) if stage=='A' else (t.ZERO,t.ONE)
    assert len(s)==10 and len({x['case_id'] for x in s})==10
    assert [x['arm'] for x in s]==[arms[0],arms[1],arms[1],arms[0],arms[0],arms[1],arms[1],arms[0],arms[0],arms[1]]
    assert sum(x['arm']==arms[0] for x in s)==sum(x['arm']==arms[1] for x in s)==5
    assert not t.protocol(stage)['automatic_reruns'] and t.protocol(stage)['fresh_process_per_case']
    assert all(x['iterations']==1 for x in s) if stage=='A' else sum(x['iterations'] for x in s)==5


@pytest.mark.parametrize('spec',t.schedule('A')+t.schedule('B'),ids=lambda s:s['case_id'])
def test_exact_dose_event_capture_callback_alignment_and_force_label(spec,tmp_path):
    a=result(spec,tmp_path);assert a['capture_valid']
    assert (a['delta_iterations'],a['delta_sim_time_ns'],a['command_audit']['advancing_requests'])==(spec['iterations'],spec['sim_time_delta_ns'],spec['iterations'])
    assert a['event_capture']['single_listener_contract'] and a['event_capture']['activation_before_S0']
    assert len(a['event_capture']['events'])==(4 if spec['listener'] and spec['iterations'] else 0)
    assert all(x['force_semantics']=='PRE_SOLVE_NONPHYSICAL_FORCE_ARGUMENT' and x['producer_timestamp_ns'] is None for x in a['event_capture']['events'])


@pytest.mark.parametrize('mutation',['clock','twist','pose','reset','force','velocity','sensor','planner','UP','extra_tick'])
def test_existing_contamination_contract_not_weakened(mutation):
    spec=t.schedule('A')[1];rec,_=physical(spec);e=rec['phase_qualification']
    if mutation=='clock':e['packets'][-1]['sim_time_ns']+=1
    elif mutation in ['twist','pose','reset','force','velocity']:rec['command_audit'][0].update(kind='TWIST' if mutation=='twist' else 'RPC',request_type='Empty',service='/'+mutation)
    elif mutation=='sensor':e['host_POST']['production_sensor']['sequence']+=1
    elif mutation=='planner':e['host_POST']['logical']['env_previous_action']='up'
    elif mutation=='UP':rec['events'][-1]['exception']=None
    elif mutation=='extra_tick':rec['command_audit'][4]['payload']['multi_step']=2
    with pytest.raises(t.g.InvalidCapture):t.r.analyze(rec,spec)


def test_stage_a_neutral_pairs_all_endpoints_and_markers(tmp_path):
    results=[result(s,tmp_path) for s in t.schedule('A')];a=t.aggregate_a(results)
    assert a['classification']=='CONTACT_EVENT_LISTENER_NEUTRAL' and a['Stage_B_permitted']
    assert len(a['matched_comparisons'])==5 and len(a['all_S1_pairwise_comparisons'])==45
    assert all(x['pass'] for x in a['matched_comparisons'])
    assert not a['physical_timing_interpreted']


@pytest.mark.parametrize('mutation',['nonneutral','missing_event','other_listener','missing_channel','baseline','control_marker'])
def test_stage_a_failure_blocks_stage_b(mutation,tmp_path):
    results=[result(s,tmp_path) for s in t.schedule('A')];x=next(x for x in results if x['listener'])
    expected='CONTACT_EVENT_LISTENER_NEUTRALITY_UNRESOLVED'
    if mutation=='nonneutral':x['S1'][0]['microstate']['geometry']['right_wheel']['center_pose']['position_world_m'][2]+=1e-9;expected='CONTACT_EVENT_LISTENER_NONNEUTRAL'
    elif mutation=='missing_event':x['event_capture']['availability']=False
    elif mutation=='other_listener':x['event_capture']['single_listener_contract']=False
    elif mutation=='missing_channel':x['S1'][0]['microstate']['joint_wrench']['right']['force_xyz_N']=None
    elif mutation=='baseline':x['S0'][-1]['microstate']['generalized_q']['right']+=1e-5;expected='BASELINE_UNSTABLE'
    else:results[0]['measurements']['geometry.right_wheel.center_pose.position_world_m[2]']['delta']=0.
    a=t.aggregate_a(results);assert a['classification']==expected and not a['Stage_B_permitted']


def test_invalid_capture_retained_and_gate_not_satisfied(tmp_path):
    results=[result(s,tmp_path) for s in t.schedule('A')];s=t.schedule('A')[3]
    results[3]={'case_id':s['case_id'],'arm':s['arm'],'capture_valid':False,'classification':'CAPTURE_INVALID','invalid_reason':'synthetic infrastructure failure'}
    a=t.aggregate_a(results);assert a['status']=='CAPTURE_FAILED' and not a['Stage_B_permitted'] and a['results'][3]['classification']=='CAPTURE_INVALID'


@pytest.mark.parametrize('mutation',['sequence','bracket','paused','force_label','producer_stamp','point','clock','mutation','io','ZERO_event'])
def test_malformed_or_contaminated_event_capture_invalid(mutation,tmp_path):
    spec=t.schedule('B')[1];rec,a=physical(spec);rows=event_rows(spec,rec,a);ev=next(x for x in rows if x['kind']=='contact_event')
    if mutation=='sequence':ev['event_sequence']+=1
    elif mutation=='bracket':ev['inside_physics_window']=False
    elif mutation=='paused':ev['paused']=True
    elif mutation=='force_label':ev['force_semantics']='MEASURED_FORCE'
    elif mutation=='producer_stamp':ev['producer_timestamp_ns']=3601000000
    elif mutation=='point':ev['point_world_m']=None
    elif mutation=='clock':next(x for x in rows if x['kind']=='stage' and x['cycle']==a['S0'][0]['postupdate_count'])['sim_time_ns']+=1
    elif mutation=='mutation':rows[-1]['surface_mutation_count']=1
    elif mutation=='io':rows[-1]['io_failed']=True
    else:spec={**spec,'iterations':0}
    path=tmp_path/'contact_surface_events.ndjson';path.write_text('\n'.join(json.dumps(x) for x in rows))
    with pytest.raises(t.g.InvalidCapture):t.event_capture(tmp_path,a,spec)


def test_event_identity_depth_sign_mapping_and_pre_solve_force_not_compared(tmp_path):
    a=result(t.schedule('B')[1],tmp_path);timing=t.timing_case(a,{k:0. for k in t.r.SUPPORTS})
    assert timing['classification']=='CONTACT_GEOMETRY_OBSERVABLE_EARLIER' and timing['complete_unique_mapping']
    assert all(x['convention_agrees_with_post_component'] and x['event_minus_S1_m']==0. for x in timing['mapping'])
    for e in a['event_capture']['events']:e['force_argument']=[123456.,-20.,7.]
    assert t.timing_case(a,{k:0. for k in t.r.SUPPORTS})['classification']==timing['classification']
    for e in a['event_capture']['events']:e['normal_world']=[-x for x in e['normal_world']]
    assert all(x['normal_relation']=='REVERSED' for x in t.timing_case(a,{k:0. for k in t.r.SUPPORTS})['mapping'])


@pytest.mark.parametrize('mutation',['depth_missing','normal_missing','point_ambiguous','identity','geometry_already_changed','depth_convention'])
def test_missing_or_ambiguous_mapping_unresolved(mutation,tmp_path):
    a=result(t.schedule('B')[1],tmp_path);ev=a['event_capture']['support_events']['right_wheel'][0]
    if mutation=='depth_missing':ev['depth_argument_m']=None
    elif mutation=='normal_missing':ev['normal_world']=None
    elif mutation=='point_ambiguous':a['S1'][0]['microstate']['supports']['right_wheel']['contacts'][0]['points']*=2
    elif mutation=='identity':ev['collision1']=99999
    elif mutation=='geometry_already_changed':
        for e in a['event_capture']['events']:e['readback']['engine_collision_pose']['right_wheel']['position_world_m'][2]+=1e-6
    else:ev['depth_argument_m']=-ev['depth_argument_m']
    timing=t.timing_case(a,{k:0. for k in t.r.SUPPORTS})
    assert timing['classification']=='CONTACT_EVENT_TIMING_UNRESOLVED'


def test_stage_b_baseline_all_stages_and_same_support_replication(tmp_path):
    ar=tmp_path/'a';br=tmp_path/'b';ar.mkdir();br.mkdir()
    a=[result(s,ar) for s in t.schedule('A')];b=[result(s,br) for s in t.schedule('B')]
    summary=t.aggregate_b(b,a);assert summary['classification']=='CONTACT_GEOMETRY_OBSERVABLE_EARLIER'
    assert len(summary['baseline_equivalence']['pairwise_checks'])==190
    assert summary['ZERO_event_counts']==[0]*5 and summary['public_observation_refinement']=='CONTACT_GEOMETRY_OBSERVABLE_EARLIER_THAN_POSTPHYSICS_BUNDLE'
    assert not summary['mediator_selected'] and not summary['further_invasive_hooks_permitted']


def test_stage_b_gate_precedes_any_runtime_or_destination_write(tmp_path,monkeypatch):
    monkeypatch.setattr(t,'A_ROOT',tmp_path/'a');monkeypatch.setattr(t,'B_ROOT',tmp_path/'b')
    with pytest.raises(t.g.InvalidCapture,match='Stage B blocked'):t.run('B')
    assert not t.B_ROOT.exists()
    t.A_ROOT.mkdir();(t.A_ROOT/'contact_event_qualification.json').write_text(json.dumps({'status':'QUALIFICATION_CAPTURE_COMPLETE','classification':'CONTACT_EVENT_LISTENER_NONNEUTRAL','Stage_B_permitted':False}))
    with pytest.raises(t.g.InvalidCapture,match='not neutral'):t.stage_b_gate()


def test_gate_cannot_be_faked_by_relabeling_saved_result(tmp_path,monkeypatch):
    monkeypatch.setattr(t,'A_ROOT',tmp_path)
    (tmp_path/'contact_event_qualification.json').write_text(json.dumps({'status':'CAPTURE_FAILED','classification':'CONTACT_EVENT_LISTENER_NEUTRAL','Stage_B_permitted':True}))
    (tmp_path/'contact_event_preflight.json').write_text('{}')
    with pytest.raises(t.g.InvalidCapture):t.stage_b_gate()


def test_precise_binary64_comparison_and_missing_values():
    assert t.exact_compare({'x':1.},{'x':math.nextafter(1.,math.inf)})
    assert t.exact_compare({'x':0.},{'x':-0.})
    assert not t.exact_compare({'x':None},{'x':None})
    assert t.event_fn({'component_available':False}) is None


def test_production_and_stop_contracts():
    for stage in ('A','B'):
        p=t.protocol(stage);assert p['production_sha256']=='92def637ff4da2be1348502d345a30721cc845c34704f0b125d4ff1a26fdcc55'
        assert not p['Action24_UP'] and not p['causal_intervention']
        assert 'unresolved ends read-only timing investigation' in str(p['stop_rules'])
    run=inspect.getsource(t.run);assert run.count('record=capture(')==1 and 'stage_b_gate()' in run
    assert 'STAGE_B_REMAINS_UNEXECUTED_SEPARATE_INVOCATION_REQUIRED' in run


def test_static_preflight_artifacts_if_built():
    for stage,root in [('A',t.HOST1_ROOT),('A',t.A_ROOT),('B',t.B_ROOT)]:
        path=root/'contact_event_preflight.json'
        if not path.exists():continue
        pf=json.loads(path.read_text());assert all(pf['gates'].values()) and len(pf['definitions'])==10
        assert pf['production_sha_before']==pf['production_sha_after']==t.g.EXPECTED_SHA
        state=t.preflight_evidence_state(root)
        assert state in ('FRESH_PREFLIGHT_ROOT','COMPLETED_PRESERVED_HOST_EVIDENCE')
        for definition in pf['definitions']:
            t.validate_sdf(definition['sdf'],definition['spec']);assert t.g.sha(definition['production_sdf'])==t.g.EXPECTED_SHA
        # Archived runtime evidence retains its original diagnostic source
        # hashes. T1 explicitly changes these three diagnostic files only.
        changed={str(x.resolve()) for x in (t.SOURCE,Path(t.__file__),Path(__file__))}
        archived=root!=t.A_ROOT
        guard={k:v for k,v in pf['guard_manifest'].items() if not archived or k not in changed}
        t.g.history.verify_manifest(guard)
    assert json.loads((t.B_ROOT/'stage_b_blocked.json').read_text())['status']=='BLOCKED_UNTIL_STAGE_A_NEUTRAL'


def test_stage_a_never_computes_physical_timing_before_neutrality(tmp_path,monkeypatch):
    spec=t.schedule('A')[1];record,a=physical(spec)
    (tmp_path/'contact_surface_events.ndjson').write_text('\n'.join(json.dumps(x) for x in event_rows(spec,record,a)))
    def reject(*a,**k):raise AssertionError('Stage A may not run timing interpretation')
    monkeypatch.setattr(t.r,'analyze',reject)
    analyzed=t.analyze(record,spec,tmp_path)
    assert analyzed['capture_valid'] and not analyzed['physical_timing_interpreted']
    assert 'first_change' not in analyzed and 'stages' not in analyzed


@pytest.mark.parametrize('mutate',['late_opt_in','missing_opt_in','preexisting_opt_in'])
def test_opt_in_configuration_is_part_of_neutrality_not_assumed(mutate,tmp_path):
    spec=t.schedule('A')[1];rec,a=physical(spec);rows=event_rows(spec,rec,a)
    for row in rows:
        if row['stage']!='PreUpdate':continue
        if mutate=='late_opt_in':row['opt_in_first_activation_iteration']=3600
        elif mutate=='missing_opt_in':row['opt_in_present_after_resolve']=0
        else:row['opt_in_creation_attempt_count']=0
    (tmp_path/'contact_surface_events.ndjson').write_text('\n'.join(json.dumps(x) for x in rows))
    assert not t.event_capture(tmp_path,a,spec)['activation_before_S0']


def test_every_installed_surface_property_is_snapshotted_read_only():
    import re
    header=Path('/usr/include/gz/physics7/gz/physics/ContactProperties.hh').read_text()
    section=header[header.index('struct ContactSurfaceParams'):header.index('public: template <typename PolicyT, typename FeaturesT>')]
    members=re.findall(r'\b(\w+)\s*;',section)
    assert len(members)==14
    source=t.SOURCE.read_text();serializer=source[source.index('static std::string SurfaceJSON'):source.index('static void MathJSONVector')]
    assert all('p.'+name in serializer for name in members)
    assert not re.search(r'p\.\w+\s*=(?!=)',serializer)


def test_listener_activation_and_existing_measurement_sources_frozen():
    assert t.static_contract()['documented_opt_in_only']
    pf=json.loads((t.r.DEFAULT_OUTPUT/'microstate_preflight.json').read_text())
    assert t.g.sha(t.r.SOURCE)==pf['observer_build']['source_sha256']
    assert 'r.verify_capture(record,spec)' in inspect.getsource(t.neutrality_endpoints)
    assert 'r.analyze' not in inspect.getsource(t.neutrality_endpoints)


def test_unexpected_force_argument_is_api_conflict_not_physical_force(tmp_path):
    spec=t.schedule('A')[1];rec,a=physical(spec);rows=event_rows(spec,rec,a)
    for ev in rows:
        if ev['kind']=='contact_event':ev['force_argument']=[1.,2.,3.]
    (tmp_path/'contact_surface_events.ndjson').write_text('\n'.join(json.dumps(x) for x in rows))
    capture=t.event_capture(tmp_path,a,spec)
    assert not capture['documented_pre_solve_force_default_agrees']
    assert all(ev['force_semantics']=='PRE_SOLVE_NONPHYSICAL_FORCE_ARGUMENT' for ev in capture['events'])


def test_absent_pre_solve_force_is_not_fabricated_zero(tmp_path):
    spec=t.schedule('B')[1];rec,a=physical(spec);rows=event_rows(spec,rec,a)
    for ev in rows:
        if ev['kind']=='contact_event':ev['force_argument']=None
    (tmp_path/'contact_surface_events.ndjson').write_text('\n'.join(json.dumps(x) for x in rows))
    a['event_capture']=t.event_capture(tmp_path,a,spec)
    assert all(ev['force_argument'] is None for ev in a['event_capture']['events'])
    assert t.timing_case(a,{k:0. for k in t.r.SUPPORTS})['classification']=='CONTACT_GEOMETRY_OBSERVABLE_EARLIER'


def test_depth_readback_noise_can_block_false_earlier_claim(tmp_path):
    a=result(t.schedule('B')[1],tmp_path)
    for k in a['noise_envelope']:
        if k.endswith('.depth_m'):a['noise_envelope'][k]=1e-5
    assert t.timing_case(a,{k:0. for k in t.r.SUPPORTS})['classification']=='CONTACT_EVENT_TIMING_UNRESOLVED'


def test_fresh_process_lifecycle_no_overlap_or_identity_reuse():
    record={'shutdown_completed':True,'runtime_identity':{'partition':'new','topic':'/new'}}
    life={'events':[{'event':'launch','wall_monotonic_s':10.,'status':{'status':'Running','available':True,'pid':1,'partition':'new'}},
                    {'event':'close','wall_monotonic_s':20.,'pid':1,'partition':'new','exit_code':0}],
          **{k:True for k in ['shutdown_proven','fresh_single_server','observer_subscriptions_closed','qualification_transport_closed']}}
    parts=set();topics=set();assert t.r.verify_lifecycle(record,life,5.,parts,topics)==20.
    with pytest.raises(t.g.InvalidCapture,match='identity reused'):t.r.verify_lifecycle(record,life,5.,parts,topics)
    with pytest.raises(t.g.InvalidCapture,match='overlap'):t.r.verify_lifecycle(record,life,11.,set(),set())


def test_stage_b_does_not_reinterpret_a_different_postphysics_bundle(tmp_path):
    ar=tmp_path/'a';br=tmp_path/'b';ar.mkdir();br.mkdir()
    a=[result(s,ar) for s in t.schedule('A')];b=[result(s,br) for s in t.schedule('B')]
    x=next(x for x in b if x['arm']==t.ONE);x['measurements']['geometry.right_wheel.center_pose.position_world_m[2]']['delta']=0.
    out=t.aggregate_b(b,a)
    assert out['classification']=='CONTACT_EVENT_TIMING_UNRESOLVED' and not out['further_invasive_hooks_permitted']
    assert 'ONE_timing' not in out
