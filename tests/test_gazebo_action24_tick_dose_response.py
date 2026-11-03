"""AN-I offline dose protocol and orchestration tests; live launch forbidden."""
import copy
import json
from collections import Counter
from types import SimpleNamespace

import pytest
from tools import diagnose_v07_gazebo_action24_tick_dose_response as d


@pytest.fixture(autouse=True)
def no_gazebo(monkeypatch):
    from aero_ai_studio.gazebo.process_manager import GazeboProcessManager
    def fail(*a,**k):raise AssertionError('OFFLINE TEST: GAZEBO FORBIDDEN')
    monkeypatch.setattr(GazeboProcessManager,'launch',fail)
    monkeypatch.setattr(d.g.ab,'_run_case',fail)


def test_exact_25_balanced_interleaved_cases():
    rows=d.schedule()
    assert len(rows)==25 and len({r['case_id'] for r in rows})==25
    assert Counter(r['tick_count'] for r in rows)=={n:5 for n in range(5)}
    for n in range(5):
        assert {r['replicate_id'] for r in rows if r['tick_count']==n}=={f'R{j}' for j in range(1,6)}
        assert sorted((r['ordinal']-1)%5 for r in rows if r['tick_count']==n)==list(range(5))
    assert [r['tick_count'] for r in rows[:10]]==[0,1,2,3,4,1,2,3,4,0]


def test_schedule_freezes_and_rejects_tampering(tmp_path):
    frozen=d.freeze_files(tmp_path)
    assert d.load_frozen(tmp_path)==d.schedule()
    assert frozen==d.freeze_files(tmp_path)
    rows=d.schedule();rows.reverse()
    (tmp_path/'prospective_schedule.json').write_text(json.dumps(rows))
    with pytest.raises(d.InvalidCapture):d.load_frozen(tmp_path)
    with pytest.raises(d.InvalidCapture):d.freeze_files(tmp_path)


@pytest.mark.parametrize('n',range(5))
def test_plan_canonical_DOWN_and_exact_tick_contract(n):
    name=f'TICK_{n}_R3';p=d.plan(name)
    assert p['actions']==d.g.SUFFIX
    assert p['canonical_indices']==list(range(8,25))
    assert p['terminal_suffix']==['23 DOWN','production BRAKE_LINEAR','production stopped contract','24 UP +0.5']
    assert p['scenario_seed']==42 and p['reset_seed']==43
    with d.dose_plans():
        assert d.g.tick_count(name)==n
        d.g.verify_treatment(name,{'iteration':3600,'sim_time_ns':3_600_000_000,'paused':True},
            {'iteration':3600+n,'sim_time_ns':3_600_000_000+n*1_000_000,'paused':True},42,42,0)
        for extra in (n+1,n-1):
            with pytest.raises(d.InvalidCapture):
                d.g.verify_treatment(name,{'iteration':3600,'sim_time_ns':3_600_000_000,'paused':True},
                    {'iteration':3600+extra,'sim_time_ns':3_600_000_000+extra*1_000_000,'paused':True},42,42,0)


@pytest.mark.parametrize('n',range(1,5))
def test_single_advance_calls_step_once_with_N_no_retry(n,monkeypatch):
    from aero_ai_studio.gazebo.stepping import GazeboStepper
    calls=[]
    class Probe:
        def __init__(self,*a,**k):self.time=0
        def step_simulation(self,n_steps=1):
            assert self.STEP_RETRIES==0
            calls.append(n_steps)
            self.time+=n_steps*.001
            self.last_verification={'valid':True,'iteration_delta':n_steps}
    monkeypatch.setattr('aero_ai_studio.gazebo.stepping.GazeboStepper',Probe)
    adapter=SimpleNamespace(env=SimpleNamespace(transport=None,stepper=SimpleNamespace(world='w',time=3.6,timeout=1)))
    d.single_advance(adapter,n)
    assert calls==[n]
    assert adapter.env.stepper.time==pytest.approx(3.6+n*.001)


def test_zero_cannot_call_advancement_and_context_restores():
    with pytest.raises(d.InvalidCapture):d.single_advance(None,0)
    old,advance=d.g.plan,d.g.advance_ticks
    with pytest.raises(RuntimeError):
        with d.dose_plans():
            assert d.g.advance_ticks is d.single_advance
            raise RuntimeError('fixture')
    assert d.g.plan is old and d.g.advance_ticks is advance


