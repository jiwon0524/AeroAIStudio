"""Static and synthetic packets only. Never run a target/fixture/service/bwrap."""
from pathlib import Path
import sys,json,copy,tempfile,os,hashlib
from unittest.mock import patch
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'scripts'))
import contract as C
import launcher
m=C.read();cases=[]
def rejected(name,fn):
 try:fn()
 except (ValueError,OSError,KeyError):cases.append(dict(case=name,status='PASS_REJECTED'))
 else:raise AssertionError(name)
def mutate(name,fn):
 q=copy.deepcopy(m);fn(q);rejected(name,lambda:C.validate(q,C.digest(q),files=False))
mutate('stale_attestor',lambda q:q['implementation'].update(attestor=str(R.parents[1]/'validation/gazebo-joint-isolation-v1/scripts/live.py')))
def stale_code(q):
 key=q['implementation']['attestor'];q['code'][key]['source']=str(R.parents[1]/'validation/gazebo-joint-isolation-v1/scripts/live.py');q['code'][key]['real_path']=q['code'][key]['source']
mutate('mixed_checker_file',stale_code)
mutate('missing_mount',lambda q:q['mounts'].pop(q['roles']['native']))
mutate('changed_allowlist',lambda q:q.update(allowlist_text=q['allowlist_text']+'0'*64+' /unexpected.so\n'))
mutate('ordered_bwrap_argv',lambda q:q['ordered_bwrap_argv'].__setitem__(1,'--share-net'))
mutate('missing_soname_edge',lambda q:q['soname_edges'].pop())
mutate('wrong_soname_alias',lambda q:q['soname_edges'][0].update(provider='/unexpected/provider.so'))
mutate('required_mapping_missing',lambda q:q['required_canonical_mappings'].remove(q['roles']['native']))
mutate('stale_native_Physics_identity',lambda q:q['native']['expected']['physics'].__setitem__(2,1))
def mix_old(q):
 row=q['mounts'][q['roles']['physics']];row['source']=q['forbidden_backings'][0];row['real_path']=row['source']
mutate('old_ELF_mixture',mix_old)
mutate('same_name_other_inode_projection',lambda q:q['elfs'][q['roles']['dart_ode']].update(inode=123))
rejected('manifest_seal',lambda:C.validate(dict(m,status='tampered'),files=False))
# FD identity/hash failures, using new temporary files; never edit an actual input.
with tempfile.TemporaryDirectory(dir=R/'work') as t:
 p=Path(t)/Path(m['roles']['dart_ode']).name;p.write_bytes(b'other provider')
 expected=m['mounts'][m['roles']['dart_ode']];row=dict(expected,source=str(p),real_path=str(p))
 rejected('same_name_other_inode_FD',lambda:C.checked_file(row))
 s=p.stat();row.update(device=s.st_dev,inode=s.st_ino,sha256=m['mounts']['/input/joint-elf.sha256']['sha256'])
 rejected('changed_allowlist_FD_bytes',lambda:C.checked_file(row))
 symlink=Path(t)/'dangling';symlink.symlink_to('absent')
 rejected('existing_dangling_marker',lambda:C.absent([str(symlink)]))
fds=dict(zip(m['fd_sources'],range(10,10+len(m['fd_sources']))));keys=list(fds);fds[keys[1]]=fds[keys[0]]
rejected('FD_alias_collision',lambda:C.bwrap(m,fds))
# No endpoint is called: refusal precedes even a manager query, file creation or spawn.
with patch('subprocess.Popen',side_effect=AssertionError('service/target spawned')),patch('subprocess.check_output',side_effect=AssertionError('manager queried')),patch('os.execve',side_effect=AssertionError('target exec')):
 result=launcher.preflight();assert result['exit_code']==78 and all(result[k] is False for k in ['manager_queried','service_started','marker_created','go_sent'])
cases.append(dict(case='pre_manager_marker_service_exit78',status='PASS_REFUSAL'))
# Stage opens only regular read-only inputs and derives the same FD mount order.
import source_loader,fcntl
loader=source_loader.runtime(m);modules,loaded_code=loader.__enter__()
stage=modules['stage']
with patch('subprocess.Popen',side_effect=AssertionError('target spawned')),patch('os.execve',side_effect=AssertionError('target exec')):
 with stage.inputs(m) as (argv,opened):
  saved=list(opened.values());assert len(saved)==len(set(saved)) and min(saved)>=10
  assert argv==C.bwrap(m,opened)
  assert all(fcntl.fcntl(fd,fcntl.F_GETFL)&os.O_ACCMODE==os.O_RDONLY for fd in saved)
 for fd in saved:
  try:os.fstat(fd)
  except OSError:pass
  else:raise AssertionError('FD leak')
