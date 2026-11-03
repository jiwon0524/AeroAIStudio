import copy
import json
from types import SimpleNamespace
import pytest
from tools import diagnose_v07_gazebo_action24_yaw_intervention as y
from tools import gazebo_yaw_checkpoints as cp
from test_gazebo_action24_yaw_intervention import state,yaw_state,arms
from test_gazebo_action24_duration_matched import analysis_record
from yaw_checkpoint_fixtures import atomic_checkpoint


def test_exact_host2_same_time_newer_paused_origin_regression(state):
    forensic=json.loads((y.HOST2/'yaw_intervention_isolation_forensics.json').read_text())
    evidence=forensic['sample_alignment_audit']['cases']['RIGHT_YAW_MATCHED']['PRE_update_phase_staleness']
    old=evidence['saved_advancing_PRE'];current=evidence['current_paused_native_before_RPC']
    assert old['iteration']==current['iteration']==3600 and old['sim_time_ns']==current['sim_time_ns']==3_600_000_000
    old_payload=y.pose_payload(old,'RIGHT_YAW_MATCHED','simple_agent')
    assert [old_payload['position'][key]-current['position_world_m'][j] for j,key in enumerate(('x','y','z'))]==pytest.approx([2.566397647729701e-7,-1.570749199597543e-7,-4.727277424509957e-7],abs=1e-20)
    newer=copy.deepcopy(state)
    for key in ('position_world_m','orientation_world_xyzw','linear_velocity_world_m_s','angular_velocity_world_rad_s','native_wheel_links'):
        newer[key]=copy.deepcopy(current[key])
    newer.update(zip(('roll_rad','pitch_rad','yaw_rad'),cp.rpy(newer['orientation_world_xyzw'])))
    checkpoint=atomic_checkpoint(newer)
    repaired,proof=y.request_from_checkpoint(checkpoint,'RIGHT_YAW_MATCHED')
    assert list(repaired['position'].values())==current['position_world_m']
    rr=cp.rpy(list(repaired['orientation'].values()))
    assert rr[:2]==pytest.approx([current['roll_rad'],current['pitch_rad']],abs=1e-20)
    assert old['roll_rad']-current['roll_rad']==pytest.approx(1.3904540239555212e-6)
    assert old['pitch_rad']-current['pitch_rad']==pytest.approx(1.2661818097111276e-6)
    assert proof['non_yaw_construction_deltas']['x']==proof['non_yaw_construction_deltas']['y']==proof['non_yaw_construction_deltas']['z']==0.
    with pytest.raises(y.InvalidCapture,match='advancing request origin rejected'):y.request_from_checkpoint(old,'RIGHT_YAW_MATCHED')


@pytest.mark.parametrize('category',['native','support','wrench'])
def test_same_iteration_time_different_update_phase_rejected(state,category):
    c=atomic_checkpoint(state);raw=c['raw']
    raw[category]['postupdate_count' if category=='native' else 'read_phase_id']-=1
    with pytest.raises(y.InvalidCapture):cp.normalize(raw,c['marker'])


@pytest.mark.parametrize('category',['model_pose','native','wheels','support','wrench'])
def test_explicit_provenance_required_for_every_category(state,category):
    c=atomic_checkpoint(state);del c['raw']['field_sources'][category]
    with pytest.raises(y.InvalidCapture,match='provenance missing'):cp.normalize(c['raw'],c['marker'])


def test_current_model_and_native_pose_must_agree_at_construction_precision(state):
    c=atomic_checkpoint(state);c['raw']['model_pose']['position_world_m'][0]+=.257e-6
    with pytest.raises(y.InvalidCapture,match='model pose and current native'):cp.normalize(c['raw'],c['marker'])


def test_sham_fixed_target_must_already_be_current_yaw(state):
    altered=yaw_state(state,y.TARGETS['RIGHT_YAW_SHAM']+.001)
    with pytest.raises(y.InvalidCapture,match='SHAM_TARGET_NOT_CURRENT_YAW'):
        y.request_from_checkpoint(atomic_checkpoint(altered),'RIGHT_YAW_SHAM')
    target=atomic_checkpoint(state)
    payload,assertion=y.request_from_checkpoint(target,'RIGHT_YAW_SHAM')
    assert assertion['valid'] and abs(assertion['intended_yaw_delta_rad'])<y.tolerance_spec()['yaw_target_tolerance_rad']


def test_matched_requests_current_xyz_roll_pitch_and_only_new_yaw(state):
    c=atomic_checkpoint(state);a,p=y.request_from_checkpoint(c,'RIGHT_YAW_MATCHED')
    assert list(a['position'].values())==c['model_state']['position_world_m']
    roll,pitch,yaw=cp.rpy(list(a['orientation'].values()))
    assert (roll,pitch)==pytest.approx((c['model_state']['roll_rad'],c['model_state']['pitch_rad']),abs=1e-20)
    assert yaw==pytest.approx(.378577077577,abs=1e-16)
    assert max(map(abs,p['non_yaw_construction_deltas'].values()))<1e-14


