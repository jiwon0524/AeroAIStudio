import hashlib,json,os,subprocess,sys,unittest
from pathlib import Path
from unittest.mock import patch
B=Path(__file__).resolve().parents[1];sys.path.insert(0,str(B/'scripts'))
import common
class Loader(unittest.TestCase):
 def run_loader(self,*args):return subprocess.run([str(B/'work/native_loader'),*args],text=True,capture_output=True,timeout=5)
 def read(self,c,n):return json.loads((B/'reports'/c/n).read_text())
 def test_default_no_load(self):
  p=self.run_loader();self.assertEqual(p.returncode,77);self.assertNotIn('open_begin',p.stdout)
 def test_contract_no_load(self):
  p=self.run_loader('--contract');self.assertEqual(p.returncode,0);self.assertNotIn('open_begin',p.stdout)
 def test_unsupported_no_load(self):
  p=self.run_loader('--unknown');self.assertEqual(p.returncode,77);self.assertNotIn('open_begin',p.stdout)
 def test_mock_open_error(self):
  p=self.run_loader('--simulate','open-error');self.assertEqual(p.returncode,20);self.assertNotIn('"ATTEMPT"',p.stdout)
 def test_elf_and_identity(self):
  e=common.load_manifest()['profiles']['harmless_fixture_only'][0];fd=common.validate(common.load_manifest(),'harmless_fixture_only')
  try:self.assertEqual(hashlib.sha256((B/'work/native_loader').read_bytes()).hexdigest(),e['sha256'])
  finally:
   for x in fd:os.close(x)
  out=subprocess.check_output(['readelf','-d',str(B/'work/native_loader')],text=True);self.assertNotIn('libdart',out)
  syms=subprocess.check_output(['readelf','-Ws',str(B/'work/native_loader')],text=True);self.assertIn('dlopen@',syms);self.assertIn('dlclose@',syms)
 def test_native_cases(self):
  for c in ('accept','reject','timeout'):
   r=self.read(c,'native_fixture_execution.json');self.assertEqual(r['status'],'PASS');self.assertEqual(r['returncode'],0 if c=='accept' else 78)
   self.assertNotIn('"result":"ATTEMPT"',r['stdout'])
 def test_go_reject_timeout(self):
  for c in ('reject','timeout'):
   r=self.read(c,'native_fixture_execution.json');self.assertFalse(r['go_sent']);self.assertFalse(r['body_entered'])
  self.assertGreaterEqual(self.read('timeout','native_fixture_execution.json')['elapsed_seconds'],3)
 def test_cleanup(self):
  for c in ('accept','reject','timeout'):
   r=self.read(c,'process_cleanup.json');self.assertEqual(r['cleanup']['status'],'PASS');self.assertTrue(r['host_temp_removed']);self.assertTrue(r['canary_removed'])
 def test_cgroup(self):
  for c in ('accept','reject','timeout'):
   r=self.read(c,'resource_readback.json')['observed']
   for k,v in {'memory.max':'67108864','memory.swap.max':'0','pids.max':'8','cpu.max':'25000 100000'}.items():self.assertEqual(r[k],v)
 def test_strict_gate_dispatch(self):
  sent=[]
  with patch.object(common.readiness,'post_open') as p,patch('mapped.start_id',return_value='fixed'):
   p.side_effect=lambda pid,start,core,baseline,send:(send('CLOSE\n') or {'status':'PASS_FILE_IDENTITY'})
   common.gate(os.getpid(),common.load_manifest(),sent.append,require_core=True)
  self.assertEqual(sent,['GO\n'])
 def test_manifest_core_unchanged(self):
  m=common.load_manifest();self.assertEqual(m['profiles']['installed_core_future_only'],common.old_manifest()['profiles']['installed_core_future_only'])
 def test_reject_checker_no_go(self):
  sent=[]
  with patch.object(common,'verify',return_value={'status':'FAIL'}):common.gate(os.getpid(),common.load_manifest(),sent.append)
  self.assertEqual(sent,[])
if __name__=='__main__':unittest.main()
