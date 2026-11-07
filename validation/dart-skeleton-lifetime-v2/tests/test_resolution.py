"""Non-executing regressions: only readelf and Python source/plan inspection."""
import copy,json,sys,unittest
from pathlib import Path
from unittest.mock import patch
B=Path(__file__).resolve().parents[1];sys.path.insert(0,str(B/'scripts'))
import resolution as r
from common import load_manifest
class ResolutionTests(unittest.TestCase):
 def setUp(self):self.m=load_manifest();self.cmd,self.fds=r.plan(self.m)
 def test_corrected_actual_plan(self):self.assertEqual(r.preflight(self.m)['status'],'PASS_STATIC_RESOLUTION')
 def test_failed_v1_configuration_rejected(self):
  cmd=self.cmd[:];i=cmd.index('/usr/lib/x86_64-linux-gnu/libdart.so.6.13');del cmd[i-2:i+1]
  with self.assertRaisesRegex(ValueError,'missing alias libdart.so.6.13'):r.check_command(self.m,cmd,self.fds)
 def test_wrong_approved_target_rejected(self):
  cmd=self.cmd[:];i=cmd.index('/usr/lib/x86_64-linux-gnu/libdart.so.6.13');cmd[i-1]='201'
  with self.assertRaisesRegex(ValueError,'wrong alias target'):r.check_command(self.m,cmd,self.fds)
 def test_conflicting_duplicate_rejected(self):
  cmd=['--ro-bind-fd','201','/usr/lib/x86_64-linux-gnu/libdart.so.6.13']+self.cmd
  with self.assertRaisesRegex(ValueError,'conflicting mount'):r.check_command(self.m,cmd,self.fds)
 def test_unapproved_fd_rejected(self):
  cmd=self.cmd[:];i=cmd.index('/usr/lib/x86_64-linux-gnu/libdart.so.6.13');cmd[i-1]='999'
  with self.assertRaisesRegex(ValueError,'unknown FD'):r.check_command(self.m,cmd,self.fds)
 def test_interpreter_link_rejected(self):
  cmd=self.cmd[:];i=cmd.index('/lib64');cmd[i-1]='wrong'
  with self.assertRaisesRegex(ValueError,'symlink missing'):r.check_command(self.m,cmd,self.fds)
 def test_source_metadata_tamper_rejected(self):
  m=copy.deepcopy(self.m);m['profiles']['harmless_fixture_only'][0]['needed']=[]
  with self.assertRaisesRegex(ValueError,'metadata mismatch'):r.check_command(m,self.cmd,self.fds)
 def test_preflight_failure_before_marker_or_service(self):
  import launch
  with patch.object(sys,'argv',['launch','--execute-approved-skeleton-once']),patch.object(launch,'preflight',side_effect=ValueError('static alias failure')),patch.object(launch.subprocess,'run') as service:
   with self.assertRaisesRegex(ValueError,'static alias failure'):launch.main()
   service.assert_not_called()
  self.assertFalse(any((B/'work').glob('*attempt*')));self.assertFalse((B/'reports/runtime').exists())
 def test_new_alias_allowed_before_GO(self):
  import readiness_fixed as ready
  core=self.m['profiles']['installed_core_future_only'];mounts,_=ready.aliases(core)
  self.assertEqual(mounts['/usr/lib/x86_64-linux-gnu/libdart.so.6.13']['sha256'],core[0]['sha256'])
  source=(B/'scripts/common.py').read_text();self.assertIn('readiness_fixed as readiness',source)
 def test_supervisor_checks_before_service_marker(self):
  source=(B/'scripts/supervisor.py').read_text()
  self.assertLess(source.index('preflight(manifest)'),source.index("with (W/attempt).open('x')"))
  self.assertLess(source.index('preflight(manifest)'),source.index('subprocess.Popen(command'))
if __name__=='__main__':unittest.main()
