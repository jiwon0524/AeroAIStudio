"""Separate actual/harmless pinned profiles. Actual remains pre-service blocked."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import *
import os,re,subprocess,copy
old=load('previous_plan_builder','validation/gazebo-joint-isolation-v1/scripts/plan.py')
def row(path):
 path=Path(path).resolve();fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
 try:r=identity.describe_fd(fd)
 finally:os.close(fd)
 text=subprocess.check_output(['/usr/bin/readelf','-dW',str(path)],text=True)
 return dict(r,real_path=str(path),soname=re.findall(r'\(SONAME\).*?\[(.*?)\]',text),needed=[],runpath=re.findall(r'\(RUNPATH\).*?\[(.*?)\]',text),rpath=[])
def binding(r,kind='ELF_canonical'):return dict(r,source=r['real_path'],kind=kind)
def write_plan(profile,p):
 validate(p);dump(B/'reports'/(profile+'_plan.json'),p);sources=sorted({r['source'] for r in p['mounts'].values()});dump(B/'reports'/(profile+'_argv.json'),{'argv':argv(p,dict(zip(sources,range(10,10+len(sources))))),'symbolic_FDs':dict(zip(range(10,10+len(sources)),sources))})
def prepare():
 prior=ROOT/'validation/gazebo-joint-isolation-v1/reports/plan.json';p=json.loads(prior.read_text());m=json.loads((ROOT/'validation/gazebo-joint-harness-fix-v1/reports/final_manifest.json').read_text());oldexe=m['executable'];newexe=str(B/'work/aero-joint-harness-ack')
 p['profile']='actual';p['base_plan_sha256']=sha(prior);p['candidate_elfs'].pop(oldexe);r=row(newexe);p['candidate_elfs'][newexe]=r
 p['mounts']={d:v for d,v in p['mounts'].items() if v['source']!=oldexe};p['mounts'][newexe]=binding(r)
 p['required_canonical_mappings']=[newexe if x==oldexe else x for x in p['required_canonical_mappings']];p['payload'][1]=newexe
 # Keep dependency edges from the same pinned link; only executable identity changes.
 for e in p['edges']:
  if e['consumer']==oldexe:e['consumer']=newexe
 allow=B/'inputs/joint-elf.sha256';allow.write_text(''.join(r['sha256']+' '+path+'\n' for path,r in sorted(p['candidate_elfs'].items()) if not r.get('launcher_only')))
 st=allow.stat();p['mounts']['/input/joint-elf.sha256']={'source':str(allow),'real_path':str(allow),'sha256':sha(allow),'device':st.st_dev,'inode':st.st_ino,'kind':'anchor_allowlist'}
 config=B/'inputs/server.config';st=config.stat();p['mounts']['/input/server.config']={'source':str(config),'real_path':str(config),'sha256':sha(config),'device':st.st_dev,'inode':st.st_ino,'kind':'server_config'}
 p['dynamic_coverage']='STATIC_LOOKUP_PINNED_RUNTIME_ACCESS_UNVERIFIED';p['blockers']=['DYNAMIC_RESOURCE_CLOSURE_UNVERIFIED: sdformat/Fuel runtime accesses and silent fallback are not fully attested','HARMLESS_END_TO_END_PENDING'];p['ack_protocol']={'GO':'GO\n','EXIT_ACK':'EXIT_ACK\n','timeout_ms':5000,'native_waits_before_Server_destructor':True}
 p['outputs']=['reports/actual_runtime','reports/actual_runtime_integrity.json'];p['one_shot']=['work/actual_collection_attempt.json','work/actual_attempt.json'];write_plan('actual',p)
 # Harmless profile exposes no subject/GZ library, plugin, schema or original evidence.
 paths=[B/'work/harmless',ROOT/'validation/gazebo-joint-isolation-v1/work/fd_bridge',Path('/usr/lib/x86_64-linux-gnu/libc.so.6'),Path('/usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2')]
 elfs={str(path.resolve()):row(path) for path in paths};mounts={path:binding(r) for path,r in elfs.items()}
 for path,r in elfs.items():
  for soname in r['soname']:mounts[str(Path(path).parent/soname)]=binding(r,'SONAME_alias')
 for name in ['unused-a','unused-b']:
  f=B/'inputs'/name;f.write_text('harmless profile; no plugin\n');st=f.stat();mounts['/input/'+name]={'source':str(f),'real_path':str(f),'sha256':sha(f),'device':st.st_dev,'inode':st.st_ino,'kind':'fixture_argument'}
 h={'profile':'harmless','status':'AUTHORIZED_HARMLESS_ONCE_ONLY','candidate_elfs':elfs,'mounts':mounts,'required_canonical_mappings':[str((B/'work/harmless').resolve()),str(Path('/usr/lib/x86_64-linux-gnu/libc.so.6').resolve()),str(Path('/usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2').resolve())],'payload':[str(paths[1]),str(paths[0]),'/input/unused-a','/input/unused-b'],'resources':limits,'blockers':[],'outputs':['reports/harmless_runtime','reports/harmless_integrity.json'],'one_shot':['work/harmless_collection_attempt.json','work/harmless_attempt.json'],'host_tools':p['host_tools'],'ack_protocol':p['ack_protocol'],'subject_load_allowed':False}
 write_plan('harmless',h)
def validate(p):
 need(p['profile'] in ('actual','harmless'),'profile')
 for path,h in p['host_tools'].items():need(sha(path)==h and os.access(path,os.X_OK),'host tool changed/not executable')
 for dest,r in p['mounts'].items():
  need(Path(dest).is_absolute() and '..' not in Path(dest).parts,'unsafe destination');need(r['source']==r['real_path'] and sha(r['source'])==r['sha256'],'backing SHA')
  st=os.stat(r['source']);need((st.st_dev,st.st_ino)==(r['device'],r['inode']),'backing inode')
  need(not dest.startswith(('/home/','/usr/local/')) and not dest.endswith('/libgz-physics-dartsim-plugin.so'),'forbidden destination')
  if p['profile']=='harmless':need(not re.search(r'lib(?:dart|gz-)',Path(dest).name),'subject in harmless profile')
 for path in p['required_canonical_mappings']:need(path in p['mounts'],'required input')
 if p['profile']=='actual':
  for edge in p['edges']:need(p['mounts'][edge['mount']]['source']==edge['provider'],'alias mismatch')
 return True
def argv(p,fds):
 # Reuse exact isolation layout; its validator is stricter for the old schema,
 # so invoke only the shared builder with this phase's validated profile.
 namespace=old.argv.__globals__;previous=namespace['validate'];namespace['validate']=validate
 try:a=old.argv(p,fds)
 finally:namespace['validate']=previous
 if p['profile']=='harmless':
  for name in ('AERO_JOINT_ELF_ALLOWLIST','SDF_PATH'):
   at=a.index(name)-1;del a[at:at+3]
 else:
  a[a.index('--dir'):a.index('--dir')]=['--dir','/input/resources']
  at=a.index('--')
  a[at:at]=['--setenv','GZ_SIM_SERVER_CONFIG_PATH','/input/server.config','--setenv','GZ_SIM_RESOURCE_PATH','/input/resources','--setenv','GZ_SIM_SYSTEM_PLUGIN_PATH',str(Path(p['payload'][2]).parent),'--setenv','GZ_SIM_PHYSICS_ENGINE_PATH',str(Path(p['payload'][3]).parent)]
 return a
def read_plan(profile):
 pin=B/'reports/source_pin.json';need(sha(pin)==(B/'inputs/source_pin.sha256').read_text().strip(),'source pin')
 for path,h in json.loads(pin.read_text())['files'].items():need(sha(ROOT/path)==h,'pinned input changed '+path)
 p=json.loads((B/'reports'/(profile+'_plan.json')).read_text());validate(p);return p
def ready(p):
 validate(p)
 if p['profile']=='actual':raise ValueError('actual launcher BLOCKED before marker/service: '+', '.join(p['blockers']))
 need(p['status']=='AUTHORIZED_HARMLESS_ONCE_ONLY' and p.get('subject_load_allowed') is False and not p['blockers'],'harmless scope gate')
 # Enforce the compile receipt, not a promise about an arbitrary executable.
 build=json.loads((B/'reports/build.json').read_text());need(sha(p['payload'][1])==build['ELFs'][p['payload'][1]]['sha256'],'fixture binary')
 need(build['ELFs'][p['payload'][1]]['needed']==['libc.so.6'],'fixture dependencies')
if __name__=='__main__':prepare();print('PASS separate actual/harmless plans; actual BLOCKED')
