"""Pure fixtures. No services, namespaces, markers or native target execution."""
import sys,copy,json,tempfile,os,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from common import *
import plan,supervisor,live
from protocol import Lines,Session
RESULTS=[]
def reject(name,fn):
 try:fn()
 except (ValueError,policy.Rejected,KeyError,OSError) as e:RESULTS.append({'case':name,'status':'PASS_REJECTED','reason':str(e)})
 else:raise AssertionError(name+' was accepted')

def fixture():
 provider={'real_path':'/fixture/engine','sha256':'a'*64,'build_id':'1','device':1,'inode':1};ode=dict(provider,real_path='/fixture/ode',inode=2)
 mappings={r['real_path']:dict(r,path=r['real_path']) for r in [provider,ode]}
 c={'capabilities':dict(live_collector_verified=True,pre_step_zero_verified=True,closure_complete=True),'engine_provider':provider,'detector_candidates':{'ode':ode},'allowed_mappings':mappings,'required_mappings':list(mappings)}
 state=dict.fromkeys(policy.STATE,0.0);state['z']=1.0
 raw={'kind':'ready_state','iteration':0,'sim_time_ns':0,'dt_ns':0,'paused':True,'native_frame':0,'native_time':0,'init_count':1,'state_source':'measured_live_components','state':state}
 engine={'kind':'engine_entry','module':'/fixture/engine','this':'0x1','anchor':'0x20','module_base':'0x10'}
 typed=[{'kind':'typed','label':label,'base':'0x3','this':'0x4'} for label in ['dart/ode/getType','gz/ode/getType']]
 def attest(r,fp):return dict(r,kind='LIVE_READY_PAUSED',steps_observed=0,engine={'source':'active_instance_provider','backend':'DART','provider':provider},detector={'source':'active_world_detector_instance','type':'ode','provider':ode},mappings=list(mappings.values()),pid_identity_stable=True,namespace_cgroup_limits_verified=True)
 sent=[];s=Session(c,attest,sent.append)
 for _ in range(2):
  s.stderr('AERO_WORLD entity=1 world=0x1 solver=0x2 detector=0x3 init=1 iteration=0 sim_time=0 native_frame=0 native_time=0')
  s.packet(engine)
  for t in typed:s.packet(t)
  s.packet(copy.deepcopy(raw))
 return s,sent

def samples(s):
 for i in range(1,101):
  state=dict.fromkeys(policy.STATE,0.0);state.update(z=1-.5*9.81*(i*.001)**2,vz=-9.81*i*.001)
  s.packet({'kind':'sample','iteration':i,'sim_time_ns':i*1000000,'dt_ns':1000000,'paused':False,'native_frame':i,'native_time':i*.001,'init_count':1,'state_source':'measured_live_components','state':state})

