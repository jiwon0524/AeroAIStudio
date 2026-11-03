"""Offline AN-G contracts and mocked lifecycle; live Gazebo is forbidden."""
import copy
import json
import threading
from types import SimpleNamespace
from pathlib import Path
import pytest

from tools import diagnose_v07_gazebo_action24_one_tick_control as t


def boundary(iteration=3600):
    return {"iteration": iteration, "sim_time_ns": iteration * 1_000_000, "paused": True}


def test_exact_two_arm_canonical_plans():
    assert t.CASES == ("ZERO_TICK_CONTROL", "ONE_TICK_TREATMENT")
    for case in t.CASES:
        p = t.plan(case)
        assert p["canonical_indices"] == list(range(8, 25))
        assert p["actions"] == "right left up down left down left right left up up right left left up down up".split()
        assert p["scenario_seed"] == 42 and p["reset_seed"] == 43
        assert p["previous_logical_action"] == "down"
        assert p["transition_type"] == "LINEAR_REVERSAL"
        assert p["phases"] == ["BRAKE_LINEAR", "stopped", "experiment checkpoint", "ACQUIRE_LINEAR"]


@pytest.mark.parametrize("case,steps", list(zip(t.CASES, (0, 1))))
def test_exact_duration_and_no_publication_contract(case, steps):
    t.verify_treatment(case, boundary(), boundary(3600 + steps), 99, 99, 0)


@pytest.mark.parametrize("case,steps", [(t.CASES[0], 1), (t.CASES[1], 0), (t.CASES[1], 2)])
def test_wrong_step_count_invalid(case, steps):
    with pytest.raises(t.InvalidCapture, match="iteration count"):
        t.verify_treatment(case, boundary(), boundary(3600 + steps), 99, 99, 0)


@pytest.mark.parametrize("case", t.CASES)
def test_no_added_zero_twist_or_other_publication(case):
    with pytest.raises(t.InvalidCapture, match="COMMAND_PUBLICATION"):
        t.verify_treatment(case, boundary(), boundary(3600 + t.CASES.index(case)), 99, 100, 0)


@pytest.mark.parametrize("case", t.CASES)
def test_pose_rpc_inside_treatment_is_forbidden(case):
    with pytest.raises(t.InvalidCapture, match="treatment window"):
        t.verify_treatment(case, boundary(), boundary(3600 + t.CASES.index(case)), 99, 99, 1)


def test_wrong_nanoseconds_invalid():
    end = boundary(3601)
    end["sim_time_ns"] += 1
    with pytest.raises(t.InvalidCapture, match="simulation duration"):
        t.verify_treatment(t.CASES[1], boundary(), end, 99, 99, 0)


@pytest.mark.parametrize("which", ("pre", "post"))
def test_explicit_pause_is_required(which):
    pre, post = boundary(), boundary()
    (pre if which == "pre" else post)["paused"] = False
    with pytest.raises(t.InvalidCapture, match="paused boundary"):
        t.verify_treatment(t.CASES[0], pre, post, 99, 99, 0)


@pytest.mark.parametrize("zero,one,pattern,allowed", [
    ("CANONICAL_ACTION24_FAILURE_REPRODUCED", "SUPPORT_RECOVERY_AND_TRANSLATION_SUCCESS", "ONE_PRE_ACQUISITION_TICK_SUFFICIENT_TO_CHANGE_OUTCOME_IN_THIS_CONTEXT", True),
    ("CANONICAL_ACTION24_FAILURE_REPRODUCED", "CANONICAL_ACTION24_FAILURE_REPRODUCED", "ONE_TICK_ALONE_INSUFFICIENT", True),
    ("SUPPORT_RECOVERY_AND_TRANSLATION_SUCCESS", "SUPPORT_RECOVERY_AND_TRANSLATION_SUCCESS", "COMMON_DIAGNOSTIC_TREATMENT_OR_REPRODUCIBILITY_CONFOUND", False),
    ("SUPPORT_RECOVERY_AND_TRANSLATION_SUCCESS", "CANONICAL_ACTION24_FAILURE_REPRODUCED", "UNEXPECTED_DIRECTIONAL_TICK_EFFECT", False),
    ("OTHER_PHYSICAL_OUTCOME", "SUPPORT_RECOVERY_AND_TRANSLATION_SUCCESS", "RESULT_UNRESOLVED", False),
])
def test_baseline_reproduction_gates_interpretation(zero, one, pattern, allowed):
    result = t.outcome_interpretation(zero, one)
    assert result["pattern"] == pattern
    assert result["causal_interpretation_allowed"] is allowed
    assert result["yaw_causal_status"] == "YAW_CAUSAL_RELEVANCE_UNRESOLVED"
    if not allowed:
        assert result["baseline_gate"] == "ZERO_TICK_BASELINE_REPRODUCTION_FAILED"


