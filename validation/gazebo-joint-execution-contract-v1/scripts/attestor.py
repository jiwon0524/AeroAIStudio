"""Live-only attestation and owned cleanup. Never called by static preparation."""
from common import *
import os,re
smoke=load('joint_smoke','validation/dart-cgroup-smoke-v1/scripts/smoke.py')
def _integration_argv(unit,payload):
    props={'MemoryMax':'64M','MemorySwapMax':'0','TasksMax':'8','CPUQuota':'25%','CPUQuotaPeriodSec':'100ms','RuntimeMaxSec':'8s','TimeoutStopSec':'2s','KillMode':'control-group','OOMPolicy':'stop','Delegate':'no','Slice':'app.slice'}
    return ['/usr/bin/systemd-run','--user','--wait','--collect','--pipe','--unit='+unit]+['--property='+k+'='+v for k,v in props.items()]+payload
ID_KEYS=('real_path','sha256','build_id','device','inode')
def fingerprint(row):return {k:row[k] for k in ID_KEYS}
def contract(plan):
 return plan['attestation']
# These capability flags are evaluated only after runtime_ready and live checks.
def service_argv(unit,payload):
 a=_integration_argv(unit,payload)
 a=[t for t in a if not t.startswith('--property=')]
 return a[:1]+['--property='+k+'='+v for k,v in limits.items()]+['--property=UnsetEnvironment=LD_PRELOAD LD_AUDIT LD_LIBRARY_PATH PYTHONPATH PYTHONHOME']+a[1:]

def owned_stop(saved,current,identities_now):
 need(bool(saved.get('InvocationID')) and bool(saved.get('Id')),'missing saved ownership')
 need(all(current.get(k)==saved[k] for k in ('Id','InvocationID','ControlGroup','MainPID')),'unit ownership changed')
 need(all(saved_id and now and saved_id['pid']==now['pid'] and saved_id['start']==now['start'] for saved_id,now in identities_now),'PID/start ownership changed')
 return ['/usr/bin/systemctl','--user','stop','--',saved['Id']]

def cleanup_ok(unit_state,cgroup_exists,remaining,controller_diff):
 return unit_state.get('LoadState')=='not-found' and not cgroup_exists and not remaining and not controller_diff

