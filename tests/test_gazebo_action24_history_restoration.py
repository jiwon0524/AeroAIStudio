import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import diagnose_v07_gazebo_action24_history_restoration as hr


def test_exact_canonical_order():
    assert hr.CANONICAL == tuple('UP DOWN UP UP UP DOWN UP RIGHT LEFT UP DOWN LEFT DOWN LEFT RIGHT LEFT UP UP RIGHT LEFT LEFT UP DOWN UP'.lower().split())


@pytest.mark.parametrize('k,expected', [(0,['down','up']), (1,['up','down','up']),
    (2,['left','up','down','up']), (3,['left','left','up','down','up'])])
def test_candidate_construction(k, expected):
    plan=hr.candidate(k)
    assert plan['actions']==expected
    assert plan['prefix']==expected[:-2]
    assert plan['canonical_indices']==list(range(23-k,25))


def test_progressive_history_and_invariant_suffix():
    plans=[hr.candidate(i) for i in range(23)]
    for k,plan in enumerate(plans):
        assert plan['actions'][-2:]==['down','up']
        assert plan['terminal_suffix']==['23 DOWN','production BRAKE_LINEAR','production stopped contract','24 UP +0.5']
        if k: assert plan['actions'][1:]==plans[k-1]['actions']
    assert plans[-1]['actions']==list(hr.CANONICAL)
    assert len({p['name'] for p in plans})==23


@pytest.mark.parametrize('k', [-1,23,1.5,True])
def test_invalid_history_index(k):
    with pytest.raises(ValueError):hr.candidate(k)


def samples(persistent=False, temporary=True):
    rows=[]
    for i in range(1,111):
        d=i-11
        unloaded=(d>=1 and (persistent or (temporary and d<=2)))
        supports={key:{'state':'VALID_EMPTY_CONTACT_SET' if persistent and key=='left_wheel' and unloaded else 'VALID_CONTACTS',
                       'Fn_N':0. if unloaded and key in ('left_wheel','right_wheel','front_caster') else 7. if key in ('left_wheel','right_wheel') else 5.}
                  for key in ('left_wheel','right_wheel','front_caster','rear_caster')}
        if persistent and unloaded:supports['front_caster']['Fn_N']=12.25;supports['rear_caster']['Fn_N']=12.25
        rows.append({'iteration':i,'delta_ms':d,'sim_time_ns':i*1000000,'supports':supports,
            'total_Fn_N':sum(s['Fn_N'] for s in supports.values()),
            'joint_transmitted_wrench':{s:{'actual_velocity_rad_s':5. if d>=1 else 0.} for s in ('left','right')},
            'chassis_position_world_m':[0. if persistent else max(0,d)*.0003,0,.11],'yaw_rad':0.})
    return rows


def record_from_rows(rows):
    record={'events':[{'action':'up','end_sim_time':.110,'up_command_sim_time':.010,
        'action_publication':{'commanded_twist':{'linear':{'x':.5}},'action_publish_sequence':2,
            'command_publish_sequence_before':1,'action_command_sim_time':.010}}],
        'support_rows':[],'wrench_rows':[],'native_samples':[]}
    for row in rows:
        i=row['iteration']
        supports={k:{'state':v['state'],'component_available':True,'contacts':[] if v['state']=='VALID_EMPTY_CONTACT_SET' else [
            {'pair_classification':'SUPPORT_GROUND','points':[{'body_1_force_world_n':[0,0,v['Fn_N']],
                'normal_world':[0,0,1],'depth_m':.0001}]}]} for k,v in row['supports'].items()}
        record['support_rows'].append({'kind':'support_iteration','paused':False,'iteration':i,'sim_time_ns':i*1000000,'supports':supports})
        record['wrench_rows'].append({'kind':'joint_wrench_sample','paused':False,'iteration':i,'sim_time_ns':i*1000000,
            **{s:{'state':'VALID_WRENCH','actual_velocity_available':True,
                'actual_velocity_rad_s':row['joint_transmitted_wrench'][s]['actual_velocity_rad_s'],
                'force_xyz_N':[0,0,1],'torque_xyz_N_m':[0,1,0]} for s in ('left','right')}})
        record['native_samples'].append({'paused':False,'iteration':i,'simulation_time_s':i*.001,
            'all_link_native_velocities_available':True,'links':[{'expected_scoped_name':'simple_agent::'+name,
                'position_world_m':row['chassis_position_world_m'],'orientation_world_xyzw':[0,0,0,1],
                'linear_velocity_world_m_s':[0 if row['chassis_position_world_m'][0]==0 else .3,0,0],
                'angular_velocity_world_rad_s':[0,0,0]} for name in ('body','left_wheel','right_wheel')]})
    return record