def test_exact_production_reset_conflict_is_proven():
    audit = t.reset_rpc_audit()
    assert audit["classification"] == "CANONICAL_RESET_REQUIRES_POSE_RPC"
    assert audit["whole_arm_NO_POSE_RPC_possible_without_reset_change"] is False
    assert len(audit["call_chain"]) == 3
    assert "set_pose" in audit["call_chain"][-1]["expression"]


def test_runtime_cli_dispatch_is_mocked(monkeypatch, capsys):
    calls=[]
    def fake_run(output,artifact_dir):
        calls.append(output)
        return {'status':'CAPTURE_FAILED','diagnostic_error':'fixture only'}
    monkeypatch.setattr(t,'run',fake_run)
    assert t.main(['--host-run'])==1
    assert calls==[t.DEFAULT_OUTPUT]
    assert 'fixture only' in capsys.readouterr().out


def test_preflight_canonical_reset_RPC_allowed_and_static_only(tmp_path,monkeypatch):
    libs={k:tmp_path/(k+'.so') for k in ('support','wrench','native')}
    for path in libs.values():path.write_text('synthetic build fixture, not loaded')
    builds={name:{'plugin_info_exit_code':0,'ldd_exit_code':0,'unresolved_dependencies':[]} for name in ('support','wrench')}
    builds['native']={'static_inspection':{'registration_status':'PASS','dependencies_status':'PASS'}}
    monkeypatch.setattr(t.ab,'_build_all',lambda _: (libs,builds))
    monkeypatch.setattr(t,'protected_manifest',lambda: {})
    monkeypatch.setattr(t,'audit_host1_sensor_failure',lambda:{'classification':'PHASE_3H_AN_G_HOST1_ZERO_TICK_CAPTURE_INFRASTRUCTURE_FAILURE'})
    result=t.preflight(tmp_path/'static')
    assert result['status']=='PREFLIGHT_PASS'
    assert result['reset_rpc_audit']['classification']=='CANONICAL_RESET_REQUIRES_POSE_RPC'
    assert all(result['gates'].values())
    assert not result['gazebo_launched'] and not result['runtime_evidence_created']
    assert result['runtime_execution_enabled']
    assert not list((tmp_path/'static').rglob('*.ndjson'))
    assert not list((tmp_path/'static').rglob('case_result.json'))
    assert result['production_sha256_before']==result['production_sha256_after']==t.EXPECTED_SHA


def test_existing_evidence_cannot_be_overwritten(tmp_path):
    existing = tmp_path / "existing"
    existing.mkdir()
    raw = existing / "case_result.json"
    raw.write_text("preserve")
    with pytest.raises(FileExistsError):
        t.preflight(existing)
    assert raw.read_text() == "preserve"
    with pytest.raises(FileExistsError):
        t.preflight(t.ROOT / "validation/v071-host/gazebo-action24-yaw-intervention-phase3han-host3")


def test_plan_is_not_runtime_evidence_and_copies_do_not_alias():
    a = t.plan(t.CASES[0])
    a["actions"].clear()
    assert len(t.plan(t.CASES[0])["actions"]) == 17
    assert t.plan(t.CASES[0])["runtime_implementation_ready"]


@pytest.fixture(autouse=True)
def forbid_live_simulation(monkeypatch):
    from aero_ai_studio.gazebo.process_manager import GazeboProcessManager
    def forbidden(*a,**k):
        raise AssertionError('LIVE GAZEBO FORBIDDEN IN OFFLINE TESTS')
    monkeypatch.setattr(GazeboProcessManager,'launch',forbidden)
    monkeypatch.setattr(t.ab,'_run_case',forbidden)


@pytest.fixture
def state():
    return copy.deepcopy(json.loads(t.y.REFERENCE.read_text())['pre_Action24_comparison']['comparison']['RIGHT_HISTORY'])


@pytest.mark.parametrize('service',['/world/x/set_pose','/world/x/set_pose/blocking','/world/x/set_pose_vector'])
def test_scope_boundaries_allow_reset_but_not_same_pose_treatment(service):
    pose={'kind':'RPC','service':service,'payload':{'same_pose':True}}
    logs=[pose,{'kind':'RPC','service':'/checkpoint'},pose,{'kind':'TWIST'},pose]
    assert t.audit_window(logs,1,2)['treatment_window_pose_rpc_count']==0
    with pytest.raises(t.InvalidCapture,match='POSE_RPC'):
        t.audit_window(logs,1,3)
    # Post-experiment operations are excluded, never silently counted as treatment.
    assert t.audit_window(logs,1,2)['end_audit_cursor_exclusive']==2


