import sys,copy,json,os
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from common import *
from protocol import AckWindow,HarmlessSession,Lines
import supervisor,plan
cases=[]
def reject(name,f):
 try:f()
 except (ValueError,OSError,KeyError) as e:cases.append({'case':name,'status':'PASS_REJECTED','reason':str(e)})
 else:raise AssertionError(name)
def prepared(snapshot=None):
 sent=[];w=AckWindow(sent.append,lambda:snapshot or {'status':'PASS_FILE_IDENTITY','start':'s1','pid':77},'s1',77);s=HarmlessSession(w,lambda:True)
 for _ in range(2):s.packet({'kind':'fixture_ready','iteration':0,'sim_time_ns':0})
 s.authorize()
 for i in range(1,101):s.packet({'kind':'fixture_sample','iteration':i,'sim_time_ns':i*1000000})
 s.packet({'kind':'final_wait','iteration':100,'sim_time_ns':100000000});return w,s,sent
def main():
 w,s,sent=prepared();need(sent==[b'GO\n'],'GO only before mapping');w.send_ack();need(sent==[b'GO\n',b'EXIT_ACK\n'],'distinct tokens');s.finalize(True,True,0,True,True,True);cases.append({'case':'positive_GO_final_mapping_ACK_EOF_exit','status':'PASS_SYNTHETIC'})
 reject('duplicate_ACK',w.send_ack)
 for name,snapshot in [('missing_mapping',{'status':'FAIL','start':'s1','pid':77}),('wrong_PID',{'status':'PASS_FILE_IDENTITY','start':'s1','pid':78}),('PID_reused',{'status':'PASS_FILE_IDENTITY','start':'s2','pid':77})]:
  w,_,sent=prepared(snapshot);reject(name,w.send_ack);need(sent==[b'GO\n'],'ACK leaked')
 w,s,_=prepared();reject('ACK_missing_or_timeout',lambda:s.finalize(True,True,0,True,True,True))
 w,s,_=prepared();w.observe=lambda:(_ for _ in ()).throw(ProcessLookupError('child exited before snapshot'));reject('early_child_exit',w.send_ack)
 w,s,_=prepared();w.observe=lambda:(_ for _ in ()).throw(TimeoutError('mapping deadline exceeded'));reject('ACK_timeout',w.send_ack)
 w,s,_=prepared();w.send_ack();reject('101st_sample_after_ACK',lambda:s.packet({'kind':'fixture_sample','iteration':101,'sim_time_ns':101000000}))
 reject('EOF_missing_after_ACK',lambda:s.finalize(False,True,0,True,True,True));reject('exit_nonzero_after_ACK',lambda:s.finalize(True,True,70,True,True,True))
 p=plan.read_plan('actual')
 with patch.object(supervisor.smoke,'properties',side_effect=AssertionError('manager query')),patch.object(supervisor,'exclusive',side_effect=AssertionError('actual marker')):reject('actual_profile_blocked_before_manager_marker_service',lambda:supervisor.run('actual'))
 h=plan.read_plan('harmless');plan.ready(h);need(all('libdart' not in d and 'libgz-' not in d for d in h['mounts']),'fixture exposes subject')
 need(all(not os.path.lexists(B/r) for r in p['outputs']+p['one_shot']),'actual runtime path exists')
 dump(B/'reports/tests.json',{'status':'PASS_STATIC_MOCK_ONLY','cases':cases});print('PASS',len(cases),'ACK/EOF/identity/prelaunch mock cases')
if __name__=='__main__':main()
