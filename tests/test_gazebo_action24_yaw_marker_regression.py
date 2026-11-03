"""Offline regression of Host1's accepted-step / missing-paused-marker boundary."""
import copy
import json
from types import SimpleNamespace

import pytest

from tools import diagnose_v07_gazebo_action24_yaw_intervention as y
from aero_ai_studio.gazebo.stepping import GazeboStepper
from test_gazebo_action24_yaw_intervention import state, yaw_state, good_row, arms
from yaw_checkpoint_fixtures import atomic_checkpoint
from test_gazebo_linear_reversal_executor import _executor, _request


class Host1StatsTransport:
    """Actual Host1 structure: 3601 reached, but paused field omitted initially."""
    def __init__(self, sequence=313, mode='normal'):
        self.i,self.ns,self.seq=3600,3_600_000_000,sequence
        self.mode=mode;self.request_history=[];self.queue=[];self.ticks=0
        self.data=self.stats(True)
    def stats(self, paused=None):
        d={'iterations':self.i,'iterations_normalized':self.i,
           'sim_time':{'sec':self.ns//1_000_000_000,'nsec':self.ns%1_000_000_000}}
        if paused is not None:d['paused']=paused
        return d
    def subscribe(self,*a):pass
    def cursor(self,*a):return self.seq
    def sequence_snapshot(self):return {'stats':self.seq}
    def snapshot(self,*a):return {'data':copy.deepcopy(self.data),'sequence':self.seq,'received_at':0.}
    def sample(self,*a):return copy.deepcopy(self.data)
    def request(self,service,req,rep,payload,**kwargs):
        self.request_history.append({'service':service,'payload':copy.deepcopy(payload),'attempts':[{'response':{'data':True}}]})
        if payload.get('multi_step'):
            assert payload=={'pause':True,'multi_step':1}
            self.i+=1;self.ns+=1_000_000;self.ticks+=1;self.seq+=2
            self.data=self.stats()  # Matches paused_after:null from both Host1 arms.
        elif req=='WorldControl':
            assert payload=={'pause':True}
            a=self.stats();b=self.stats(True)
            if self.mode=='wrong_iteration':b['iterations']+=1;b['iterations_normalized']+=1
            if self.mode=='wrong_time':b['sim_time']['nsec']+=1
            if self.mode=='no_paused':b.pop('paused')
            self.queue=[] if self.mode=='missing' else [(self.seq+1,a),(self.seq+2,b)]
        return {'data':False} if self.mode=='rejected' and req=='WorldControl' else {'data':True}
    def messages_after(self,topic,cursor,timeout):
        frames=self.queue;self.queue=[]
        if frames:
            self.seq,self.data=copy.deepcopy(frames[-1])
        return copy.deepcopy(frames)


def adapter_for_transport(transport):
    owner=GazeboStepper(transport,'world',timeout=.01)
    owner.time=3.6
    verification={'valid':True,'iteration_delta':100,'expected_iteration_delta':100,
                  'after_sim_time':3.6,'iterations_after':3600,'paused_after':True}
    owner.last_verification=verification
    env=SimpleNamespace(transport=transport,stepper=owner)
    a=SimpleNamespace(env=env)
    row=good_row();row['step_evidence']=copy.deepcopy(verification)
    a._yaw_step_tracker={'active_depth':0,'completed_steps':[{'start_sim_time':3.5,'end_sim_time':3.6,'verification':copy.deepcopy(verification)}]}
    return a,row


@pytest.mark.parametrize('sequence',[313,315])
def test_exact_host1_step_returns_but_old_marker_fails_and_fresh_pause_repairs(sequence):
    t=Host1StatsTransport(sequence)
    a,_=adapter_for_transport(t)
    step=y.exact_one_step(a)
    assert step['valid'] is True and step['paused_after'] is None
    assert step['iterations_after']==3601 and step['after_sim_time']==3.601
    with pytest.raises(y.InvalidCapture,match='paused WorldStatistics for exact current simulation time 3601000000 ns missing; no physics advanced by marker'):
        y.dm.physics_mark(a)  # Exact Host1 old call/expression, unchanged helper.
    evidence={};mark=y.synchronize_paused(a,3601,3_601_000_000,evidence)
    assert mark['paused'] is True and mark['iteration']==3601
    assert mark['sim_time_ns']==3_601_000_000 and mark['stats_receive_sequence']>sequence+2
    assert t.ticks==1  # Pause synchronization never adds another physics tick.
    assert [x['payload'] for x in t.request_history]==[{'pause':True,'multi_step':1},{'pause':True}]
    assert evidence['observed_stats'][0]['data'].get('paused') is None
    assert evidence['observed_stats'][1]['data']['paused'] is True
    it={'post_service_pause_synchronization':evidence,'before_Action24_publication_marker':mark}
    y.pause_sync_validity(it)


@pytest.mark.parametrize('case',y.CASES)
def test_complete_repaired_intervention_handles_host1_null_pause_without_ordering_failure(monkeypatch,tmp_path,state,case):
    t=Host1StatsTransport();a,row=adapter_for_transport(t)
    calls=[]
    a.env.controller=SimpleNamespace(name='simple_agent',get_pose=lambda *args:atomic_checkpoint(yaw_state(state,y.TARGETS[case]))['production_Pose_V']['pose'])
    a.env.timeout=.01;a.env._refresh=lambda:(calls.append('refresh'),setattr(a.env,'pose',a.env.controller.get_pose()))
    def observed(adapter,native,mark,label):
        calls.append(('checkpoint',mark['iteration']))
        selected=copy.deepcopy(state) if label=='PRE_RPC' else yaw_state(state,y.TARGETS[case])
        return atomic_checkpoint(selected,label,mark,phase=1000 if label=='PRE_RPC' else 1001)
    monkeypatch.setattr(y.checkpoints,'acquire',observed)
    monkeypatch.setattr(y.checkpoints,'not_superseded',lambda *a:None)
    evidence={};y.perform_intervention(a,case,tmp_path,None,row,evidence)
    # The old Host1 perform_intervention deterministically fails before after/native.
    assert evidence['pre_acquire_checkpoint_ready'] is True
    assert evidence['post_service_step_verification']['paused_after'] is None
    assert evidence['post_service_pause_synchronization']['valid'] is True
    assert evidence['pose_application_proof']['valid'] is True
    assert evidence['advancing_iterations']==1 and evidence['elapsed_ns']==1_000_000
    assert calls==[('checkpoint',3600),('checkpoint',3601),'refresh']
    assert [x['payload'] for x in t.request_history if x['service'].endswith('set_pose')]==[evidence['requested_pose']]
    assert t.ticks==1 and a.env.stepper.dt==.1


@pytest.mark.parametrize('mode',['missing','no_paused','wrong_iteration','wrong_time','rejected'])
def test_missing_or_inexact_explicit_marker_invalid_never_fabricated(mode):
    t=Host1StatsTransport(mode=mode);a,_=adapter_for_transport(t)
    # Prepare the exact post-step state without a second physics request.
    t.i=3601;t.ns=3_601_000_000;t.data=t.stats();a.env.stepper.time=3.601
    with pytest.raises(y.InvalidCapture):y.synchronize_paused(a,3601,3_601_000_000,{})
    assert t.ticks==0


@pytest.mark.parametrize('fault',['active','no_completed','wrong_completion','bad_verification'])
def test_intervention_cannot_step_inside_inflight_or_unproven_transaction(fault):
    t=Host1StatsTransport();a,row=adapter_for_transport(t)
    if fault=='active':a._yaw_step_tracker['active_depth']=1
    elif fault=='no_completed':a._yaw_step_tracker['completed_steps']=[]
    elif fault=='wrong_completion':a._yaw_step_tracker['completed_steps'][0]['end_sim_time']=3.5
    else:a.env.stepper.last_verification={'valid':False}
    with pytest.raises(y.InvalidCapture):y.perform_intervention(a,y.CASES[0],None,None,row,{})
    assert t.ticks==0 and not t.request_history


def test_tracker_restores_no_inflight_step_after_success_and_error():
    s=SimpleNamespace(time=3.5,last_verification={})
    def step():s.time=3.6;s.last_verification={'valid':True};return s.time
    s.step_simulation=step;a=SimpleNamespace(env=SimpleNamespace(stepper=s))
    y.track_production_steps(a)
    assert s.step_simulation()==3.6 and a._yaw_step_tracker['active_depth']==0
    assert len(a._yaw_step_tracker['completed_steps'])==1


def test_real_production_executor_constructs_acquisition_baseline_after_completed_callback():
    executor,adapter,physics=_executor()
    events=[]
    def callback(row):
        events.append(('brake_chunk',row['simulation_end'],row['body_stopped_contract']['pass']))
        if row['body_stopped_contract']['pass']:
            # Simulate only the diagnostic's already-completed, synchronized tick.
            # Actual executor code must take its acquisition clock/cursor afterwards.
            physics.stepper.time+=.001
            events.append(('synchronized_checkpoint',physics.stepper.time))
        return {}
    result=executor.execute_plan(executor.plan(_request()),on_braking_chunk=callback)
    phases=result.execution_evidence['phase_evidence']
    assert result.status.value=='EXECUTED'
    assert adapter.actions==['up']
    assert phases[0]['completion_result'] is True
    assert phases[0]['end_sim_time']==pytest.approx(2.201)
    assert phases[1]['start_sim_time']==pytest.approx(2.201)
    assert phases[1]['acquire_publish_sim_time']==pytest.approx(2.201)
    assert phases[1]['simulation_time_equal_at_publish'] is True
    assert events[-1][0]=='synchronized_checkpoint'


def test_between_action_stopping_would_destroy_canonical_transition():
    down=y.dm.gazebo_physics_twist('down')
    proof=y.canonical_transition(down)
    assert proof['transition_type']=='LINEAR_REVERSAL' and down==y.dm.gazebo_physics_twist('down')
    with pytest.raises(y.InvalidCapture,match='actual DOWN'):
        y.canonical_transition({'linear':{'x':0.},'angular':{'z':0.}})


def test_pose_application_must_be_observed_before_acquisition(state):
    with pytest.raises(y.InvalidCapture,match='yaw application not proven'):
        y.prove_pose_application(state,'RIGHT_YAW_MATCHED')
    target=yaw_state(state,y.TARGETS['RIGHT_YAW_MATCHED'])
    assert y.prove_pose_application(target,'RIGHT_YAW_MATCHED')['valid']
    del target['native_wheel_links']
    with pytest.raises(y.InvalidCapture):
        y.prove_pose_application(target,'RIGHT_YAW_MATCHED')


def test_predetermined_isolation_limits_exactly_equal_failed_host1_preflight():
    saved=json.loads((y.HOST1/'yaw_intervention_preflight.json').read_text())['tolerances']
    assert y.tolerance_spec()==saved
    assert y.DEFAULT_OUTPUT.name=='gazebo-action24-yaw-intervention-phase3han-host3'
    with pytest.raises(FileExistsError):y.ensure_output(y.HOST1)


def test_yaw_isolation_failure_does_not_emit_captured_or_causal_result(monkeypatch,tmp_path,capsys):
    monkeypatch.setattr(y,'run',lambda *a:{'status':'INTERVENTION_ISOLATION_FAILED','isolation':{'failures':['phase changed']},'interpretation':'INTERVENTION_ISOLATION_FAILED'})
    assert y.main(['--output',str(tmp_path/'host2')])==2
    text=capsys.readouterr().out
    assert 'INTERVENTION_ISOLATION_FAILED' in text
    assert 'CAPTURED' not in text and 'YAW_NORMALIZATION_RESCUES' not in text


@pytest.mark.parametrize('field',['commanded_twist','action_publish_sequence','action_command_sim_time'])
def test_fresh_positive_up_publication_still_required(field):
    from test_gazebo_action24_duration_matched import analysis_record
    record=analysis_record(False)
    record['events'][0]['action_publication'].pop(field)
    with pytest.raises(y.InvalidCapture,match='publication'):
        y.dm.command_active_t0(record)


def test_missing_acquire_phase_invalidates_even_with_an_up_named_event():
    from test_gazebo_action24_duration_matched import analysis_record
    record=analysis_record(False)
    event=record['events'][0]
    record['events']=[dict(canonical_index=i,action=a) for i,a in zip(range(8,24),y.plan(y.CASES[0])['actions'][:-1])]+[event]
    event['execution_evidence']={'phase_evidence':[{'phase':'BRAKE_LINEAR','completion_result':True,'end_sim_time':.120}]}
    check=y.validate(record,y.CASES[0],None,43,None,set(),set())
    assert not check['case_valid']
    assert any('BRAKE_LINEAR/stopped/ACQUIRE_LINEAR ordering not proven' in x for x in check['invalid_reasons'])
    assert check['physical_classifier_attempted'] is False


def test_pause_marker_never_accepted_from_ack_alone():
    with pytest.raises(y.InvalidCapture,match='marker/RPC proof missing'):
        y.pause_sync_validity({'post_service_pause_synchronization':{'response':{'data':True}}})
