"""AN-R offline synthetic contracts; no runtime evidence or physical conclusions."""
import copy
import inspect
import json
import math
from pathlib import Path
import pytest
from tools import diagnose_v07_gazebo_physical_microstate_ordering as r


@pytest.fixture(autouse=True)
def no_runtime(monkeypatch):
    from aero_ai_studio.gazebo.process_manager import GazeboProcessManager
    def refuse(*a,**k):raise AssertionError('offline test forbids Gazebo/Host execution')
    monkeypatch.setattr(GazeboProcessManager,'launch',refuse)
    monkeypatch.setattr(r.g.ab,'_run_case',refuse)
    monkeypatch.setattr(r.q,'capture',refuse)


def state(changed=False):
    geometry={}
    for i,k in enumerate(r.LINKS):
        p={'position_world_m':[float(i),0.,.05 if k!='body' else .11],'orientation_world_xyzw':[0.,0.,0.,1.]}
        if changed:
            p['position_world_m'][2]+=r.RIGHT_Z_REFERENCE if k=='right_wheel' else 1e-8
            if k=='body':p['orientation_world_xyzw']=[math.sin(1e-8/2),math.sin(2e-8/2),0.,math.sqrt(1-math.sin(1e-8/2)**2-math.sin(2e-8/2)**2)]
        geometry[k]={'collision_pose':p,'ECM_link_pose':copy.deepcopy(p),
          'linear_velocity_world_m_s':[0.,0.,1e-7 if changed else 0.], 'angular_velocity_world_rad_s':[0.,0.,0.],
          'ECM_link_linear_velocity':[0.,0.,0.],'ECM_link_angular_velocity':[0.,0.,0.], 'provenance':'synthetic'}
    supports={}
    for k in r.SUPPORTS:
        fn=6.125+(r.FN_REFERENCE[k] if changed else 0.)
        supports[k]={'component_available':True,'state':'VALID_CONTACTS','component_producer_stamp_ns':None,
          'contacts':[{'pair_classification':'SUPPORT_GROUND','points':[{'depth_m':1e-6-(1e-8 if changed else 0.),
            'normal_world':[0.,0.,1.],'position_world_m':[0.,0.,0.],'body_1_force_world_n':[0.,0.,fn],
            'body_2_force_world_n':[0.,0.,-fn],'body_1_torque_reported_N_m':None,'body_2_torque_reported_N_m':None}]}]}
    joints={k:{'state':'VALID_WRENCH','actual_velocity_available':True,'actual_velocity_rad_s':0.,
      'force_xyz_N':[0.,0.,1.+(1e-5 if changed else 0.)],'torque_xyz_N_m':[0.,0.,0.]} for k in ['left','right']}
    return r.decorate_state({'geometry':geometry,'supports':supports,'joint_wrench':joints,
      'generalized_q':{'left':-.004,'right':1.004},'solver_internal_state':None,'provenance':{'fixture':'synthetic; not runtime evidence'}})


def marker(n=0):return {'iteration':3600+n,'sim_time_ns':3600000000+1000000*n,'paused':True,
    'stats_source':'transport_snapshot','observed_snapshot':{'iterations_normalized':3600+n,'paused':True,
    'sim_time':{'sec':3,'nsec':600000000+1000000*n}}}


