import json,os,sys,unittest
from pathlib import Path
from unittest.mock import patch
B=Path(__file__).resolve().parents[1];sys.path.insert(0,str(B/'scripts'))
import common
class Integration(unittest.TestCase):
 def read(self,case,name):return json.loads((B/'reports'/case/name).read_text())
 def test_cases(self):
  for c in ('accept','reject','timeout'):self.assertEqual(self.read(c,'native_fixture_execution.json')['status'],'PASS')
 def test_accept_order(self):
  r=self.read('accept','native_fixture_execution.json');events=[json.loads(x) for x in r['stdout'].splitlines() if x.startswith('{')];ph=[x['phase'] for x in events]
  self.assertLess(ph.index('post_open_ready'),ph.index('post_open_accepted'));self.assertLess(ph.index('post_open_accepted'),ph.index('body_entered'));self.assertEqual(r['returncode'],0)
  self.assertTrue(all(not x.get('loader_compiled',False) for x in events))
 def test_reject(self):
  r=self.read('reject','native_fixture_execution.json');self.assertEqual(r['returncode'],78);self.assertFalse(r['go_sent']);self.assertFalse(r['body_entered']);self.assertIn('sha256 mismatch',r['error'])
 def test_timeout(self):
  r=self.read('timeout','native_fixture_execution.json');self.assertEqual(r['returncode'],78);self.assertGreaterEqual(r['elapsed_seconds'],3);self.assertFalse(r['go_sent']);self.assertFalse(r['body_entered'])
 def test_limits(self):
  for c in ('accept','reject','timeout'):
   r=self.read(c,'resource_readback.json')['observed']
   for k,v in {'memory.max':'67108864','memory.swap.max':'0','pids.max':'8','cpu.max':'25000 100000'}.items():self.assertEqual(r[k],v)
 def test_cleanup(self):
  for c in ('accept','reject','timeout'):
   r=self.read(c,'process_cleanup.json');self.assertEqual(r['cleanup']['status'],'PASS');self.assertFalse(r['cleanup']['remaining_identities']);self.assertTrue(r['host_temp_removed']);self.assertTrue(r['canary_removed'])
 def test_controller(self):
  for c in ('accept','reject','timeout'):self.assertEqual(self.read(c,'controller_diff.json')['before_to_after'],[])
 def test_fallback_honest(self):
  r=self.read('accept','mapped_library_validation.json');self.assertEqual(r['status'],'PASS_FILE_IDENTITY')
  if any(x['map_files_open']=='UNAVAILABLE' for x in r['records']):self.assertEqual(r['map_files_status'],'UNAVAILABLE')
 def test_rejected_checker_no_go(self):
  sent=[]
  with patch.object(common,'verify',return_value={'status':'FAIL'}):common.gate(1,common.load_manifest(),sent.append)
  self.assertEqual(sent,[])
 def test_accepted_checker_go(self):
  sent=[]
  with patch.object(common,'verify',return_value={'status':'PASS_FILE_IDENTITY'}):common.gate(1,common.load_manifest(),sent.append)
  self.assertEqual(sent,['GO\n'])
 def test_core_profile(self):
  m=common.load_manifest();fds=common.validate(m,'installed_core_future_only')
  try:
   self.assertEqual(len(fds),16);mounts,edges=common.readiness.aliases(m['profiles']['installed_core_future_only']);self.assertEqual(len(edges),58);self.assertIn('/usr/lib/x86_64-linux-gnu/libdart.so.6.13.2',mounts)
  finally:
   for fd in fds:os.close(fd)
 def test_core_review_path(self):
  s=(B/'fixtures/core_review_only.c').read_text();self.assertNotIn('/audit/libdart',s);self.assertIn('RTLD_NOW|RTLD_LOCAL',s);self.assertIn('permission,"GO\\n"',s)
if __name__=='__main__':unittest.main()