def movement(record, valid):
    record['events'][-1]['telemetry']={'physics_validation':{'valid':valid,'expected_distance':.05,
        'expected_yaw':0.,'body_forward_displacement':.03 if valid else 0.,'world_direction_raw_ok':valid,
        'collision_may_block_motion':False}}
    return record


def test_command_active_t0_distinct_from_wheel_actuation():
    record=record_from_rows(samples())
    t0,table=hr.terminal_table(record)
    assert t0['iteration']==11
    assert t0['first_observed_wheel_actuation']['iteration']==12
    assert t0['first_observed_wheel_actuation']['delta_ms']==1
    assert [r['delta_ms'] for r in table[:21]]==list(range(-5,16))


def test_temporary_unloading_is_success_not_reproduced_failure():
    record=movement(record_from_rows(samples()),True)
    result=hr.classify_candidate(record,{'case_valid':True})
    assert result['classification']=='SUPPORT_RECOVERY_AND_TRANSLATION_SUCCESS'
    assert not result['persistent_drive_Fn_zero']


def test_persistent_pattern_and_no_translation_reproduces():
    record=movement(record_from_rows(samples(persistent=True)),False)
    result=hr.classify_candidate(record,{'case_valid':True})
    assert result['classification']=='CANONICAL_ACTION24_FAILURE_REPRODUCED'
    assert result['native_body_forward_translation_m']==0


def test_temporary_unloading_with_movement_failure_is_not_canonical_failure():
    record=movement(record_from_rows(samples()),False)
    assert hr.classify_candidate(record,{'case_valid':True})['classification']=='OTHER_PHYSICAL_OUTCOME'


def test_odometry_alone_cannot_classify_success():
    record=movement(record_from_rows(samples(persistent=True)),True)
    assert hr.classify_candidate(record,{'case_valid':True})['classification']=='OTHER_PHYSICAL_OUTCOME'


def test_invalid_telemetry_never_classified():
    with pytest.raises(hr.InvalidCapture):hr.classify_candidate({}, {'case_valid':False})


@pytest.mark.parametrize('key',['support_rows','wrench_rows','native_samples'])
def test_zero_samples_rejected(key):
    record=record_from_rows(samples());record[key]=[]
    with pytest.raises(hr.InvalidCapture):hr.terminal_table(record)


@pytest.mark.parametrize('key',['support_rows','wrench_rows','native_samples'])
def test_nonadvancing_or_missing_terminal_samples_rejected(key):
    record=record_from_rows(samples());del record[key][30]
    with pytest.raises(hr.InvalidCapture):hr.terminal_table(record)


def test_terminal_samples_must_cover_full_acquisition():
    record=record_from_rows(samples());record['native_samples']=record['native_samples'][:-1]
    with pytest.raises(hr.InvalidCapture):hr.terminal_table(record)


def test_fresh_unique_topic_and_partition_required(monkeypatch):
    monkeypatch.setattr(hr.ab,'validate_case',lambda r:{'case_valid':True,'invalid_reasons':[]})
    plan=hr.candidate(0)
    record={'runtime_identity':{'partition':'old','topic':'/aero/'+plan['name']},'events':[
        {'action':'down','canonical_index':23},{'action':'up','canonical_index':24}], 'prefix_completed':True}
    result=hr.validate_candidate(record,plan,{'old'},{'/aero/'+plan['name']})
    assert not result['case_valid']
    assert any('stale process partition' in r for r in result['invalid_reasons'])
    assert any('stale or wrong candidate native topic' in r for r in result['invalid_reasons'])


def test_failure_validator_precedes_stale_success_telemetry():
    event=movement(record_from_rows(samples()),True)['events'][-1]
    event['exception']={'evidence':{'validator_evidence':{'valid':False,'expected_distance':.05,'body_forward_displacement':0.}}}
    assert hr.find_movement_validator(event)['valid'] is False