def fixture(spec):
    n=spec['iterations'];seq=0
    def packet(i,post=False,automatic=False):
        nonlocal seq
        tick=n if post else 0
        trace=[]
        for stage in r.STAGES:
            seq+=1;change=post and n and (not automatic or stage in r.STAGES[2:])
            trace.append({'stage':stage,'callback_sequence':seq,'iteration':3600+tick,
              'sim_time_ns':3600000000+tick*1000000,'paused':not automatic,'microstate':state(bool(change))})
        return {'request_id':0 if automatic else i+1,'operation_code':2 if automatic else [0,0,0,1,0,0,0][i],
          'event':'advancing_observation' if automatic else 'armed_readback' if i==3 else 'readback',
          'error':'','paused':not automatic,'iteration':3600+tick,'sim_time_ns':3600000000+tick*1000000,
          'postupdate_count':100+seq,'advancing_callback_count':3600+tick,'WorldPoseCmd_active':0,
          'WorldPoseCmd_active_PRE':0,'WorldPoseCmd_observations':3,'callback_trace':trace,'microstate':copy.deepcopy(trace[-1]['microstate'])}
    packets=[packet(i) for i in range(4)];auto=[packet(0,True,True)] if n else [];packets +=[packet(i,True) for i in range(4,7)]
    host={'logical':{'env_previous_action':'down','adapter_previous_action':'down','controller_command':{'linear':{'x':0.},'angular':{'z':0.}}},
      'production_sensor':{'sequence':36,'previous_timestamp':3.6,'cached_observation_identity':123},'production_step_tracker':{'active_depth':0}}
    def rpc(kind,payload):return {'kind':'RPC','request_type':kind,'service':'/test/physical_microstate/request' if kind=='Int32' else '/world/test/control',
      'payload':payload,'response':{'data':True},'transport_evidence':{'attempts':[{'attempt':1}]}}
    audit=[rpc('Int32',{'data':c}) for c in (0,0,0,1)]
    if n:audit.append(rpc('WorldControl',{'pause':True,'multi_step':1}))
    audit.append(rpc('WorldControl',{'pause':True}));audit +=[rpc('Int32',{'data':0}) for _ in range(3)]
    e={'spec':spec,'qualification_completed':True,'failed_stage':None,'packets':packets,'advancing_observations':auto,
      'PRE_marker':marker(),'POST_marker':marker(n),'before_optional_tick_stats':marker(),'after_optional_tick_stats':marker(n),
      'host_PRE':host,'host_POST':copy.deepcopy(host),'window_start':0,'window_end':len(audit),
      'stopped_chunk':{'phase':'BRAKE_LINEAR','iterations_contract_pass':True,'world_pose_history_contract':{'pass':True},
        'body_stopped_contract':{'pass':True},'collision_events':[],'simulation_end':3.6},'completed_brake':{'active_physics_transactions':0}}
    return {'case':spec['case_id'],'phase_qualification':e,'command_audit':audit,
      'events':[{'canonical_index':i,'exception':None,'terminated':False} for i in range(8,24)]+[{'exception':{'message':r.STOP}}],
      'terminal_entry_history':{'production_plan':{'request':{'previous_command':r.g.dm.gazebo_physics_twist('down'),'transition_type':'LINEAR_REVERSAL'},
        'phases':[{'kind':'BRAKE_LINEAR'},{'kind':'ACQUIRE_LINEAR'}]}}}


def result(spec):return r.analyze(fixture(spec),spec)


def test_frozen_ten_case_schedule():
    s=r.schedule();assert len(s)==10 and len({x['case_id'] for x in s})==10
    assert [x['ordinal'] for x in s]==list(range(1,11))
    assert [x['arm'] for x in s]==[r.ZERO,r.ONE,r.ONE,r.ZERO,r.ZERO,r.ONE,r.ONE,r.ZERO,r.ZERO,r.ONE]
    assert sum(x['arm']==r.ZERO for x in s)==sum(x['arm']==r.ONE for x in s)==5
    assert not r.protocol()['automatic_reruns'] and r.protocol()['fresh_process_per_case']


@pytest.mark.parametrize('spec',r.schedule(),ids=lambda s:s['case_id'])
def test_exact_dose_and_q_guard(spec):
    a=result(spec);assert a['capture_valid']
    assert (a['delta_iterations'],a['delta_sim_time_ns'],a['command_audit']['advancing_requests'])==(spec['iterations'],spec['sim_time_delta_ns'],spec['iterations'])
    assert a['q_guard']=={'left':0.,'right':0.}
    assert a['classification']==('SAME_OBSERVABLE_STAGE' if spec['iterations'] else 'ORDERING_UNRESOLVED')


