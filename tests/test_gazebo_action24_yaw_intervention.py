import copy
import json
import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import diagnose_v07_gazebo_action24_yaw_intervention as y
from yaw_checkpoint_fixtures import atomic_checkpoint
from test_gazebo_action24_duration_matched import analysis_record
from test_gazebo_action24_history_restoration import samples, record_from_rows, movement


@pytest.fixture
def state():
    reference = json.loads(y.REFERENCE.read_text())
    return copy.deepcopy(reference['pre_Action24_comparison']['comparison']['RIGHT_HISTORY'])


def yaw_state(before, target):
    after = copy.deepcopy(before)
    angle = target-before['yaw_rad']
    dq = [0.,0.,math.sin(angle/2),math.cos(angle/2)]
    after['yaw_rad'] = target
    after['orientation_world_xyzw'] = y.rpy_quaternion(before['roll_rad'],before['pitch_rad'],target)
    for side,link in after['native_wheel_links'].items():
        delta = [v-u for u,v in zip(before['position_world_m'],link['position_world_m'])]
        dx,dy,dz = delta
        rotated = [math.cos(angle)*dx-math.sin(angle)*dy,math.sin(angle)*dx+math.cos(angle)*dy,dz]
        link['position_world_m'] = [v+d for v,d in zip(before['position_world_m'],rotated)]
        link['orientation_world_xyzw'] = y.dm.qmul(dq,link['orientation_world_xyzw'])
    return after


def arms(state):
    return {case:{'yaw_intervention':{'before':copy.deepcopy(state),
            'after':yaw_state(state,y.TARGETS[case]),'requested_pose':y.pose_payload(state,case,'simple_agent')}} for case in y.CASES}


def test_exact_right_history_and_terminal_suffix():
    expected='right left up down left down left right left up up right left left up down up'.split()
    for case in y.CASES:
        p=y.plan(case)
        assert p['actions']==expected
        assert p['prefix']==expected[:-2]
        assert p['canonical_indices']==list(range(8,25))
        assert p['terminal_suffix']==['23 DOWN','production BRAKE_LINEAR','production stopped contract','24 UP +0.5']
    assert y.TARGETS=={'RIGHT_YAW_SHAM':.282913297223,'RIGHT_YAW_MATCHED':.378577077577}


def test_requests_preserve_xyz_roll_pitch_and_phase(state):
    original=copy.deepcopy(state)
    for c in y.CASES:
        p=y.pose_payload(state,c,'simple_agent')
        assert list(p['position'].values())==state['position_world_m']
        q=list(p['orientation'].values());x,z,v,w=q
        roll=math.atan2(2*(w*x+z*v),1-2*(x*x+z*z))
        pitch=math.asin(2*(w*z-v*x))
        assert roll==pytest.approx(state['roll_rad'],abs=1e-15)
        assert pitch==pytest.approx(state['pitch_rad'],abs=1e-15)
        assert set(p)=={'name','position','orientation'}
    assert state==original


def good_row():
    return {'phase':'BRAKE_LINEAR','simulation_end':3.6,'iterations_contract_pass':True,
            'world_pose_history_contract':{'pass':True},'body_stopped_contract':{'pass':True},'collision_events':[]}


@pytest.mark.parametrize('field',['body_stopped_contract','world_pose_history_contract','iterations_contract_pass','collision_events'])
def test_stopped_brake_required_before_intervention(field):
    row=good_row();row[field]={'pass':False} if field.endswith('contract') else (['collision'] if field=='collision_events' else False)
    with pytest.raises(y.InvalidCapture):y.stopped_chunk(row)


