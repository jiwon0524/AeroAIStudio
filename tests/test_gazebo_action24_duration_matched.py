import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import diagnose_v07_gazebo_action24_duration_matched as dm
from test_gazebo_action24_history_restoration import samples, record_from_rows, movement


def test_exact_canonical_suffix_and_preparation_intents():
    expected='left up down left down left right left up up right left left up down up'.split()
    for case in dm.CASES:
        p=dm.plan(case)
        assert p['actions'][1:]==expected
        assert p['canonical_indices'][1:]==list(range(9,25))
        assert p['actions'][-2:]==['down','up']
    assert dm.plan('CONTROL_SHAM')['actions'][0]=='neutral_sham'
    assert dm.plan('CONTROL_SHAM')['canonical_indices'][0] is None
    assert dm.plan('RIGHT_HISTORY')['actions'][0]=='right'
    assert dm.plan('RIGHT_HISTORY')['canonical_indices'][0]==8


def fake_adapter():
    calls=[]
    class Stepper:
        physics_dt=.001;dt=.1;time=.2;iteration=200;last_verification={}
        def _snapshot(self):
            return {'data':{'iterations':self.iteration,'paused':True,'sim_time':{'nsec':round(self.time*1e9)}},'sequence':self.iteration}
        def step_simulation(self):
            calls.append('physics');self.time+=.1;self.iteration+=100
            self.last_verification={'valid':True,'iteration_delta':100}
        def reset_world(self):raise AssertionError('reset forbidden')
    class Controller:
        publish_sequence=1;last_published_command={}
        def stop_agent(self):
            calls.append('neutral');self.publish_sequence+=1
            self.last_published_command={'linear':{'x':0.},'angular':{'z':0.}}
        def reset_agent_pose(self,*a):raise AssertionError('reposition forbidden')
    env=SimpleNamespace(stepper=Stepper(),controller=Controller(),_refresh=lambda:calls.append('refresh'),
        contacts=SimpleNamespace(reset=lambda *a:(_ for _ in ()).throw(AssertionError('contact reset forbidden'))))
    return SimpleNamespace(env=env),calls


def test_sham_advances_exact_physics_duration_without_reset_or_reposition():
    adapter,calls=fake_adapter()
    result=dm.neutral_advance(adapter)
    assert calls==['neutral','physics','refresh']
    assert result['start']['iteration']==200 and result['end']['iteration']==300
    assert result['advancing_iterations']==100 and result['simulation_duration_ns']==100_000_000
    assert result['action_publication']['commanded_twist']=={'linear':{'x':0.},'angular':{'z':0.}}
    assert result['semantics']['wall_clock_wait_used'] is False


def test_invalid_preparation_progress_fails():
    adapter,_=fake_adapter()
    adapter.env.stepper.step_simulation=lambda:None
    with pytest.raises(dm.history.InvalidCapture):dm.neutral_advance(adapter)


def test_wrong_neutral_command_fails():
    adapter,_=fake_adapter()
    adapter.env.controller.stop_agent=lambda:setattr(adapter.env.controller,'last_published_command',{'linear':{'x':.5}})
    with pytest.raises(dm.history.InvalidCapture):dm.neutral_advance(adapter)


def initial_state():
    return {'iteration':200,'sim_time_ns':200_000_000,'position_world_m':[1.5,1.5,.1096],
        'orientation_world_xyzw':[0.,0.,0.,1.], 'wheel_phase_mod_2pi_rad':{'left':0.,'right':0.},
        'supports':{k:{'state':'VALID_CONTACTS','Fn_N':5.} for k in ('left_wheel','right_wheel','front_caster','rear_caster')}}


def pair_records():
    prep={'start':{'iteration':200,'sim_time_ns':200_000_000,'sim_time_s':.2},
        'end':{'iteration':300,'sim_time_ns':300_000_000,'sim_time_s':.3},
        'advancing_iterations':100,'simulation_duration_ns':100_000_000}
    config={'scenario_seed':42,'reset_seed':43,'target':{'name':'simple_agent','position':{'x':1.5,'y':1.5,'z':.16}}}
    return {case:{'preparation':copy.deepcopy(prep),'configured_reset_condition':copy.deepcopy(config),
        'runtime_identity':{'partition':case,'topic':'/aero/'+case}} for case in dm.CASES}