@pytest.mark.parametrize('mutation',['twist','pose','reset','force','velocity','physics','friction','extra_step','extra_ns','zero_step','retry','sensor','planner','WorldPoseCmd','UP','history','boundary','missing_solve'])
def test_reject_contamination_or_incomplete_capture(mutation):
    spec=r.schedule()[0 if mutation=='zero_step' else 1];rec=fixture(spec);e=rec['phase_qualification']
    if mutation in ['twist','pose','reset','force','velocity','physics','friction']:
        rec['command_audit'][0].update(kind='TWIST' if mutation=='twist' else 'RPC',request_type='Empty',service='/world/test/'+mutation)
    elif mutation=='extra_step':rec['command_audit'][4]['payload']['multi_step']=2
    elif mutation=='zero_step':rec['command_audit'].insert(0,{'kind':'RPC','request_type':'WorldControl','payload':{'pause':True,'multi_step':1}});e['window_end']+=1
    elif mutation=='extra_ns':e['packets'][-1]['sim_time_ns']+=1
    elif mutation=='retry':rec['command_audit'][4]['transport_evidence']['attempts']*=2
    elif mutation=='sensor':e['host_POST']['production_sensor']['sequence']+=1
    elif mutation=='planner':e['host_POST']['logical']['env_previous_action']='up'
    elif mutation=='WorldPoseCmd':e['packets'][-1]['WorldPoseCmd_active']=1
    elif mutation=='UP':rec['events'][-1]['exception']=None
    elif mutation=='history':rec['events'][0]['canonical_index']=7
    elif mutation=='boundary':e['stopped_chunk']['body_stopped_contract']['pass']=False
    elif mutation=='missing_solve':e['advancing_observations']=[]
    with pytest.raises(r.g.InvalidCapture):r.analyze(rec,spec)


@pytest.mark.parametrize('mutation',['order','sequence','gap','clock','endpoint'])
def test_callback_contract(mutation):
    s=r.schedule()[1];rec=fixture(s);p=rec['phase_qualification']['advancing_observations'][0];trace=p['callback_trace']
    if mutation=='order':trace[1],trace[2]=trace[2],trace[1]
    elif mutation=='sequence':trace[2]['callback_sequence']=trace[1]['callback_sequence']
    elif mutation=='gap':trace[0]['callback_sequence']=1000
    elif mutation=='clock':trace[0]['iteration']+=1
    elif mutation=='endpoint':trace[-1]['microstate']['generalized_q']['right']+=1e-5
    with pytest.raises(r.g.InvalidCapture):r.analyze(rec,s)


def test_full_precision_deltas_statistics_and_signed_zero():
    a=1.;b=math.nextafter(a,math.inf);v=r.delta_vector({'x':a,'missing':None},{'x':b,'missing':None})
    assert v['x']['delta']==2.220446049250313e-16 and not v['x']['bitwise_equal']
    assert v['missing']['delta'] is None
    assert not r.bit_equal(0.,-0.)
    v=r.statistics_vector([r.RIGHT_Z_REFERENCE]*5)
    assert v['min']==v['max']==v['mean']==v['median']==r.RIGHT_Z_REFERENCE
    assert v['population_standard_deviation']==0 and v['bitwise_equal'] and v['sign_consistent']


def test_geometry_contact_joint_channels_and_provenance():
    s=state();assert set(s['geometry'])==set(r.LINKS)
    for v in s['geometry'].values():assert v['center_pose']==v['collision_pose'] and len(v['center_pose']['roll_pitch_yaw_rad'])==3
    for v in s['supports'].values():
        assert v['contact_present'] and v['contact_count']==v['point_count']==1 and v['Fn_N']==6.125
        assert v['component_producer_stamp_ns'] is None and 'NO_PRODUCER_STAMP' in v['freshness']
    assert set(s['joint_wrench'])=={'left','right'} and s['normal_relative_velocity_m_s'] is None
    assert s['solver_internal_state'] is None


@pytest.mark.parametrize('kind',['support','force','normal','caster','wrench'])
def test_missing_channels_never_become_zero(kind):
    s=state();v=s['supports']['right_wheel']
    if kind=='support':v['component_available']=False;v['contacts']=[]
    elif kind in ['force','normal']:v['contacts'][0]['points'][0]['body_1_force_world_n' if kind=='force' else 'normal_world']=None
    elif kind=='caster':s['geometry']['front_caster']['collision_pose']=None
    elif kind=='wrench':s['joint_wrench']['right'].pop('force_xyz_N')
    r.decorate_state(s)
    if kind in ['support','force','normal']:assert v['Fn_N'] is None
    elif kind=='caster':assert s['geometry']['front_caster']['center_pose'] is None
    else:assert s['joint_wrench']['right']['force_xyz_N'] is None
    assert r.statistics_vector([None]*5)['status']=='UNAVAILABLE'


