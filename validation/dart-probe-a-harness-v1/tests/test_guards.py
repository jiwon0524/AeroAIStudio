import copy,json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
B=Path(__file__).resolve().parents[1];sys.path.insert(0,str(B/'scripts'))
import allowlist,identity,mapped,supervisor,stage
class Guards(unittest.TestCase):
 def setUp(self):self.manifest=allowlist.load_manifest()
 def rejects(self,config=None,manifest=None):
  launch=Mock()
  with self.assertRaises((ValueError,OSError)):supervisor.guard(config or copy.deepcopy(supervisor.CONFIG),manifest or self.manifest,launch)
  launch.assert_not_called()
 def test_allowlist_valid(self):
  for name in self.manifest['profiles']:
   fds=allowlist.validate(self.manifest,name)
   for fd in fds:os.close(fd)
 def test_missing_library(self):
  m=copy.deepcopy(self.manifest);m['profiles']['installed_core_future_only'].pop();self.rejects(manifest=m)
 def test_hash_mismatch(self):
  m=copy.deepcopy(self.manifest);m['profiles']['installed_core_future_only'][0]['sha256']='0'*64;self.rejects(manifest=m)
 def test_build_id_mismatch(self):
  m=copy.deepcopy(self.manifest);m['profiles']['installed_core_future_only'][0]['build_id']='00';self.rejects(manifest=m)
 def test_sandbox_gate(self):
  c=copy.deepcopy(supervisor.CONFIG);c['mount_namespace']=False;self.rejects(config=c)
 def test_network_gate(self):
  c=copy.deepcopy(supervisor.CONFIG);c['network_namespace']=False;self.rejects(config=c)
 def test_readonly_gate(self):
  c=copy.deepcopy(supervisor.CONFIG);c['read_only']=False;self.rejects(config=c)
 def test_resource_gate(self):
  c=copy.deepcopy(supervisor.CONFIG);c['limits']['TasksMax']=9;self.rejects(config=c)
 def test_supervisor_gate(self):
  c=copy.deepcopy(supervisor.CONFIG);c['supervisor_ready']=False;self.rejects(config=c)
 def test_manifest_pin(self):
  with patch.object(allowlist.hashlib,'sha256') as h:
   h.return_value.hexdigest.return_value='bad'
   with self.assertRaisesRegex(ValueError,'pin'):allowlist.load_manifest()
 def test_profile_runpath_gate(self):
  m=copy.deepcopy(self.manifest);m['profiles']['installed_core_future_only'][0]['runpath']=['/tmp:'];self.rejects(manifest=m)
 def test_fd_cleanup_on_second_profile_failure(self):
  fd=os.open(B/'fixtures/base_probe_a.c',os.O_RDONLY)
  with patch.object(supervisor,'validate',side_effect=[[fd],ValueError('second profile')]):
   with self.assertRaises(ValueError):supervisor.guard(supervisor.CONFIG,self.manifest,Mock())
  with self.assertRaises(OSError):os.fstat(fd)
 def test_no_loader_imports(self):
  sym=subprocess.check_output(['/usr/bin/readelf','--dyn-syms','-W',str(B/'work/native_fixture')],text=True)
  self.assertNotIn(' dlopen',sym);self.assertNotIn(' dlclose',sym)
 def test_base_source_exact_reuse(self):
  self.assertEqual((B/'fixtures/base_probe_a.c').read_bytes(),(B.parent/'dart-probe-a-static-audit-v1/fixtures/probe_a.c').read_bytes())
 def test_fd_bind_only(self):
  e=self.manifest['profiles']['harmless_fixture_only'];cmd=stage.bwrap(e,[11,12,13],14,15,[])
  self.assertEqual(cmd.count('--ro-bind-fd'),5);self.assertNotIn('--bind',cmd);self.assertNotIn('--ro-bind',cmd)
  self.assertNotIn('/usr/bin/python3',cmd[cmd.index('--clearenv'):]);self.assertNotIn('--share-net',cmd)
 def test_live_limit_reader_rejects_mock_bad_value(self):
  with tempfile.TemporaryDirectory(dir=B/'work') as d:
   for k,v in (('memory.max','67108864'),('memory.swap.max','0'),('pids.max','8'),('cpu.max','25000 100000')):Path(d,k).write_text(v)
   stage.resources(Path(d));Path(d,'pids.max').write_text('9')
   with self.assertRaisesRegex(ValueError,'resource'):stage.resources(Path(d))
 def test_maps_unexpected(self):
  row=mapped.parse_maps('1000-2000 r-xp 0000 00:01 99 /unexpected.so')[0]
  with self.assertRaisesRegex(ValueError,'unexpected'):mapped.mapping_entry(row,[])
 def test_maps_replaced_inode(self):
  e=self.manifest['profiles']['harmless_fixture_only'][0];row={'path':e['sandbox_path'],'device':e['device'],'inode':e['inode']+1}
  with self.assertRaisesRegex(ValueError,'inode'):mapped.mapping_entry(row,[e])
 def test_maps_deleted(self):
  with self.assertRaisesRegex(ValueError,'deleted'):mapped.mapping_entry({'path':'/x (deleted)'},[])
 def test_missing_pid_is_failure(self):self.assertEqual(mapped.verify(2147483647,[])['status'],'FAIL')
 def test_corrupt_elf(self):
  with tempfile.TemporaryFile() as f:
   f.write(b'not ELF');f.flush()
   with self.assertRaises(ValueError):identity.describe_fd(f.fileno())
 def test_build_id_matches_readelf(self):
  e=self.manifest['profiles']['harmless_fixture_only'][0];fd=identity.open_checked(e)
  try:self.assertEqual(identity.build_id_fd(fd),e['build_id'])
  finally:os.close(fd)
 def test_owned_file_mutation_rejected(self):
  data=(B/'work/native_fixture').read_bytes()
  with tempfile.TemporaryFile(dir=B/'work') as f:
   f.write(data);f.flush();expected=identity.describe_fd(f.fileno())
   os.pwrite(f.fileno(),b'X',len(data)-1)
   with self.assertRaisesRegex(ValueError,'sha256'):identity.check_fd(f.fileno(),expected)
 def test_device_identity_mismatch(self):
  e=copy.deepcopy(self.manifest['profiles']['harmless_fixture_only'][0]);fd=os.open(e['real_path'],os.O_RDONLY);e['device']+=1
  try:
   with self.assertRaisesRegex(ValueError,'device'):identity.check_fd(fd,e)
  finally:os.close(fd)
 def test_no_implicit_execution(self):
  with patch.object(sys,'argv',['supervisor']),patch.object(subprocess,'Popen') as p:
   with self.assertRaisesRegex(ValueError,'explicit'):supervisor.main()
   p.assert_not_called()
if __name__=='__main__':unittest.main()