def fake_search(monkeypatch,tmp_path,outcomes):
    called=[]
    monkeypatch.setattr(hr,'source',lambda p:(None,42,{}))
    monkeypatch.setattr(hr.ab,'_build_all',lambda p:({},{}))
    def capture(plan,scenario,output,libraries,seed,**kwargs):
        k=plan['restored_preceding_action_count'];called.append(k)
        return {'seed':42,'canonical_reset_pose':{'x':1.5,'y':1.5,'z':.11,'orientation':{'x':0.,'y':0.,'z':0.,'w':1.}},
            'runtime_identity':{'partition':'partition'+str(k),'topic':'/aero/'+plan['name']},
            'wall_start_monotonic_s':k*2.,'wall_end_after_shutdown_monotonic_s':k*2.+1,'k':k}
    monkeypatch.setattr(hr,'reset_validity',lambda *a:{"reset_valid":True,"invalid_reasons":[],"configured_reset_condition":{},"measured_reset_state":{}})
    monkeypatch.setattr(hr,'capture_candidate',capture)
    monkeypatch.setattr(hr,'validate_candidate',lambda *a:{'case_valid':True,'invalid_reasons':[]})
    monkeypatch.setattr(hr,'classify_candidate',lambda r,i:{'classification':outcomes[r['k']]})
    return called


def test_stops_on_first_reproducing_history_without_monotonicity(monkeypatch,tmp_path):
    called=fake_search(monkeypatch,tmp_path,['SUPPORT_RECOVERY_AND_TRANSLATION_SUCCESS']*3+['CANONICAL_ACTION24_FAILURE_REPRODUCED'])
    report=hr.run(tmp_path,tmp_path/'out')
    assert called==[0,1,2,3]
    assert report['status']=='CAPTURED'
    assert report['shortest_tested_reproducing_history']==hr.candidate(3)
    assert not report['global_minimum_claimed'] and not report['monotonicity_assumed']
    assert all((tmp_path/'out'/hr.candidate(k)['name']/'candidate_analysis.json').exists() for k in range(4))


def test_all_23_run_when_no_candidate_reproduces(monkeypatch,tmp_path):
    called=fake_search(monkeypatch,tmp_path,['SUPPORT_RECOVERY_AND_TRANSLATION_SUCCESS']*23)
    report=hr.run(tmp_path,tmp_path/'out')
    assert called==list(range(23))
    assert report['search_status']=='ALL_23_CANDIDATES_CAPTURED_NO_MATCHING_FAILURE'


def test_invalid_candidate_stops_nonzero_without_physical_classification(monkeypatch,tmp_path,capsys):
    called=fake_search(monkeypatch,tmp_path,[])
    monkeypatch.setattr(hr,'validate_candidate',lambda *a:{'case_valid':False,'invalid_reasons':['zero native samples']})
    assert hr.main(['--output',str(tmp_path/'out')])==1
    assert called==[0]
    report=json.loads((tmp_path/'out/history_restoration_capture.json').read_text())
    assert 'physical_classification' not in report['candidates'][0]
    assert not list((tmp_path/'out').rglob('candidate_analysis.json'))
    text=capsys.readouterr().out
    assert 'CAPTURE_FAILED' in text and 'zero native samples' in text and '\nCAPTURED\n' not in text


def test_preflight_cannot_create_runtime_evidence(monkeypatch,tmp_path):
    scenario=SimpleNamespace(seed=42,start=(1,1))
    monkeypatch.setattr(hr,'source',lambda p:(scenario,42,{}))
    monkeypatch.setattr(hr.ab,'_build_all',lambda p:({},{}))
    monkeypatch.setattr(hr.ab.GazeboWorldGenerator,'generate',lambda *a,**k:tmp_path/'production.sdf')
    def instrument(prod,output,libs,topic_identity=None):
        return tmp_path/'diagnostic.sdf',{'native':{'topic':'/aero/'+topic_identity}}
    monkeypatch.setattr(hr.ab,'_instrument_world',instrument)
    report=hr.preflight(tmp_path,tmp_path/'preflight')
    assert report['status']=='PREFLIGHT_PASS' and report['runtime_evidence_created'] is False
    assert len({p['runtime_topic'] for p in report['candidates']})==23
    assert not list((tmp_path/'preflight').rglob('*.ndjson'))
    assert not list((tmp_path/'preflight').rglob('case_result.json'))