@pytest.mark.parametrize('kind',['geometry','velocity','quaternion','actual_q'])
def test_malformed_required_channel_invalid(kind):
    s=state()
    if kind=='geometry':s['geometry']['right_wheel']['collision_pose']=None
    elif kind=='velocity':s['geometry']['body']['linear_velocity_world_m_s']=[float('nan')]*3
    elif kind=='quaternion':s['geometry']['body']['collision_pose']['orientation_world_xyzw']=[0.,0.,0.,2.]
    else:s['generalized_q']['right']=None
    with pytest.raises(r.g.InvalidCapture):r.decorate_state(s)


def test_simultaneous_at_available_stage_and_no_substep_claim():
    a=result(r.schedule()[1]);f=a['first_change'];assert f['classification']=='SAME_OBSERVABLE_STAGE'
    assert all(v['first_resolved_change']['stage']==r.STAGES[2] for k,v in f['candidates'].items() if k in ['RIGHT_Z','LEFT_Z','CHASSIS_Z','roll','pitch','right_wheel_Fn','left_wheel_Fn','front_caster_Fn','rear_caster_Fn','right_transmitted_wrench','left_transmitted_wrench','right_wheel_depth','left_wheel_depth'])
    assert 'physical producer/substep ordering remains unresolved' in f['scope']


@pytest.mark.parametrize('family,expected',[('geometry','GEOMETRY_FIRST'),('depth','CONTACT_DEPTH_FIRST'),('force','WRENCH_OR_FORCE_FIRST')])
def test_distinguishable_external_stages(family,expected):
    s0=state();s1=state(True);mid=copy.deepcopy(s0)
    if family=='geometry':mid['geometry']=copy.deepcopy(s1['geometry'])
    elif family=='depth':
        for k in r.SUPPORTS:mid['supports'][k]['contacts'][0]['points'][0]['depth_m']=s1['supports'][k]['contacts'][0]['points'][0]['depth_m']
    else:
        for k in r.SUPPORTS:mid['supports'][k]['Fn_N']=s1['supports'][k]['Fn_N']
    stages=[{'stage':r.STAGES[1],'callback_sequence':1,'iteration':3601,'sim_time_ns':3601000000,'paused':False,'microstate':mid},
      {'stage':r.STAGES[2],'callback_sequence':2,'iteration':3601,'sim_time_ns':3601000000,'paused':False,'microstate':s1}]
    assert r.first_changes(s0,stages,{})['classification']==expected


def test_noise_blocks_false_first_change():
    a=result(r.schedule()[1]);s0=a['S0'][-1]['microstate'];noise={k:1. for k in r.observed(s0)}
    f=r.first_changes(s0,a['stages'],noise)
    assert f['candidates']['RIGHT_Z']['first_resolved_change'] is None and f['classification']=='ORDERING_UNRESOLVED'


def test_baseline_all_pairs_object_identity_excluded_and_instability_blocks():
    rs=[result(s) for s in r.schedule()]
    rs[-1]['baseline_command_state']['production_sensor']['cached_observation_identity']=999
    b=r.baseline_equivalence(rs);assert b['status']=='OBSERVED_BASELINE_EQUIVALENT' and len(b['pairwise_checks'])==45
    rs[-1]['S0'][-1]['microstate']['geometry']['body']['center_pose']['position_world_m'][2]+=1e-6
    a=r.aggregate(rs);assert a['classification']=='BASELINE_UNSTABLE' and not a['physical_interpretation_permitted']
    assert 'ONE_delta_statistics' not in a


def test_complete_block_replication_preload_weight_and_exact_vectors():
    a=r.aggregate([result(s) for s in r.schedule()])
    assert a['status']=='QUALIFICATION_CAPTURE_COMPLETE' and a['classification']=='SAME_OBSERVABLE_STAGE'
    assert a['RIGHT_Z_replication']['matches']
    assert len(a['RIGHT_Z_replication']['vector'])==5
    assert set(a['replication_classes'])=={'PHYSICAL_MICROSTATE_CHANGE_REPLICATED','RIGHT_Z_MARKER_REPLICATED','SUPPORT_PRELOAD_CHANGE_REPLICATED'}
    assert all(v['matches'] for v in a['support_preload_replication'].values())
    assert all(v['S0']['approximately_balanced'] and v['S1']['approximately_balanced'] for v in a['weight_balance'])
    assert not a['mediator_selected'] and not a['Action24_outcomes_tested']


