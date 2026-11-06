import importlib.util,json,unittest
from pathlib import Path
B=Path(__file__).resolve().parents[1];R=B/'reports'
def load(n):return json.loads((R/n).read_text())
class Readiness(unittest.TestCase):
 def test_json_and_no_creation(self):
  for p in R.glob('*.json'):self.assertIsInstance(json.loads(p.read_text()),dict)
  x=load('cgroup_capabilities.json');self.assertFalse(x['creation_attempted']);self.assertFalse(x['resource_excess_tests_run'])
 def test_delegation_scope(self):
  x=load('cgroup_capabilities.json');a=x['ancestors_leaf_to_root'];leaf=a[0];manager=next(p for p in a if p['path'].endswith('/user@1000.service'))
  self.assertNotIn('cpu',leaf['files']['cgroup.controllers']['value'].split());self.assertIn('error',leaf['files']['cpu.max'])
  self.assertTrue({'cpu','memory','pids'}<=set(manager['files']['cgroup.subtree_control']['value'].split()))
 def test_api_is_not_authorization(self):
  a=load('cgroup_capabilities.json')['transient_API_support'];self.assertTrue(a['method_found']);self.assertIn('no authorization test',a['semantics']);self.assertEqual(load('verdict.json')['transient_creation_permission'].split(';')[0],'UNVERIFIED')
 def test_plan_generator_is_smoke_only(self):
  spec=importlib.util.spec_from_file_location('review_plan',B/'scripts/plan.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  plan=module.build();self.assertEqual(plan,load('approval_plan.json'));argv=plan['creation_argv'];self.assertEqual(argv[-2:],['/usr/bin/sleep','5']);self.assertIn('--user',argv);self.assertNotIn('--scope',argv);self.assertTrue(plan['execute_only_after_explicit_approval'])
  for k,v in {'MemoryMax':'64M','MemorySwapMax':'0','TasksMax':'8','CPUQuota':'25%','RuntimeMaxSec':'8s','KillMode':'control-group','Delegate':'no'}.items():self.assertIn('--property='+k+'='+v,argv)
 def test_pressure_tests_not_run_and_finite(self):
  p=load('resource_test_plan.json');self.assertEqual(len(p['tests']),8);self.assertEqual({t['status'] for t in p['tests']},{'SKIP'});self.assertIn('no fallback to RLIMIT',' '.join(p['baseline_and_gate']));self.assertIn('16',next(t for t in p['tests'] if t['id']=='pids_pressure')['case'])
 def test_risk_states_and_blocked(self):
  x=load('probe_a_blockers.json');self.assertEqual(x['Probe_A'],'BLOCKED');self.assertEqual(x['Probe_B_D'],'BLOCKED')
  self.assertTrue(all(r['status'] in ('VERIFIED','PARTIALLY_VERIFIED','UNVERIFIED','BLOCKED') for r in x['risks']))
 def test_no_runtime_promotion(self):
  x=load('verdict.json');self.assertEqual(x['verdict'],'CGROUP_DELEGATION_PARTIAL');self.assertEqual(x['runtime'],'NOT_RUNTIME_VERIFIED');self.assertEqual(x['Stage_B'],'BLOCKED');self.assertFalse(x['actual_cgroup_or_unit_creation']);self.assertFalse(x['actual_resource_pressure_tests'])
if __name__=='__main__':unittest.main()