def test_prefix_uses_production_step_before_invariant_terminal_suffix(monkeypatch,tmp_path):
    from aero_ai_studio.training import gazebo_physics
    calls=[]
    class Environment:
        def __init__(self):self.env=SimpleNamespace(pose={'x':1.5})
        def reset(self,seed):calls.append(('reset',seed))
    monkeypatch.setattr(gazebo_physics,'GazeboPhysicsTrainingEnvironment',Environment)
    monkeypatch.setattr(hr.ab,'_execute_captured',lambda env,action,phase: calls.append(('prefix',action)) or {'action':action,'exception':None,'terminated':False})
    def base_run(name,history,scenario,root,output,libraries,seed):
        assert history is True
        env=gazebo_physics.GazeboPhysicsTrainingEnvironment();env.reset(seed)
        calls.extend([('terminal','down'),('terminal','production_brake_stopped_up'),('shutdown',name)])
        return {'events':[{'action':'down'},{'action':'up'}]}
    monkeypatch.setattr(hr.ab,'_run_case',base_run)
    monkeypatch.setattr(hr,'reset_validity',lambda *a:{"configured_reset_condition":{},"measured_reset_state":{}})
    record=hr.capture_candidate(hr.candidate(3),None,tmp_path,{},42)
    assert calls[:4]==[('reset',42),('prefix','left'),('prefix','left'),('prefix','up')]
    assert calls[4:6]==[('terminal','down'),('terminal','production_brake_stopped_up')]
    assert [e['canonical_index'] for e in record['events']]==list(range(20,25))
    assert gazebo_physics.GazeboPhysicsTrainingEnvironment is Environment


def test_fresh_manager_identities_and_candidate_topics():
    from aero_ai_studio.gazebo.process_manager import GazeboProcessManager
    managers=[GazeboProcessManager() for _ in range(23)]
    assert len({m.partition for m in managers})==23
    assert all(m.process is None for m in managers)
    assert len({'/aero/native/'+hr.candidate(i)['name'] for i in range(23)})==23


def test_incomplete_prefix_cannot_validate(monkeypatch):
    monkeypatch.setattr(hr.ab,'validate_case',lambda r:{'case_valid':True,'invalid_reasons':[]})
    plan=hr.candidate(1)
    record={'prefix_completed':False,'runtime_identity':{'partition':'new','topic':'/aero/'+plan['name']},
            'events':[{'canonical_index':23,'action':'down'},{'canonical_index':24,'action':'up'}]}
    result=hr.validate_candidate(record,plan)
    assert not result['case_valid']
    assert any('canonical history did not complete' in r for r in result['invalid_reasons'])


def test_late_support_recovery_prevents_persistent_failure():
    rows=samples(persistent=True)
    for row in rows[-20:]:
        for side in ('left_wheel','right_wheel'):
            row['supports'][side]={'state':'VALID_CONTACTS','Fn_N':5.}
    record=movement(record_from_rows(rows),False)
    result=hr.classify_candidate(record,{'case_valid':True})
    assert result['classification']=='OTHER_PHYSICAL_OUTCOME'
    assert not result['persistent_drive_Fn_zero']


def test_collision_cannot_be_canonical_failure():
    record=movement(record_from_rows(samples(persistent=True)),False)
    record['events'][-1]['telemetry']['physics_validation']['collision_may_block_motion']=True
    assert hr.classify_candidate(record,{'case_valid':True})['classification']=='OTHER_PHYSICAL_OUTCOME'


def test_recovery_window_must_extend_beyond_initial_transient():
    record=movement(record_from_rows(samples()[:40]),True)
    record['events'][-1]['end_sim_time']=.040
    with pytest.raises(hr.InvalidCapture,match='insufficient terminal recovery'):
        hr.classify_candidate(record,{'case_valid':True})


def test_diagnostic_exception_returns_nonzero(monkeypatch,tmp_path,capsys):
    monkeypatch.setattr(hr,'run',lambda *a:(_ for _ in ()).throw(TimeoutError('native observer topic timeout')))
    assert hr.main(['--output',str(tmp_path)])==1
    assert 'CAPTURE_FAILED: TimeoutError: native observer topic timeout' in capsys.readouterr().out


