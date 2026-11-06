import json,selectors,subprocess,unittest
from pathlib import Path
B=Path(__file__).resolve().parents[1];EXE=B/'work/fixture_offline'
def invoke(*args):
 p=subprocess.run([str(EXE),*args],capture_output=True,text=True,timeout=2);return p,[json.loads(l) for l in p.stdout.splitlines()]
class FixtureTests(unittest.TestCase):
 def test_default_contract(self):
  p,rows=invoke('--contract');self.assertEqual(p.returncode,0);self.assertFalse(rows[0]['loader_compiled']);self.assertEqual(rows[0]['result'],'STATIC_ONLY')
 def test_actual_entry_disabled(self):
  p,rows=invoke('--execute-approved-core-load','fake','fake');self.assertEqual(p.returncode,77);self.assertEqual(rows[0]['result'],'REJECTED')
 def test_simulated_success(self):
  p,rows=invoke('--simulate','success');self.assertEqual(p.returncode,0);self.assertEqual([r['sequence'] for r in rows],list(range(1,7)));self.assertTrue(all(not r['loader_compiled'] for r in rows));self.assertTrue(all(r['result']=='SIMULATED' for r in rows))
  self.assertEqual(sorted(r['monotonic_ns'] for r in rows),[r['monotonic_ns'] for r in rows])
 def test_simulated_open_error(self):
  p,rows=invoke('--simulate','open-error');self.assertEqual(p.returncode,20);self.assertFalse(any(r['phase']=='close_begin' for r in rows));self.assertIn('"open"',rows[2]['detail']);self.assertIn('\n',rows[2]['detail'])
 def test_simulated_close_error(self):
  p,rows=invoke('--simulate','close-error');self.assertEqual(p.returncode,21);self.assertEqual(rows[-2]['phase'],'close_result');self.assertEqual(rows[-2]['result'],'ERROR')
 def test_unknown_input(self):
  p,_=invoke('--simulate','not-allowed');self.assertEqual(p.returncode,64)
 def test_timeout_and_signal_cleanup(self):
  p=subprocess.Popen([str(EXE),'--await-signal'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
  try:
   with selectors.DefaultSelector() as s:
    s.register(p.stdout,selectors.EVENT_READ);self.assertTrue(s.select(1));first=json.loads(p.stdout.readline());self.assertEqual(first['phase'],'ready')
   with self.assertRaises(subprocess.TimeoutExpired):p.wait(timeout=.05)
   p.terminate();out,err=p.communicate(timeout=2);self.assertEqual(p.returncode,143);self.assertEqual(json.loads(out)['signal'],15);self.assertEqual(err,'')
  finally:
   if p.poll() is None:p.terminate();p.wait(timeout=4)
   p.stdout.close();p.stderr.close()
 def test_default_no_dynamic_load_imports(self):
  s=subprocess.check_output(['/usr/bin/readelf','--dyn-syms','-W',str(EXE)],text=True)
  self.assertNotIn(' dlopen',s);self.assertNotIn(' dlclose',s)
  dyn=subprocess.check_output(['/usr/bin/readelf','-dW',str(EXE)],text=True);self.assertNotIn('libdart',dyn);self.assertNotIn('RUNPATH',dyn)
 def test_native_branch_object_only(self):
  p=B/'work/loader_review_only.o';s=subprocess.check_output(['/usr/bin/readelf','-sW',str(p)],text=True);self.assertIn(' dlopen',s);self.assertIn(' dlclose',s)
  h=subprocess.check_output(['/usr/bin/readelf','-hW',str(p)],text=True);self.assertIn('REL (Relocatable file)',h)
if __name__=='__main__':unittest.main()