@pytest.mark.parametrize('case',t.CASES)
def test_mocked_treatment_calls_no_pose_or_twist_and_steps_exactly(case,state,monkeypatch,tmp_path):
    from yaw_checkpoint_fixtures import atomic_checkpoint
    calls=[]
    clock={'iteration':3600,'sim_time_ns':3_600_000_000,'paused':True}
    controller=SimpleNamespace(last_command={'linear':{'x':0.},'angular':{'z':0.}},publish_sequence=10,
                               get_pose=lambda *a: calls.append('get_pose') or current['pose'])
    adapter=SimpleNamespace(env=SimpleNamespace(controller=controller,previous_action='down',
                            stepper=SimpleNamespace(time=3.6),timeout=1,_refresh=lambda:calls.append('refresh')))
    current={}
    native=SimpleNamespace(samples=[])
    def checkpoint(adapter,native,mark,stage):
        calls.append(stage)
        cp=atomic_checkpoint(state,stage,mark,100 if stage=='PRE_RPC' else 200)
        cp['raw']['native']['world_pose_command_audit']={'enabled':True,'active_component_count':0,
            'component_observations_total':2,'read_callbacks_total':100 if stage=='PRE_RPC' else 200}
        current['pose']=cp['production_Pose_V']['pose']
        native.samples.append(cp['raw']['native'])
        return cp
    def step(adapter):
        calls.append('one_tick')
        clock['iteration']+=1;clock['sim_time_ns']+=1_000_000
        adapter.env.stepper.time+=.001
        return {'valid':True,'iteration_delta':1}
    def pause(adapter,i,ns,evidence):
        calls.append('pause')
        assert (i,ns)==(clock['iteration'],clock['sim_time_ns'])
        return dict(clock)
    monkeypatch.setattr(t.dm,'physics_mark',lambda _:dict(clock))
    monkeypatch.setattr(t.y,'completed_brake_checkpoint',lambda *a:{'active_physics_transactions':0})
    monkeypatch.setattr(t.checkpoints,'acquire',checkpoint)
    monkeypatch.setattr(t.checkpoints,'not_superseded',lambda *a:None)
    monkeypatch.setattr(t.y,'exact_one_step',step)
    monkeypatch.setattr(t.y,'synchronize_paused',pause)
    row={'phase':'BRAKE_LINEAR','iterations_contract_pass':True,'world_pose_history_contract':{'pass':True},
         'body_stopped_contract':{'pass':True},'collision_events':[]}
    evidence={};audit={'events':[]}
    t.perform_treatment(adapter,case,native,row,evidence,audit)
    assert calls.count('one_tick')==t.CASES.index(case)
    assert calls.count('pause')==1
    assert 'refresh' not in calls
    assert calls.count('PRE_RPC')==calls.count('POST_RPC')==1
    assert evidence['logical_before']==evidence['logical_after']
    assert evidence['post_marker']['iteration']-evidence['boundary_marker']['iteration']==t.CASES.index(case)
    assert audit['events']==[]


@pytest.mark.parametrize('change',('XYZ','yaw','phase','Fn','wrench','contact'))
def test_PRE_equivalence_blocks_changed_state(state,change):
    other=copy.deepcopy(state)
    if change=='XYZ':other['position_world_m'][0]+=.1
    elif change=='yaw':other['yaw_rad']+=.1
    elif change=='phase':other['wheel_phase_mod_2pi_rad']['left']+=.1
    elif change=='Fn':other['supports']['left_wheel']['Fn_N']+=1
    elif change=='wrench':other['joint_transmitted_wrench']['left']['torque_norm_N_m']+=1
    else:other['supports']['left_wheel']['state']='VALID_EMPTY_CONTACT_SET'
    assert t.pre_equivalence(state,other,t.y.tolerance_spec())['classification']=='PRE_TREATMENT_ARMS_DIFFERENT'


def test_identical_PRE_and_descriptive_POST_phase(state):
    assert t.pre_equivalence(state,copy.deepcopy(state),t.y.tolerance_spec())['classification']=='PRE_TREATMENT_ARMS_EQUIVALENT'
    changed=copy.deepcopy(state);changed['wheel_phase_mod_2pi_rad']['left']+=1e-8
    result=t.descriptive_delta(state,changed)
    assert result['description_only_not_an_isolation_gate']
    assert result['phase_deltas']['left']==pytest.approx(1e-8)
    assert result['phase_deltas']['differential_phase_rad']==pytest.approx(5e-9)
    assert result['phase_deltas']['common_phase_rad']==pytest.approx(5e-9)