def test_pose_sham_and_active_use_same_service_and_one_step(monkeypatch,tmp_path,state):
    for case in y.CASES:
        calls=[]
        stepper=SimpleNamespace(time=3.6,world='world')
        class Transport:
            request_history=[]
            def request(self,service,req,rep,payload,**kwargs):
                calls.append((service,req,rep,payload,kwargs))
                self.request_history.append({'service':service,'payload':payload,'attempts':[{'response':{'data':True}}]})
                return {'data':True}
        env=SimpleNamespace(stepper=stepper,transport=Transport(),controller=SimpleNamespace(name='simple_agent',get_pose=lambda *a:atomic_checkpoint(yaw_state(state,y.TARGETS[case]))['production_Pose_V']['pose']),
                            timeout=5,_refresh=lambda:calls.append('refresh'))
        env._refresh=lambda:(calls.append('refresh'),setattr(env,'pose',env.controller.get_pose()))
        adapter=SimpleNamespace(env=env)
        def mark(a):return {'iteration':round(stepper.time*1000),'sim_time_ns':round(stepper.time*1e9)}
        def advance(a):calls.append('one_step');stepper.time+=.001;return {'valid':True,'iteration_delta':1}
        monkeypatch.setattr(y.dm,'physics_mark',mark)
        monkeypatch.setattr(y.checkpoints,'acquire',lambda a,c,m,label:atomic_checkpoint(copy.deepcopy(state) if label=='PRE_RPC' else yaw_state(state,y.TARGETS[case]),label,m,phase=1000 if label=='PRE_RPC' else 1001))
        monkeypatch.setattr(y.checkpoints,'not_superseded',lambda *a:None)
        monkeypatch.setattr(y,'completed_brake_checkpoint',lambda *a:{'active_physics_transactions':0})
        def synchronize(a,i,ns,evidence):
            calls.append('pause_sync');return {'iteration':i,'sim_time_ns':ns}
        monkeypatch.setattr(y,'synchronize_paused',synchronize)
        monkeypatch.setattr(y,'exact_one_step',advance)
        evidence={};y.perform_intervention(adapter,case,tmp_path,None,good_row(),evidence)
        assert calls[0][:3]==('/world/world/set_pose','Pose','Boolean')
        assert calls[0][4]=={'max_attempts':1}
        assert calls[1:]==['one_step','pause_sync','refresh']
        assert evidence['advancing_iterations']==1 and evidence['elapsed_ns']==1_000_000
        assert evidence['requested_pose']['position']==dict(zip(('x','y','z'),state['position_world_m']))
        assert evidence['pose_service_call_count']==1


def test_exact_one_step_uses_separate_stepper_not_production_dt(monkeypatch):
    from aero_ai_studio.gazebo import stepping
    calls=[]
    class Probe:
        def __init__(self,t,w,**kw):
            calls.append(kw);self.last_verification={};self.time=0
        def step_simulation(self):
            self.time+=.001;self.last_verification={'valid':True,'iteration_delta':1}
    monkeypatch.setattr(stepping,'GazeboStepper',Probe)
    s=SimpleNamespace(world='world',time=3.6,dt=.1,timeout=5)
    a=SimpleNamespace(env=SimpleNamespace(stepper=s,transport=object()))
    assert y.exact_one_step(a)['iteration_delta']==1
    assert s.time==pytest.approx(3.601) and s.dt==.1
    assert calls==[{'physics_dt':.001,'dt':.001,'timeout':5}]


def test_reference_tolerances_are_fixed_and_tight():
    s=y.tolerance_spec();limits=s['per_arm_limits']
    assert s['calibration_iterations']==[3598,3599,3600,3601]
    assert limits['left.phase_rad']<2e-6 and limits['right.phase_rad']<2e-6
    assert max(limits['XYZ.'+str(j)] for j in range(3))<1e-6
    assert s['wheel_stopped_linear_equivalent_m_s']==.02
    assert s['pair_difference_of_changes_limits']=={k:2*v for k,v in limits.items()}


def test_clean_yaw_only_state_passes_isolation(state):
    result=y.isolation(arms(state),y.tolerance_spec())
    assert result['classification']=='YAW_INTERVENTION_ISOLATED',result['failures']
    assert result['observed_yaw_gap_rad']==pytest.approx(.095663780354,abs=1e-15)


