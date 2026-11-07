import json,unittest
from pathlib import Path
B=Path(__file__).resolve().parents[1];R=B/'reports'
def read(n):return json.loads((R/(n+'.json')).read_text())
class Observed(unittest.TestCase):
 def test_native_go_order(self):
  x=read('native_fixture_execution');self.assertEqual(x['status'],'PASS');self.assertEqual(x['returncode'],0);self.assertTrue(x['go_sent']);self.assertTrue(x['body_entered'])
  rows=[json.loads(l) for l in x['stdout'].splitlines()];phases=[r['phase'] for r in rows]
  self.assertLess(phases.index('harness_ready'),phases.index('body_entered'));self.assertTrue(all(not r['loader_compiled'] for r in rows))
  self.assertEqual([r['sequence'] for r in rows],list(range(1,len(rows)+1)))
 def test_actual_mapping_identity(self):
  x=read('mapped_library_validation');self.assertEqual(x['status'],'PASS_FILE_IDENTITY');self.assertTrue(x['all_required']);self.assertEqual(len(x['records']),3)
  entries=read('library_allowlist')['profiles']['harmless_fixture_only'];by_path={e['sandbox_path']:e for e in entries}
  for row in x['records']:
   for key in ('device','inode','sha256','build_id'):self.assertEqual(row['identity'][key],by_path[row['path']][key])
  self.assertFalse(any('libdart' in row['path'] or 'libgz-' in row['path'] for row in x['records']))
 def test_unavailable_map_files_not_pass(self):
  x=read('mapped_library_validation');self.assertEqual(x['map_files_status'],'UNAVAILABLE')
  for row in x['records']:
   self.assertEqual(row['map_files_open'],'UNAVAILABLE');self.assertEqual(row['map_files_errno'],1);self.assertEqual(row['fallback'],'proc_root_fd')
 def test_resources_membership(self):
  x=read('resource_readback')['observed']
  for key,val in (('memory.max','67108864'),('memory.swap.max','0'),('pids.max','8'),('cpu.max','25000 100000')):self.assertEqual(x[key],val)
  self.assertLess(int(x['memory.peak']),67108864);self.assertEqual(x['pids.current'],'3')
  for row in read('native_fixture_execution')['host_processes']:self.assertIn('/aero-probe-a-harmless-v1-',row['cgroup'])
 def test_cleanup_and_controller(self):
  c=read('process_cleanup');self.assertEqual(c['cleanup']['status'],'PASS');self.assertTrue(c['cleanup']['cgroup_removed']);self.assertFalse(c['cleanup']['remaining_identities']);self.assertTrue(c['host_temp_removed']);self.assertTrue(c['canary_removed'])
  d=read('controller_diff');self.assertFalse(d['before_to_after']);self.assertTrue(all(x['expected'] for x in d['during']));self.assertEqual(d['manager_before']['values'],d['manager_after']['values'])
 def test_isolation_and_initial_fail_closed(self):
  x=read('native_fixture_execution');self.assertFalse(x['socket_controls']['sandbox_host_connections']);self.assertEqual(x['socket_controls']['positive_controls'],[True]*3)
  self.assertIn('"phase":"isolation","result":"PASS"',x['stdout']);self.assertIn('errno=26',x['stdout'])
  old=json.loads((R/'initial/native_fixture_execution.json').read_text());self.assertEqual(old['status'],'FAIL');self.assertFalse(old['body_entered']);self.assertFalse(old['go_sent']);self.assertEqual(old['cleanup']['status'],'PASS')
if __name__=='__main__':unittest.main()
