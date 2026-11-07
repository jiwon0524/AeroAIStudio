"""Pure synthetic evidence + static ELF tests. Never runs target/native/service."""
import copy,json,sys,unittest,math,io,hashlib,os
from pathlib import Path
from unittest.mock import patch
B=Path(__file__).resolve().parents[1];sys.path.insert(0,str(B/'scripts'))
from gate import Gate,Rejected,validate_run
import inputs,launch,runtime_layout

def synthetic():
 c=json.loads((B/'reports/runtime_contract.json').read_text())
 # Only the mock policy test gets true capabilities. Never write back contract.
 c['capabilities'].update(live_collector_verified=True,pre_step_zero_verified=True,closure_complete=True)
 state={'x':0.,'y':0.,'z':1.,'vx':0.,'vy':0.,'vz':0.,'roll':0.,'pitch':0.,'yaw':0.}
 e={'kind':'LIVE_READY_PAUSED','iteration':0,'sim_time_ns':0,'steps_observed':0,'paused':True,
 'engine':{'source':'active_instance_provider','backend':'DART','provider':c['engine_provider']},
 'detector':{'source':'active_world_detector_instance','type':'bullet','provider':c['detector_candidates']['bullet']},
 'mappings':[c['allowed_mappings'][p] for p in c['required_mappings']],'pid_identity_stable':True,'namespace_cgroup_limits_verified':True,
 'state_source':'measured_live_components','state':state}
 return c,e

def trajectory():
 rows=[]
 for i in range(1,101):
  t=i*.001;s={'x':0.,'y':0.,'z':1-4.905*t*t,'vx':0.,'vy':0.,'vz':-9.81*t,'roll':0.,'pitch':0.,'yaw':0.}
  rows.append({'iteration':i,'sim_time_ns':i*1000000,'dt_ns':1000000,'paused':False,'state_source':'measured_live_components','state':s})
 return rows