@pytest.mark.parametrize('feature',['left_phase','right_phase','common_phase','XYZ','roll','velocity','Fn','depth','wrench','state','yaw'])
def test_collateral_changes_fail_isolation(state,feature):
    r=arms(state);s=r['RIGHT_YAW_MATCHED']['yaw_intervention']['after']
    if feature=='left_phase':s['wheel_phase_mod_2pi_rad']['left']+=.001
    elif feature=='right_phase':s['wheel_phase_mod_2pi_rad']['right']+=.001
    elif feature=='common_phase':
        for side in ('left','right'):s['wheel_phase_mod_2pi_rad'][side]+=.001
    elif feature=='XYZ':s['position_world_m'][0]+=.001
    elif feature=='roll':s['roll_rad']+=.001
    elif feature=='velocity':s['linear_velocity_world_m_s'][0]+=.1
    elif feature=='Fn':s['supports']['left_wheel']['Fn_N']+=1
    elif feature=='depth':s['supports']['left_wheel']['depths_m'][0]+=.001
    elif feature=='wrench':s['joint_transmitted_wrench']['left']['torque_norm_N_m']+=1
    elif feature=='state':s['supports']['left_wheel']['state']='VALID_EMPTY_CONTACT_SET'
    else:s['yaw_rad']+=.01
    result=y.isolation(r,y.tolerance_spec())
    assert result['classification']=='INTERVENTION_ISOLATION_FAILED'
    assert result['failures']


def test_phase_checks_report_left_right_differential_and_common(state):
    r=y.isolation(arms(state),y.tolerance_spec())
    for c in y.CASES:
        checks=r['observed'][c]['checks']
        assert all(k in checks for k in ('left.phase_rad','right.phase_rad','differential_phase_rad','common_phase_rad'))


@pytest.mark.parametrize('status',['INTERVENTION_ISOLATION_FAILED','CAPTURE_INVALID'])
def test_isolation_failure_blocks_all_causal_interpretations(status):
    labels={'RIGHT_YAW_SHAM':'RIGHT_YAW_SHAM_CANONICAL_FAILURE','RIGHT_YAW_MATCHED':'RIGHT_YAW_MATCHED_SUCCESS'}
    assert y.interpretation(status,labels)==status


@pytest.mark.parametrize('a,b,want',[
 ('CANONICAL_FAILURE','SUCCESS','YAW_NORMALIZATION_RESCUES_ACTION24_IN_RIGHT_HISTORY_CONTEXT'),
 ('CANONICAL_FAILURE','CANONICAL_FAILURE','YAW_NORMALIZATION_ALONE_INSUFFICIENT'),
 ('SUCCESS','SUCCESS','POSE_SERVICE_ITSELF_DISRUPTS_FAILURE_REPRODUCTION'),
 ('SUCCESS','CANONICAL_FAILURE','YAW_INTERVENTION_RESULT_UNRESOLVED')])
def test_interpretation_matrix(a,b,want):
    assert y.interpretation('YAW_INTERVENTION_ISOLATED',dict(zip(y.CASES,('RIGHT_YAW_SHAM_'+a,'RIGHT_YAW_MATCHED_'+b))))==want


@pytest.mark.parametrize('validity',[(False,True),(True,False),(False,False)])
def test_invalid_capture_never_classifies(monkeypatch,validity):
    monkeypatch.setattr(y.history,'classify_candidate',lambda *a:pytest.fail('must not classify'))
    with pytest.raises(y.InvalidCapture):
        y.analyze({},dict(zip(y.CASES,({'case_valid':v} for v in validity))),{})


def test_keyed_t0_and_actuation_are_separate():
    r=analysis_record(False)
    t=y.dm.command_active_t0(r)
    assert t['iteration']==121 and t['publication_iteration']==120
    assert t['first_observed_wheel_actuation']['iteration']==122
    r['native_samples'].reverse()
    with pytest.raises(y.InvalidCapture):y.dm.command_active_t0(r)