def test_identical_canonical_reset_configuration_and_duration_match(monkeypatch):
    monkeypatch.setattr(dm,'state_at',lambda *a:initial_state())
    pair=pair_records();result=dm.pair_controls(pair)
    assert result['duration_equality_verified']
    assert result['initial_comparison']['classification']=='INITIAL_STATE_EQUIVALENT'
    assert result['SHAM']['advancing_iterations']==result['RIGHT']['advancing_iterations']==100


@pytest.mark.parametrize('field', ['advancing_iterations','simulation_duration_ns'])
def test_duration_mismatch_cannot_classify(monkeypatch,field):
    monkeypatch.setattr(dm,'state_at',lambda *a:initial_state())
    pair=pair_records();pair['RIGHT_HISTORY']['preparation'][field]+=1
    with pytest.raises(dm.history.InvalidCapture):dm.pair_controls(pair)


def test_different_reset_configuration_fails_pair(monkeypatch):
    monkeypatch.setattr(dm,'state_at',lambda *a:initial_state())
    pair=pair_records();pair['RIGHT_HISTORY']['configured_reset_condition']['reset_seed']=42
    with pytest.raises(dm.history.InvalidCapture):dm.pair_controls(pair)


def test_material_initial_phase_difference_rejected(monkeypatch):
    pair=pair_records()
    def state(record,*args):
        result=initial_state()
        if record is pair['RIGHT_HISTORY']:result['wheel_phase_mod_2pi_rad']['left']=.168
        return result
    monkeypatch.setattr(dm,'state_at',state)
    with pytest.raises(dm.history.InvalidCapture):dm.pair_controls(pair)


def test_command_active_t0_separate_from_first_motion():
    record=record_from_rows(samples())
    t0=dm.history.command_active_t0(record)
    assert t0['iteration']==11
    assert t0['first_observed_wheel_actuation']=={'kind':'FIRST_OBSERVED_WHEEL_ACTUATION','iteration':12,'delta_ms':1}


@pytest.mark.parametrize('case,success_label,failure_label',[
    ('CONTROL_SHAM','DURATION_MATCHED_SHAM_SUCCESS','DURATION_MATCHED_SHAM_CANONICAL_FAILURE'),
    ('RIGHT_HISTORY','RIGHT_HISTORY_SUCCESS','RIGHT_HISTORY_CANONICAL_FAILURE')])
def test_existing_strict_contracts_and_temporary_unloading(case,success_label,failure_label):
    success=movement(record_from_rows(samples()),True)
    failure=movement(record_from_rows(samples(persistent=True)),False)
    assert dm.case_outcome(case,dm.history.classify_candidate(success,{'case_valid':True})['classification'])==success_label
    assert dm.case_outcome(case,dm.history.classify_candidate(failure,{'case_valid':True})['classification'])==failure_label


def test_invalid_telemetry_never_gets_physical_classification(monkeypatch):
    monkeypatch.setattr(dm.history,'classify_candidate',lambda *a:(_ for _ in ()).throw(AssertionError('must not classify')))
    with pytest.raises(dm.history.InvalidCapture):dm.analyze({}, {})


@pytest.mark.parametrize('sham,right,expected',[
 ('DURATION_MATCHED_SHAM_SUCCESS','RIGHT_HISTORY_CANONICAL_FAILURE','ACTION08_RIGHT_HISTORY_REQUIRED_BEYOND_ELAPSED_TIME_CONTROL'),
 ('DURATION_MATCHED_SHAM_CANONICAL_FAILURE','RIGHT_HISTORY_CANONICAL_FAILURE','EXTRA_ELAPSED_PHYSICS_TIME_SUFFICIENT_TO_REPRODUCE_FAILURE'),
 ('DURATION_MATCHED_SHAM_SUCCESS','RIGHT_HISTORY_SUCCESS','H15_FAILURE_NOT_REPRODUCED_IN_MATCHED_CONTROL'),
 ('DURATION_MATCHED_SHAM_CANONICAL_FAILURE','RIGHT_HISTORY_SUCCESS','MATCHED_CONTROL_RESULT_UNRESOLVED'),
 ('OTHER_PHYSICAL_OUTCOME','RIGHT_HISTORY_CANONICAL_FAILURE','MATCHED_CONTROL_RESULT_UNRESOLVED')])
