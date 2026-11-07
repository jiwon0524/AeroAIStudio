"""Non-executing tests. No native invocation, service, live mapping or target loader."""
import io,json,sys,unittest
from pathlib import Path
from unittest.mock import patch
B=Path(__file__).resolve().parents[1];sys.path.insert(0,str(B/'scripts'))
import common,launch,body_shape_supervisor as supervisor

GOOD=[{'phase':'post_open_ready','result':'WAIT'},
 {'phase':'created','skeletons':1,'bodies':1,'joints':1,'shape_nodes':1,'shape_owner_matches':True},
 {'phase':'external_shape_released','shape_retained':True},
 {'phase':'owner_release_observed','skeleton_expired':True,'shape_expired':True,'individual_destructors':'NOT_OBSERVED'},
 {'phase':'lifetime_success','scope':'normal_owner_release_only','individual_destructors':'NOT_OBSERVED'}]
def encode(rows):return '\n'.join(json.dumps(x) for x in rows)
class ContractTests(unittest.TestCase):
 def test_prepared_hashes_branch_ancestry(self):common.check_prepared()
 def test_default_only_prints_contract(self):
  with patch.object(sys,'argv',['launch']),patch('sys.stdout',new_callable=io.StringIO) as out,patch.object(launch,'preflight',side_effect=AssertionError('no runtime preflight')):
   self.assertEqual(launch.main(),0);self.assertIn('PREPARED_NOT_EXECUTED',out.getvalue())
 def test_fresh_rejects_dangling_path(self):
  with patch.object(common.os.path,'lexists',return_value=True):
   with self.assertRaisesRegex(ValueError,'existing lifetime'):common.check_fresh()
 def test_bad_prepared_hash_rejected(self):
  contract={'prepared_source_sha256':{'fixtures/body_shape.cpp':'0'*64}}
  with patch.object(common.json,'loads',return_value=contract):
   with self.assertRaisesRegex(ValueError,'prepared source changed'):common.check_prepared()
 def test_manager_failure_precedes_marker(self):
  with patch.object(sys,'argv',['launch','--execute-approved-body-shape-once']),patch.object(supervisor,'prepare_service',side_effect=ValueError('manager unavailable')),patch.object(launch.preservation.p,'snapshot',side_effect=AssertionError('snapshot forbidden')):
   with self.assertRaisesRegex(ValueError,'manager unavailable'):launch.main()
  common.check_fresh()
 def test_synthetic_sequence_recognized_without_destructor_claim(self):self.assertTrue(supervisor.lifetime_ok(encode(GOOD)))
 def test_substring_exit_not_sufficient(self):self.assertFalse(supervisor.lifetime_ok('lifetime_success'))
 def test_missing_duplicate_reordered_events_rejected(self):
  for rows in (GOOD[:-1],GOOD+GOOD[-1:],list(reversed(GOOD))):self.assertFalse(supervisor.lifetime_ok(encode(rows)))
 def test_expired_false_rejected(self):
  rows=json.loads(json.dumps(GOOD));rows[3]['shape_expired']=False
  self.assertFalse(supervisor.lifetime_ok(encode(rows)))
 def test_dtor_proof_claim_rejected(self):
  rows=json.loads(json.dumps(GOOD));rows[4]['individual_destructors']='PROVEN'
  self.assertFalse(supervisor.lifetime_ok(encode(rows)))
 def test_no_fixture_before_go_and_no_manual_delete(self):
  text=(B/'fixtures/body_shape.cpp').read_text()
  self.assertLess(text.index('read(STDIN_FILENO'),text.index('Skeleton::create('))
  self.assertLess(text.index('shape.reset();'),text.index('owner.reset();'))
  for forbidden in ('new dart::','delete node','delete pair','World::','dlopen(','system('):self.assertNotIn(forbidden,text)
 def test_fixed_limits_mount_payload(self):
  from resolution import plan
  cmd,_=plan(common.load_manifest());self.assertEqual(cmd[-2:],['/fixture/native_fixture','--owned-body-shape-once'])
  for flag in ('--cpu=2:2','--as=268435456:268435456','--unshare-all','--cap-drop','--die-with-parent'):self.assertIn(flag,cmd)
if __name__=='__main__':unittest.main()