cases.append(dict(case='checked_RO_FD_mount_layout_and_close_without_exec',status='PASS_READ_ONLY'))
# New actual attestor uses namespace module path, never host realpath substitution.
A=modules['attestor'];Attestor=A.Attestor
att=Attestor(m,7,'s','/own',(1,2),(3,4));provider=dict(kind='engine_entry',module=m['roles']['dartsim'],anchor='0x1800',module_base='0x1000',this='0x1900')
wrong=dict(range='1000-2000',device=m['elfs'][m['roles']['dartsim']]['device'],inode=m['elfs'][m['roles']['dartsim']]['inode']+1)
with patch.object(A.mapped,'parse_maps',return_value=[wrong]),patch.object(Path,'read_text',return_value='synthetic maps'):
 rejected('mapped_provider_other_inode',lambda:att.provider(provider))
provider['module']='/different/same-name.so';rejected('selected_provider_wrong_path',lambda:att.provider(provider))
ode=dict(kind='typed',label='dart/ode/getType',module=m['provider_paths']['dart_ode'][0],anchor='0x1800',module_base='0x1000',this='0x1900')
good=dict(range='1000-2000',device=m['elfs'][m['roles']['dart_ode']]['device'],inode=m['elfs'][m['roles']['dart_ode']]['inode'])
with patch.object(A.mapped,'parse_maps',return_value=[good]),patch.object(Path,'read_text',return_value='synthetic maps'):
 assert att.provider(ode)==m['attestation']['detector_candidates']['ode']
cases.append(dict(case='namespace_ODE_SONAME_provider_without_host_realpath',status='PASS_MOCK_ONLY'))
mutate('wrong_active_provider_namespace_alias',lambda q:q['provider_paths']['dart_ode'].__setitem__(0,q['roles']['dart_ode']))
# Reuse exact AckSession/Gate rules with synthetic actual-protocol state values.
AckWindow=modules['protocol'].AckWindow;AckSession=modules['protocol'].AckSession
NativeSession=modules['native_gate'].NativeSession
def packets():
 roles=['world_bytes',*m['native']['schema_closure'],'server_config','conversion/1_10.convert','physics','physics_provider','dartsim','dartsim_provider','schema_init','schema_include','schema_root','server_config_parse','conversion','world_parse','world_graph','physics_loaded','dartsim_loaded','complete']
 return [dict(kind='native_resource',seq=i+1,role=r,sha256=m['native']['expected'].get(r,['',0,0])[0],device=m['native']['expected'].get(r,['',0,0])[1],inode=m['native']['expected'].get(r,['',0,0])[2],ok=True) for i,r in enumerate(roles)]
def setup():
 writes=[];window=AckWindow(writes.append,lambda:dict(status='PASS_FILE_IDENTITY',start='s',pid=7),'s',7)
 def measured(raw,fp):
  return dict(raw,kind='LIVE_READY_PAUSED',steps_observed=0,engine=dict(source='active_instance_provider',backend='DART',provider=m['attestation']['engine_provider']),detector=dict(source='active_world_detector_instance',type='ode',provider=m['attestation']['detector_candidates']['ode']),mappings=[m['attestation']['allowed_mappings'][p] for p in m['required_canonical_mappings']],pid_identity_stable=True,namespace_cgroup_limits_verified=True)
 return NativeSession(m['native']['expected'],m['native']['schema_closure'],AckSession(m['attestation'],measured,window)),window,writes