def test_exact_pair_interpretation(sham,right,expected):
    assert dm.interpretation(sham,right)==expected


def test_two_fresh_capture_paths_and_no_sham_directional_action(monkeypatch,tmp_path):
    from aero_ai_studio.training import gazebo_physics
    from aero_ai_studio.gazebo.process_manager import GazeboProcessManager
    seen=[]
    class Base:
        def __init__(self):
            adapter,calls=fake_adapter();self.env=adapter.env;self.calls=calls;self.partition=GazeboProcessManager().partition
            seen.append(self)
        def step(self,action):
            self.calls.append(action);self.env.stepper.step_simulation()
            return SimpleNamespace(reason='moving',terminated=False)
    monkeypatch.setattr(gazebo_physics,'GazeboPhysicsTrainingEnvironment',Base)
    def capture(plan,scenario,output,libraries,seed,runtime_namespace):
        env=gazebo_physics.GazeboPhysicsTrainingEnvironment();events=[]
        for index,action in zip(plan['canonical_indices'],plan['actions']):
            start=env.env.stepper.time;env.step(action)
            events.append({'canonical_index':index,'action':action,'start_sim_time':start,'end_sim_time':env.env.stepper.time})
        return {'events':events,'runtime_identity':{'partition':env.partition,'topic':'/aero/'+plan['name']+'/'+runtime_namespace},
            'runtime_namespace':runtime_namespace}
    monkeypatch.setattr(dm.history,'capture_candidate',capture)
    monkeypatch.setattr(dm.history,'reset_validity',lambda *a:{'configured_reset_condition':{},'measured_reset_state':{}})
    a=dm.capture('CONTROL_SHAM',None,tmp_path/'sham',{},43,'run')
    b=dm.capture('RIGHT_HISTORY',None,tmp_path/'right',{},43,'run')
    assert seen[0].calls[:4]==['neutral','physics','refresh','left']
    assert seen[1].calls[0]=='right'
    assert a['runtime_identity']['partition']!=b['runtime_identity']['partition']
    assert a['runtime_identity']['topic']!=b['runtime_identity']['topic']
    assert a['events'][0]['canonical_index'] is None
    assert [e['action'] for e in a['events'][1:]]==list(dm.SUFFIX)
    assert gazebo_physics.GazeboPhysicsTrainingEnvironment is Base


def test_preflight_no_runtime_evidence_and_no_source_changes(monkeypatch,tmp_path):
    scenario=SimpleNamespace(seed=42,start=(1,1))
    monkeypatch.setattr(dm.history,'source',lambda *a:(scenario,43,{}))
    production=tmp_path/'production.sdf';production.write_text('unchanged')
    guard={str(production):dm.ab._sha(production)}
    monkeypatch.setattr(dm,'protected_manifest',lambda:guard)
    reference=tmp_path/'reference.json';reference.write_text(json.dumps({'executed_histories':{'H15':[
        {'canonical_index':8,'action':'right','start_sim_time_s':.2,'end_sim_time_s':.3}]}}))
    monkeypatch.setattr(dm,'REFERENCE',reference)
    diagnostic=tmp_path/'diagnostic.sdf';diagnostic.write_text('<sdf><world><physics><max_step_size>.001</max_step_size></physics></world></sdf>')
    monkeypatch.setattr(dm.ab,'_build_all',lambda *a:({},{}))
    monkeypatch.setattr(dm.ab.GazeboWorldGenerator,'generate',lambda *a,**kw:production)
    monkeypatch.setattr(dm.ab,'_instrument_world',lambda *a,topic_identity=None:(diagnostic,{'native':{'topic':'/aero/'+topic_identity}}))
    monkeypatch.setattr(dm,'audit_host1',lambda:{'status':'DIAGNOSTIC_CAPTURE_FAILURE','physical_classification_attempted':False})
    out=tmp_path/'preflight';result=dm.preflight(tmp_path,out)
    assert result['status']=='PREFLIGHT_PASS' and not result['runtime_evidence_created']
    assert result['scenario_seed']==42 and result['reset_seed']==43
    assert len({c['runtime_topic'] for c in result['cases']})==2
    assert not list(out.rglob('*.ndjson')) and not list(out.rglob('case_result.json'))
    assert not (out/'duration_matched_analysis.json').exists()
    assert dm.ab._sha(production)==guard[str(production)]


