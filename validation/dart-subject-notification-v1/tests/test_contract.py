"""Non-executing tests. No native invocation, service, live mapping or target loader."""
import io,json,sys,unittest
from pathlib import Path
from unittest.mock import patch
B=Path(__file__).resolve().parents[1];sys.path.insert(0,str(B/'scripts'))
import common,launch,notification_supervisor as supervisor

GOOD=[{'phase':'post_open_ready','result':'WAIT'},
 {'phase':'registered','bodies':1,'shape_nodes':1,'subjects':2,'callbacks_before_release':0},
 {'phase':'notifications_observed','shape_node_callbacks':1,'body_node_callbacks':1,'order':['shape_node','body_node'],'within_owner_reset':True,'subjects_remaining':0},
 {'phase':'lifetime_success','scope':'subject_notifications_only','individual_destructors':'NOT_OBSERVED','allocator_balance':'NOT_MEASURED'}]
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
  contract={'prepared_source_sha256':{'fixtures/notification.cpp':'0'*64}}
  with patch.object(common.json,'loads',return_value=contract):
   with self.assertRaisesRegex(ValueError,'prepared source changed'):common.check_prepared()
 def test_manager_failure_precedes_marker(self):
  with patch.object(sys,'argv',['launch','--execute-approved-notification-once']),patch.object(supervisor,'prepare_service',side_effect=ValueError('manager unavailable')),patch.object(launch.preservation.p,'snapshot',side_effect=AssertionError('snapshot forbidden')):
   with self.assertRaisesRegex(ValueError,'manager unavailable'):launch.main()
  common.check_fresh()
 def test_synthetic_sequence_recognized_without_destructor_claim(self):self.assertTrue(supervisor.lifetime_ok(encode(GOOD)))
 def test_substring_exit_not_sufficient(self):self.assertFalse(supervisor.lifetime_ok('lifetime_success'))
 def test_missing_duplicate_reordered_events_rejected(self):
  for rows in (GOOD[:-1],GOOD+GOOD[-1:],list(reversed(GOOD))):self.assertFalse(supervisor.lifetime_ok(encode(rows)))
 def test_missing_callback_rejected(self):
  rows=json.loads(json.dumps(GOOD));rows[2]['body_node_callbacks']=0
  self.assertFalse(supervisor.lifetime_ok(encode(rows)))
 def test_dtor_proof_claim_rejected(self):
  rows=json.loads(json.dumps(GOOD));rows[3]['individual_destructors']='PROVEN'
  self.assertFalse(supervisor.lifetime_ok(encode(rows)))
 def test_callback_duplicate_wrong_order_window_rejected(self):
  for key,value in [('shape_node_callbacks',2),('order',['body_node','shape_node']),('within_owner_reset',False),('subjects_remaining',1)]:
   rows=json.loads(json.dumps(GOOD));rows[2][key]=value
   self.assertFalse(supervisor.lifetime_ok(encode(rows)))
 def test_early_callback_rejected(self):
  rows=json.loads(json.dumps(GOOD));rows[1]['callbacks_before_release']=1
  self.assertFalse(supervisor.lifetime_ok(encode(rows)))
 def test_weak_expiration_cannot_replace_callbacks(self):
  rows=json.loads(json.dumps(GOOD));rows[2]={'phase':'notifications_observed','skeleton_expired':True,'shape_expired':True}
  self.assertFalse(supervisor.lifetime_ok(encode(rows)))
 def test_collector_has_no_callback_allocation_or_output(self):
  text=(B/'fixtures/notification.cpp').read_text();cb=text.split('void handleDestructionNotification',1)[1].split('};',1)[0]
  for forbidden in ('printf','puts','new ','malloc','addSubject','watch('):self.assertNotIn(forbidden,cb)
 def test_no_fixture_before_go_and_no_manual_delete(self):
  text=(B/'fixtures/notification.cpp').read_text()
  self.assertLess(text.index('read(STDIN_FILENO'),text.index('Skeleton::create('))
  self.assertLess(text.index('recorder.window = true;'),text.index('owner.reset();'))
  for forbidden in ('new dart::','delete node','delete pair','World::','dlopen(','system('):self.assertNotIn(forbidden,text)
 def test_fixed_limits_mount_payload(self):
  from resolution import plan
  cmd,_=plan(common.load_manifest());self.assertEqual(cmd[-2:],['/fixture/native_fixture','--owned-notification-once'])
  for flag in ('--cpu=2:2','--as=268435456:268435456','--unshare-all','--cap-drop','--die-with-parent'):self.assertIn(flag,cmd)
if __name__=='__main__':unittest.main()