class GateTests(unittest.TestCase):
 def setUp(self):self.c,self.e=synthetic()
 def rejects(self,e):
  with self.assertRaises(Rejected):Gate(self.c).authorize([e,copy.deepcopy(e)])
 def test_synthetic_acceptance_only(self):self.assertEqual(Gate(self.c).authorize([self.e,copy.deepcopy(self.e)]),'GO\n')
 def test_real_contract_never_authorizes(self):
  c=json.loads((B/'reports/runtime_contract.json').read_text())
  with self.assertRaisesRegex(Rejected,'collector unavailable'):Gate(c).authorize([self.e,self.e])
 def test_backend_mismatch(self):self.e['engine']['backend']='BULLET';self.rejects(self.e)
 def test_selection_string_not_instance_evidence(self):self.e['engine']['source']='world_config';self.rejects(self.e)
 def test_engine_provider_mismatch(self):self.e['engine']['provider']={};self.rejects(self.e)
 def test_detector_mismatch(self):self.e['detector']['type']='UNVERIFIED';self.rejects(self.e)
 def test_mapping_not_active_detector_evidence(self):self.e['detector']['source']='mapped_library';self.rejects(self.e)
 def test_detector_provider_mismatch(self):self.e['detector']['provider']=self.c['engine_provider'];self.rejects(self.e)
 def test_approved_soname_alias_identity(self):
  canonical='/usr/lib/x86_64-linux-gnu/libdart.so.6.13.2';alias='/usr/lib/x86_64-linux-gnu/libdart.so.6.13'
  i=next(i for i,x in enumerate(self.e['mappings']) if x['path']==canonical)
  self.e['mappings'][i]=self.c['allowed_mappings'][alias]
  self.assertEqual(Gate(self.c).authorize([self.e,self.e]),'GO\n')
 def test_missing_mapping(self):self.e['mappings'].pop();self.rejects(self.e)
 def test_unexpected_mapping(self):self.e['mappings'].append({'path':'/tmp/trace/libdart.so'});self.rejects(self.e)
 def test_mapping_hash_mismatch(self):self.e['mappings']=copy.deepcopy(self.e['mappings']);self.e['mappings'][0]['sha256']='0'*64;self.rejects(self.e)
 def test_mapping_inode_mismatch(self):self.e['mappings']=copy.deepcopy(self.e['mappings']);self.e['mappings'][0]['inode']+=1;self.rejects(self.e)
 def test_prego_iteration_changed(self):self.e['iteration']=1;self.rejects(self.e)
 def test_prego_time_changed(self):self.e['sim_time_ns']=1000000;self.rejects(self.e)
 def test_missing_detector_observation(self):self.e.pop('detector');self.rejects(self.e)
 def test_missing_mapping_observation(self):self.e.pop('mappings');self.rejects(self.e)
 def test_missing_state_observation(self):self.e['state'].pop('vz');self.rejects(self.e)
 def test_missing_process_observation(self):self.e.pop('pid_identity_stable');self.rejects(self.e)
 def test_missing_isolation_observation(self):self.e.pop('namespace_cgroup_limits_verified');self.rejects(self.e)
 def test_initial_config_not_measurement(self):self.e['state_source']='sdf';self.rejects(self.e)
 def test_changed_between_two_prego_samples(self):
  other=copy.deepcopy(self.e);other['sim_time_ns']=1
  with self.assertRaises(Rejected):Gate(self.c).authorize([self.e,other])
 def test_go_cannot_be_reused(self):
  g=Gate(self.c);g.authorize([self.e,self.e])
  with self.assertRaises(Rejected):g.authorize([self.e,self.e])
 def test_100_step_model(self):self.assertTrue(validate_run(trajectory()))
 def test_wrong_sample_counts(self):
  for n in (0,99,101):
   with self.assertRaises(Rejected):validate_run((trajectory()+trajectory())[:n])
 def test_wrong_iteration_or_time(self):
  for k in ('iteration','sim_time_ns','dt_ns'):
   rows=trajectory();rows[50][k]+=1
   with self.assertRaises(Rejected):validate_run(rows)
 def test_missing_orientation_is_rejected(self):
  rows=trajectory();rows[-1]['state'].pop('yaw')
  with self.assertRaises(Rejected):validate_run(rows)
 def test_nonfinite_state_rejected(self):
  rows=trajectory();rows[5]['state']['vz']=float('nan')
  with self.assertRaises(Rejected):validate_run(rows)
 def test_bad_final_fall_rejected(self):
  rows=trajectory();rows[-1]['state']['z']=1
  with self.assertRaises(Rejected):validate_run(rows)
 def test_launcher_blocks_before_any_runtime(self):
  with patch.object(sys,'argv',['launch','--execute-approved-gazebo-once']):
   with self.assertRaisesRegex(ValueError,'NOT_EXECUTION_READY'):launch.main()
  for p in ('reports/runtime','work/runtime_attempt.json','work/runtime_collection_attempt.json'):self.assertFalse(os.path.lexists(B/p))
 def test_even_forged_ready_flags_cannot_launch(self):
  c=copy.deepcopy(self.c);c.update(status='EXECUTION_READY',blockers=[],risk_acceptance='EXPLICITLY_RECORDED');c['capabilities']={k:True for k in c['capabilities']}
  with self.assertRaisesRegex(ValueError,'not implemented'):launch.require_executable_contract(c)
 def test_default_prints_blocked_contract(self):
  with patch.object(sys,'argv',['launch']),patch('sys.stdout',new_callable=io.StringIO) as out:self.assertEqual(launch.main(),0)
  self.assertIn('PREPARED_BLOCKED',out.getvalue())
 def test_source_and_artifact_pins(self):
  c=json.loads((B/'reports/runtime_contract.json').read_text())
  for p,h in c['source_sha256'].items():self.assertEqual(hashlib.sha256((B/p).read_bytes()).hexdigest(),h,p)
 def test_changed_source_pin_blocks_before_runtime(self):
  import preflight
  c=json.loads((B/'reports/runtime_contract.json').read_text());first=next(iter(c['source_sha256']));c['source_sha256'][first]='0'*64
  with patch.object(preflight.json,'loads',return_value=c):
   with self.assertRaisesRegex(ValueError,'source/input changed'):preflight.check_inputs()
 def test_readelf_fd_resolution(self):self.assertEqual(inputs.preflight_static()['status'],'PASS_STATIC_RESOLUTION')
 def test_missing_core_soname_rejected(self):
  m=json.loads((B/'reports/elf_manifest.json').read_text());cmd,fds=inputs.plan(m);i=cmd.index('/usr/lib/x86_64-linux-gnu/libdart.so.6.13');del cmd[i-2:i+1]
  with self.assertRaisesRegex(ValueError,'missing alias'):inputs.validate_plan(m,cmd,fds)
 def test_world_fd_mismatch(self):
  m=json.loads((B/'reports/elf_manifest.json').read_text());cmd,fds=inputs.plan(m);i=cmd.index('/fixture/minimal.sdf');cmd[i-1]='6666'
  with self.assertRaisesRegex(ValueError,'world FD'):inputs.validate_plan(m,cmd,fds)
 def test_resource_service_limits(self):
  argv=runtime_layout.service_argv('not-started.service',[])
  for v in ('MemoryMax=512M','MemorySwapMax=0','TasksMax=64','CPUQuota=100%','RuntimeMaxSec=30s','TimeoutStopSec=2s'):self.assertIn('--property='+v,argv)
 def test_cleanup_unknown_is_not_pass(self):self.assertFalse(runtime_layout.cleanup_ok({}))
 def test_owned_stop_needs_matching_nonempty_invocation(self):
  self.assertFalse(runtime_layout.owned_stop_allowed('own',{'Id':'own','InvocationID':''},{'Id':'own','InvocationID':''}))
  self.assertFalse(runtime_layout.owned_stop_allowed('own',{'Id':'own','InvocationID':'A'},{'Id':'own','InvocationID':'B'}))
 def test_native_is_blocked_before_server_construction(self):
  s=(B/'src/server.cc').read_text();self.assertLess(s.index('if (!aero_gate::LiveAdapterAvailable())'),s.index('gz::sim::Server server'))
  self.assertIn('return false;',(B/'src/adapter.cc').read_text())
  self.assertIn('trustedReadyCollected = false',s);self.assertNotIn('server.RunOnce(',s)
 def test_observer_cannot_return_to_physics(self):
  s=(B/'src/observer.cc').read_text().split('void PreUpdate',1)[1].split('void PostUpdate',1)[0]
  self.assertIn('std::_Exit(78)',s);self.assertNotIn('GO',s)
if __name__=='__main__':unittest.main()
