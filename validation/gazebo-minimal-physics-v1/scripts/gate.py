"""Pure observation-policy model. It does not authenticate or collect live data."""
import math
class Rejected(ValueError):pass
def need(ok,reason):
 if not ok:raise Rejected(reason)
def integer(v):return type(v) is int
STATE=('x','y','z','vx','vy','vz','roll','pitch','yaw')
def state(s):
 need(isinstance(s,dict) and all(k in s and type(s[k]) in (int,float) and math.isfinite(s[k]) for k in STATE),'missing/nonfinite state observation')
 return s
class Gate:
 def __init__(self,contract):self.c=contract;self.sent=False
 def check_ready(self,e):
  need(self.c['capabilities']['live_collector_verified'] is True,'live collector unavailable')
  need(self.c['capabilities']['pre_step_zero_verified'] is True,'zero-step guarantee unavailable')
  need(self.c['capabilities']['closure_complete'] is True,'runtime closure incomplete')
  need(isinstance(e,dict) and e.get('kind')=='LIVE_READY_PAUSED','missing live observation')
  need(integer(e.get('iteration')) and e['iteration']==0,'pre-GO iteration changed')
  need(integer(e.get('sim_time_ns')) and e['sim_time_ns']==0,'pre-GO time changed')
  need(e.get('paused') is True and integer(e.get('steps_observed')) and e['steps_observed']==0,'pre-GO not paused/zero')
  engine=e.get('engine',{});need(isinstance(engine,dict),'missing engine observation')
  need(engine.get('source')=='active_instance_provider' and engine.get('backend')=='DART','backend observation mismatch')
  need(engine.get('provider')==self.c['engine_provider'],'engine provider mismatch')
  detector=e.get('detector',{});need(isinstance(detector,dict),'missing detector observation')
  need(detector.get('source')=='active_world_detector_instance','no active detector observation')
  expected=self.c['detector_candidates'].get(detector.get('type'))
  need(expected is not None and detector.get('provider')==expected,'detector/provider mismatch')
  rows=e.get('mappings');need(isinstance(rows,list),'missing mapped ELF observation')
  seen=set();seen_ids=set()
  for row in rows:
   need(isinstance(row,dict) and row.get('path') in self.c['allowed_mappings'],'unexpected mapping')
   path=row['path'];need(path not in seen,'duplicate mapping');seen.add(path)
   need(row==self.c['allowed_mappings'][path],'mapped ELF identity mismatch')
   seen_ids.add(tuple(row[k] for k in ('real_path','sha256','build_id','device','inode')))
  required_ids={tuple(self.c['allowed_mappings'][p][k] for k in ('real_path','sha256','build_id','device','inode')) for p in self.c['required_mappings']}
  need(required_ids<=seen_ids,'missing required mapping')
  need(e.get('pid_identity_stable') is True and e.get('namespace_cgroup_limits_verified') is True,'missing process/isolation observation')
  need(e.get('state_source')=='measured_live_components','state is not measured')
  s=state(e.get('state'));need(abs(s['z']-1)<=1e-9 and all(abs(s[k])<=1e-9 for k in STATE if k!='z'),'initial state mismatch')
  return True
 def authorize(self,snapshots):
  need(not self.sent,'GO already sent')
  need(isinstance(snapshots,list) and len(snapshots)==2,'need two pre-GO observations')
  for e in snapshots:self.check_ready(e)
  need(snapshots[0]==snapshots[1],'pre-GO observation changed')
  # Does not write stdin or start anything. Caller must supply real attestation.
  self.sent=True;return 'GO\n'
def validate_run(samples):
 need(isinstance(samples,list) and len(samples)==100,'not exactly 100 samples')
 for i,e in enumerate(samples,1):
  need(isinstance(e,dict) and integer(e.get('iteration')) and e['iteration']==i,'step sequence mismatch')
  need(integer(e.get('sim_time_ns')) and e['sim_time_ns']==i*1000000,'simulation time mismatch')
  need(integer(e.get('dt_ns')) and e['dt_ns']==1000000 and e.get('paused') is False,'dt/paused mismatch')
  need(e.get('state_source')=='measured_live_components','missing measured state')
  state(e.get('state'))
 f=samples[-1]['state']
 need(abs(f['z']-0.95095)<=0.002 and f['z']<1,'freefall z mismatch')
 need(abs(f['vz']+0.981)<=0.02 and f['vz']<0,'freefall velocity mismatch')
 need(all(abs(f[k])<=1e-6 for k in ('x','y','vx','vy','roll','pitch','yaw')),'lateral/rotation mismatch')
 return True