def ready(s):
 for _ in range(2):s.stderr('AERO_WORLD entity=1 world=0x10 solver=0x20 detector=0x30 init=1 iteration=0 sim_time=0 native_frame=0 native_time=0')
 for _ in range(2):
  s.packet(dict(kind='engine_entry',module=m['roles']['dartsim'],this='0x40',anchor='0x50',module_base='0x10'))
  for label in ['dart/ode/getType','gz/ode/getType']:s.packet(dict(kind='typed',label=label,base='0x30',this='0x30',anchor='0x60',module='synthetic',module_base='0x10'))
  state={k:0 for k in ['x','y','z','vx','vy','vz','roll','pitch','yaw']};state['z']=1
  s.packet(dict(kind='ready_state',iteration=0,sim_time_ns=0,dt_ns=0,paused=True,native_frame=0,native_time=0,init_count=1,state_source='measured_live_components',state=state))
def initialized():
 s,w,out=setup()
 for p in packets():s.packet(p)
 ready(s);s.authorize();assert out==[b'GO\n'];return s,w,out
s,w,out=initialized()
for i in range(1,101):
 t=i*.001;state={k:0 for k in ['x','y','z','vx','vy','vz','roll','pitch','yaw']};state.update(z=1-4.905*t*t,vz=-9.81*t)
 s.packet(dict(kind='sample',iteration=i,sim_time_ns=i*1000000,dt_ns=1000000,paused=False,native_frame=i,native_time=t,init_count=1,state_source='measured_live_components',state=state))
s.packet(dict(kind='final_wait',iteration=100,sim_time_ns=100000000));w.send_ack();assert s.finalize(True,True,0,True,True,True)['status']=='PASS';assert out==[b'GO\n',b'EXIT_ACK\n'];cases.append(dict(case='actual_protocol_synthetic_GO_100_final_mapping_ACK_EOF_exit_cleanup',status='PASS_MOCK_ONLY'))
s,w,out=setup();rejected('early_native_ready_regression',lambda:ready(s));assert out==[]
s,w,out=initialized();rejected('GO_after_late_load_attempt',lambda:s.packet(dict(kind='native_resource',seq=999,role='fatal',sha256='',device=0,inode=0,ok=False)));rejected('failed_attempt_cannot_finalize',lambda:s.finalize(True,True,0,True,True,True))
s,w,out=setup();rejected('auxiliary_resource_fallback',lambda:s.packet(dict(kind='aux_resource_request',path='/scratch/fallback')));assert out==[]
s,w,out=initialized();rejected('post_GO_auxiliary_request',lambda:s.packet(dict(kind='aux_resource_request',path='/scratch/late')))
# Source ordering must include two *distinct* Validate calls after native complete.
src=R/'work/src/sim/src';run=(src/'SimulationRunner.cc').read_text();block=run[run.index('    aero_resource::Ready();'):run.index('    if (!aero_joint::WaitGo')]
assert block.count('JointState("ready_state"')==2 and block.count('JointValidate(this->currentInfo)')==2
assert 'JointValidate' in block.split('JointState')[0] and 'JointValidate' in block.split('JointState')[1]
phy=(src/'systems/physics/Physics.cc').read_text();init=phy[phy.index('bool Physics::JointInit'):phy.index('void Physics::JointState')];assert 'State("ready_state"' not in init
assert (R/'scripts/protocol.py').read_bytes()==(R.parents[1]/'validation/gazebo-joint-resolution-v1/scripts/protocol.py').read_bytes()
cases.append(dict(case='two_independent_ready_snapshots_after_native_completion',status='PASS_STATIC_ONLY'))
# Explicitly do not mistake the mock rejection for a missing DART syscall guard.
assert m['technical']['resource_paths']=='BLOCKED' and len(m['blockers'])>=2
assert loaded_code[str(R/'scripts/attestor.py')]==m['code'][str(R/'scripts/attestor.py')]['sha256']
loader.__exit__(None,None,None)
import types
with patch.dict(sys.modules,{'attestor':types.ModuleType('stale_attestor')}):
 def stale_cached():
  with source_loader.runtime(m):pass
 rejected('stale_cached_attestor_module',stale_cached)
cases.append(dict(case='authenticated_source_only_import_no_pyc',status='PASS_PYTHON_SOURCE_ONLY'))
(R/'reports/tests.json').write_text(json.dumps(dict(status='PASS_STATIC_MOCK_ONLY',cases=cases,subject_execution=False,harmless_execution=False,manager_queries=0,service_starts=0,marker_consumption=0,source_guard_for_unknown_DART_paths=False),indent=2)+'\n');print('PASS',len(cases),'static/mock cases; actual runtime remains unverified')