@pytest.mark.parametrize('stream',['support_rows','wrench_rows','native_samples'])
def test_missing_exact_required_iteration_invalid(stream):
    r=analysis_record(False);r[stream]=[row for row in r[stream] if row['iteration']!=126]
    with pytest.raises(y.InvalidCapture,match='126'):y.dm.terminal_alignment(r)


@pytest.mark.parametrize('persistent,valid,want',[
 (False,True,'SUPPORT_RECOVERY_AND_TRANSLATION_SUCCESS'),
 (False,False,'OTHER_PHYSICAL_OUTCOME'),
 (True,False,'CANONICAL_ACTION24_FAILURE_REPRODUCED')])
def test_physical_contract_unchanged(persistent,valid,want):
    record=movement(record_from_rows(samples(persistent=persistent)),valid)
    assert y.history.classify_candidate(record,{'case_valid':True})['classification']==want


def test_missing_events_returns_invalid_capture_not_indexerror():
    result=y.validate({'events':[]},y.CASES[0],None,43,None,set(),set())
    assert not result['case_valid'] and not result['physical_classifier_attempted']
    assert 'IndexError' not in str(result)


@pytest.mark.parametrize('prior',y.PROTECTED)
def test_old_evidence_never_output(prior):
    with pytest.raises(FileExistsError):y.ensure_output(prior)
    with pytest.raises(FileExistsError):y.ensure_output(prior/'child')


def test_preflight_only_static_artifacts(monkeypatch,tmp_path):
    production=tmp_path/'production.sdf';production.write_text('<sdf><world><physics><max_step_size>.001</max_step_size></physics></world></sdf>')
    digest=y.ab._sha(production)
    monkeypatch.setattr(y,'protected_manifest',lambda:{str(production):digest})
    monkeypatch.setattr(y,'audit_host1',lambda:{'classification':'PHASE_3H_AN_HOST1_DIAGNOSTIC_CAPTURE_FAILURE'})
    monkeypatch.setattr(y.history,'source',lambda *a:(None,43,{}))
    monkeypatch.setattr(y.history,'configured_reset_target',lambda *a:{'canonical':True})
    monkeypatch.setattr(y.ab,'_build_all',lambda *a:({},{}))
    monkeypatch.setattr(y.ab.GazeboWorldGenerator,'generate',lambda *a,**k:production)
    monkeypatch.setattr(y.ab,'PRODUCTION_HASH',digest)
    def fake_instrument(*args,topic_identity=None):
        diagnostic=tmp_path/('diag_'+topic_identity.replace('/','_')+'.sdf')
        diagnostic.write_text('<sdf><world><physics><max_step_size>.001</max_step_size></physics><plugin name="aero_diagnostic::NativeLinkVelocityObserver"/></world></sdf>')
        return diagnostic,{'native':{'topic':'/'+topic_identity}}
    monkeypatch.setattr(y.ab,'_instrument_world',fake_instrument)
    out=tmp_path/'static';r=y.preflight(tmp_path,out)
    assert r['status']=='PREFLIGHT_PASS' and not r['gazebo_launched'] and not r['runtime_evidence_created']
    assert not list(out.rglob('*.ndjson')) and not list(out.rglob('case_result.json'))
    assert not (out/'yaw_intervention_analysis.json').exists()
    assert len({x['instrumentation']['native']['topic'] for x in r['cases']})==2
    assert y.ab._sha(production)==digest


def test_production_hash_unchanged():
    path=y.ab.DEFAULT_ARTIFACT/'worlds/aero_ef81a06d3164/world.sdf'
    assert y.ab._sha(path)=='92def637ff4da2be1348502d345a30721cc845c34704f0b125d4ff1a26fdcc55'


