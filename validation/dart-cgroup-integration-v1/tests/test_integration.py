import importlib.util,json,unittest
from pathlib import Path
from unittest.mock import patch
B=Path(__file__).resolve().parents[1]
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
m=load('integration',B/'scripts/integration.py');f=load('fixture',B/'tests/fixture.py')
class SafetyTests(unittest.TestCase):
 def test_limits(self):
  a=m.argv('owned.service',['/usr/bin/python3'])
  self.assertIn('--pipe',a)
  for p in ('MemoryMax=64M','TasksMax=8','CPUQuota=25%','MemorySwapMax=0','KillMode=control-group','Delegate=no','RuntimeMaxSec=8s'):
   self.assertIn('--property='+p,a)
 def test_namespace_mounts(self):
  a=m.bwrap({},Path('/owned'))
  self.assertIn('--unshare-all',a);self.assertNotIn('--share-net',a);self.assertNotIn('--bind',a)
  for path in ('/project','/fixture','/limits'):self.assertIn(path,a)
  self.assertEqual(a.count('--tmpfs'),4)
 def test_fresh_name_and_one_shot(self):
  source=(B/'scripts/integration.py').read_text()
  self.assertIn("uuid.uuid4().hex[:10]",source);self.assertIn("open('x')",source)
  self.assertIn('unit collision',source);self.assertIn('one-shot campaign guard',source)
 def test_missing_approval_no_process(self):
  with patch.object(m.sys,'argv',['integration']),patch.object(m.subprocess,'Popen') as p:
   with self.assertRaisesRegex(RuntimeError,'approval'):m.main()
   p.assert_not_called()
 def test_namespace_gate_before_tree(self):
  cfg={'sandbox':True,'host_ns':{k:'same' for k in ('user','mnt','pid','net')}}
  with patch.object(f.os,'readlink',return_value='same'),patch.object(f.resource,'getrlimit',return_value=(268435456,268435456)),patch.object(f.subprocess,'Popen') as p:
   with self.assertRaisesRegex(RuntimeError,'namespace'):f.gate(cfg)
   p.assert_not_called()
 def test_cgroup_gate_before_tree(self):
  with patch.object(f.Path,'read_text',return_value='0::/wrong'),patch.object(f.subprocess,'Popen') as p:
   with self.assertRaisesRegex(RuntimeError,'cgroup'):f.gate({'sandbox':False,'cgroup':'/owned'})
   p.assert_not_called()
 def test_controller_diff(self):
  a={k:None for k in m.smoke.KEYS};a['memory.max']='max';b=dict(a,**{'memory.max':'1'})
  d=m.smoke.differences({'other':a},{'other':b},'owned')
  self.assertFalse(d[0]['expected'])
 def test_no_retry_or_pressure(self):
  s=(B/'tests/fixture.py').read_text();self.assertIn('if role<2:',s);self.assertIn('time.sleep(2)',s)
  self.assertNotIn('SIGKILL',s);self.assertNotIn('World',s)
if __name__=='__main__':unittest.main()