def mark(i,ns):
    return {'iteration':i,'sim_time_ns':ns,'paused':True,'stats_source':'transport_snapshot',
            'observed_snapshot':{'iterations_normalized':i,'paused':True,
                                'sim_time':{'sec':str(ns//1_000_000_000),'nsec':ns%1_000_000_000}}}


def record(n):
    events=[{'kind':'RPC','request_type':'Empty','service':'/native/checkpoint','payload':{}}]
    if n:events.append({'kind':'RPC','request_type':'WorldControl','payload':{'pause':True,'multi_step':n}})
    events.extend([{'kind':'RPC','request_type':'WorldControl','payload':{'pause':True}},
                   {'kind':'RPC','request_type':'Empty','service':'/native/checkpoint','payload':{}}])
    end=mark(3600+n,3_600_000_000+n*1_000_000)
    return {'one_tick_treatment':{'boundary_marker':mark(3600,3_600_000_000),
             'post_marker':end,'before_UP_publication_marker':copy.deepcopy(end),
             'window_start_cursor':0,'window_end_cursor':len(events)},'command_audit':events}


@pytest.mark.parametrize('n',range(5))
def test_exact_integer_stats_and_request_count(n):
    r=record(n);proof=d.exact_treatment(r,n)
    assert proof['iterations']==n and proof['elapsed_ns']==n*1_000_000
    assert proof['advancement_request_count']==bool(n)
    r['one_tick_treatment']['post_marker']['observed_snapshot']['sim_time']['nsec']+=1
    with pytest.raises(d.InvalidCapture):d.exact_treatment(r,n)


def test_N_separate_step_requests_invalid_even_if_final_duration_matches():
    r=record(3);r['command_audit'][1:2]=[{'kind':'RPC','request_type':'WorldControl','payload':{'pause':True,'multi_step':1}} for _ in range(3)]
    r['one_tick_treatment']['window_end_cursor']=len(r['command_audit'])
    with pytest.raises(d.InvalidCapture,match='one advancement'):d.exact_treatment(r,3)


@pytest.mark.parametrize('change',['float_ns','fallback','wrong_iterations'])
def test_no_float_rounding_or_reconstructed_timestamp(change):
    m=mark(3600,3_600_000_000)
    if change=='float_ns':m['observed_snapshot']['sim_time']['nsec']=600000000.0
    elif change=='fallback':m['stats_source']='verified_stepper_WorldStatistics'
    else:m['observed_snapshot']['iterations_normalized']=3601
    with pytest.raises(d.InvalidCapture):d.exact_stats(m)


@pytest.mark.parametrize('kind',['pose','twist','worldpose'])
def test_treatment_command_guards_remain_strict(kind):
    if kind=='worldpose':
        with pytest.raises(d.InvalidCapture):d.g.pose_command_counter({'world_pose_command_audit':{'enabled':True,'active_component_count':1}})
    else:
        item={'kind':'RPC','service':'/world/x/set_pose'} if kind=='pose' else {'kind':'TWIST'}
        with pytest.raises(d.InvalidCapture):d.g.audit_window([item],0,1)


def result_rows(success_counts,invalid=None,other=None):
    invalid=invalid or {};other=other or {};out=[]
    for slot in d.schedule():
        n=slot['tick_count'];rep=int(slot['replicate_id'][1:]);valid=rep>invalid.get(n,0)
        status=d.SUCCESS if rep<=invalid.get(n,0)+success_counts[n] else 'OTHER_PHYSICAL_OUTCOME' if rep<=invalid.get(n,0)+success_counts[n]+other.get(n,0) else d.FAILURE
        v={**slot,'case_valid':valid,'status':'VALID' if valid else 'CAPTURE_INVALID','invalid_reasons':[] if valid else ['fixture infrastructure error']}
        if valid:v['analysis']={'classification':status,'native_displacement_m':.03 if status==d.SUCCESS else 0.,
            'Pose_V_displacement_m':.03 if status==d.SUCCESS else 0.,'final_forward_velocity_m_s':.5 if status==d.SUCCESS else 0.,
            'support_recovery_ms':7 if status==d.SUCCESS else None,
            'events':{k:None for k in ('first_drive_unloading_ms','first_caster_takeover_ms','first_both_drive_recovery_ms','first_sustained_drive_recovery_ms','first_material_translation_ms')}}
        out.append(v)
    return out


@pytest.mark.parametrize('successes,expected',[([0,5,5,5,5],'PATTERN_A_THRESHOLD'),
 ([0,1,2,3,4],'PATTERN_B_GRADED'),([0,3,1,4,2],'PATTERN_C_NON_MONOTONIC'),
 ([0,0,0,0,0],'PATTERN_D_NO_REPRODUCIBLE_TICK_EFFECT'),([1,5,5,5,5],'PATTERN_E_BASELINE_UNSTABLE')])
def test_prospective_pattern_logic(successes,expected):
    p=d.classify_pattern(d.dose_table(result_rows(successes)))
    assert p['primary_classification']==expected
    assert p['strong_complete_threshold']==(successes==[0,5,5,5,5])


def test_invalids_excluded_and_never_physical_failure():
    rows=result_rows([0,3,5,5,5],{1:2})
    table=d.dose_table(rows)
    assert table[1]['valid_replicates']==3 and table[1]['invalid_replicates']==2
    assert table[1]['success_count']==3 and table[1]['failure_count']==0
    assert table[1]['success_rate']==1
    assert table[1]['native_displacement_m']['n_observed']==3
    assert d.classify_pattern(table)['primary_classification']=='PATTERN_F_CAPTURE_INADEQUATE'


def test_missing_baseline_is_not_claimed_as_physical_instability():
    p=d.classify_pattern(d.dose_table(result_rows([0,4,5,5,5],{0:1,1:1})))
    assert not p['strong_complete_threshold']
    assert 'BASELINE_CAPTURE_INCOMPLETE_NOT_PHYSICAL_VARIABILITY' in p['descriptive_flags']
    assert 'BASELINE_OUTCOME_VARIABILITY_OR_FAILURE_NONREPRODUCTION' not in p['descriptive_flags']


def test_baseline_success_retained_not_case_invalidated():
    table=d.dose_table(result_rows([2,5,5,5,5]))
    assert table[0]['valid_replicates']==5 and table[0]['failure_count']==3 and table[0]['success_count']==2
    assert d.classify_pattern(table)['primary_classification']=='PATTERN_E_BASELINE_UNSTABLE'


def test_other_outcome_not_silently_counted_as_failure():
    table=d.dose_table(result_rows([0,3,5,5,5],other={1:2}))
    assert table[1]['other_count']==2 and table[1]['failure_count']==0


def test_no_overwrite_accepted_or_primary_runtime_evidence(tmp_path):
    with pytest.raises(FileExistsError):d.ensure_output(d.g.DEFAULT_OUTPUT)
    (tmp_path/'case_result.json').write_text('preserve')
    with pytest.raises(FileExistsError):d.ensure_output(tmp_path)
    assert (tmp_path/'case_result.json').read_text()=='preserve'


def test_default_CLI_cannot_launch(monkeypatch):
    monkeypatch.setattr(d,'run',lambda *a:pytest.fail('unintentional runtime dispatch'))
    assert d.main([])==1


@pytest.mark.parametrize('shutdown_proven', [False, True])
def test_primary_orchestrator_no_reruns_and_shutdown_fence(tmp_path, monkeypatch, shutdown_proven):
    output=tmp_path/'experiment'
    frozen=d.freeze_files(output)
    d.g.history.write_json(output/'tick_dose_preflight.json', {
        'status':'PREFLIGHT_PASS','runner_sha256':d.g.sha(d.__file__),
        'helper_sha256':d.g.sha(d.g.__file__),'frozen_file_sha256':frozen,
        'protected_source_sha256_before_after':{}})
    monkeypatch.setattr(d,'protected_manifest',lambda:{})
    monkeypatch.setattr(d,'self_check',lambda:None)
    monkeypatch.setattr(d.g,'production_sensor_order_contract',lambda:None)
    monkeypatch.setattr(d.g.history,'source',lambda _: (None,43,None))
    monkeypatch.setattr(d,'load_reference',lambda:{})
    monkeypatch.setattr(d.g.ab,'_build_all',lambda _: ({},{}))
    monkeypatch.setattr(d.g,'verify_static_builds',lambda _:None)
    calls=[]
    def invalid_case(case,scenario,directory,*args):
        calls.append(case)
        d.g.history.write_json(directory/'process_lifecycle.json',{'shutdown_proven':shutdown_proven})
        raise d.InvalidCapture('fixture capture failure')
    monkeypatch.setattr(d,'capture_case',invalid_case)
    report=d.run(output)
    assert calls==[r['case_id'] for r in d.schedule()][:25 if shutdown_proven else 1]
    assert len(report['case_results'])==25
    assert all(not r['case_valid'] for r in report['case_results'])
    assert all(r['primary_prospective'] and not r['post_hoc'] for r in report['case_results'])
    assert sum(r['failure_count'] for r in report['dose_response_table'])==0
    assert report['primary_classification']=='PATTERN_F_CAPTURE_INADEQUATE'


def test_all_numeric_microstate_components_summarized_without_linearity_assumption():
    rows=result_rows([0,5,5,5,5])
    for r in rows:
        n=r['tick_count'];a=r['analysis']
        a.update(S0={},frozen_feature_deltas={},event_relative_trajectory=[],
                 all_saved_numeric_deltas={'native_wheel_links.left.velocity':float(n*n)})
    report=d.aggregate(rows)
    component=report['all_numeric_S1_minus_S0_by_dose']['native_wheel_links.left.velocity']
    assert [component[str(n)]['median'] for n in range(5)]==[0.,1.,4.,9.,16.]
    assert all(component[str(n)]['n_observed']==5 for n in range(5))


def test_capture_lifecycle_records_fresh_server_and_observer_each_case(tmp_path,monkeypatch):
    from aero_ai_studio.gazebo.process_manager import GazeboProcessManager
    Native=d.g.ab.native.NativeVelocityCapture
    monkeypatch.setattr(GazeboProcessManager,'launch',lambda manager,*a,**k: manager.status())
    monkeypatch.setattr(GazeboProcessManager,'close',lambda manager: setattr(manager.process,'returncode',0))
    monkeypatch.setattr(Native,'subscribe',lambda native,*a,**k: setattr(native,'subscribed',True))
    class Process:
        returncode=None
        def __init__(self,pid):self.pid=pid
        def poll(self):return self.returncode
    identities=[]
    def fake_capture(case,scenario,directory,*args):
        manager=GazeboProcessManager();manager.process=Process(100+len(identities))
        manager.launch(None)
        observer=SimpleNamespace(topic=case,subscribed=False)
        Native.subscribe(observer)
        observer.subscribed=False
        manager.close()
        identities.append((manager.partition,manager.process.pid))
        return {'case_id':case}
    monkeypatch.setattr(d.g,'capture',fake_capture)
    for case in ('TICK_0_R1','TICK_1_R1'):
        directory=tmp_path/case
        result=d.capture_case(case,None,directory,{},43,'test')
        ledger=result['dose_process_lifecycle']
        assert ledger['fresh_single_server_launch'] and ledger['shutdown_proven']
        assert ledger['observer_lifecycle_complete']
        assert (directory/'process_lifecycle.json').exists()
    assert len({p for p,pid in identities})==2
    assert len({pid for p,pid in identities})==2


def started_ledger():
    ledger=d.initial_ledger();slot=ledger['slots'][0]
    slot.update(state='STARTED',started_wall_monotonic_s=1.)
    slot['transitions'].append('STARTED')
    return ledger


def captured_ledger(invalid=False):
    ledger=started_ledger();slot=ledger['slots'][0]
    state='CAPTURE_INVALID' if invalid else 'CAPTURED'
    slot.update(state=state,capture_outcome=state,artifact_paths={} if invalid else {'case_result':'fixture.json'})
    if invalid:slot['invalid_reasons']=['fixture infrastructure failure']
    slot['transitions'].append(state)
    return ledger


def finalized_invalid(ledger,index):
    slot=ledger['slots'][index]
    slot.update(state='FINALIZED',transitions=['SCHEDULED','STARTED','CAPTURE_INVALID','SHUTDOWN_PROVEN','FINALIZED'],
        started_wall_monotonic_s=1.,capture_outcome='CAPTURE_INVALID',artifact_paths={},
        invalid_reasons=['fixture'],shutdown_proven=True,process_lifecycle={'shutdown_proven':True},
        result={'case_id':slot['case_id'],'case_valid':False,'status':'CAPTURE_INVALID','invalid_reasons':['fixture']})


@pytest.mark.parametrize('stage',['SCHEDULED','STARTED','CAPTURED','CAPTURE_INVALID','SHUTDOWN_PROVEN','FINALIZED'])
def test_incremental_ledger_every_intermediate_state(tmp_path,stage):
    ledger=d.initial_ledger() if stage=='SCHEDULED' else started_ledger() if stage=='STARTED' else captured_ledger(stage=='CAPTURE_INVALID')
    if stage=='SHUTDOWN_PROVEN':
        slot=ledger['slots'][0];slot.update(state=stage,shutdown_proven=True);slot['transitions'].append(stage)
    if stage=='FINALIZED':finalized_invalid(ledger,0)
    d.write_json(tmp_path/'ledger.json',ledger,d.validate_ledger)
    assert json.loads((tmp_path/'ledger.json').read_text())==ledger
    assert all(slot['state']=='SCHEDULED' for slot in ledger['slots'][1:])
    assert all('result' not in slot and 'started_wall_monotonic_s' not in slot for slot in ledger['slots'][1:])


def test_all25_finalized_and_malformed_completion_rejected(tmp_path):
    ledger=d.initial_ledger()
    for i in range(25):finalized_invalid(ledger,i)
    ledger['block_state']='FINISHED'
    d.write_json(tmp_path/'ledger.json',ledger,d.validate_ledger)
    del ledger['slots'][7]['result']['invalid_reasons']
    with pytest.raises(ValueError,match='incomplete FINALIZED'):
        d.write_json(tmp_path/'ledger.json',ledger,d.validate_ledger)
    assert json.loads((tmp_path/'ledger.json').read_text())['slots'][7]['result']['invalid_reasons']==['fixture']


def test_incomplete_valid_finalized_analysis_rejected():
    ledger=d.initial_ledger();finalized_invalid(ledger,0)
    ledger['slots'][0]['result'].update(case_valid=True,status='VALID',analysis={'classification':d.SUCCESS})
    with pytest.raises(ValueError,match='incomplete FINALIZED case analysis'):d.validate_ledger(ledger)


def test_exact_Host1_tuple_failure_reproduced_and_repaired(tmp_path):
    fixture=json.loads((d.FORENSICS/'serialization_fixture.json').read_text())
    for k,v in fixture['derived_native_contact_kinematics'].items():
        if isinstance(v,list):fixture['derived_native_contact_kinematics'][k]=tuple(v)
    legacy=tmp_path/'old.json'
    with pytest.raises(d.InvalidCapture,match='incomplete result serialization'):
        d.g.history.write_json(legacy,fixture)
    assert json.loads(legacy.read_text())!=fixture  # complete JSON; tuple/list mismatch
    repaired=tmp_path/'new.json';d.write_json(repaired,fixture)
    assert json.loads(repaired.read_text())==d.ledger_io.json_value(fixture)
    d.write_json(tmp_path/'zero_completed.json',d.initial_ledger(),d.validate_ledger)


@pytest.mark.parametrize('fault',['replace','fsync','nonserializable'])
def test_atomic_failure_keeps_previous_valid_ledger(tmp_path,monkeypatch,fault):
    path=tmp_path/'ledger.json';original=d.initial_ledger();d.write_json(path,original,d.validate_ledger)
    update=started_ledger()
    def fail(*a,**k):raise OSError('injected crash before commit')
    if fault=='replace':monkeypatch.setattr(d.ledger_io.os,'replace',fail)
    elif fault=='fsync':monkeypatch.setattr(d.ledger_io.os,'fsync',fail)
    else:update['bad']=object()
    with pytest.raises((OSError,ValueError)):d.write_json(path,update,d.validate_ledger)
    assert json.loads(path.read_text())==original
    assert not list(tmp_path.glob('*.tmp'))


def test_host1_immutable_host2_fresh_and_original_order():
    assert d.DEFAULT_OUTPUT.name.endswith('host2') and d.DEFAULT_OUTPUT!=d.HOST1
    assert d.schedule()==json.loads((d.HOST1/'prospective_schedule.json').read_text())
    with pytest.raises(FileExistsError):d.ensure_output(d.HOST1)
    with pytest.raises(FileExistsError):d.write_json(d.HOST1/'never_write.json',{})
    assert all(s['state']=='SCHEDULED' and 'result' not in s for s in d.initial_ledger()['slots'])


def test_Host1_inventory_hashes_and_launch_shutdown_evidence():
    inventory=json.loads((d.FORENSICS/'inventory.json').read_text())
    d.g.history.verify_manifest({f['path']:f['sha256'] for f in inventory['files']})
    lifecycle=json.loads((d.HOST1/'TICK_0_R1/process_lifecycle.json').read_text())
    assert lifecycle['events'][0]['status']['pid']==6744
    assert lifecycle['shutdown_proven'] and lifecycle['events'][-1]['exit_code']==0
    assert d.g.sha(d.HOST1/'TICK_0_R1/world/aero_ef81a06d3164/world.sdf')==d.g.EXPECTED_SHA


def test_process_safety_refuses_matching_prior_partition_without_killing(tmp_path):
    proc=tmp_path/'999999';proc.mkdir()
    (proc/'cmdline').write_bytes(b'gz\x00sim\x00world.sdf\x00')
    (proc/'environ').write_bytes(b'GZ_PARTITION=aero_9fd360c54e3c48ec950570b8f3ba280e\x00')
    with pytest.raises(d.InvalidCapture,match='prior diagnostic process still active'):d.process_safety(tmp_path)
    (proc/'environ').write_bytes(b'GZ_PARTITION=unrelated_user_world\x00')
    assert d.process_safety(tmp_path)['matching_processes']==[]
    assert proc.exists()


def test_full_mocked25_orchestration_serializes_real_tuple_shape(tmp_path,monkeypatch):
    output=tmp_path/'fresh';frozen=d.freeze_files(output)
    d.write_json(output/'tick_dose_preflight.json',{
        'status':'PREFLIGHT_PASS','runner_sha256':d.g.sha(d.__file__),
        'helper_sha256':d.g.sha(d.g.__file__),'frozen_file_sha256':frozen,
        'protected_source_sha256_before_after':{}})
    monkeypatch.setattr(d,'protected_manifest',lambda:{})
    monkeypatch.setattr(d,'self_check',lambda:None)
    monkeypatch.setattr(d,'process_safety',lambda: {})
    monkeypatch.setattr(d.g,'production_sensor_order_contract',lambda:None)
    monkeypatch.setattr(d.g.history,'source',lambda _: (None,43,None))
    monkeypatch.setattr(d,'load_reference',lambda:{})
    monkeypatch.setattr(d.g.ab,'_build_all',lambda _: ({},{}))
    monkeypatch.setattr(d.g,'verify_static_builds',lambda _:None)
    calls=[]
    def capture(case,*args):
        calls.append(case)
        return {'dose_process_lifecycle':{'shutdown_proven':True,'fresh_single_server_launch':True,'observer_lifecycle_complete':True},
            'shutdown_completed':True,'runtime_identity':{'partition':case,'topic':case},
            'wall_start_monotonic_s':len(calls)*2,'wall_end_after_shutdown_monotonic_s':len(calls)*2+1}
    monkeypatch.setattr(d,'capture_case',capture)
    monkeypatch.setattr(d.g,'validate',lambda *a: {'case_valid':True,'invalid_reasons':[]})
    monkeypatch.setattr(d,'exact_treatment',lambda *a:{})
    monkeypatch.setattr(d,'pre_controls',lambda *a:{'classification':'PRE_TREATMENT_ARMS_EQUIVALENT'})
    fixture=json.loads((d.FORENSICS/'serialization_fixture.json').read_text())['derived_native_contact_kinematics']
    for k,v in fixture.items():
        if isinstance(v,list):fixture[k]=tuple(v)
    def analyze(record,check,n):
        case=calls[-1]
        a=next(r['analysis'] for r in result_rows([0,5,5,5,5]) if r['case_id']==case)
        a.update(case_id=case,tick_count=n,T0={},S0={},S1={},S1_minus_S0={},
            frozen_feature_deltas={},all_saved_numeric_deltas={},
            event_relative_trajectory=[{'delta_ms':0,'iteration':1,'supports':{},'derived_native_contact_kinematics':fixture}])
        return a
    monkeypatch.setattr(d,'analyze_case',analyze)
    report=d.run(output)
    assert calls==[s['case_id'] for s in d.schedule()]
    assert report['status']=='CAPTURED'
    ledger=json.loads((output/'prospective_case_ledger.json').read_text())
    d.validate_ledger(ledger)
    assert ledger['block_state']=='FINISHED'
    assert all(s['state']=='FINALIZED' and s['shutdown_proven'] for s in ledger['slots'])


def test_truncated_temporary_write_is_rejected_before_replace(tmp_path,monkeypatch):
    path=tmp_path/'ledger.json';original=d.initial_ledger();d.write_json(path,original,d.validate_ledger)
    fsync=d.ledger_io.os.fsync
    def truncate(fd):
        for temporary in tmp_path.glob('*.tmp'):
            temporary.write_text('{"slots":')
        fsync(fd)
    monkeypatch.setattr(d.ledger_io.os,'fsync',truncate)
    with pytest.raises(json.JSONDecodeError):d.write_json(path,started_ledger(),d.validate_ledger)
    assert json.loads(path.read_text())==original


def test_offline_preflight_ledger_contract_uses_real_writers():
    d.ledger_contract_self_check()