class Attestor:
 def __init__(self,plan,pid,start,cgroup,go_stat,obs_stat):
  self.plan=plan;self.pid=pid;self.start=start;self.cgroup=cgroup;self.go_stat=go_stat;self.obs_stat=obs_stat;self.c=contract(plan);self.last_mapping=None;self.ready_evidence=[];self.last_isolation=None
 def mappings(self):
  entries=[dict(row,sandbox_path=dest,required=False) for dest,row in self.c['allowed_mappings'].items()]
  result=mapped.verify(self.pid,entries);need(result['status']=='PASS_FILE_IDENTITY' and result['start']==self.start,'mapping/PID verification failed: '+result.get('error','unknown'))
  observed={(r['device'],r['inode']) for r in result['records']}
  for p in self.plan['required_canonical_mappings']:
   row=self.plan['elfs'][p];need((row['device'],row['inode']) in observed,'required mapping missing '+p)
  self.last_mapping=result;return result
 def isolation(self):
  pid=self.pid;ident=smoke.identity(pid);need(ident and ident['start']==self.start and ident['cgroup']=='0::'+self.cgroup,'cgroup/PID membership')
  for kind in ('mnt','net','user','pid'):
   need(os.readlink('/proc/'+str(pid)+'/ns/'+kind)!=os.readlink('/proc/self/ns/'+kind),'namespace not isolated '+kind)
  target=smoke.CG/self.cgroup.lstrip('/')
  for k,v in readback.items():need(smoke.read(target/k)==v,'live resource mismatch '+k)
  text=Path('/proc',str(pid),'limits').read_text()
  for label,value in [('Max cpu time','10'),('Max file size','1048576'),('Max core file size','0'),('Max open files','256'),('Max address space','2147483648')]:
   match=re.search('^'+label+r'\s+(\S+)\s+(\S+)',text,re.M);need(match and match.groups()==(value,value),'rlimit mismatch '+label)
  for fd,expected in [(3,self.go_stat),(4,self.obs_stat)]:
   st=os.stat('/proc/'+str(pid)+'/fd/'+str(fd));need((st.st_dev,st.st_ino)==expected,'FIFO identity mismatch')
  mounts={}
  for line in Path('/proc',str(pid),'mountinfo').read_text().splitlines():
   left=line.split(' - ',1)[0].split();dest=left[4].replace('\\040',' ');mounts[dest]=set(left[5].split(','))
  expected=set(self.plan['mounts'])|{'/','/proc','/dev','/dev/shm','/scratch','/run'}
  need(all(p in expected or p.startswith('/dev/') for p in mounts),'unexpected mount')
  for dest,row in self.plan['mounts'].items():
   need(dest in mounts and 'ro' in mounts[dest],'missing/writable mount '+dest)
   path=Path('/proc',str(pid),'root')/dest.lstrip('/');fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
   try:
    st=os.fstat(fd);need((st.st_dev,st.st_ino)==(row['device'],row['inode']),'mounted inode mismatch '+dest)
   finally:os.close(fd)
  self.last_isolation={'pid':pid,'start':self.start,'cgroup':self.cgroup,'namespaces':{k:os.readlink('/proc/'+str(pid)+'/ns/'+k) for k in ('mnt','net','user','pid')},'cgroup_readback':{k:smoke.read(target/k) for k in readback},'proc_limits':text,'mountinfo_sha256':hashlib.sha256(Path('/proc',str(pid),'mountinfo').read_bytes()).hexdigest(),'mounted_inputs_checked':len(self.plan['mounts']),'FD3_identity':list(self.go_stat),'FD4_identity':list(self.obs_stat)}
  return True
 def provider(self,row):
  # Module names belong to the child's mount namespace, not host realpath.
  if row.get('kind')=='engine_entry':role='dartsim'
  elif row.get('label')=='dart/ode/getType':role='dart_ode'
  elif row.get('label')=='gz/ode/getType':role='dartsim'
  else:raise ValueError('unknown active provider role')
  path=row['module'];need(path in self.plan['provider_paths'][role], 'selected provider logical path mismatch')
  need(path in self.plan['elfs'],'unknown provider')
  entry=self.plan['elfs'][path];address=int(row['anchor'],16);bias=int(row['module_base'],16)
  need(int(row['this'],16)>0 and address>=bias,'provider pointer/bias')
  maps=mapped.parse_maps(Path('/proc',str(self.pid),'maps').read_text())
  need(any(int(x['range'].split('-')[0],16)<=address<int(x['range'].split('-')[1],16) and (x['device'],x['inode'])==(entry['device'],entry['inode']) for x in maps),'anchor outside provider')
  return fingerprint(entry)
 def ready(self,raw,fingerprint_rows):
  self.isolation();observation=self.mappings();engine,typed=fingerprint_rows
  need(self.provider(engine)==self.c['engine_provider'],'engine feature provider mismatch')
  for row in typed:
   expected=self.c['detector_candidates']['ode'] if row['label']=='dart/ode/getType' else self.c['engine_provider']
   need(self.provider(row)==expected,'typed ODE/wrapper provider mismatch')
  self.ready_evidence.append({'raw':raw,'typed':typed,'engine':engine,'mapping':observation,'isolation':self.last_isolation})
  return dict(raw,kind='LIVE_READY_PAUSED',steps_observed=0,engine={'source':'active_instance_provider','backend':'DART','provider':self.c['engine_provider']},detector={'source':'active_world_detector_instance','type':'ode','provider':self.c['detector_candidates']['ode']},mappings=[self.c['allowed_mappings'][r['path']] for r in observation['records']],pid_identity_stable=True,namespace_cgroup_limits_verified=True)
