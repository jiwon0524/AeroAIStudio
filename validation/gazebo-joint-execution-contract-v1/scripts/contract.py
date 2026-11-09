"""One sealed execution-input contract. Pure read-only validation; no launch."""
from pathlib import Path
import hashlib,json,os,stat,copy
R=Path(__file__).resolve().parents[1];ROOT=R.parents[1]
KEYS=('real_path','sha256','build_id','device','inode')
class Refused(ValueError):pass
def need(ok,why):
 if not ok:raise Refused(why)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def canonical_bytes(m):return (json.dumps(m,sort_keys=True,separators=(',',':'))+'\n').encode()
def digest(m):return hashlib.sha256(canonical_bytes(m)).hexdigest()
def fingerprint(row):return {k:row[k] for k in KEYS}
def check_fd(fd,row):
 a=os.fstat(fd);need(stat.S_ISREG(a.st_mode),'not regular')
 need(type(row['device']) is int and type(row['inode']) is int,'noninteger identity')
 need((a.st_dev,a.st_ino)==(row['device'],row['inode']),'FD device/inode mismatch')
 h=hashlib.sha256();off=0
 while True:
  b=os.pread(fd,1048576,off)
  if not b:break
  h.update(b);off+=len(b)
 z=os.fstat(fd)
 need((a.st_dev,a.st_ino,a.st_size,a.st_mtime_ns,a.st_ctime_ns)==(z.st_dev,z.st_ino,z.st_size,z.st_mtime_ns,z.st_ctime_ns),'FD mutated')
 need(h.hexdigest()==row['sha256'],'FD hash mismatch')