def test_both_arms_automatically_preserved_on_capture_failure(monkeypatch,tmp_path,capsys):
    calls=[]
    monkeypatch.setattr(y,'protected_manifest',lambda:{})
    monkeypatch.setattr(y.history,'source',lambda *a:(None,43,{}))
    monkeypatch.setattr(y.ab,'_build_all',lambda *a:({},{}))
    def capture(case,scenario,out,*args):
        calls.append(case)
        record={'shutdown_completed':True,'canonical_reset_pose':{},'runtime_identity':{'partition':case,'topic':'/'+case}}
        y.write_json(out/'case_result.json',record)
        return record
    monkeypatch.setattr(y,'capture',capture)
    monkeypatch.setattr(y,'validate',lambda *a:{'case_valid':False,'invalid_reasons':['missing telemetry']})
    assert y.main(['--output',str(tmp_path/'out')])==1
    assert calls==list(y.CASES)
    assert all((tmp_path/'out'/c/'case_result.json').exists() for c in y.CASES)
    assert 'CAPTURED' not in capsys.readouterr().out.splitlines()


def analyzed_pair(state):
    rs={}
    for j,c in enumerate(y.CASES):
        r=analysis_record(j==0)
        r.update(configured_reset_condition={'same':True},runtime_identity={'partition':c,'topic':'/'+c},
                 wall_start_monotonic_s=j*2.,wall_end_after_shutdown_monotonic_s=j*2.+1.)
        r['yaw_intervention']=arms(state)[c]['yaw_intervention']
        rs[c]=r
    return rs


def test_full_analysis_emits_correct_physical_labels_and_keyed_table(state):
    r=y.analyze(analyzed_pair(state),{c:{'case_valid':True} for c in y.CASES},y.tolerance_spec())
    assert r['status']=='CAPTURED'
    assert r['interpretation']=='YAW_NORMALIZATION_RESCUES_ACTION24_IN_RIGHT_HISTORY_CONTEXT'
    assert r['case_outcomes']=={'RIGHT_YAW_SHAM':'RIGHT_YAW_SHAM_CANONICAL_FAILURE','RIGHT_YAW_MATCHED':'RIGHT_YAW_MATCHED_SUCCESS'}
    assert [x['delta_ms'] for x in r['detail_0_through_15_ms']]==list(range(16))
    assert all(t['publication_iteration']==120 and t['iteration']==121 for t in r['T0'].values())


def test_full_analysis_isolation_failure_never_calls_physical_classifier(monkeypatch,state):
    records=analyzed_pair(state)
    records['RIGHT_YAW_MATCHED']['yaw_intervention']['after']['wheel_phase_mod_2pi_rad']['left']+=.1
    monkeypatch.setattr(y.history,'classify_candidate',lambda *a:pytest.fail('isolation failed; classifier forbidden'))
    r=y.analyze(records,{c:{'case_valid':True} for c in y.CASES},y.tolerance_spec())
    assert r['interpretation']=='INTERVENTION_ISOLATION_FAILED'
    assert not r['physical_classification_created'] and r['case_outcomes']=={}
    assert all(not v['physical_classification_created'] for v in r['Action24'].values())


@pytest.mark.parametrize('field',['iteration_delta','duration_delta','publication','completion'])
def test_exact_post_service_timing_rejects_any_extra_step(field):
    req={'iteration':3600,'sim_time_ns':3_600_000_000}
    after={'iteration':3601,'sim_time_ns':3_601_000_000}
    it={'request_marker':copy.deepcopy(req),'service_completion_marker':copy.deepcopy(req),
        'before_Action24_publication_marker':copy.deepcopy(after),'first_advancing_post_service_marker':copy.deepcopy(after),
        'advancing_iterations':1,'elapsed_ns':1_000_000}
    t={'publication_iteration':3601,'publication_sim_time_ns':3_601_000_000}
    assert y.intervention_timing_validity(it,t)[2]==after
    if field=='iteration_delta':it['advancing_iterations']=2
    elif field=='duration_delta':it['elapsed_ns']=2_000_000
    elif field=='publication':t['publication_iteration']+=1
    else:it['service_completion_marker']['iteration']+=1
    with pytest.raises(y.InvalidCapture):y.intervention_timing_validity(it,t)