def main():
 p=plan.read_plan();plan.validate(p);sources=sorted({r['source'] for r in p['mounts'].values()});argv=plan.argv(p,dict(zip(sources,range(10,10+len(sources)))))
 need(argv.count('--ro-bind-fd')==len(p['mounts']) and '--ro-bind' not in argv and '--bind' not in argv,'FD-only mounts')
 need(argv[-4:]==p['payload'] and argv[0]=='/usr/bin/bwrap','actual ordered payload')
 need(not any(x.get('kind')=='directory' for x in p['mounts'].values()),'directory exposure')
 first=p['edges'][0];bad=copy.deepcopy(p);bad['mounts'][first['mount']]['source']=p['payload'][1];reject('wrong_alias',lambda:plan.validate(bad))
 bad=copy.deepcopy(p);bad['mounts'][first['mount']]['inode']+=1;reject('same_SHA_wrong_inode',lambda:plan.validate(bad))
 bad=copy.deepcopy(p);bad['mounts']={k:v for k,v in bad['mounts'].items() if v['kind']!='SDF_schema_candidate'};reject('dynamic_inputs_missing',lambda:plan.validate(bad))
 # A current execution attempt must fail before even manager query or marker creation.
 with patch.object(supervisor.smoke,'properties',side_effect=AssertionError('manager/service accessed')),patch.object(supervisor,'exclusive',side_effect=AssertionError('marker created')):
  reject('technical_block_before_manager_marker_service',lambda:supervisor.run(str(B/'reports/approved_execution.json')))
 bad=copy.deepcopy(p);bad['blockers']=[];bad['dynamic_coverage']='COMPLETE';reject('risk_decision_missing',lambda:plan.runtime_ready(bad,str(B/'reports/approved_execution.json')))
 att=live.Attestor(p,999999,'mock-start','/mock',(1,1),(1,2))
 with patch.object(live.mapped,'verify',return_value={'status':'PASS_FILE_IDENTITY','start':'mock-start','records':[]}):reject('live_required_mapping_missing',att.mappings)
 s,sent=fixture();s.authorize();need(sent==[b'GO\n'],'one GO');samples(s);need(s.finalize(True,True,0,True,True,True)['status']=='PASS','positive completion')
 RESULTS.append({'case':'positive_GO_100_samples_EOF_exit_cleanup_integrity','status':'PASS_SYNTHETIC_ONLY'})
 s,_=fixture();s.ready[1]['iteration']=1;reject('pre_GO_iteration_change',s.authorize)
 s,_=fixture();s.ready[0]['native_time']=.001;reject('pre_GO_native_time_change',s.authorize)
 s,_=fixture();s.worlds[1]['world']='0x99';reject('pre_GO_world_change',s.authorize)
 s,_=fixture();s.fingerprints[1]=(s.fingerprints[1][0],[]);reject('provider_evidence_missing',s.authorize)
 s,_=fixture();s.contract['allowed_mappings']={};reject('unexpected_mapping',s.authorize)
 s,_=fixture();s.contract['required_mappings'].append('/missing');reject('required_mapping_missing',s.authorize)
 s,_=fixture();s.contract['capabilities']['live_collector_verified']=False;reject('isolation_or_collector_unknown',s.authorize)
 s,_=fixture();s.authorize();reject('duplicate_GO',s.authorize)
 s,_=fixture();s.authorize();samples(s);reject('101st_sample',lambda:s.packet(dict(s.samples[-1],iteration=101)))
 for name,params in [('EOF_missing',(False,True,0,True,True,True)),('exit_failure',(True,True,1,True,True,True)),('cleanup_unknown',(True,True,0,None,True,True)),('integrity_failure',(True,True,0,True,False,True)),('final_mapping_unknown',(True,True,0,True,True,None))]:
  s,_=fixture();s.authorize();samples(s);reject(name,lambda:s.finalize(*params))
 s,_=fixture();s.authorize();reject('sample_missing',lambda:s.finalize(True,True,0,True,True,True))
 s,_=fixture();s.authorize();samples(s);s.samples[-1]['state']['z']=0;reject('freefall_failure',lambda:s.finalize(True,True,0,True,True,True))
 l=Lines(20,10);l.feed(b'123456789\n');l.feed(b'123456789\n');reject('cumulative_output_overflow',lambda:l.feed(b'x'))
 l=Lines(100,10);reject('pending_buffer_overflow',lambda:l.feed(b'x'*11))
 l=Lines(100,10);l.feed(b'incomplete');reject('EOF_truncated_line',l.finish)
 saved={'Id':'own.service','InvocationID':'abc','ControlGroup':'/own','MainPID':'12'};now=dict(saved,InvocationID='other')
 reject('cleanup_InvocationID_changed',lambda:live.owned_stop(saved,now,[]))
 reject('cleanup_PID_start_changed',lambda:live.owned_stop(saved,saved,[({'pid':12,'start':'1'},{'pid':12,'start':'2'})]))
 need(not live.cleanup_ok({'LoadState':'not-found'},False,[{'pid':1}],[]),'remaining process accepted')
 with tempfile.TemporaryDirectory(prefix='joint-policy-fixture-',dir='/tmp') as folder:
  x=Path(folder)/'dangling';x.symlink_to('missing');reject('dangling_output_collision',lambda:supervisor.absent([x]))
  reject('dangling_parent_collision',lambda:supervisor.absent([x/'out']))
  parent=Path(folder)/'real';parent.mkdir();link=Path(folder)/'alias';link.symlink_to(parent);reject('symlink_output_ancestor',lambda:supervisor.absent([link/'out']))
 need(not any(os.path.lexists(B/r) for r in p['outputs']+p['one_shot']),'runtime output/marker created')
 dump(B/'reports/tests.json',{'status':'PASS_STATIC_MOCK_ONLY','cases':RESULTS,'service_starts':0,'subject_loads':0,'harness_runs':0,'runtime_markers_created':0});print('PASS',len(RESULTS),'synthetic positive/negative cases; no runtime marker or subject execution')
if __name__=='__main__':main()
