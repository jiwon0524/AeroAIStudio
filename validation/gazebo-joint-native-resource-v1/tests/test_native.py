"""Python packet/model tests only. No native module, fixture or binary execution."""
import sys,copy,json,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1];B=R.parents[1]
sys.path.insert(0,str(R/'scripts'));from native_gate import NativeSession
sys.path.insert(0,str(B/'validation/gazebo-joint-resolution-v1/scripts'))
from protocol import HarmlessSession,AckWindow
expected={r:('a'*64,1,i+1) for i,r in enumerate(['schema/root.sdf','schema/nested.sdf','conversion/1_10.convert','server_config','physics','physics_provider','dartsim','dartsim_provider'])}
expected['world_bytes']=('b'*64,0,0)
roles=['world_bytes','schema/root.sdf','schema/nested.sdf','schema_init','schema_include','schema_init','schema_root','conversion/1_10.convert','conversion','world_parse','world_graph','server_config','server_config_parse','physics','physics_provider','physics_loaded','dartsim','dartsim_provider','dartsim_loaded','complete']
def rows():
 return [dict(kind='native_resource',seq=i+1,role=r,sha256=expected.get(r,('',0,0))[0],device=expected.get(r,('',0,0))[1],inode=expected.get(r,('',0,0))[2],ok=True) for i,r in enumerate(roles)]
def setup():
 writes=[];window=AckWindow(writes.append,lambda:dict(status='PASS_FILE_IDENTITY',start='s',pid=9),'s',9)
 return NativeSession(expected,{'schema/root.sdf','schema/nested.sdf'},HarmlessSession(window,lambda:True)),window,writes
cases=[]
def reject(name, packets, after=None):
 s,w,out=setup()
 try:
  for p in packets:s.packet(p)
  if after:after(s,w,out)
 except ValueError:cases.append(dict(case=name,status='PASS_REJECTED'))
 else:raise AssertionError(name)
s,w,out=setup()
for p in rows():s.packet(p)
for _ in range(2):s.packet(dict(kind='fixture_ready',iteration=0,sim_time_ns=0))
s.authorize()
for i in range(1,101):s.packet(dict(kind='fixture_sample',iteration=i,sim_time_ns=i*1000000))
s.packet(dict(kind='final_wait',iteration=100,sim_time_ns=100000000));w.send_ack()
assert s.finalize(True,True,0,True,True,True)['samples']==100
assert out==[b'GO\n',b'EXIT_ACK\n'];cases.append(dict(case='native_preamble_ack_eof',status='PASS_MOCK_ONLY'))
for name,role,field,value in [('missing_schema','schema/nested.sdf','ok',False),('nested_include_parse','schema_include','ok',False),('same_name_other_file','schema/nested.sdf','inode',999),('plugin_fallback','physics','sha256','f'*64),('world_bytes','world_bytes','sha256','f'*64),('provider_mismatch','dartsim_provider','inode',999),('boolean_fd_identity','physics','device',True)]:
 ps=rows();next(p for p in ps if p['role']==role)[field]=value;reject(name,ps)
for role in ['schema/nested.sdf','schema_include','world_parse','physics_provider','dartsim_loaded','complete']:
 ps=[p for p in rows() if p['role']!=role]
 for i,p in enumerate(ps):p['seq']=i+1
 ps.append(dict(kind='fixture_ready',iteration=0,sim_time_ns=0));reject('missing_observation_'+role,ps)
reject('late_load_after_GO',rows(),lambda s,w,out:(s.packet(dict(kind='fixture_ready',iteration=0,sim_time_ns=0)),s.packet(dict(kind='fixture_ready',iteration=0,sim_time_ns=0)),s.authorize(),s.packet(dict(kind='native_resource',seq=21,role='fatal',sha256='',device=0,inode=0,ok=False))))
reject('early_ready', [dict(kind='fixture_ready',iteration=0,sim_time_ns=0)])
# Source-order assertions bind the rejection boundary to the actual call sites.
src=R/'work/src';manager=(src/'sim/src/SystemManager.cc').read_text();start=manager.index('void SystemManager::LoadPlugin(');end=manager.index('size_t SystemManager::TotalCount',start);text=manager[start:end]
assert text.index('CheckLoadRequest')<text.index('this->systemLoader->LoadPlugin')
loader=(src/'sim/src/SystemLoader.cc').read_text();text=loader[loader.index('public: bool InstantiateSystemPlugin'):];assert text.index('CheckLoadRequest')<text.index('FindSharedLibrary')<text.index('BeforeLoad')<text.index('loader.LoadLib')
engine=(src/'sim/src/systems/physics/Physics.cc').read_text();assert engine.index('CheckLoadRequest')<engine.index('std::filesystem::canonical(pluginLib)')<engine.index('BeforeLoad')<engine.index('pluginLoader.LoadLib')
parser=(src/'sdformat/src/parser.cc').read_text();assert 'initFile(filename, _config, element, _errors)' in parser and 'required schema XML parse failed' in parser
assert 'SDF::EmbeddedSpec(' not in parser
native=(R/'inputs/native_resource.cc').read_text();assert native.index('if(failed||sealed) Fail("late load request denied")')<native.index('read(it->second,role)')
run=(src/'sim/src/SimulationRunner.cc').read_text();assert run.index('aero_resource::Ready()')<run.index('JointState("ready_state"')<run.index('WaitGo(3')
cases.append(dict(case='native_source_order_and_latch',status='PASS_STATIC_ONLY'))
p=subprocess.run([sys.executable,'-I','-B',str(R/'scripts/preflight.py')],capture_output=True,text=True);assert p.returncode==78 and not json.loads(p.stdout)['service_started']
cases.append(dict(case='pre_service_exit78',status='PASS'))
import importlib.util
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('native_supervisor',R/'scripts/supervisor.py');sup=importlib.util.module_from_spec(spec);spec.loader.exec_module(sup)
with patch.object(sup.smoke,'properties',side_effect=AssertionError('manager query')), patch.object(sup,'exclusive',side_effect=AssertionError('marker write')), patch.object(sup.subprocess,'Popen',side_effect=AssertionError('service started')):
 try:sup.run('actual')
 except ValueError as error:assert 'unsealed native' in str(error)
 else:raise AssertionError('unsealed native launcher accepted')
cases.append(dict(case='native_supervisor_pre_manager_marker_service_refusal',status='PASS'))
(R/'reports/tests.json').write_text(json.dumps(dict(status='PASS_STATIC_MOCK_ONLY',cases=cases,native_execution=False,harmless_execution=False),indent=2)+'\n');print('PASS',len(cases),'static/mock cases')