def test_tolerance_boundary_inclusive_and_next_float_fails(state):
    r=arms(state);tol=y.tolerance_spec()
    key='left.force_norm_N';limit=2**-10
    tol['per_arm_limits'][key]=limit;tol['pair_difference_of_changes_limits'][key]=2*limit
    v=r['RIGHT_YAW_MATCHED']['yaw_intervention']['after']['joint_transmitted_wrench']['left']
    v['force_norm_N']+=limit
    assert y.isolation(r,tol)['classification']=='YAW_INTERVENTION_ISOLATED'
    v['force_norm_N']=math.nextafter(v['force_norm_N'],math.inf)
    assert y.isolation(r,tol)['classification']=='INTERVENTION_ISOLATION_FAILED'


def test_runtime_hook_intervenes_after_callback_before_original_acquisition(monkeypatch,tmp_path,state):
    from aero_ai_studio.training import gazebo_physics as gp
    calls=[]
    original_environment=gp.GazeboPhysicsTrainingEnvironment
    class Base:
        def __init__(self):
            self.env=SimpleNamespace(stepper=SimpleNamespace(time=3.4),telemetry={},
                controller=SimpleNamespace(publish_sequence=1,last_published_command={},last_command=y.dm.gazebo_physics_twist('down')))
        def step(self,action):
            executor=gp.GazeboLinearReversalControlExecutor(self)
            def callback(row):calls.append('production_callback');return {}
            from aero_ai_studio.simulation.control_execution import ControlExecutionRequest,plan_control_execution
            p=plan_control_execution(ControlExecutionRequest('up',y.dm.gazebo_physics_twist('down'),y.dm.gazebo_physics_twist('up'),'LINEAR_REVERSAL'))
            return executor.execute_plan(p,on_braking_chunk=callback)
    class BaseExecutor:
        def __init__(self,adapter):self.training_environment=adapter
        def execute_plan(self,plan,*,on_braking_chunk=None):
            calls.append('brake_complete')
            on_braking_chunk(good_row())
            calls.append('original_acquisition')
            return SimpleNamespace(execution_evidence={},reason='complete',terminated=False)
    monkeypatch.setattr(gp,'GazeboPhysicsTrainingEnvironment',Base)
    monkeypatch.setattr(gp,'GazeboLinearReversalControlExecutor',BaseExecutor)
    monkeypatch.setattr(y,'perform_intervention',lambda *a:calls.append('intervention'))
    def capture_candidate(*a,**k):
        adapter=gp.GazeboPhysicsTrainingEnvironment()
        # The native wrapper is installed before inherited launch/discovery.
        y.ab.native.NativeVelocityCapture(None)
        y.ab._execute_captured(adapter,'up','CANONICAL_ACTION_17')
        assert calls==['brake_complete','production_callback','original_acquisition']
        calls.clear()
        y.ab._execute_captured(adapter,'up','BRAKE_LINEAR_THEN_UP')
        assert calls==['brake_complete','production_callback','intervention','original_acquisition']
        return {}
    monkeypatch.setattr(y.history,'capture_candidate',capture_candidate)
    y.capture(y.CASES[0],None,tmp_path,{},43,'unique')
    assert gp.GazeboPhysicsTrainingEnvironment is Base
    assert gp.GazeboLinearReversalControlExecutor is BaseExecutor
    assert original_environment is not Base


def test_same_raw_capture_is_never_overwritten(tmp_path):
    path=tmp_path/'out';path.mkdir();(path/'case_result.json').write_text('{}')
    with pytest.raises(FileExistsError):y.run(tmp_path,path)
    with pytest.raises(FileExistsError):y.preflight(tmp_path,path)