@pytest.mark.parametrize('root',dm.PROTECTED)
def test_prior_evidence_output_paths_rejected(root):
    with pytest.raises(FileExistsError):dm.ensure_output(root)
    with pytest.raises(FileExistsError):dm.ensure_output(root/'overwrite')


def test_production_sha_still_accepted():
    world=dm.ab.DEFAULT_ARTIFACT/'worlds/aero_ef81a06d3164/world.sdf'
    assert dm.ab._sha(world)=='92def637ff4da2be1348502d345a30721cc845c34704f0b125d4ff1a26fdcc55'


def test_both_cases_execute_and_invalid_capture_exits_nonzero(monkeypatch,tmp_path,capsys):
    calls=[]
    monkeypatch.setattr(dm,'protected_manifest',lambda:{})
    monkeypatch.setattr(dm.history,'source',lambda *a:(None,43,{}))
    monkeypatch.setattr(dm.ab,'_build_all',lambda *a:({},{}))
    def capture(case,*args):
        calls.append(case)
        return {'shutdown_completed':True,'canonical_reset_pose':{},'runtime_identity':{},'wall_start_monotonic_s':len(calls)*2.,'wall_end_after_shutdown_monotonic_s':len(calls)*2.+1}
    monkeypatch.setattr(dm,'capture',capture)
    monkeypatch.setattr(dm,'validate',lambda *a:{'case_valid':False,'invalid_reasons':['zero native samples']})
    assert dm.main(['--output',str(tmp_path/'out')])==1
    assert calls==list(dm.CASES)
    report=json.loads((tmp_path/'out/duration_matched_analysis.json').read_text())
    assert report['status']=='CAPTURE_FAILED' and 'case_outcomes' not in report
    assert report['physical_classification_created'] is False
    lines=capsys.readouterr().out.splitlines()
    assert 'CAPTURE_FAILED' in lines and 'CAPTURED' not in lines


def analysis_record(failure):
    original=movement(record_from_rows(samples(persistent=failure)),not failure)
    result={'events':copy.deepcopy(original['events']),'preparation':copy.deepcopy(pair_records()['CONTROL_SHAM']['preparation']),
        'configured_reset_condition':copy.deepcopy(pair_records()['CONTROL_SHAM']['configured_reset_condition'])}
    result['preparation']={'start':{'iteration':10,'sim_time_ns':10_000_000,'sim_time_s':.01},
        'end':{'iteration':110,'sim_time_ns':110_000_000,'sim_time_s':.11},
        'advancing_iterations':100,'simulation_duration_ns':100_000_000}
    for key in ('support_rows','wrench_rows','native_samples'):
        result[key]=[]
        for i in range(1,111):
            row=copy.deepcopy(original[key][0]);row['iteration']=i
            if key=='native_samples':row['simulation_time_s']=i/1000
            else:row['sim_time_ns']=i*1_000_000
            result[key].append(row)
        for value in original[key]:
            row=copy.deepcopy(value);row['iteration']+=110
            if key=='native_samples':row['simulation_time_s']=row['iteration']/1000
            else:row['sim_time_ns']=row['iteration']*1_000_000
            result[key].append(row)
    event=result['events'][0]
    event['canonical_index']=24
    result['runtime_identity']={'partition':'fixture','topic':'/aero/fixture'}
    for key in ('support_rows','wrench_rows'):
        for row in result[key]:row['epoch']=1
    for row in result['native_samples']:row['world_entity_id']=1
    event['end_sim_time']=.220
    event['up_command_sim_time']=.120
    event['action_publication']['action_command_sim_time']=.120
    return result