def test_newer_same_time_pose_invalidates_checkpoint_before_rpc(state):
    c=atomic_checkpoint(state);latest=copy.deepcopy(c['raw']['native']);latest['postupdate_count']+=1
    latest['links'][0]['position_world_m'][0]+=.257e-6
    with pytest.raises(y.InvalidCapture,match='superseded'):cp.not_superseded(SimpleNamespace(samples=[latest]),c)


def test_checkpoint_capture_is_separate_from_native_physics_stream(state,tmp_path):
    class Base:
        def __init__(self,*a):self.samples=[];self.topic='/native/test'
        def receive(self,m,seq,wall):self.samples.append(json.loads(m['data']))
    class Capture(cp.CaptureMixin,Base):pass
    capture=Capture();capture.checkpoint_output=tmp_path/'paused.ndjson'
    raw=atomic_checkpoint(state)['raw']
    capture.receive({'data':json.dumps(raw)},4,1.)
    assert len(capture.checkpoints)==1 and capture.samples==[]
    capture.receive({'data':json.dumps({'paused':False,'iteration':1})},5,2.)
    assert len(capture.samples)==1 and len(capture.checkpoints)==1


def test_paused_heartbeats_do_not_change_t0_or_advancing_sample_counts(state):
    r=analysis_record(False);baseline=y.dm.command_active_t0(r)
    for name in ('support_rows','wrench_rows','native_samples'):
        row=copy.deepcopy(r[name][0]);row['paused']=True
        r[name]=[row]*20+r[name]
    assert y.dm.command_active_t0(r)==baseline
    assert len(y.dm.keyed_streams(r)['support_rows'])==220


def test_post_checkpoint_must_be_new_phase_and_exact_one_tick(state):
    st=yaw_state(state,y.TARGETS['RIGHT_YAW_MATCHED'])
    c=atomic_checkpoint(st,'POST_RPC',{'iteration':3601,'sim_time_ns':3_601_000_000,'paused':True},phase=1001)
    a,m=cp.validate(c,c['marker'],'POST_RPC')
    assert a['iteration']==3601 and m['yaw_rad']==pytest.approx(y.TARGETS['RIGHT_YAW_MATCHED'])
    with pytest.raises(y.InvalidCapture):cp.validate(c,{'iteration':3600,'sim_time_ns':3_600_000_000},'POST_RPC')


def test_held_component_age_is_explicit_not_fresh_paused_physics(state):
    c=atomic_checkpoint(state);assert 'held' in c['raw']['measurement_age_limitation']
    del c['raw']['measurement_age_limitation']
    with pytest.raises(y.InvalidCapture,match='age limitation missing'):cp.normalize(c['raw'],c['marker'])


def test_all_original_isolation_limits_and_features_retained(state):
    saved=json.loads((y.HOST2/'yaw_intervention_preflight.json').read_text())['tolerances']
    assert y.tolerance_spec()==saved
    rs=arms(state)
    for case in y.CASES:
        rs[case]['yaw_intervention']['pre_checkpoint']=atomic_checkpoint(state)
        rs[case]['yaw_intervention']['post_checkpoint']=atomic_checkpoint(rs[case]['yaw_intervention']['after'],'POST_RPC',{'iteration':3601,'sim_time_ns':3_601_000_000},phase=1001)
    iso=y.isolation(rs,saved)
    for case in y.CASES:
        checks=iso['observed'][case]['checks']
        assert set(saved['per_arm_limits'])<=set(checks)
        for key in saved['per_arm_limits']:
            assert all(field in checks[key] for field in ('before','after','delta','limit','ratio','pass','source_provenance'))


def test_cli_reports_both_arm_and_pair_counts_without_truncation(monkeypatch,tmp_path,capsys):
    failures=['RIGHT_YAW_SHAM: field'+str(i) for i in range(28)]+['RIGHT_YAW_MATCHED: field'+str(i) for i in range(35)]+['between-arm after: x']*12+['between-arm collateral change: x']*12
    monkeypatch.setattr(y,'run',lambda *a:{'status':'INTERVENTION_ISOLATION_FAILED','isolation':{'failures':failures},'interpretation':'INTERVENTION_ISOLATION_FAILED'})
    assert y.main(['--output',str(tmp_path)])==2
    out=capsys.readouterr().out
    for text in ('RIGHT_YAW_SHAM: failure count = 28','RIGHT_YAW_MATCHED: failure count = 35','between-arm after: failure count = 12','between-arm collateral change: failure count = 12','Full failed field names and values:','YAW_CAUSAL_RELEVANCE_UNRESOLVED'):
        assert text in out
    assert 'CAPTURED' not in out


@pytest.mark.parametrize('prior',[y.HOST1,y.HOST2])
def test_old_host_directories_protected_and_host3_new(prior):
    assert y.DEFAULT_OUTPUT.name.endswith('host3')
    with pytest.raises(FileExistsError):y.ensure_output(prior)