@pytest.mark.parametrize('active,total',[(1,0),(0,None)])
def test_missing_or_active_WorldPoseCmd_audit_invalid(active,total):
    with pytest.raises(t.InvalidCapture):
        t.pose_command_counter({'world_pose_command_audit':{'enabled':True,'active_component_count':active,
                               'component_observations_total':total,'read_callbacks_total':3}})


def test_WorldPoseCmd_audit_is_opt_in_and_read_only():
    source=(t.ROOT/'tools/gazebo_native_link_velocity_observer.cc').read_text()
    assert 'auditWorldPoseCommands{false}' in source
    method=source[source.index('private: void ObservePoseCommands'):source.index('private: bool auditWorldPoseCommands')]
    assert 'const gz::sim::EntityComponentManager &' in method
    assert 'WorldPoseCmd' in method
    assert all(token not in method for token in ('CreateComponent','SetData','RemoveComponent','SetWorldPose'))


def test_event_relative_T0_not_wheel_actuation_and_keyed_sparse_rejection():
    from test_gazebo_action24_duration_matched import analysis_record
    record=analysis_record(False)
    t0=t.dm.command_active_t0(record)
    assert t0['iteration']==121
    assert t0['first_observed_wheel_actuation']['iteration']==122
    maps=t.dm.keyed_streams(record)
    maps['wrench_rows'].pop(126)
    with pytest.raises(t.InvalidCapture,match='126'):
        t.dm.aligned_sample(maps,126,'+5ms')


@pytest.mark.parametrize('persistent,expected',[(False,'SUPPORT_RECOVERY_AND_TRANSLATION_SUCCESS'),
                                              (True,'CANONICAL_ACTION24_FAILURE_REPRODUCED')])
def test_unchanged_production_physical_contract(persistent,expected):
    from test_gazebo_action24_history_restoration import samples,record_from_rows,movement
    r=movement(record_from_rows(samples(persistent=persistent)),not persistent)
    assert t.history.classify_candidate(r,{'case_valid':True})['classification']==expected
    with pytest.raises(t.InvalidCapture):
        t.history.classify_candidate(r,{'case_valid':False})


def test_invalid_case_cannot_physically_classify():
    with pytest.raises(t.InvalidCapture,match='invalid telemetry'):
        t.analyze({}, {c:{'case_valid':False} for c in t.CASES}, {})



def test_cli_requires_explicit_host_run_flag(monkeypatch):
    monkeypatch.setattr(t,'run',lambda *a:pytest.fail('unexpected runtime dispatch'))
    assert t.main([])==1


@pytest.mark.parametrize('same_key',('partition','topic'))
def test_fresh_independent_process_identities_required(same_key):
    a={'configured_reset_condition':{},'runtime_identity':{'partition':'a','topic':'a'},'shutdown_completed':True,
       'wall_end_after_shutdown_monotonic_s':1,'wall_start_monotonic_s':0}
    b=copy.deepcopy(a);b['runtime_identity']={'partition':'b','topic':'b'}
    b['wall_start_monotonic_s']=2
    t.pair_identity_gate(a,b)
    b['runtime_identity'][same_key]=a['runtime_identity'][same_key]
    with pytest.raises(t.InvalidCapture):t.pair_identity_gate(a,b)


def test_first_process_must_shutdown_before_second():
    a={'configured_reset_condition':{},'runtime_identity':{'partition':'a','topic':'a'},'shutdown_completed':True,
       'wall_end_after_shutdown_monotonic_s':3}
    b={'configured_reset_condition':{},'runtime_identity':{'partition':'b','topic':'b'},'shutdown_completed':True,
       'wall_start_monotonic_s':2}
    with pytest.raises(t.InvalidCapture):t.pair_identity_gate(a,b)


def test_earliest_support_topology_and_translation_report_is_event_relative(state):
    rows=[]
    for dt in range(8):
        a,b=copy.deepcopy(state),copy.deepcopy(state)
        a.update(iteration=100+dt,native_forward_displacement_from_T0_m=0)
        b.update(iteration=101+dt,native_forward_displacement_from_T0_m=0 if dt<5 else .000001)
        if dt>=5:
            b['supports']['left_wheel']['state']='VALID_EMPTY_CONTACT_SET'
            b['supports']['left_wheel']['Fn_N']=0
        rows.append({'delta_ms':dt,t.CASES[0]:a,t.CASES[1]:b})
    result=t.earliest_differences(rows)['first_exact_nonzero_difference']
    assert result['contact_topology']['delta_ms']==5
    assert result['body_forward_translation']['delta_ms']==5