@pytest.mark.parametrize('sham_failure,right_failure,expected',[
 (False,True,'ACTION08_RIGHT_HISTORY_REQUIRED_BEYOND_ELAPSED_TIME_CONTROL'),
 (True,True,'EXTRA_ELAPSED_PHYSICS_TIME_SUFFICIENT_TO_REPRODUCE_FAILURE'),
 (False,False,'H15_FAILURE_NOT_REPRODUCED_IN_MATCHED_CONTROL')])
def test_complete_pair_analysis_and_boundary_tables(sham_failure,right_failure,expected):
    records={'CONTROL_SHAM':analysis_record(sham_failure),'RIGHT_HISTORY':analysis_record(right_failure)}
    for case,record in records.items():record['runtime_identity']={'partition':case,'topic':'/aero/'+case}
    result=dm.analyze(records,{case:{'case_valid':True} for case in dm.CASES})
    assert result['status']=='CAPTURED' and result['interpretation']==expected
    assert len(result['boundary_comparisons'])==3
    assert len(result['detail_0_to_15_ms'])==16
    assert [r['delta_ms'] for r in result['support_recovery_5_6_7_ms']]==[5,6,7]
    assert len(result['paired_terminal_table'])==105
    for case in dm.CASES:
        assert result['Action24'][case]['T0']['iteration']==121
        assert result['Action24'][case]['T0']['first_observed_wheel_actuation']['iteration']==122
        assert 'wheel_phase_mod_2pi_rad' in result['Action24'][case]['full_terminal_UP_table'][0]
    assert result['wheel_phase_causality_claimed'] is False


def test_valid_pair_cli_writes_complete_analysis(monkeypatch,tmp_path,capsys):
    monkeypatch.setattr(dm,'protected_manifest',lambda:{})
    monkeypatch.setattr(dm.history,'source',lambda *a:(None,43,{}))
    monkeypatch.setattr(dm.ab,'_build_all',lambda *a:({},{}))
    def capture(case,*args):
        record=analysis_record(case=='RIGHT_HISTORY')
        index=dm.CASES.index(case)
        record.update(shutdown_completed=True,canonical_reset_pose={},
            runtime_identity={'partition':case,'topic':'/aero/'+case},
            wall_start_monotonic_s=index*2.,wall_end_after_shutdown_monotonic_s=index*2.+1)
        return record
    monkeypatch.setattr(dm,'capture',capture)
    monkeypatch.setattr(dm,'validate',lambda *a:{'case_valid':True,'invalid_reasons':[]})
    assert dm.main(['--output',str(tmp_path/'out')])==0
    report=json.loads((tmp_path/'out/duration_matched_analysis.json').read_text())
    assert report['status']=='CAPTURED'
    assert report['interpretation']=='ACTION08_RIGHT_HISTORY_REQUIRED_BEYOND_ELAPSED_TIME_CONTROL'
    assert 'CAPTURED' in capsys.readouterr().out.splitlines()


@pytest.fixture
def host1_empty_events():
    # Exact structural condition preserved by Host1 RIGHT_HISTORY: the base
    # reset advanced to iteration 200, but no captured action event returned.
    return {'events':[],'seed':43,'gazebo_launched':True,'shutdown_completed':True,
        'case_result_written':True,'prefix_completed':False,
        'infrastructure_failure':{'type':'AttributeError','message':"'NoneType' object has no attribute 'get'",'evidence':None},
        'support_rows':[{'kind':'support_iteration','paused':False,'iteration':i,'sim_time_ns':i*1_000_000} for i in range(1,201)],
        'wrench_rows':[{'kind':'joint_wrench_sample','paused':False,'iteration':i,'sim_time_ns':i*1_000_000} for i in range(1,201)],
        'native_samples':[{'paused':False,'iteration':i,'simulation_time_s':i/1000} for i in range(1,201)]}


