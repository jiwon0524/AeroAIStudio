"""Native DART constraint/algebra tests; never invokes World::step or Gazebo."""
import json,subprocess,struct,importlib.util
from pathlib import Path
import pytest
R=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('trace_schema',R/'trace_schema.py');schema=importlib.util.module_from_spec(spec);spec.loader.exec_module(schema)
def vals(r):return schema.values(r)
def invoke(binary,mode,enabled,path):
 return subprocess.run([str(R/'work'/binary),mode,enabled,str(path)],capture_output=True,text=True,check=True)
@pytest.mark.parametrize('mode',['primary_true','primary_false','primary_nan','nan_no_fallback','real_dantzig','real_pgs_fallback'])
def test_installed_vs_trace_off_on(mode,tmp_path):
 original=invoke('original_boxed',mode,'off',tmp_path/'none_original')
 disabled=invoke('trace_boxed',mode,'off',tmp_path/'none_disabled')
 on=tmp_path/'on.json';enabled=invoke('trace_boxed',mode,'on',on)
 assert original.stdout==disabled.stdout==enabled.stdout
 assert not (tmp_path/'none_disabled').exists()
 d=json.loads(on.read_text());assert d['fault_bits']==0 and d['window_complete']
 check=schema.inspect(on);assert check['schema']=='VALID' and check['collection']=='COMPLETE'
 assert not check['runtime_verified'] and not check['row_identity_complete']
 assert 'ROW_IDENTITIES_INCOMPLETE' in check['qualification_blockers']
 assert all(r['assembly']==1 for r in d['records'] if r['kind'] in ['A0','b0','x0','final_x'])
@pytest.mark.parametrize('mode,raw,called,fallback,repair',[('primary_true',1,0,None,0),('primary_false',0,1,1,0),('primary_nan',1,1,0,0),('nan_no_fallback',1,0,None,1)])
def test_branch_statuses_separate(mode,raw,called,fallback,repair,tmp_path):
 p=tmp_path/'case.json';invoke('trace_boxed',mode,'on',p);rs=json.loads(p.read_text())['records']
 def one(k):return vals(next(r for r in rs if r['kind']==k))[0]
 assert one('primary_raw_return')==raw
 assert one('fallback_called')==called
 assert one('nan_repair_required')==repair
 if fallback is not None:assert one('fallback_raw_return')==fallback
 else:assert not any(r['kind']=='fallback_raw_return' for r in rs)
 if mode=='nan_no_fallback':assert vals(next(r for r in rs if r['kind']=='final_x'))==[0]*4

def test_real_dantzig_freeze_and_matrix_snapshot(tmp_path):
 p=tmp_path/'real.json';invoke('trace_boxed','real_dantzig','on',p);rs=json.loads(p.read_text())['records']
 for k in ['freeze_permutation','freeze_findex','freeze_x_permuted','freeze_mu_hi','freeze_lo_effective','freeze_hi_effective','freeze_x_original_order','return_permutation','dantzig_x_unpermuted']:
  assert any(r['kind']==k for r in rs)
 A=[vals(r) for r in rs if r['kind']=='A0'];assert len(A)==4 and all(len(x)==4 for x in A)
 for i,row in enumerate(A):
  for j,x in enumerate(row):assert abs(x-(2.00002 if i==j else .1))<1e-14
 assert vals(next(r for r in rs if r['kind']=='findex0'))==[-1,0,-1,2]
 assert vals(next(r for r in rs if r['kind']=='b0'))==[1,.2,1,.2]

def test_schema_detects_corruption_and_does_not_promote(tmp_path):
 p=tmp_path/'real.json';invoke('trace_boxed','real_dantzig','on',p);d=json.loads(p.read_text())
 d['records']=[r for r in d['records'] if r['kind']!='final_x'];p.write_text(json.dumps(d));assert schema.inspect(p)['collection']=='INCOMPLETE'
 d['schema_version']=99;p.write_text(json.dumps(d))
 with pytest.raises(ValueError):schema.inspect(p)
