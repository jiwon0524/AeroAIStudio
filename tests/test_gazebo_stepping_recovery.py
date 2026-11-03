import time
import pytest

from aero_ai_studio.gazebo.stepping import GazeboStepper
from aero_ai_studio.gazebo.stepping import (
    model_only_reset_stats_contract,
    world_reset_stats_contract,
)
from aero_ai_studio.gazebo.transport import normalize_topic_message


class StatsTransport:
    def __init__(self,mode):
        self.mode=mode;self.time=0.;self.iterations=0;self.paused=True;self.sequence=0
        self.requests=0;self.calls=[];self.available=True;self.history=[]

    def subscribe(self,*args):pass

    def _stats(self):
        sample={'sim_time':{'sec':int(self.time),'nsec':round((self.time%1)*1e9)},
                'iterations':self.iterations,'paused':self.paused}
        if self.mode=='reset_omitted_iterations' and self.time==0.:
            sample.pop('iterations')
            return normalize_topic_message('WorldStatistics',sample)
        return sample

    def sample(self,topic,min_time=-1,timeout=5):
        if not self.available:raise TimeoutError('stats unavailable')
        result=self._stats()
        stamp=result['sim_time']['sec']+result['sim_time']['nsec']*1e-9
        if stamp<min_time:raise TimeoutError('stats stale')
        return result

    def snapshot(self,topic):
        return {'data':self._stats() if self.available else None,
                'sequence':self.sequence,'received_at':time.monotonic() if self.available else None}

    def sequence_snapshot(self):return {'/scan':self.sequence}

    def messages_after(self,topic,sequence,timeout=0):
        return [(seq,data) for seq,data in self.history if seq>sequence]

    def sample_after_sequence(self,topic,after_sequence,*,min_time=-1,max_time=None,timeout=5):
        from aero_ai_studio.gazebo.transport import stamp
        for seq,data in self.messages_after(topic,after_sequence,timeout):
            value=stamp(data)
            if value>=min_time and (max_time is None or value<=max_time):return data,seq
        raise TimeoutError('no fresh stats')

    def _publish_stats(self):
        self.sequence+=1;self.history.append((self.sequence,self._stats()))

    def request(self,service,request_type,response_type,payload):
        self.calls.append(dict(payload));self.requests+=1
        if payload.get('reset',{}).get('model_only') is True:
            if self.mode=='model_only_rejected':return {'data':False}
            if self.mode=='model_only_bad_iterations':self.iterations+=1
            self.paused=True;self._publish_stats()
            return {'data':True}
        if payload.get('reset',{}).get('all') is True:
            if self.mode=='reset_unconfirmed':return {'data':True}
            self.time=0.;self.iterations=0;self.paused=True;self._publish_stats()
            return {'data':True}
        if self.mode=='false':return {'data':False}
        if self.mode=='normal':self._advance(.1,100);return {'data':True}
        if self.mode=='executed_lost':self._advance(.1,100);raise TimeoutError('CLI acknowledgement lost')
        if self.mode=='iteration_mismatch':self._advance(.1,99);raise TimeoutError('CLI acknowledgement lost')
        if self.mode=='unpaused_after_timeout':
            self._advance(.1,100);self.paused=False;self._publish_stats();raise TimeoutError('CLI acknowledgement lost')
        if self.mode=='ack_without_progress':return {'data':True}
        if self.mode=='zero_then_retry' and self.requests==1:
            self._publish_stats();raise TimeoutError('service did not execute')
        if self.mode=='stats_unavailable':
            self.available=False;raise TimeoutError('service timed out')
        if self.mode=='partial':self._advance(.04,40);raise TimeoutError('partial execution')
        if self.mode=='excessive':self._advance(.2,200);raise TimeoutError('unexpected extra execution')
        if self.mode=='retry_lost' and self.requests==1:
            self._publish_stats();raise TimeoutError('first call not executed')
        if self.mode=='retry_lost' and self.requests==2:
            self._advance(.1,100);raise TimeoutError('retry response lost')
        if self.mode=='retry_exact' and self.requests==1:
            self._publish_stats();raise TimeoutError('first call not executed')
        self._advance(.1,100);return {'data':True}

    def _advance(self,seconds,iterations):
        self.time+=seconds;self.iterations+=iterations;self.paused=True;self._publish_stats()


def make_stepper(mode):
    t=StatsTransport(mode)
    return t,GazeboStepper(t,'test',physics_dt=.001,dt=.1,timeout=.01)


def test_normal_control_response_requires_expected_simulation_progress():
    t,s=make_stepper('normal')
    assert s.step_simulation()==pytest.approx(.1)
    assert s.last_verification['classification']=='acknowledged'
    assert s.last_verification['observed_delta']==pytest.approx(.1)
    assert s.last_verification['iteration_delta']==100
    assert s.last_verification['paused_ok']
    assert len(t.calls)==1


def test_timeout_after_exact_progress_reconciles_without_duplicate_step():
    t,s=make_stepper('executed_lost')
    assert s.step_simulation()==pytest.approx(.1)
    assert s.last_verification['classification']=='executed_response_lost'
    assert s.last_verification['retry_count']==0
    assert s.last_verification['duplicate_step_prevented']
    assert len(t.calls)==1