def test_exact_host1_empty_events_regression(host1_empty_events):
    # Old inherited implementation deterministically raises at events[-1].
    with pytest.raises(IndexError):dm.history.validate_candidate(host1_empty_events,dm.plan('RIGHT_HISTORY'))
    check=dm.validate(host1_empty_events,'RIGHT_HISTORY',None,43,None,set(),set())
    assert not check['case_valid']
    assert check['support_sample_count']==check['wrench_sample_count']==check['native_sample_count']==200
    assert any('terminal Action24 UP event' in x and 'source length 0' in x for x in check['invalid_reasons'])
    assert not any('IndexError' in x for x in check['invalid_reasons'])
    assert check['physical_classifier_attempted'] is False
    assert check['fatal_error']['message']=="'NoneType' object has no attribute 'get'"


def test_original_bare_action_error_preserved_not_masked_by_none_evidence():
    adapter,_=fake_adapter();adapter.env.telemetry={}
    def fail(action):raise RuntimeError('original RIGHT prelude observation error')
    adapter.step=fail
    result=dm.execute_captured(adapter,'right','CANONICAL_ACTION_08')
    assert result['exception']['type']=='RuntimeError'
    assert result['exception']['message']=='original RIGHT prelude observation error'
    assert any('original RIGHT prelude observation error' in line for line in result['exception']['traceback'])
    assert result['execution_evidence']=={}
    assert not result['up_reached']


def test_empty_required_window_is_invalidcapture():
    record=analysis_record(False)
    record['support_rows']=[]
    with pytest.raises(dm.history.InvalidCapture,match='zero advancing samples'):dm.terminal_alignment(record)


@pytest.mark.parametrize('delta',[5,6,7])
def test_exact_required_comparison_iteration_missing(delta):
    record=analysis_record(False);target=121+delta
    for key in ('support_rows','wrench_rows','native_samples'):
        record[key]=[r for r in record[key] if r['iteration']!=target]
    with pytest.raises(dm.history.InvalidCapture,match=f'Action24 \\+{delta} ms.*iteration {target}'):
        dm.terminal_alignment(record)


def test_sparse_required_window_cannot_substitute_nearest_sample():
    record=analysis_record(False)
    for key in ('support_rows','wrench_rows','native_samples'):
        record[key]=[r for r in record[key] if r['iteration']!=125]
    with pytest.raises(dm.history.InvalidCapture,match='relative iteration 4.*125'):dm.terminal_alignment(record)


def test_command_active_t0_missing_cannot_shift_origin():
    record=analysis_record(False)
    for key in ('support_rows','wrench_rows','native_samples'):
        record[key]=[r for r in record[key] if r['iteration']!=121]
    with pytest.raises(dm.history.InvalidCapture,match='COMMAND_ACTIVE_T0.*121'):dm.command_active_t0(record)


def test_missing_wheel_actuation_is_explicit():
    record=analysis_record(False)
    for row in record['wrench_rows']:
        for side in ('left','right'):row[side]['actual_velocity_rad_s']=0.
    with pytest.raises(dm.history.InvalidCapture,match='FIRST_OBSERVED_WHEEL_ACTUATION missing'):dm.command_active_t0(record)


def test_mismatched_stream_iteration_rejected():
    record=analysis_record(False)
    row=next(r for r in record['wrench_rows'] if r['iteration']==126);row['iteration']=127
    with pytest.raises(dm.history.InvalidCapture):dm.terminal_alignment(record)


def test_mismatched_epoch_rejected():
    record=analysis_record(False)
    for row in record['wrench_rows']:
        if row['iteration']>=126:row['epoch']=2
    with pytest.raises(dm.history.InvalidCapture,match='epoch mismatch'):dm.terminal_alignment(record)


