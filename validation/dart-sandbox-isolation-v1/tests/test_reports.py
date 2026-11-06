import json,unittest
from pathlib import Path
R=Path(__file__).resolve().parents[1]/'reports'
def load(n):return json.loads((R/n).read_text())
class Review(unittest.TestCase):
 def test_json(self):
  for p in R.glob('*.json'):self.assertIsInstance(json.loads(p.read_text()),dict)
 def test_namespaces_limits_and_no_targets(self):
  r=load('fixture_results.json')
  for t in r['tests']:
   if not t['gate_ready']:continue
   d=json.loads(t['stdout'].splitlines()[0]);self.assertTrue(d['maps_clean'])
   for k,v in r['host_namespaces'].items():self.assertNotEqual(d['namespaces'][k],v)
   self.assertEqual(d['limits']['RLIMIT_AS'],[268435456]*2);self.assertEqual(d['limits']['RLIMIT_CORE'],[0,0])
 def test_files_network(self):
  r=load('fixture_results.json');self.assertTrue(r['canary_preserved']);self.assertEqual(r['host_listener_received'],[])
  t=next(x for x in r['tests'] if x['test_id']=='filesystem');self.assertEqual(json.loads(t['stdout'].splitlines()[1]),{'/media/value':30,'/opt/value':30})
 def test_fail_closed(self):
  t=next(x for x in load('fixture_results.json')['tests'] if x['test_id']=='fail_closed');self.assertFalse(t['fixture_entered']);self.assertFalse(t['gate_ready']);self.assertNotEqual(t['returncode'],0)
 def test_termination(self):
  t=next(x for x in load('fixture_results.json')['tests'] if x['test_id']=='descendants');self.assertGreaterEqual(len(t['observed_processes']),3);self.assertEqual(t['live_survivors'],[]);self.assertTrue(t['temporary_cleanup'])
 def test_no_promotion(self):
  r=load('verdict.json');self.assertEqual(r['verdict'],'SANDBOX_ISOLATION_PARTIAL');self.assertEqual(r['probe_A'],'BLOCKED');self.assertEqual(r['runtime'],'NOT_RUNTIME_VERIFIED');self.assertEqual(r['Stage_B'],'BLOCKED')
if __name__=='__main__':unittest.main()
