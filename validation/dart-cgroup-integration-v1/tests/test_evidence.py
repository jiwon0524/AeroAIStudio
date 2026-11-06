"""Read-only assertions against actual, preserved revalidation evidence."""
import json,unittest
from pathlib import Path
R=Path(__file__).resolve().parents[1]/'reports';V=R/'revalidation'
def get(n):return json.loads((V/(n+'.json')).read_text())
class ObservedEvidence(unittest.TestCase):
 def test_three_generation_membership(self):
  for name in ('inheritance','bubblewrap'):
   d=get(name);self.assertEqual(d['status'],'PASS');self.assertEqual(len(d['records']),3)
   p=[x for x in d['host_processes'] if 'python' in x['executable']]
   self.assertEqual(len(p),3);self.assertEqual({x['cgroup'] for x in p},{'0::'+d['cgroup']})
 def test_resource_values(self):
  for name in ('inheritance','bubblewrap'):
   d=get(name)['readback']
   for k,v in (('memory.max','67108864'),('pids.max','8'),('cpu.max','25000 100000'),('memory.swap.max','0')):self.assertEqual(d[k],v)
   self.assertLessEqual(int(d['pids.current']),8);self.assertLess(int(d['memory.peak']),67108864)
 def test_namespace_identity(self):
  d=get('bubblewrap');cfg=json.loads(d['command'][-1]);self.assertTrue(all(d['records'][0]['ns'][k]!=v for k,v in cfg['host_ns'].items()))
  for x in d['records']:self.assertEqual(x['cgroup'],'0::/')
 def test_filesystem_network(self):
  d=get('bubblewrap')['records'][0]['isolation'];self.assertEqual(d['ipv4_external'],101);self.assertEqual(d['ipv6_external'],101)
  self.assertEqual(d['unix_host'],2);self.assertEqual(d['abstract_host'],111);self.assertEqual(d['ipv6_host'],111)
  self.assertTrue(d['private_writes']);self.assertFalse(get('socket_controls')['sandbox_connection_received'])
 def test_cleanup(self):
  d=get('process_cleanup');self.assertTrue(d['host_temp_removed']);self.assertTrue(d['project_canary_removed'])
  for x in d['cases'].values():self.assertEqual(x['status'],'PASS');self.assertFalse(x['remaining_identities']);self.assertTrue(x['cgroup_removed'])
 def test_controllers_restored(self):
  d=get('controller_diff');self.assertEqual(d['before_to_after'],[])
  self.assertEqual(d['manager_before']['values'],d['manager_after']['values'])
  for x in d['cases'].values():
   self.assertFalse(x['after']);self.assertTrue(all(y['expected'] for y in x['during']))
 def test_integrity(self):
  d=json.loads((R/'integrity.json').read_text());self.assertEqual(d['status'],'PASS');self.assertFalse(d['changed_or_missing']);self.assertTrue(d['main_status_unchanged'])
if __name__=='__main__':unittest.main()