def test_native_process_world_mismatch_rejected():
    record=analysis_record(False)
    next(r for r in record['native_samples'] if r['iteration']==126)['world_entity_id']=2
    with pytest.raises(dm.history.InvalidCapture,match='world identity'):dm.terminal_alignment(record)


def test_valid_keyed_alignment_t0_and_actuation_provenance():
    record=analysis_record(False)
    maps,t0,indices=dm.terminal_alignment(record)
    assert t0['publication_iteration']==120 and t0['publication_sim_time_ns']==120_000_000
    assert t0['iteration']==121 and t0['sim_time_ns']==121_000_000
    act=t0['first_observed_wheel_actuation']
    assert act['iteration']==122 and act['sim_time_ns']==122_000_000
    assert act['delta_iterations']==1 and act['delta_ms']==1.
    assert len(indices)==105
    for delta in (5,6,7):
        s,w,n=dm.aligned_sample(maps,121+delta,'required point')
        assert s['iteration']==w['iteration']==n['iteration']==121+delta
        assert s['epoch']==w['epoch']==1


def test_verified_exact_stats_can_supply_marker_without_advancing_physics():
    adapter,calls=fake_adapter()
    adapter.env.stepper._snapshot=lambda:{'data':None}
    adapter.env.stepper.last_verification={'valid':True,'after_sim_time':.2,'iterations_after':200,'paused_after':True}
    mark=dm.physics_mark(adapter)
    assert mark['iteration']==200 and mark['stats_source']=='verified_stepper_WorldStatistics'
    assert calls==[]


def test_marker_rejects_wrong_time_without_nearest_substitution():
    adapter,calls=fake_adapter()
    adapter.env.stepper._snapshot=lambda:{'data':{'iterations':199,'paused':True,'sim_time':{'nsec':199_000_000}}}
    with pytest.raises(dm.history.InvalidCapture,match='exact current simulation time'):dm.physics_mark(adapter)
    assert calls==[]


@pytest.mark.parametrize('valid_first',[True,False])
def test_one_valid_one_invalid_case_preserves_evidence_and_has_no_pair_interpretation(monkeypatch,tmp_path,capsys,valid_first):
    monkeypatch.setattr(dm,'protected_manifest',lambda:{})
    monkeypatch.setattr(dm.history,'source',lambda *a:(None,43,{}))
    monkeypatch.setattr(dm.ab,'_build_all',lambda *a:({},{}))
    monkeypatch.setattr(dm.history,'classify_candidate',lambda *a:(_ for _ in ()).throw(AssertionError('must not classify')))
    originals={}
    def capture(case,scenario,output,*args):
        index=dm.CASES.index(case)
        record={'case':case,'shutdown_completed':True,'canonical_reset_pose':{},'runtime_identity':{},
            'wall_start_monotonic_s':index*2.,'wall_end_after_shutdown_monotonic_s':index*2.+1}
        originals[case]=json.dumps(record)
        (output/'case_result.json').write_text(originals[case])
        return record
    monkeypatch.setattr(dm,'capture',capture)
    monkeypatch.setattr(dm,'validate',lambda r,case,*a:{'case_valid':valid_first if case=='CONTROL_SHAM' else not valid_first,
        'invalid_reasons':[] if (valid_first if case=='CONTROL_SHAM' else not valid_first) else ['required terminal observation missing'],
        'physical_classifier_attempted':False})
    out=tmp_path/'host2'
    assert dm.main(['--output',str(out)])==1
    report=json.loads((out/'duration_matched_analysis.json').read_text())
    assert report['status']=='CAPTURE_FAILED' and 'interpretation' not in report and 'case_outcomes' not in report
    for case in dm.CASES:assert (out/case/'case_result.json').read_text()==originals[case]
    text=capsys.readouterr().out
    assert 'CONTROL_SHAM runtime: '+('VALID' if valid_first else 'INVALID') in text
    assert 'RIGHT_HISTORY runtime: '+('INVALID' if valid_first else 'VALID') in text