def test_source_uses_completed_canonical_episode_not_later_failure(monkeypatch):
    scenario=SimpleNamespace(seed=42,start=(1,1))
    monkeypatch.setattr(hr.ab,'extract_reversal_replay',lambda p:{'completed_episode_actions':[list(hr.CANONICAL)],
        'failed_episode_saved_prefix':['wrong','episode'],'scenario':{},'training_seed':42})
    monkeypatch.setattr(hr.ab.ScenarioSpec,'from_dict',lambda d:scenario)
    assert hr.source(Path('.'))[1]==43


def test_nonfinite_native_pose_rejected():
    record=record_from_rows(samples())
    record['native_samples'][20]['links'][0]['orientation_world_xyzw'][0]=float('nan')
    with pytest.raises(hr.InvalidCapture,match='invalid native orientation'):hr.terminal_table(record)


def test_late_but_sustained_recovery_and_real_translation_is_success():
    rows=samples(persistent=True)
    for row in rows[-20:]:
        for side in ('left_wheel','right_wheel'):
            row['supports'][side]={'state':'VALID_CONTACTS','Fn_N':5.}
        row['chassis_position_world_m'][0]=(row['delta_ms']-79)*.0015
    record=movement(record_from_rows(rows),True)
    result=hr.classify_candidate(record,{'case_valid':True})
    assert result['classification']=='SUPPORT_RECOVERY_AND_TRANSLATION_SUCCESS'
    assert not result['persistent_drive_Fn_zero']


@pytest.fixture
def serialized_candidate(tmp_path):
    plan=hr.candidate(0)
    record=movement(record_from_rows(samples()),True)
    record['events'][0].update(canonical_index=24,up_reached=True,
        execution_evidence={'execution_phases':[{'phase':'BRAKE_LINEAR','completion_result':True,'end_sim_time':.010},
            {'phase':'ACQUIRE_LINEAR','start_sim_time':.010}]})
    record['events'].insert(0,{'action':'down','canonical_index':23})
    sdf=tmp_path/'diagnostic.sdf'
    library=tmp_path/'observer.so';library.write_bytes(b'static registration checked separately by preflight')
    sdf.write_text('<sdf><world>'+''.join(
        '<plugin name="aero_diagnostic::'+name+'" filename="'+str(library)+'">'+
        ('<topic>/aero/'+plan['name']+'</topic>' if name=='NativeLinkVelocityObserver' else '')+'</plugin>'
        for name in ('ContinuousSupportObserver','JointTransmittedWrenchObserver','NativeLinkVelocityObserver'))+'</world></sdf>')
    record.update(gazebo_launched=True,sdf_path=str(sdf),runtime_sdf_passed_to_gazebo=str(sdf),
        reset_completed=True,reset_evidence={'normal_reset_pass':True,'body_residual_velocity_stopped':True,'odometry_fresh_and_stopped':True},
        observer_sdf={'observation_only':True,'diagnostic_sdf_sha256':hr.ab._sha(sdf)},
        case_result_written=True,shutdown_completed=True,prefix_completed=True,
        runtime_identity={'partition':'fresh','topic':'/aero/'+plan['name']},case_result_path=str(tmp_path/'case_result.json'))
    hr.write_json(record['case_result_path'],record)
    return plan,record


def test_complete_runtime_validity_gate_can_pass(monkeypatch,serialized_candidate):
    plan,record=serialized_candidate
    old_sha=hr.ab._sha
    monkeypatch.setattr(hr.ab,'_sha',lambda p:hr.ab.PRODUCTION_HASH if Path(p).name=='world.sdf' else old_sha(p))
    integrity=hr.validate_candidate(record,plan)
    assert integrity['case_valid'],integrity['invalid_reasons']
    assert hr.classify_candidate(record,integrity)['classification']=='SUPPORT_RECOVERY_AND_TRANSLATION_SUCCESS'


def test_valid_candidate_rejects_stale_identity(monkeypatch,serialized_candidate):
    plan,record=serialized_candidate
    old_sha=hr.ab._sha
    monkeypatch.setattr(hr.ab,'_sha',lambda p:hr.ab.PRODUCTION_HASH if Path(p).name=='world.sdf' else old_sha(p))
    integrity=hr.validate_candidate(record,plan,{'fresh'},{record['runtime_identity']['topic']})
    assert not integrity['case_valid']
    assert any('stale' in r for r in integrity['invalid_reasons'])