@pytest.mark.parametrize('mode',["zero_then_retry","retry_exact"])
def test_zero_progress_is_the_only_timeout_state_that_can_retry(mode):
    t,s=make_stepper(mode)
    assert s.step_simulation()==pytest.approx(.1)
    assert s.last_verification['classification']=='acknowledged'
    assert s.last_verification['retry_count']==1
    assert s.last_verification['duplicate_step_prevented']
    assert len(t.calls)==2
    assert t.time==pytest.approx(.1)


def test_timeout_after_partial_progress_fails_without_retry():
    t,s=make_stepper('partial')
    with pytest.raises(RuntimeError,match='refusing duplicate step'):
        s.step_simulation()
    assert s.last_verification['classification']=='ambiguous_partial_progress'
    assert s.last_verification['observed_delta']==pytest.approx(.04)
    assert s.last_verification['retry_count']==0
    assert len(t.calls)==1


def test_timeout_after_excessive_progress_fails_without_retry():
    t,s=make_stepper('excessive')
    with pytest.raises(RuntimeError,match='refusing duplicate step'):
        s.step_simulation()
    assert s.last_verification['observed_delta']==pytest.approx(.2)
    assert len(t.calls)==1


def test_retry_response_lost_is_reconciled_at_exact_expected_progress():
    t,s=make_stepper('retry_lost')
    assert s.step_simulation()==pytest.approx(.1)
    assert s.last_verification['classification']=='executed_response_lost'
    assert s.last_verification['retry_count']==1
    assert len(t.calls)==2


def test_boolean_false_is_rejected_without_timeout_recovery_or_retry():
    t,s=make_stepper('false')
    with pytest.raises(RuntimeError,match='Boolean false'):
        s.step_simulation()
    assert s.last_verification['classification']=='service_rejected'
    assert not s.last_verification['service_timeout']
    assert len(t.calls)==1


def test_timeout_with_unavailable_stats_fails_closed_without_retry():
    t,s=make_stepper('stats_unavailable')
    with pytest.raises(RuntimeError,match='fresh /stats evidence is unavailable'):
        s.step_simulation()
    assert s.last_verification['classification']=='ambiguous_stats_unavailable'
    assert s.last_verification['duplicate_step_prevented']
    assert len(t.calls)==1


@pytest.mark.parametrize('mode',['iteration_mismatch','unpaused_after_timeout'])
def test_exact_time_without_iteration_or_pause_evidence_does_not_reconcile(mode):
    t,s=make_stepper(mode)
    with pytest.raises(RuntimeError,match='refusing duplicate step'):
        s.step_simulation()
    assert s.last_verification['classification']=='ambiguous_partial_progress'
    assert len(t.calls)==1


def test_acknowledged_request_with_unverified_progress_is_never_retried():
    t,s=make_stepper('ack_without_progress')
    with pytest.raises(RuntimeError,match='acknowledged WorldControl'):
        s.step_simulation()
    assert s.last_verification['classification']=='acknowledged_progress_unverified'
    assert len(t.calls)==1


def test_duplicate_step_prevention_preserves_original_multi_step_payload():
    t,s=make_stepper('executed_lost')
    s.step_simulation()
    assert t.calls==[{'pause':True,'multi_step':100}]


def test_world_reset_all_reconciles_new_paused_time_epoch_without_stepping():
    t,s=make_stepper('normal')
    t._advance(.3,300);s.time=.3
    evidence=s.reset_world()
    assert evidence['method']=='world_control_reset_all'
    assert evidence['valid'] is True
    assert evidence['after_sim_time']==pytest.approx(0.)
    assert evidence['after_iterations']==0
    assert evidence['paused_after'] is True
    assert s.time==pytest.approx(0.)
    assert t.calls[-1]=={'pause':True,'reset':{'all':True}}


def test_world_reset_all_accepts_protobuf_omitted_zero_iterations_and_records_provenance():
    t,s=make_stepper('reset_omitted_iterations')
    t._advance(.3,300);s.time=.3
    evidence=s.reset_world()
    assert evidence['valid'] is True
    assert evidence['stats_sequence_before']==1
    assert evidence['stats_sequence_after']==2
    assert evidence['after_sim_time']==pytest.approx(0.)
    assert evidence['paused_after'] is True
    assert evidence['iterations_raw_present'] is False
    assert evidence['iterations_normalized']==0
    assert evidence['iterations_defaulted_from_protobuf'] is True
    assert evidence['stats_reset_contract']['pass'] is True