@pytest.mark.parametrize('mode,dim,reason',[('wheel',3,5),('caster',1,5),('limit',3,1)])
def test_real_private_contact_and_joint_fields(mode,dim,reason,tmp_path):
 p=tmp_path/'fields.json';off=invoke('private_fields_fixture',mode,'off',tmp_path/'off');on=invoke('private_fields_fixture',mode,'on',p)
 assert off.stdout==on.stdout
 rs=json.loads(p.read_text())['records'];params=vals(next(r for r in rs if r['kind']=='contact_parameters'))
 assert params[0]==8e-9 and params[10]==dim
 assert params[1]==params[2]==(.001 if mode=='caster' else 1.)
 assert params[3:6]==[0.,.01,1e-5]
 jac=[r for r in rs if r['kind']=='jacobian_A'];assert len(jac)==dim
 assert vals(jac[0])==[.02,-.16,0.,0.,0.,1.]
 joint=next(r for r in rs if r['kind']=='joint_row');assert joint['identity']=='fixture_joint';assert vals(joint)[:2]==[0,0]
 branch=next(r for r in rs if r['kind']=='joint_branch');assert vals(branch)[1]==reason
 assert len(vals(next(r for r in rs if r['kind']=='applied_contact_impulse')))==dim
 assert next(r for r in rs if r['kind']=='contact_skeletonA')['identity']=='synthetic_agent'

def test_real_dantzig_early_failure_mapping(tmp_path):
    original=subprocess.run([str(R/'work/original_failure'),str(tmp_path/'none')],capture_output=True,text=True,check=True,timeout=5)
    path=tmp_path/'failure.json';trace=subprocess.run([str(R/'work/trace_failure'),str(path)],capture_output=True,text=True,check=True,timeout=5)
    assert original.stdout==trace.stdout
    assert trace.stdout.startswith('0 ')
    rs=json.loads(path.read_text())['records'];assert any(r['kind']=='dantzig_failure' for r in rs)
    assert vals(next(r for r in rs if r['kind']=='failure_permutation'))==[0]
    assert not any(r['kind']=='dantzig_x_unpermuted' for r in rs)

def test_offline_residual_uses_preserved_A_and_effective_bounds(tmp_path):
    p=tmp_path/'real.json';invoke('trace_boxed','real_dantzig','on',p);rows=schema.bounded_residual(p)
    assert rows[0]['status']=='COMPUTED_OFFLINE_NOT_CAPTURE_VERDICT'
    assert rows[0]['bound_violation_impulse']<1e-12
    assert rows[0]['kkt_velocity_residual']<1e-12

def test_fallback_type_is_recorded(tmp_path):
    p=tmp_path/'fallback.json';invoke('trace_boxed','primary_false','on',p)
    rs=json.loads(p.read_text())['records'];assert next(r for r in rs if r['kind']=='fallback_type')['identity']=='fallback'

@pytest.mark.parametrize('mode,expected',[('off','0 0 0 0 0'),('on','1 0 0 0 0'),('bad','0 16 0 0 0')])
def test_world_constructor_opt_in_without_stepping(mode,expected):
    import os
    env={k:v for k,v in os.environ.items() if not k.startswith('DART_TRACE_') and k!='DART_INTERNAL_TRACE_V1'}
    if mode!='off':env.update(DART_INTERNAL_TRACE_V1='1',DART_TRACE_RUN_ID='SYNTHETIC_CONFIG',DART_TRACE_WORLD='env_fixture',DART_TRACE_FIRST_FRAME='10',DART_TRACE_LAST_FRAME='15' if mode=='bad' else '14')
    result=subprocess.run([str(R/'work/world_config_fixture')],env=env,capture_output=True,text=True,check=True,timeout=10)
    assert result.stdout.strip()==expected

def test_dantzig_return_true_can_still_record_internal_error(tmp_path):
    original=subprocess.run([str(R/'work/original_failure'),str(tmp_path/'none'),'continue'],capture_output=True,text=True,check=True,timeout=5)
    p=tmp_path/'continued.json';trace=subprocess.run([str(R/'work/trace_failure'),str(p),'continue'],capture_output=True,text=True,check=True,timeout=5)
    assert original.stdout==trace.stdout and trace.stdout.startswith('1 ')
    rs=json.loads(p.read_text())['records']
    assert any(r['kind']=='dantzig_internal_error' for r in rs)
    assert any(r['kind']=='dantzig_x_unpermuted' for r in rs)


def test_real_pgs_fallback_observed_without_changing_legacy_selection(tmp_path):
    p=tmp_path/'pgs.json';invoke('trace_boxed','real_pgs_fallback','on',p)
    rs=json.loads(p.read_text())['records']
    assert vals(next(r for r in rs if r['kind']=='fallback_called'))==[1]
    assert next(r for r in rs if r['kind']=='fallback_type')['identity']=='PgsBoxedLcpSolver'
    assert vals(next(r for r in rs if r['kind']=='fallback_raw_return'))==[1]
