from common import *
prior=load('previous_live_attestation','validation/gazebo-joint-isolation-v1/scripts/live.py')
smoke=prior.smoke;service_argv=prior.service_argv;owned_stop=prior.owned_stop;cleanup_ok=prior.cleanup_ok
class FixtureAttestor(prior.Attestor):
 def __init__(self,p,pid,start,cgroup,go_stat,obs_stat):
  self.plan=p;self.pid=pid;self.start=start;self.cgroup=cgroup;self.go_stat=go_stat;self.obs_stat=obs_stat
  self.c={'allowed_mappings':{d:dict(prior.fingerprint(r),path=d) for d,r in p['mounts'].items() if r['source'] in p['candidate_elfs']}}
  self.ready_evidence=[];self.last_mapping=None;self.last_isolation=None
 def initial(self):
  self.isolation();m=self.mappings();self.ready_evidence.append({'isolation':self.last_isolation,'mapping':m,'scope':'harmless only; no DART/physics attestation'});return m
class ActualAttestor(prior.Attestor):pass