def test_complete_serialization_is_mandatory(monkeypatch,serialized_candidate):
    plan,record=serialized_candidate
    old_sha=hr.ab._sha
    monkeypatch.setattr(hr.ab,'_sha',lambda p:hr.ab.PRODUCTION_HASH if Path(p).name=='world.sdf' else old_sha(p))
    Path(record['case_result_path']).write_text('{}')
    assert not hr.validate_candidate(record,plan)['case_valid']


@pytest.fixture
def reset_fixture(tmp_path,monkeypatch):
    import copy
    scenario_data={'seed':42,'start':[1,1],'name':'canonical'}
    scenario=SimpleNamespace(seed=42,start=(1,1),to_dict=lambda:copy.deepcopy(scenario_data))
    directory=tmp_path/'world';directory.mkdir()
    sdf=directory/'diagnostic.sdf';sdf.write_text('<sdf/>')
    (directory/'metadata.json').write_text(json.dumps({'scenario':scenario_data,'agent_entity':'simple_agent','control_mode':'PHYSICS'}))
    old_sha=hr.ab._sha
    monkeypatch.setattr(hr.ab,'_sha',lambda p:hr.ab.PRODUCTION_HASH if Path(p).name=='world.sdf' else old_sha(p))
    pose={'x':1.5,'y':1.5,'z':.10961918906889385,'orientation':{'x':0.,'y':0.,'z':0.,'w':1.},'yaw':0.}
    target=hr.configured_reset_target(scenario)
    evidence={'seed':43,'normal_reset_pass':True,'restart_fallback_used':False,'reset_method':'fresh_process_initialization',
        'body_residual_velocity_stopped':True,'odometry_fresh_and_stopped':True,
        'set_pose_response':{'payload':target,'accepted':True,'response':{'data':True}},
        'pose_after_settle':pose,'reset_trace':{'seed':43,'requested_pose':copy.deepcopy(target),
            'post_settle_body_pose':pose,'post_settle_simulation_time':.2,
            'post_set_pose_body_pose':copy.deepcopy(pose),'post_set_pose_simulation_time':.1}}
    record={'sdf_path':str(sdf),'seed':43,'reset_completed':True,'canonical_reset_pose':pose,'reset_evidence':evidence,
        'native_samples':[{'paused':False,'simulation_time_s':.2,'iteration':200,'links':[
            {'expected_scoped_name':'simple_agent::body','position_world_m':[1.5,1.5,pose['z']],
             'linear_velocity_world_m_s':[0,0,.001],'angular_velocity_world_rad_s':[0,0,0]}]}],
        'support_rows':[{'kind':'support_iteration','paused':False,'iteration':200,'supports':{
            k:{'state':'VALID_CONTACTS','contacts':[{'points':[{'normal_world':[0,0,1],'body_1_force_world_n':[0,0,5]}]}]}
            for k in hr.ab.support.SUPPORTS}}]}
    sample=record['native_samples'][0]
    record['native_samples']=[]
    for i in (198,199,200):
        row=copy.deepcopy(sample);row.update(iteration=i,simulation_time_s=i/1000)
        record['native_samples'].append(row)
    return scenario,record,copy.deepcopy(pose)


def test_identical_target_with_micrometre_settle_variation_is_valid(reset_fixture):
    scenario,record,reference=reset_fixture
    record['canonical_reset_pose']['z']-=9.999453723374963e-7
    result=hr.reset_validity(record,scenario,43,reference)
    assert result['reset_valid'],result['invalid_reasons']
    assert result['configured_reset_condition']['target']==hr.configured_reset_target(scenario)
    assert result['measured_reset_state']['native_iteration']==200


def test_different_configured_reset_target_fails(reset_fixture):
    scenario,record,reference=reset_fixture
    record['reset_evidence']['set_pose_response']['payload']['position']['z']+=1e-9
    assert not hr.reset_validity(record,scenario,43,reference)['reset_valid']


def test_different_reset_seed_fails(reset_fixture):
    scenario,record,reference=reset_fixture
    record['seed']=42
    assert not hr.reset_validity(record,scenario,43,reference)['reset_valid']