def checked_file(row):
 p=row['source'];need(Path(p).is_absolute() and os.path.realpath(p)==p,'noncanonical backing file')
 fd=os.open(p,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
 try:check_fd(fd,row)
 finally:os.close(fd)
def allowlist(m):
 # Native VerifyAnchor compares the in-namespace dladdr path, never host aliases.
 return ''.join(row['sha256']+' '+dest+'\n' for dest,row in sorted(m['elfs'].items()) if dest!=m['payload'][0])
def attestation(m):
 allowed={p:dict(fingerprint(row),path=p) for p,row in m['elfs'].items() if p!=m['payload'][0]}
 return dict(capabilities=dict(live_collector_verified=True,pre_step_zero_verified=True,closure_complete=True),engine_provider=fingerprint(m['elfs'][m['roles']['dartsim']]),detector_candidates={'ode':fingerprint(m['elfs'][m['roles']['dart_ode']])},allowed_mappings=allowed,required_mappings=m['required_canonical_mappings'])
# The booleans above describe checks used by the existing Gate *after* live
# collection and runtime_ready. Stored preparation evidence never claims live PASS.
def provider_paths(m):
 ode=m['roles']['dart_ode'];source=m['elfs'][ode]['source']
 aliases=sorted({e['mount'] for e in m['soname_edges'] if e['consumer']==m['roles']['dartsim'] and e['soname'].startswith('libdart-collision-ode.so') and e['provider']==source})
 need(len(aliases)==1,'ambiguous/missing active ODE SONAME edge')
 return {'dartsim':[m['roles']['dartsim']],'dart_ode':aliases}
def bwrap(m,fdmap=None):
 sources=sorted({x['source'] for x in m['mounts'].values()})
 fds=dict(zip(sources,range(10,10+len(sources)))) if fdmap is None else fdmap
 need(set(fds)==set(sources),'missing/unexpected FD source')
 need(all(type(x) is int and x>=5 for x in fds.values()) and len(set(fds.values()))==len(fds),'invalid/shared mount FDs')
 a=['/usr/bin/bwrap','--unshare-all','--die-with-parent','--new-session','--cap-drop','ALL','--size','67108864','--tmpfs','/','--dir','/usr/lib64','--symlink','usr/lib','/lib','--symlink','usr/lib64','/lib64','--symlink','../lib/x86_64-linux-gnu/ld-linux-x86-64.so.2','/usr/lib64/ld-linux-x86-64.so.2','--proc','/proc','--dev','/dev','--size','1048576','--tmpfs','/dev/shm','--remount-ro','/dev']
 parents={str(p) for dest in m['mounts'] for p in Path(dest).parents if str(p) not in ('/','.')}
 for p in sorted(parents,key=lambda p:(len(Path(p).parts),p)):a+=['--dir',p]
 for dest,row in sorted(m['mounts'].items()):a+=['--ro-bind-fd',str(fds[row['source']]),dest]
 a+=['--dir','/input/resources','--dir','/cwd','--size','16777216','--tmpfs','/scratch','--size','16777216','--tmpfs','/run','--remount-ro','/','--chdir','/cwd','--clearenv']
 env=[('LC_ALL','C'),('TMPDIR','/scratch'),('HOME','/scratch'),('AERO_JOINT_ELF_ALLOWLIST','/input/joint-elf.sha256'),('SDF_PATH','/usr/share/sdformat14/1.10'),('GZ_SIM_SERVER_CONFIG_PATH','/input/server.config'),('GZ_SIM_RESOURCE_PATH','/input/resources'),('GZ_SIM_SYSTEM_PLUGIN_PATH',str(Path(m['roles']['physics']).parent)),('GZ_SIM_PHYSICS_ENGINE_PATH',str(Path(m['roles']['dartsim']).parent))]
 for k,v in env:a+=['--setenv',k,v]
 return a+['--']+m['payload']
def absent(paths):
 for value in paths:
  p=Path(value);need(not os.path.lexists(p),'existing output/one-shot '+str(p))
  need(all(not parent.is_symlink() for parent in p.parents),'symlink output ancestor')
def validate(m,expected_digest=None,files=True):
 if expected_digest is None:expected_digest=(R/'inputs/manifest.sha256').read_text().strip()
 need(digest(m)==expected_digest,'manifest seal mismatch')
 need(m['schema']==1 and m['profile']=='actual' and m['stage_b']=='BLOCKED' and m['risk_acceptance']=='UNDECIDED','scope')
 need(m['implementation']['attestor']==str(R/'scripts/attestor.py'),'obsolete attestor entrypoint')
 need(m['implementation']['launcher']==str(R/'scripts/launcher.py'),'obsolete launcher entrypoint')
 need(m['implementation']['collector']==str(R/'scripts/collector.py'),'obsolete collector entrypoint')
 need(m['payload'][1]==m['roles']['harness'] and m['payload'][2:]==[m['roles']['physics'],m['roles']['dartsim']],'payload role mixture')
 need(m['ordered_bwrap_argv']==bwrap(m),'ordered argv/FD mounts mismatch')
 need(m['fd_sources']==sorted({r['source'] for r in m['mounts'].values()}),'FD order mismatch')
 for section in ('code','evidence','host_tools'):
  for path,row in m[section].items():need(path==row['source']==row['real_path'],'checker/evidence path mixture')
 for dest,row in m['mounts'].items():
  need(Path(dest).is_absolute() and '..' not in Path(dest).parts and '\n' not in dest and ' ' not in dest,'unsafe mount destination')
  need(row['real_path']==row['source'] and row['mode']=='ro-file-fd','mount backing/mode')
  need(row['source'] not in m['forbidden_backings'],'old changed-component ELF mixed')
 for dest,row in m['elfs'].items():
  need(dest in m['mounts'] and all(row[k]==m['mounts'][dest][k] for k in ('source',*KEYS)),'ELF/mount identity mismatch')
 for role,dest in m['roles'].items():need(dest in m['elfs'],'required role missing '+role)
 need(set(m['roles'].values())<=set(m['required_canonical_mappings']),'missing required role mapping')
 for p in m['required_canonical_mappings']:need(p in m['elfs'],'required mapping not allowed')
 expected_edges={(p,n) for p,row in m['elfs'].items() for n in row['needed']}
 actual_edges=[(e['consumer'],e['soname']) for e in m['soname_edges']]
 need(set(actual_edges)==expected_edges and len(actual_edges)==len(set(actual_edges)),'missing/duplicate SONAME edge')
 for edge in m['soname_edges']:
  need(edge['consumer'] in m['elfs'] and edge['mount'] in m['elfs'],'missing SONAME consumer/alias')
  need(m['mounts'][edge['mount']]['source']==edge['provider'],'SONAME provider mixture')
 need(m['provider_paths']==provider_paths(m),'stale active provider namespace path')
 need(m['attestation']==attestation(m),'stale attestor projection')
 need(m['allowlist_text']==allowlist(m),'stale allowlist projection')
 allow=m['mounts']['/input/joint-elf.sha256']
 need(allow['source']==str(R/'inputs/joint-elf.sha256') and allow['sha256']==hashlib.sha256(m['allowlist_text'].encode()).hexdigest(),'allowlist mount/hash')
 native=m['native']
 for role,name in [('physics','physics'),('dartsim','dartsim')]:
  row=m['elfs'][m['roles'][name]];need(native['expected'][role]==[row['sha256'],row['device'],row['inode']],'stale native plugin identity')
 for name,value in native['expected'].items():
  if name.startswith('schema/') or name.startswith('conversion/'):
   dest='/usr/share/sdformat14/1.11/'+name.split('/',1)[1]
  elif name=='server_config':dest='/input/server.config'
  elif name in ('physics','physics_provider'):dest=m['roles']['physics']
  elif name in ('dartsim','dartsim_provider'):dest=m['roles']['dartsim']
  elif name=='world_bytes':continue
  else:raise Refused('unrecognized native input role')
  row=m['mounts'].get(dest);need(row is not None and value==[row['sha256'],row['device'],row['inode']],'native input/mount mismatch '+name)
 need(set(native['schema_closure'])<=set(native['expected']),'missing native schema closure')
 need(m['ack_protocol']=={'GO':'GO\n','EXIT_ACK':'EXIT_ACK\n','timeout_ms':5000,'native_waits_before_Server_destructor':True},'ACK protocol changed')
 need(m['resources']=={'MemoryMax':'536870912','MemorySwapMax':'0','TasksMax':'64','CPUQuota':'100%','CPUQuotaPeriodSec':'100ms','RuntimeMaxSec':'30s','TimeoutStopSec':'2s','KillMode':'control-group','OOMPolicy':'stop','Delegate':'no','Slice':'app.slice'},'service limits changed')
 need(m['stream_limits']=={'stdout_total':65536,'stdout_pending':16384,'stderr_total':1048576,'stderr_pending':65536},'output limits changed')
 need(m['deadlines']=={'host_s':40,'collection_s':25,'ack_ms':5000},'deadlines changed')
 need(m['rlimits']=={'CPU':10,'AS':2147483648,'FSIZE':1048576,'NOFILE':256,'CORE':0},'native limits changed')
 if files:
  absent(m['outputs']+m['one_shot'])
  seen=set()
  for row in list(m['code'].values())+list(m['evidence'].values())+list(m['host_tools'].values())+list(m['mounts'].values()):
   if row['source'] not in seen:checked_file(row);seen.add(row['source'])
  need(Path(allow['source']).read_text()==m['allowlist_text'],'allowlist contents changed')
  prior=json.loads((ROOT/'validation/gazebo-joint-native-resource-v1/reports/native_contract.json').read_text())
  need(native['schema_closure']==prior['schema_closure'],'schema observation closure changed')
  header=''
  for name in ('physics','dartsim'):
   row=m['elfs'][m['roles'][name]]
   header+='aero_resource::Expect('+','.join([json.dumps(name),json.dumps(m['roles'][name]),str(row['device']),str(row['inode']),json.dumps(row['sha256'])])+');\n'
  need((R/'inputs/plugin_expectations.hh').read_text()==header,'compiled harness expectations do not match manifest')
  template=(R/'inputs/fixture.hh').read_text().split('R"AERO(',1)[1].split(')AERO"',1)[0]
  world=template.replace('@SYSTEM@',m['roles']['physics']).replace('@ENGINE@',m['roles']['dartsim'])
  need(native['expected']['world_bytes']==[hashlib.sha256(world.encode()).hexdigest(),0,0],'world input/native hash mismatch')
  for key,path in m['implementation'].items():need(path in m['code'],'unsealed implementation '+key)
  for key,expected in m['preserved_contracts'].items():need(sha(key)==expected,'predecessor contract changed')
 return True
def read():
 m=json.loads((R/'reports/manifest.json').read_text());validate(m);return m
def runtime_ready(m):
 validate(m)
 need(m['technical']['resource_paths']=='RESOLVED' and not m['blockers'],'technical resource blocker before manager/marker/service')
 # Actual execution approval and risk acceptance are deliberately absent.
 raise Refused('actual execution is not authorized in this scope')
