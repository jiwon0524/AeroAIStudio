"""Evidence and stop-rule tests only; never loads the audit shared object."""
import json,unittest,importlib.util,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];B=Path(__file__).resolve().parents[1]
V1=ROOT/'validation/gazebo-minimal-physics-v1'
class StopTests(unittest.TestCase):
 def test_three_findings_remain_unresolved(self):
  e=json.loads((B/'reports/api_path_evidence.json').read_text())
  self.assertEqual(e['status']['1_active_detector_provider'],'UNRESOLVED_PUBLIC_BRIDGE_MISSING')
  self.assertEqual(e['status']['2_iteration_zero_initialization'],'UNRESOLVED_HOOK_NOT_ESTABLISHED')
  self.assertEqual(e['status']['3_runtime_collection'],'NOT_CONNECTED_PREREQUISITES_1_2_UNRESOLVED')
 def test_named_update_creation_step_chain(self):
  e=json.loads((B/'reports/api_path_evidence.json').read_text())['named_call_evidence']
  keys=('Physics_Update_CreatePhysicsEntities','Physics_Update_UpdatePhysics','Physics_Update_Step')
  sites=[int(e[k][0].split(':',1)[0].strip(),16) for k in keys]
  self.assertEqual(sites,sorted(sites));self.assertTrue(e['CreatePhysicsEntities_CreateWorldEntities'])
 def test_getter_is_not_dismissed_as_config_only(self):
  e=json.loads((B/'reports/api_path_evidence.json').read_text())['named_call_evidence']
  self.assertTrue(e['active_name_getter_getConstraintSolver']);self.assertTrue(e['active_name_getter_getCollisionDetector'])
 def test_public_audit_does_not_construct_or_walk_objects(self):
  s=(B/'src/public_api_audit.cc').read_text()
  for token in ('reinterpret_cast','dlsym(','dlopen(','server.Run(','new gz::sim::Server'):self.assertNotIn(token,s)
  self.assertIn('const std::string&',s);self.assertIn('!HasPublicDataPtr',s)
 def test_existing_adapter_stays_closed(self):
  self.assertIn('return false;',(V1/'src/adapter.cc').read_text())
  self.assertIn('trustedReadyCollected = false',(V1/'src/server.cc').read_text())
 def test_existing_launcher_refuses_before_runtime(self):
  spec=importlib.util.spec_from_file_location('unchanged_launch',V1/'scripts/launch.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
  c=json.loads((V1/'reports/runtime_contract.json').read_text())
  with self.assertRaisesRegex(ValueError,'NOT_EXECUTION_READY'):m.require_executable_contract(c)
  c.update(status='EXECUTION_READY',blockers=[],risk_acceptance='EXPLICITLY_RECORDED');c['capabilities']={k:True for k in c['capabilities']}
  with self.assertRaisesRegex(ValueError,'not implemented'):m.require_executable_contract(c)
 def test_runtime_outputs_markers_absent(self):
  c=json.loads((V1/'reports/runtime_contract.json').read_text())
  for p in c['outputs']+c['one_shot']:self.assertFalse(os.path.lexists(V1/p),p)
 def test_no_risk_acceptance_or_api_claim_promoted(self):
  c=json.loads((V1/'reports/runtime_contract.json').read_text())
  self.assertEqual(c['risk_acceptance'],'NOT_ACCEPTED');self.assertFalse(any(c['capabilities'].values()))
if __name__=='__main__':unittest.main()