def test_invalid_retention_never_full_closure():
    rs=[result(s) for s in r.schedule()];s=r.schedule()[3]
    rs[3]={'case_id':s['case_id'],'arm':s['arm'],'capture_valid':False,'classification':'CAPTURE_INVALID','invalid_reason':'infrastructure timeout','traceback':'synthetic'}
    ledger={'slots':[{'spec':spec,'state':'FINALIZED','result':value} for spec,value in zip(r.schedule(),rs)]}
    assert r.validate_ledger(ledger)==ledger
    a=r.aggregate(rs);assert a['status']=='CAPTURE_FAILED' and a['results'][3]['classification']=='CAPTURE_INVALID'
    assert not a['physical_interpretation_permitted'] and not a['replication_classes']


def test_targets_prospectively_frozen_and_not_causal():
    p=r.protocol();assert p['RIGHT_Z_reference_m']==2.940583122834628e-8 and p['Fn_delta_reference_N']==r.FN_REFERENCE
    assert set(r.CLASSES)=={'PHYSICAL_MICROSTATE_CHANGE_REPLICATED','RIGHT_Z_MARKER_REPLICATED','SUPPORT_PRELOAD_CHANGE_REPLICATED','GEOMETRY_FIRST','CONTACT_DEPTH_FIRST','WRENCH_OR_FORCE_FIRST','SAME_OBSERVABLE_STAGE','ORDERING_UNRESOLVED','SOLVER_INTERNAL_STATE_NOT_PUBLICLY_OBSERVABLE','BASELINE_UNSTABLE','CAPTURE_INVALID'}
    assert not p['causal_intervention'] and not p['Action24_UP'] and not p['causal_efficacy_testing']
    assert all(v==0 for v in p['contamination'].values())


def test_static_source_contract_and_no_closed_phase_path():
    assert r.static_contract()['legacy_phase_not_computed']
    assert 'q.capture(*args)' in inspect.getsource(r.capture)
    assert 'q.qualification_hook,q.instrument=microstate_hook,instrument' in inspect.getsource(r.read_only_capture_hooks)
    assert 'synchronize_paused' in inspect.getsource(r.microstate_hook)
    assert "max_attempts=1" in inspect.getsource(r.read_packet)
    text=r.SOURCE.read_text()
    for token in ['.ResetPosition(', 'JointPositionReset','SetForce(', 'SetVelocity(', 'SetPosition(', 'msgs::Twist','multi_step']:
        assert token not in text
    assert 'phase_from(' not in Path(r.__file__).read_text() and 'phases(' not in Path(r.__file__).read_text()


def test_solver_public_api_audit():
    a=r.solver_audit();assert a['classification']=='SOLVER_INTERNAL_STATE_NOT_PUBLICLY_OBSERVABLE'
    assert a['public_readbacks']['GetContactsFromLastStep'] and a['public_readbacks']['GetTransmittedWrench']
    assert not a['private_engine_access'] and not a['engine_mutation'] and not a['Gazebo_patch']
    assert a['installed_binary_sha256'] and a['DART_exported_getters']
    assert 'do not supply live DART' in a['DART_access_limit']


def test_ledger_schedule_not_reusable_and_no_automatic_rerun():
    ledger={'slots':[{'spec':s,'state':'SCHEDULED'} for s in r.schedule()]};assert r.validate_ledger(ledger)
    ledger['slots'][0]['spec']=r.schedule()[1]
    with pytest.raises(ValueError):r.validate_ledger(ledger)
    source=inspect.getsource(r.run)
    assert 'prospective block cannot resume or overwrite' in source and source.count('record=capture(')==1
    assert 'prior shutdown unproven' in source and 'verify_lifecycle(' in source


def test_production_sha_guard_and_prior_evidence():
    assert r.protocol()['production_sha256']=='92def637ff4da2be1348502d345a30721cc845c34704f0b125d4ff1a26fdcc55'
    assert 'production SHA changed' in inspect.getsource(r.preflight)
    assert 'preservation.DEFAULT_OUTPUT' in inspect.getsource(r.guard_manifest)


