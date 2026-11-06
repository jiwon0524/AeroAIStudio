import json,unittest
from pathlib import Path
R=Path(__file__).resolve().parents[1]/'reports'
def load(n):return json.loads((R/n).read_text())
class Review(unittest.TestCase):
 def test_json(self):
  for p in R.glob('*.json'):self.assertIsInstance(json.loads(p.read_text()),dict)
 def test_capacity(self):
  for t in load('fixture_results.json')['tests']:
   if t['test_id'] in ('tmp_capacity','output_capacity'):
    d=json.loads(t['stdout'].splitlines()[-1]);self.assertEqual(d['errno'],28);self.assertEqual(d['capacity'],4194304);self.assertLessEqual(d['bytes_written'],4194304)
 def test_supervisor(self):
  r=load('supervisor_termination.json')['tests']
  for n in ('abnormal','sigkill'):self.assertGreaterEqual(len(r[n]['observed_tree']),6);self.assertEqual(r[n]['remaining_identities'],[]);self.assertTrue(r[n]['temporary_cleanup'])
 def test_sockets(self):
  r=load('fixture_results.json');self.assertEqual(r['host_socket_controls'],[True]*3);self.assertEqual(r['host_received_after_isolation'],[])
  t=next(t for t in r['tests'] if t['test_id']=='sockets');d=json.loads(t['stdout'].splitlines()[-1]);self.assertEqual((d['unix_local'],d['ipv6_local']),('local','local'));self.assertFalse(d['host_path_visible']);self.assertEqual(d['abstract_host'],111)
 def test_fail_closed(self):
  r=load('fail_closed.json')['tests'];self.assertEqual(len(r),6)
  for t in r.values():self.assertEqual(t['status'],'PASS');self.assertFalse(t['entered']);self.assertNotEqual(t['returncode'],0)
 def test_no_promotion_and_no_target(self):
  v=load('verdict.json');self.assertEqual(v['verdict'],'SANDBOX_ISOLATION_PARTIAL');self.assertEqual(v['Probe_A'],'BLOCKED');self.assertEqual(v['runtime'],'NOT_RUNTIME_VERIFIED');self.assertEqual(v['Stage_B'],'BLOCKED')
  for t in load('fixture_results.json')['tests']:
   if t['entered']:self.assertTrue(json.loads(t['stdout'].splitlines()[0])['maps_clean'])
if __name__=='__main__':unittest.main()