def test_host2_output_and_host1_preservation_guard():
    assert dm.DEFAULT_OUTPUT.name=='gazebo-action24-duration-matched-phase3hal-host2'
    with pytest.raises(FileExistsError):dm.ensure_output(dm.HOST1)
    with pytest.raises(FileExistsError):dm.ensure_output(dm.HOST1/'CONTROL_SHAM/new.json')


def test_no_classifier_runs_when_second_keyed_window_is_incomplete(monkeypatch):
    records={'CONTROL_SHAM':analysis_record(False),'RIGHT_HISTORY':analysis_record(True)}
    for case,record in records.items():record['runtime_identity']={'partition':case,'topic':'/aero/'+case}
    for key in ('support_rows','wrench_rows','native_samples'):
        records['RIGHT_HISTORY'][key]=[r for r in records['RIGHT_HISTORY'][key] if r['iteration']!=126]
    monkeypatch.setattr(dm.history,'classify_candidate',lambda *a:(_ for _ in ()).throw(AssertionError('must not classify')))
    with pytest.raises(dm.history.InvalidCapture,match='Action24 \\+5 ms'):
        dm.analyze(records,{case:{'case_valid':True} for case in dm.CASES})


def test_empty_native_link_list_is_descriptive_invalidcapture():
    record=analysis_record(False)
    next(row for row in record['native_samples'] if row['iteration']==126)['links']=[]
    with pytest.raises(dm.history.InvalidCapture,match='three required native links missing'):dm.state_at(record,126)


def test_empty_required_wrench_vector_is_invalidcapture():
    record=analysis_record(False)
    next(row for row in record['wrench_rows'] if row['iteration']==126)['left']['force_xyz_N']=[]
    with pytest.raises(dm.history.InvalidCapture,match='expected 3 finite'):dm.state_at(record,126)


def test_base_reset_evidence_and_original_error_survive_prefix_failure(monkeypatch,tmp_path):
    from aero_ai_studio.training import gazebo_physics
    old_execute,old_failure=dm.ab._execute_captured,dm.ab._failure
    class Base:
        def __init__(self):
            a,_=fake_adapter();self.env=a.env;self.env.pose={'x':1.5,'y':1.5,'z':.1096};self.env.telemetry={}
        def reset(self,seed):
            self.last_reset_evidence={'seed':seed,'normal_reset_pass':True,'set_pose_response':{'payload':'canonical target'}}
        def step(self,action):raise RuntimeError('RIGHT failed before physics advancement')
    monkeypatch.setattr(gazebo_physics,'GazeboPhysicsTrainingEnvironment',Base)
    def inherited_capture(plan,scenario,output,libraries,seed,runtime_namespace):
        env=gazebo_physics.GazeboPhysicsTrainingEnvironment();env.reset(seed)
        event=dm.ab._execute_captured(env,'right','CANONICAL_ACTION_08');event['canonical_index']=8
        return {'events':[event],'prefix_completed':False,'shutdown_completed':True}
    monkeypatch.setattr(dm.history,'capture_candidate',inherited_capture)
    monkeypatch.setattr(dm.history,'reset_validity',lambda *a:{'configured_reset_condition':{},'measured_reset_state':{}})
    record=dm.capture('RIGHT_HISTORY',None,tmp_path/'case',{},43,'host2-new')
    assert record['reset_completed'] and record['reset_evidence']['normal_reset_pass']
    event=dm.unique_match(record['events'],lambda e:e.get('canonical_index')==8,'prelude failure')
    assert event['exception']['type']=='RuntimeError'
    assert event['exception']['diagnostic_stage']=='RIGHT prelude: production step(right)'
    assert any('RIGHT failed before physics advancement' in line for line in event['exception']['traceback'])
    assert dm.ab._execute_captured is old_execute and dm.ab._failure is old_failure
    assert gazebo_physics.GazeboPhysicsTrainingEnvironment is Base


def test_insufficient_recovery_window_rejected_before_classifier(monkeypatch):
    record=analysis_record(False)
    dm.terminal_event(record)['end_sim_time']=.160
    with pytest.raises(dm.history.InvalidCapture,match='recovery window insufficient'):dm.terminal_alignment(record)