def test_model_only_reset_preserves_time_iterations_and_pause_with_new_stats_sequence():
    t,s=make_stepper('normal')
    t._advance(.6,600);s.time=.6
    evidence=s.reset_model_only()
    assert evidence['method']=='world_control_reset_model_only'
    assert evidence['valid'] is True
    assert evidence['before_sim_time']==pytest.approx(.6)
    assert evidence['after_sim_time']==pytest.approx(.6)
    assert evidence['before_iterations']==evidence['after_iterations']==600
    assert evidence['stats_sequence_after']>evidence['stats_sequence_before']
    assert evidence['paused_after'] is True
    assert s.time==pytest.approx(.6)
    assert t.calls[-1]=={'pause':True,'reset':{'model_only':True}}
    assert evidence['stats_reset_contract']['iterations_preserved'] is True


@pytest.mark.parametrize('mode', ['model_only_rejected','model_only_bad_iterations'])
def test_model_only_rejects_false_rpc_or_changed_iteration_contract(mode):
    t,s=make_stepper(mode)
    t._advance(.6,600);s.time=.6
    with pytest.raises(RuntimeError):
        s.reset_model_only()
    assert s.last_verification['classification']=='world_reset_model_only_failed'


@pytest.mark.parametrize('before,after,seq_before,seq_after,expected', [
    ({'sim_time':{'sec':1},'iterations':100,'paused':True},
     {'sim_time':{'sec':1},'iterations':100,'paused':True},2,3,True),
    ({'sim_time':{'sec':1},'iterations':100,'paused':True},
     {'sim_time':{'sec':1},'iterations':101,'paused':True},2,3,False),
    ({'sim_time':{'sec':1},'iterations':100,'paused':True},
     {'sim_time':{'sec':1},'iterations':100,'paused':False},2,3,False),
    ({'sim_time':{'sec':1},'iterations':100,'paused':True},
     {'sim_time':{'sec':2},'iterations':200,'paused':True},2,3,False),
    ({'sim_time':{'sec':1},'iterations':100,'paused':True},
     {'sim_time':{'sec':1},'iterations':100,'paused':True},2,2,False),
])
def test_model_only_stats_contract_preserves_epoch_and_iterations(before,after,seq_before,seq_after,expected):
    contract=model_only_reset_stats_contract(before,after,seq_before,seq_after)
    assert contract['pass'] is expected


def test_world_statistics_normalization_is_limited_to_iterations_schema():
    explicit_zero=normalize_topic_message('WorldStatistics',
        {'sim_time':{},'iterations':0,'paused':True})
    omitted=normalize_topic_message('WorldStatistics',{'sim_time':{},'paused':True})
    nonzero=normalize_topic_message('WorldStatistics',
        {'sim_time':{'sec':2},'iterations':'2200','paused':True})
    odometry=normalize_topic_message('Odometry',{'linear_x':None})
    assert explicit_zero['iterations']==explicit_zero['iterations_normalized']==0
    assert explicit_zero['iterations_raw_present'] is True
    assert omitted['iterations']==omitted['iterations_normalized']==0
    assert omitted['iterations_raw_present'] is False
    assert omitted['iterations_defaulted_from_protobuf'] is True
    assert nonzero['iterations']==nonzero['iterations_normalized']==2200
    assert nonzero['iterations_raw_value']=='2200'
    assert nonzero['iterations_defaulted_from_protobuf'] is False
    assert 'iterations' not in odometry
    with pytest.raises(TypeError,match='parsed message dictionary'):
        normalize_topic_message('WorldStatistics',None)


@pytest.mark.parametrize('sample,before,after,failed',[ 
    ({'sim_time':{},'iterations':0,'paused':True},4,4,'stats_sequence_new'),
    ({'sim_time':{'sec':1},'iterations':0,'paused':True},4,5,'initial_sim_time'),
    ({'sim_time':{},'iterations':0,'paused':False},4,5,'paused'),
    ({'sim_time':{},'iterations':1,'paused':True},4,5,'iterations_zero'),
    ({'paused':True,'iterations':0},4,5,'sim_time_present'),
])
def test_world_reset_stats_contract_rejects_incomplete_or_invalid_reset_evidence(
        sample,before,after,failed):
    result=world_reset_stats_contract(sample,before,after)
    assert result['pass'] is False
    assert failed in result['failure_reason']


def test_saved_actual_reset_all_stats_fixture_passes_after_typed_normalization():
    import json
    from pathlib import Path
    fixture=json.loads((Path(__file__).parent/'fixtures'/'gazebo_reset_world_stats_zero_omitted_actual.json').read_text())
    stats=normalize_topic_message('WorldStatistics',fixture['after_world_statistics_raw'])
    contract=world_reset_stats_contract(stats,fixture['stats_sequence_before'],
                                        fixture['stats_sequence_after'])
    assert fixture['service_response']['data'] is True
    assert contract['pass'] is True
    assert contract['simulation_time']==pytest.approx(0.)
    assert contract['iterations_raw_present'] is False
    assert contract['iterations_normalized']==0
    assert contract['iterations_defaulted_from_protobuf'] is True


def test_world_reset_ack_without_fresh_epoch_stats_fails_closed():
    t,s=make_stepper('reset_unconfirmed')
    t._advance(.3,300);s.time=.3
    with pytest.raises(TimeoutError,match='stats') as error:
        s.reset_world()
    assert error.value.reset_evidence['valid'] is False
    assert len(t.calls)==1