def test_failed_reset_fails(reset_fixture):
    scenario,record,reference=reset_fixture
    record['reset_evidence']['normal_reset_pass']=False
    assert not hr.reset_validity(record,scenario,43,reference)['reset_valid']


@pytest.mark.parametrize('factor,valid',[(.999,True),(1.,True),(1.001,False)])
def test_measured_position_tolerance_boundary(reset_fixture,factor,valid):
    scenario,record,reference=reset_fixture
    record['canonical_reset_pose']['z']+=hr.RESET_POSITION_ENVELOPE_M*factor
    result=hr.reset_validity(record,scenario,43,reference)
    assert result['reset_valid'] is valid,result['invalid_reasons']


@pytest.mark.parametrize('factor,valid',[(1.,True),(1.001,False)])
def test_measured_orientation_tolerance_boundary(reset_fixture,factor,valid):
    import math
    scenario,record,reference=reset_fixture
    angle=hr.RESET_ORIENTATION_ENVELOPE_RAD*factor
    record['canonical_reset_pose']['orientation'].update(y=math.sin(angle/2),w=math.cos(angle/2))
    assert hr.reset_validity(record,scenario,43,reference)['reset_valid'] is valid


def test_excessive_measured_reset_deviation_fails(reset_fixture):
    scenario,record,reference=reset_fixture
    record['canonical_reset_pose']['z']+=.001
    assert not hr.reset_validity(record,scenario,43,reference)['reset_valid']


def test_different_scenario_or_model_fails(reset_fixture):
    scenario,record,reference=reset_fixture
    metadata=Path(record['sdf_path']).with_name('metadata.json')
    value=json.loads(metadata.read_text());value['scenario']['seed']=41;value['agent_entity']='other_agent'
    metadata.write_text(json.dumps(value))
    assert not hr.reset_validity(record,scenario,43,reference)['reset_valid']


def test_sampling_envelope_requires_native_3d_motion_bound(reset_fixture):
    scenario,record,reference=reset_fixture
    record['native_samples'][0]['links'][0]['linear_velocity_world_m_s'][2]=.021
    assert not hr.reset_validity(record,scenario,43,reference)['reset_valid']


def test_reset_measurement_time_is_not_post_prefix_time(reset_fixture):
    scenario,record,reference=reset_fixture
    record['reset_sim_time']=1.1
    value=hr.reset_validity(record,scenario,43,reference)
    assert value['reset_valid']
    assert value['measured_reset_state']['post_settle_nominal_sim_time_s']==.2


def resume_fixture(monkeypatch,tmp_path,invalid_four=False):
    prior=tmp_path/'host1';prior.mkdir()
    (prior/'history_restoration_capture.json').write_text(json.dumps({'canonical_actions':list(hr.CANONICAL),'reset_seed':43}))
    pose={'x':1.5,'y':1.5,'z':.11,'orientation':{'w':1.}}
    for k in range(6):
        d=prior/hr.candidate(k)['name'];d.mkdir()
        (d/'case_result.json').write_text(json.dumps({'canonical_reset_pose':pose,'runtime_identity':{'partition':'old'+str(k),'topic':'/old/'+str(k)}}))
    monkeypatch.setattr(hr,'source',lambda p:(None,43,{}))
    monkeypatch.setattr(hr,'reset_validity',lambda *a:{'reset_valid':True})
    def audit(directory,plan,*args):
        k=plan['restored_preceding_action_count']
        if k==5 or (k==4 and invalid_four):raise hr.InvalidCapture('original invalid capture')
        return {'candidate':plan,'physical_classification':'OTHER_PHYSICAL_OUTCOME' if k==4 else 'SUPPORT_RECOVERY_AND_TRANSLATION_SUCCESS',
            'runtime_identity':{'partition':'old'+str(k),'topic':'/old/'+str(k)}}
    monkeypatch.setattr(hr,'audit_preserved_candidate',audit)
    return prior


def test_valid_h04_other_outcome_preserved_resume_is_h05(monkeypatch,tmp_path):
    prior=resume_fixture(monkeypatch,tmp_path)
    result=hr.prepare_resume(prior,tmp_path)
    assert result['resume_index']==5 and result['resume_candidate']=='H05_from18'
    assert len(result['preserved_candidates'])==5
    assert result['preserved_candidates'][-1]['physical_classification']=='OTHER_PHYSICAL_OUTCOME'
    assert not result['unresolved_source_reset_audit']['promoted_to_valid_capture']