def test_checkpoint_rpc_collects_one_atomic_frame_and_fresh_pose_v(state):
    fixture=atomic_checkpoint(state)
    class Base:
        def __init__(self):self.samples=[];self.topic='/native/test'
        def receive(self,*a):raise AssertionError('checkpoint must not enter native stream')
    class Capture(cp.CaptureMixin,Base):pass
    cap=Capture()
    class Transport:
        request_history=[]
        def cursor(self,*a):return 1
        def request(self,service,req,rep,payload,**kwargs):
            assert (service,req,rep,payload,kwargs)==('/native/test/checkpoint','Empty','Boolean',{}, {'max_attempts':1})
            self.request_history.append({'service':service,'payload':{},'attempts':[{'response':{'data':True}}]})
            cap.samples=[copy.deepcopy(fixture['raw']['native'])]
            cap.receive({'data':json.dumps(fixture['raw'])},9,1.)
            return {'data':True}
        def messages_after(self,*a,**k):return [(2,fixture['production_Pose_V']['frame'])]
    a=SimpleNamespace(env=SimpleNamespace(transport=Transport(),timeout=.01,controller=SimpleNamespace(pose_topic='/pose')))
    got=cp.acquire(a,cap,fixture['marker'],'PRE_RPC')
    assert got['classification']=='PRE_RPC_CHECKPOINT_COHERENT'
    assert cp.validate(got,got['marker'],'PRE_RPC')[0]==got['state']
    assert len(a.env.transport.request_history)==1 and len(cap.checkpoints)==1


def test_same_time_stale_pose_v_cannot_corrobate_checkpoint(state):
    c=atomic_checkpoint(state)
    frame=copy.deepcopy(c['production_Pose_V']['frame'])
    frame['pose'][0]['position']['z']+=.473e-6
    a=SimpleNamespace(env=SimpleNamespace(timeout=.01,controller=SimpleNamespace(pose_topic='/pose'),
        transport=SimpleNamespace(messages_after=lambda *a,**k:[(2,frame)])))
    with pytest.raises(y.InvalidCapture,match='same timestamp'):
        cp.production_pose_after_request(a,1,c['marker'],c['model_state'])


def test_host2_regression_audit_does_not_use_physical_outcomes_or_make_runtime_evidence():
    audit=y.audit_host2_checkpoint_defect()
    assert audit['classification']=='HOST2_UPDATE_PHASE_DEFECT_REPRODUCED_OFFLINE'
    assert not audit['Host2_noncausal_physical_outcomes_used_for_tuning']
    assert all(case['construction_only_not_runtime_checkpoint'] for case in audit['cases'].values())


def test_cpp_checkpoint_serializer_is_paused_only_and_json_schema_matches(tmp_path):
    # In-memory ECM serialization only. No Server, world, transport Node or physics.
    import subprocess,shlex
    source=tmp_path/'checkpoint_serializer.cc'
    source.write_text('''#include <iostream>
#include "gazebo_paused_physical_checkpoint.hh"
int main(){
 gz::sim::EntityComponentManager ecm;
 gz::sim::UpdateInfo info;info.iterations=3600;info.simTime=std::chrono::milliseconds(3600);info.paused=true;
 std::cout<<aero_diagnostic::checkpoint::Serialize(info,ecm,"{}",1,99,1,3600,3600000000LL)<<"\\n";
 info.paused=false;
 try {aero_diagnostic::checkpoint::Serialize(info,ecm,"{}",2,100,1,3600,3600000000LL);return 2;}
 catch(const std::invalid_argument &){return 0;}
}''')
    flags=subprocess.run(['pkg-config','--cflags','--libs','gz-sim8','gz-msgs10'],capture_output=True,text=True,check=True)
    binary=tmp_path/'serializer'
    built=subprocess.run(['c++','-std=c++17','-I'+str(y.ab.ROOT/'tools'),str(source),'-o',str(binary),*shlex.split(flags.stdout)],capture_output=True,text=True)
    assert built.returncode==0,built.stderr
    result=subprocess.run([str(binary)],capture_output=True,text=True,check=True)
    row=json.loads(result.stdout)
    assert row['message_kind']==cp.KIND and row['paused'] is True
    assert row['postupdate_count']==row['support']['read_phase_id']==row['wrench']['read_phase_id']==99
    assert row['update_phase']==cp.PHASE and len(row['support']['supports'])==4
    # An unavailable checkpoint is never promoted to coherent simply by its tag.
    with pytest.raises(y.InvalidCapture):cp.normalize(row,{'iteration':3600,'sim_time_ns':3_600_000_000})


def test_current_checkpoint_uses_unchanged_canonical_tolerance_bytes():
    import hashlib
    saved=json.loads((y.HOST2/'yaw_intervention_preflight.json').read_text())['tolerances']
    expected=hashlib.sha256(json.dumps(saved,sort_keys=True,allow_nan=False).encode()).hexdigest()
    assert y.frozen_tolerance_digest(y.tolerance_spec())==expected
    broken=copy.deepcopy(saved);broken['per_arm_limits']['left.phase_rad']*=2
    with pytest.raises(y.InvalidCapture):y.frozen_tolerance_digest(broken)