@pytest.mark.parametrize('case',t.CASES)
def test_capture_wrapper_reset_allowed_window_fenced_and_no_extra_publication(case,state,monkeypatch,tmp_path):
    from aero_ai_studio.gazebo.transport import HarmonicTransport
    from aero_ai_studio.training.gazebo_physics import GazeboPhysicsTrainingEnvironment
    from yaw_checkpoint_fixtures import atomic_checkpoint
    transport=HarmonicTransport.__new__(HarmonicTransport)
    transport.condition=threading.Condition();transport.samples={};transport.partition='synthetic-'+case
    transport.request_history=[]
    clock=boundary(200)
    stepper=SimpleNamespace(time=.2)
    controller=SimpleNamespace(last_command=t.dm.gazebo_physics_twist('down'),publish_sequence=1)
    adapter=SimpleNamespace(env=SimpleNamespace(controller=controller,previous_action='down',stepper=stepper,timeout=1,
                            transport=transport,_refresh=lambda:None))
    native=SimpleNamespace(samples=[]);current={}
    def sync_clock():
        ns=clock['sim_time_ns'];transport.samples['/world/x/stats']={'iterations':clock['iteration'],'paused':True,
            'sim_time':{'sec':ns//1_000_000_000,'nsec':ns%1_000_000_000}}
        stepper.time=ns/1e9
    sync_clock()
    def request(self,service,request_type,response_type,payload,**kwargs):
        self.request_history.append({'service':service,'payload':copy.deepcopy(payload),'attempts':[{'response':{'data':True}}]})
        return {'data':True}
    def publish(self,*args):return None
    def reset(self,seed):
        transport.request('/world/x/set_pose','Pose','Boolean',{'canonical_reset':True})
    def acquire(adapter,native,mark,stage):
        transport.request('/native/checkpoint','Empty','Boolean',{})
        cp=atomic_checkpoint(state,stage,mark,100 if stage=='PRE_RPC' else 200)
        cp['raw']['native']['world_pose_command_audit']={'enabled':True,'active_component_count':0,
            'component_observations_total':10,'read_callbacks_total':100 if stage=='PRE_RPC' else 200}
        current['pose']=cp['production_Pose_V']['pose'];native.samples.append(cp['raw']['native'])
        return cp
    controller.get_pose=lambda *a:current['pose']
    def tick(adapter):
        clock.update(boundary(clock['iteration']+1));sync_clock()
        return {'valid':True,'iteration_delta':1}
    def pause(adapter,i,ns,ev):
        transport.request('/world/x/control','WorldControl','Boolean',{'pause':True})
        assert (i,ns)==(clock['iteration'],clock['sim_time_ns']);return copy.deepcopy(clock)
    def harness(c,scenario,output,libraries,seed,namespace):
        # Exercise real diagnostic wrappers; all production/transport internals mocked.
        GazeboPhysicsTrainingEnvironment.reset(adapter,seed)
        t.y.track_production_steps(adapter)
        clock.update(boundary(3600));sync_clock()
        controller.last_command={'linear':{'x':0.},'angular':{'z':0.}}
        transport.publish('/cmd','Twist',controller.last_command);controller.publish_sequence+=1
        row={'phase':'BRAKE_LINEAR','iterations_contract_pass':True,'world_pose_history_contract':{'pass':True},
             'body_stopped_contract':{'pass':True},'collision_events':[]}
        it={}
        t.y.perform_intervention(adapter,c,output,native,row,it)
        # Production apply_action sets last_command before calling transport.publish.
        controller.last_command=t.dm.gazebo_physics_twist('up')
        transport.publish('/cmd','Twist',controller.last_command);controller.publish_sequence+=1
        return {'yaw_intervention':it}
    monkeypatch.setattr(HarmonicTransport,'request',request)
    monkeypatch.setattr(HarmonicTransport,'publish',publish)
    monkeypatch.setattr(GazeboPhysicsTrainingEnvironment,'reset',reset)
    monkeypatch.setattr(t.y,'capture',harness)
    monkeypatch.setattr(t.y,'track_production_steps',lambda adapter:None)
    monkeypatch.setattr(t.dm,'physics_mark',lambda _:copy.deepcopy(clock))
    monkeypatch.setattr(t.y,'completed_brake_checkpoint',lambda *a:{'active_physics_transactions':0})
    monkeypatch.setattr(t.checkpoints,'acquire',acquire)
    monkeypatch.setattr(t.checkpoints,'not_superseded',lambda *a:None)
    monkeypatch.setattr(t.y,'exact_one_step',tick)
    monkeypatch.setattr(t.y,'synchronize_paused',pause)
    record=t.capture(case,None,tmp_path/case,{},43,'fixture')
    it=record['one_tick_treatment']
    assert it['treatment_window_pose_rpc_count']==0
    assert it['treatment_window_world_pose_cmd_count']==0
    assert it['treatment_window_additional_twist_publications']==0
    assert it['before_UP_publication_marker']['iteration']==3600+t.CASES.index(case)
    assert record['pose_RPC_counts']['canonical_reset_pose_rpc_count']==1
    assert record['pose_RPC_counts']['treatment_pose_rpc_count']==0
    twists=[e for e in record['command_audit'] if e['kind']=='TWIST']
    assert [e['phase'] for e in twists]==['canonical_history_and_production_braking','production_acquisition']
    assert twists[-1]['ordinal']==it['window_end_cursor']


@pytest.mark.parametrize('case',t.CASES)
def test_exact_window_RPC_policy_forbids_reset_and_additional_tick(case):
    def rpc(service,kind,payload):
        return {'kind':'RPC','service':service,'request_type':kind,'payload':payload,
                'response':{'data':True},'transport_evidence':{'attempts':[{}]}}
    events=[rpc('/native/checkpoint','Empty',{})]
    if case==t.CASES[1]:events.append(rpc('/world/x/control','WorldControl',{'pause':True,'multi_step':1}))
    events += [rpc('/world/x/control','WorldControl',{'pause':True}),rpc('/native/checkpoint','Empty',{})]
    t.window_rpc_policy(case,events,0,len(events))
    changed=copy.deepcopy(events);changed.insert(1,rpc('/world/x/control','WorldControl',{'pause':True,'reset':{'all':True}}))
    with pytest.raises(t.InvalidCapture,match='WorldControl'):t.window_rpc_policy(case,changed,0,len(changed))


def test_accepted_pause_evidence_requires_explicit_marker_argument():
    source=t.y.DEFAULT_OUTPUT/'yaw_intervention_host3_forensics.json'
    accepted=json.loads(source.read_text())['request_construction_and_sham']['RIGHT_YAW_SHAM']['pause_synchronization']
    t.validate_pause(accepted,accepted['marker'])
    with pytest.raises(t.InvalidCapture):t.validate_pause(accepted,{})



def test_static_native_dependency_failure_blocks_preflight():
    builds={name:{'plugin_info_exit_code':0,'ldd_exit_code':0,'unresolved_dependencies':[]} for name in ('support','wrench')}
    builds['native']={'static_inspection':{'registration_status':'PASS','dependencies_status':'FAIL'}}
    with pytest.raises(t.InvalidCapture,match='native observer'):t.verify_static_builds(builds)


def test_unknown_first_shutdown_never_launches_second(monkeypatch,tmp_path):
    monkeypatch.setattr(t,'protected_manifest',lambda:{})
    monkeypatch.setattr(t,'contract_self_check',lambda:{})
    monkeypatch.setattr(t.history,'source',lambda _: (None,43,None))
    monkeypatch.setattr(t.dm,'clock_spec',lambda:None)
    monkeypatch.setattr(t.y,'tolerance_spec',lambda:{})
    monkeypatch.setattr(t.y,'frozen_tolerance_digest',lambda _:None)
    monkeypatch.setattr(t.ab,'_build_all',lambda _: ({},{}))
    monkeypatch.setattr(t,'verify_static_builds',lambda _:None)
    calls=[]
    def fail(c,*a):
        calls.append(c)
        raise t.InvalidCapture('first setup failed; no shutdown record')
    monkeypatch.setattr(t,'capture',fail)
    report=t.run(tmp_path/'case')
    assert calls==[t.CASES[0]]
    assert report['status']=='CAPTURE_FAILED'
    assert not report['physical_classification_created']
    assert not report['capture_integrity'][t.CASES[1]]['case_valid']



class ScanClockTransport:
    def __init__(self):
        self.ns=3_600_000_000
        self.reads=[]
        self.publications=[]
    def subscribe(self,*args):
        return None
    def sample(self,topic,min_time,timeout):
        self.reads.append((self.ns,min_time))
        if self.ns/1e9<min_time:
            raise TimeoutError(f'No fresh Gazebo sample: {topic}, expected sim time >= {min_time}')
        return {'header':{'stamp':{'sec':self.ns//1_000_000_000,'nsec':self.ns%1_000_000_000}},
                'ranges':[5.,5.,5.,5.],'range_max':30.}
    def publish(self,topic,kind,payload):
        self.publications.append((self.ns,copy.deepcopy(payload)))


def test_exact_Host1_freshness_bound_regression_uses_unchanged_provider():
    from aero_ai_studio.gazebo.sensor_provider import RangeSensorProvider
    from aero_ai_studio.gazebo.contracts import SensorTimeoutError
    tr=ScanClockTransport();provider=RangeSensorProvider(tr,'x',(5.,2.),physics=True)
    provider.previous_timestamp=3.6;provider.sequence=36
    pose={'x':1.5,'y':1.5,'z':.11,'yaw':0.}
    with pytest.raises(SensorTimeoutError,match='3.600000001'):
        provider.get_range_observation(pose,3.598,simulation_time=3.6)
    assert provider.previous_timestamp==3.6 and provider.sequence==36
    assert tr.reads[-1][1]==3.600000001
    # This is why old ONE escaped the diagnostic gate; not a physical verdict.
    tr.ns+=1_000_000
    provider.get_range_observation(pose,3.599,simulation_time=3.601)
    assert provider.previous_timestamp==3.601 and provider.sequence==37


@pytest.mark.parametrize('case',t.CASES)
def test_real_production_sensor_only_consumed_after_fresh_UP_and_normal_advance(case,state,monkeypatch,tmp_path):
    from aero_ai_studio.gazebo.environment import GazeboEnvironment
    from aero_ai_studio.gazebo.sensor_provider import RangeSensorProvider
    from aero_ai_studio.gazebo.physics_controller import PhysicsEntityController
    from aero_ai_studio.training.gazebo_physics import GazeboPhysicsTrainingEnvironment
    from yaw_checkpoint_fixtures import atomic_checkpoint
    tr=ScanClockTransport();provider=RangeSensorProvider(tr,'x',(5.,2.),physics=True)
    provider.previous_timestamp=3.6;provider.sequence=36
    controller=PhysicsEntityController(tr,'x')
    controller.last_command={'linear':{'x':0.},'angular':{'z':0.}};controller.publish_sequence=42
    world=tmp_path/'world.sdf';world.touch()
    world.with_name('metadata.json').write_text(json.dumps({'goal_entity':'goal','obstacle_entities':[]}))
    controller.poses={'goal':{'position':{'x':5.,'y':2.}}}
    env=SimpleNamespace(controller=controller,sensors=provider,world=world,timeout=1,
                        stepper=SimpleNamespace(time=3.6),pose={'x':1.5,'y':1.5,'z':.11,'yaw':0.},
                        observation=object(),previous_action='down',minimum_clearance=float('inf'),telemetry={})
    env._refresh=lambda:GazeboEnvironment._refresh(env)
    # Establish a real production cached frame at the stopped boundary, then
    # prove the normal before-observation validator accepts it without a read.
    provider.previous_timestamp=3.5;provider.sequence=35
    env.observation=provider.get_range_observation(env.pose,3.598,simulation_time=3.6)
    assert provider.previous_timestamp==3.6 and provider.sequence==36
    tr.reads.clear()
    adapter=SimpleNamespace(env=env);native=SimpleNamespace(samples=[]);current={}
    controller.get_pose=lambda *a:current['pose']
    def mark():return {'iteration':tr.ns//1_000_000,'sim_time_ns':tr.ns,'paused':True}
    def acquire(adapter,native,marker,stage):
        cp=atomic_checkpoint(state,stage,marker,100 if stage=='PRE_RPC' else 200)
        cp['raw']['native']['world_pose_command_audit']={'enabled':True,'active_component_count':0,
                    'component_observations_total':10,'read_callbacks_total':100 if stage=='PRE_RPC' else 200}
        native.samples.append(cp['raw']['native']);current['pose']=cp['production_Pose_V']['pose']
        return cp
    def tick(adapter):
        tr.ns+=1_000_000;env.stepper.time=tr.ns/1e9
        return {'valid':True,'iteration_delta':1}
    def pause(adapter,i,ns,sync):
        assert ns==tr.ns and i==tr.ns//1_000_000
        return mark()
    monkeypatch.setattr(t.dm,'physics_mark',lambda _:mark())
    monkeypatch.setattr(t.y,'completed_brake_checkpoint',lambda *a:{'active_physics_transactions':0})
    monkeypatch.setattr(t.checkpoints,'acquire',acquire)
    monkeypatch.setattr(t.checkpoints,'not_superseded',lambda *a:None)
    monkeypatch.setattr(t.y,'exact_one_step',tick)
    monkeypatch.setattr(t.y,'synchronize_paused',pause)
    row={'phase':'BRAKE_LINEAR','iterations_contract_pass':True,'world_pose_history_contract':{'pass':True},
         'body_stopped_contract':{'pass':True},'collision_events':[]}
    evidence={};audit={'events':[]}
    before_cursor=t.sensor_cursor(adapter)
    t.perform_treatment(adapter,case,native,row,evidence,audit)
    assert tr.ns==3_600_000_000+t.CASES.index(case)*1_000_000
    assert tr.reads==[] and tr.publications==[]
    assert t.sensor_cursor(adapter)==before_cursor
    assert provider.previous_timestamp==3.6 and provider.sequence==36
    training=SimpleNamespace(env=env,max_sensor_age_ms=20)
    valid=GazeboPhysicsTrainingEnvironment._require_actual_sensor(training,env.observation)
    assert valid['timestamp']==3.6
    assert valid['age_ms']==pytest.approx(t.CASES.index(case))
    # Actual unchanged production controller publishes before any new scan read.
    controller.apply_action('up')
    assert tr.publications==[(tr.ns,t.dm.gazebo_physics_twist('up'))]
    assert controller.publish_sequence==43 and tr.reads==[]
    # Ordinary production acquisition advancement, then real production refresh.
    tr.ns+=100_000_000;env.stepper.time=tr.ns/1e9
    env._refresh()
    assert provider.previous_timestamp==tr.ns/1e9 and provider.sequence==37
    assert len(tr.reads)==1
    assert tr.reads[0][0]>tr.publications[0][0]
    fresh=GazeboPhysicsTrainingEnvironment._require_actual_sensor(training,env.observation,previous_sequence=36)
    assert fresh['timestamp']==tr.ns/1e9 and fresh['sequence']==37


def test_production_sensor_control_sources_and_canonical_order_unchanged():
    result=t.production_sensor_order_contract()
    lines=result['production_step_call_lines']
    assert lines['apply_action']<lines['step_simulation']<lines['_refresh']
    assert result['cached_before_observation']
    assert result['diagnostic_consuming_refresh_calls']==0


def test_sensor_order_audit_rejects_preUP_read_or_cache_mutation():
    before={'previous_timestamp':3.6,'sequence':36}
    it={'production_sensor_cursor_PRE':before,'production_sensor_cursor_POST':copy.deepcopy(before),
        'before_UP_publication_marker':{'sim_time_ns':3_600_000_000},'window_end_cursor':10}
    read={'phase':'production_acquisition','command_audit_cursor':11,'simulation_time':3.7,
          'sample_timestamp':3.7,'sequence_before':36,'sequence_after':37}
    r={'one_tick_treatment':it,'production_sensor_reads':[read]}
    assert t.validate_acquisition_sensor_order(r)['PRODUCTION_SENSOR_FRESHNESS_UNCHANGED']
    r['production_sensor_reads'][0]['phase']='treatment'
    with pytest.raises(t.InvalidCapture):t.validate_acquisition_sensor_order(r)
    r['production_sensor_reads'][0]['phase']='production_acquisition'
    it['production_sensor_cursor_POST']['sequence']=37
    with pytest.raises(t.InvalidCapture):t.validate_acquisition_sensor_order(r)


def test_Host1_is_invalid_infrastructure_and_ONE_is_not_physically_classified(monkeypatch):
    monkeypatch.setattr(t.history,'classify_candidate',lambda *a:pytest.fail('Host1 physical interpretation forbidden'))
    audit=t.audit_host1_sensor_failure()
    assert audit['classification']=='PHASE_3H_AN_G_HOST1_ZERO_TICK_CAPTURE_INFRASTRUCTURE_FAILURE'
    assert not audit['pair_valid'] and not audit['physical_interpretation_created']
    assert audit['cases'][t.CASES[0]]['no_fresh_UP_publication']
    assert audit['cases'][t.CASES[0]]['requested_scan_minimum_s']==3.600000001
    assert audit['cases'][t.CASES[1]]['classification']=='RUNTIME_CAPTURE_VALID_NO_PHYSICAL_INTERPRETATION'
    assert audit['ONE_classification']=='ONE_TICK_CURRENTLY_CONFOUNDED_WITH_SENSOR_FRESHNESS_GATE'