def test_preflight_artifacts_if_present():
    pfpath=r.DEFAULT_OUTPUT/'microstate_preflight.json'
    if not pfpath.exists():pytest.skip('static preflight not built yet')
    pf=json.loads(pfpath.read_text());assert pf['status']=='PREFLIGHT_PASS' and all(pf['gates'].values())
    assert len(pf['definitions'])==10 and not list(r.DEFAULT_OUTPUT.rglob('*.ndjson'))
    assert pf['production_sha_before']==pf['production_sha_after']==r.g.EXPECTED_SHA
    for definition in pf['definitions']:
        r.validate_sdf(definition['sdf']);assert r.g.sha(definition['production_sdf'])==r.g.EXPECTED_SHA
    r.g.history.verify_manifest(pf['guard_manifest'])


@pytest.mark.parametrize('mutation',['valid','duplicate_partition','duplicate_topic','overlap','nonzero_exit','missing_shutdown','multiple_launches','identity'])
def test_fresh_process_lifecycle_and_transport_isolation(mutation):
    rec={'shutdown_completed':True,'runtime_identity':{'partition':'new','topic':'/new'}}
    launch={'event':'launch','wall_monotonic_s':10.,'status':{'status':'Running','available':True,'pid':123,'partition':'new'}}
    close={'event':'close','wall_monotonic_s':20.,'exit_code':0,'pid':123,'partition':'new'}
    life={'events':[launch,close],**{k:True for k in ['shutdown_proven','fresh_single_server','observer_subscriptions_closed','qualification_transport_closed']}}
    parts=set();topics=set();previous=5.
    if mutation=='duplicate_partition':parts.add('new')
    elif mutation=='duplicate_topic':topics.add('/new')
    elif mutation=='overlap':previous=11.
    elif mutation=='nonzero_exit':close['exit_code']=1
    elif mutation=='missing_shutdown':life['qualification_transport_closed']=False
    elif mutation=='multiple_launches':life['events'].insert(0,copy.deepcopy(launch))
    elif mutation=='identity':close['pid']=124
    if mutation=='valid':assert r.verify_lifecycle(rec,life,previous,parts,topics)==20. and parts=={'new'} and topics=={'/new'}
    else:
        with pytest.raises(r.g.InvalidCapture):r.verify_lifecycle(rec,life,previous,parts,topics)


@pytest.mark.parametrize('mutation',['payload','reordered_pause','read_retry','malformed'])
def test_observation_request_protocol_evidence(mutation):
    s=r.schedule()[1];rec=fixture(s)
    if mutation=='payload':rec['command_audit'][0]['payload']={'data':1}
    elif mutation=='reordered_pause':rec['command_audit'][4],rec['command_audit'][5]=rec['command_audit'][5],rec['command_audit'][4]
    elif mutation=='read_retry':rec['command_audit'][0]['transport_evidence']['attempts']*=2
    else:rec['command_audit'][0].pop('service')
    with pytest.raises(r.g.InvalidCapture):r.analyze(rec,s)


@pytest.mark.parametrize('spec',r.schedule(),ids=lambda s:'Host1_'+s['case_id'])
def test_exact_Host1_failure_signature_and_raw_capture_distinction(spec):
    failure=json.loads(r.HOST1_FORENSICS.read_text())
    row=next(x for x in failure['ten_case_failure_matrix'] if x['case_id']==spec['case_id'])
    assert row['exception_type']=='RuntimeError' and row['exception_message']=='case result readback mismatch'
    assert row['first_failed_predicate']['predicate']=='json.loads(result_path.read_text()) != record'
    assert not row['analyzer_reached'] and not row['capture_valid']
    assert row['raw_salvageability']=='RAW_CAPTURE_PARTIAL'
    raw=[json.loads(line) for line in (r.HOST1/spec['case_id']/'physical_microstate.ndjson').read_text().splitlines()]
    assert len(raw)==7+spec['iterations']
    assert all([t['stage'] for t in p['callback_trace']]==list(r.STAGES) for p in raw)
    for p in raw:
        decoded=r.decorate(copy.deepcopy(p))
        assert decoded['microstate']['solver_internal_state'] is None
        assert decoded['microstate']['normal_relative_velocity_m_s'] is None
        assert decoded['microstate']['tangential_relative_velocity_m_s'] is None
        assert all(v['component_producer_stamp_ns'] is None for v in decoded['microstate']['supports'].values())
    requests=[x for x in raw if x['event']!='advancing_observation']
    assert requests[4]['iteration']-requests[2]['iteration']==spec['iterations']
    assert requests[4]['sim_time_ns']-requests[2]['sim_time_ns']==spec['sim_time_delta_ns']
    # Endpoint JSON is useful, but it cannot replace the lost full capture/audit.
    with pytest.raises(r.g.InvalidCapture,match='incomplete'):
        r.analyze({'phase_qualification':{'packets':[],'failed_stage':'case_result_JSON_readback'}},spec)