def test_invalid_h04_forces_resume_at_h04(monkeypatch,tmp_path):
    prior=resume_fixture(monkeypatch,tmp_path,invalid_four=True)
    result=hr.prepare_resume(prior,tmp_path)
    assert result['resume_index']==4 and result['resume_candidate']=='H04_from19'
    assert len(result['preserved_candidates'])==4


def test_host1_cannot_be_overwritten(tmp_path,monkeypatch):
    prior=tmp_path/'host1';prior.mkdir();p=prior/'raw.json';p.write_text('original')
    monkeypatch.setattr(hr,'DEFAULT_PRIOR',prior)
    with pytest.raises(FileExistsError):hr.write_json(p,{'overwrite':True})
    with pytest.raises(FileExistsError):hr.preflight(tmp_path,prior)
    with pytest.raises(FileExistsError):hr.run(tmp_path,prior)
    assert p.read_text()=='original'


def test_resume_does_not_execute_h00_through_h04(monkeypatch,tmp_path,capsys):
    outcomes=['OTHER_PHYSICAL_OUTCOME']*6+['CANONICAL_ACTION24_FAILURE_REPRODUCED']
    called=fake_search(monkeypatch,tmp_path,outcomes)
    prior=tmp_path/'host1';prior.mkdir()
    resume={'resume_index':5,'resume_candidate':'H05_from18','preserved_candidates':[{'candidate':hr.candidate(k)} for k in range(5)],
        'source_directory':str(prior),'reset_reference_pose':{'x':1.5,'y':1.5,'z':.11,'orientation':{'w':1.}},
        'prior_partitions':[],'prior_topics':[],'source_evidence_sha256':{}}
    monkeypatch.setattr(hr,'prepare_resume',lambda *a:resume)
    result=hr.run(tmp_path,tmp_path/'host2',resume_from=prior)
    assert called==[5,6]
    assert result['status']=='CAPTURED'
    assert result['resume_index']==5
    assert 'resume: H05_from18; preserved candidates: 5' in capsys.readouterr().out
    assert not (tmp_path/'host2'/hr.candidate(0)['name']).exists()


def test_host2_runtime_namespace_is_fresh_and_scoped(monkeypatch,tmp_path):
    from aero_ai_studio.training import gazebo_physics
    topics=[]
    class Env: pass
    monkeypatch.setattr(gazebo_physics,'GazeboPhysicsTrainingEnvironment',Env)
    monkeypatch.setattr(hr,'reset_validity',lambda *a:{'configured_reset_condition':{},'measured_reset_state':{}})
    monkeypatch.setattr(hr.ab,'_instrument_world',lambda *a,topic_identity=None:topics.append(topic_identity))
    def capture(name,history,scenario,root,output,libraries,seed):
        hr.ab._instrument_world(None,None,None)
        return {'events':[{'action':'down'},{'action':'up'}]}
    monkeypatch.setattr(hr.ab,'_run_case',capture)
    a=hr.capture_candidate(hr.candidate(5),None,tmp_path/'first',{},43)
    b=hr.capture_candidate(hr.candidate(5),None,tmp_path/'second',{},43)
    assert a['runtime_namespace']!=b['runtime_namespace']
    assert topics==['H05_from18/'+a['runtime_namespace'],'H05_from18/'+b['runtime_namespace']]


def test_source_manifest_detects_modification(tmp_path):
    p=tmp_path/'raw';p.write_text('before')
    manifest=hr.evidence_manifest(tmp_path)
    p.write_text('after')
    with pytest.raises(hr.InvalidCapture):hr.verify_manifest(manifest)


def test_quaternion_sign_is_not_a_different_orientation(reset_fixture):
    scenario,record,reference=reset_fixture
    record['canonical_reset_pose']['orientation']['w']=-1.
    assert hr.reset_validity(record,scenario,43,reference)['reset_valid']


def test_sampling_envelope_checks_motion_throughout_freshness_window(reset_fixture):
    scenario,record,reference=reset_fixture
    record['native_samples'][0]['links'][0]['linear_velocity_world_m_s'][2]=.1
    assert not hr.reset_validity(record,scenario,43,reference)['reset_valid']