def test_metadata_tuple_failure_reproduced_and_list_repair_proven_in_real_instrumentation(tmp_path):
    original=next(r.HOST1.glob('*/world/*/world.sdf'))
    target=tmp_path/'diagnostic.sdf';target.write_bytes(original.read_bytes())
    info={'native':{'topic':'/offline/metadata/regression'}}
    _,info=r.instrument(target,info,tmp_path/'not_loaded.so',r.schedule()[0]['case_id'],tmp_path)
    assert type(info['microstate_observer']['callback_stages']) is list
    assert json.loads(json.dumps(info,allow_nan=False))==info
    old=copy.deepcopy(info);old['microstate_observer']['callback_stages']=r.STAGES
    assert json.loads(json.dumps(old,allow_nan=False))!=old
    assert inspect.getsource(r.instrument).count('JSON roundtrip stable')==1
    harness=Path(r.g.ab.__file__).read_text()
    assert 'if json.loads(result_path.read_text()) != record:' in harness
    assert 'raise RuntimeError("case result readback mismatch")' in harness


def test_Host1_common_failure_proof_and_hash_immutability(monkeypatch):
    failure=r.host1_failure_contract()
    assert failure['common_failure_test'].startswith('A:')
    assert len(failure['normalized_failure_signatures'])==1 and failure['normalized_failure_signatures'][0]['count']==10
    assert failure['aggregate_failure_classification']=='SERIALIZATION_FAILURE'
    assert failure['repair_decision']['choice']=='C'
    original_sha=r.g.sha
    first=r.HOST1/failure['original_Host1_inventory'][0]['path']
    monkeypatch.setattr(r.g,'sha',lambda path:'changed' if Path(path)==first else original_sha(path))
    with pytest.raises(ValueError,match='immutable Host1 evidence changed'):r.host1_failure_contract()


def test_Host2_fresh_destination_and_preflight_failure_gates():
    assert r.DEFAULT_OUTPUT.name.endswith('phase3hanr-host2') and r.DEFAULT_OUTPUT!=r.HOST1
    assert not list(r.DEFAULT_OUTPUT.glob('*/case_result.json'))
    assert not list(r.DEFAULT_OUTPUT.rglob('*.ndjson'))
    required={'HOST1_FAILURE_EXPLAINED','HOST1_PRESERVED','REPAIR_DIAGNOSTIC_ONLY','ZERO_ADVANCEMENT_EXACT',
      'ONE_ADVANCEMENT_EXACT_1MS','NO_TREATMENT_COMMAND','NO_POSE_RESET','NO_PRODUCTION_SENSOR_CONSUMPTION',
      'NO_ACTION24_UP','OPTIONAL_CHANNELS_HONESTLY_UNAVAILABLE','CALLBACK_ASSUMPTIONS_RUNTIME_SUPPORTED',
      'SOLVER_INTERNAL_STATE_NOT_PUBLICLY_OBSERVABLE','HOST2_DESTINATION_FRESH','PRODUCTION_SHA_UNCHANGED'}
    assert required<=set(r.GATES)
    assert 'list(STAGES)' in inspect.getsource(r.instrument)
    assert r.protocol()['ZERO']=={'extra_iterations':0,'extra_sim_time_ns':0,'advancement_requests':0}
    assert r.protocol()['ONE']=={'extra_iterations':1,'extra_sim_time_ns':1000000,'advancement_requests':1}
    with pytest.raises(ValueError,match='Host2'):r.preflight(r.HOST1)
