"""Generate/validate ordered FD-only joint sandbox plan. No sandbox invocation."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import *
import os,re,subprocess,collections
BUILD=ROOT/'validation/gazebo-joint-harness-fix-v1/reports/final_manifest.json'
SCHEMAS=ROOT/'validation/gazebo-minimal-physics-v1/reports/resource_candidates.json'
def describe(path,expected=None):
 path=Path(path).resolve(strict=True);fd=os.open(path,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
 try:row=identity.describe_fd(fd)
 finally:os.close(fd)
 if expected:
  need(row['sha256']==expected['sha256'],'ELF SHA changed '+str(path))
  need(row['build_id'] in expected['build_id'],'Build ID changed '+str(path))
 return dict(row,real_path=str(path))
def create():
 m=json.loads(BUILD.read_text());need(sha(m['executable'])=='bd7ce6480b15debab915a69cd9e9a429b92c066063cd31882666617c0a0b3d5a','harness SHA')
 receipt=json.loads((ROOT/'validation/gazebo-joint-codegen-fix-v1/work/config-01/manifests/staged.json').read_text());need(len(receipt)==13,'receipt count')
 for f,r in receipt.items():need(sha(f)==sha(r['source'])==r['sha256'],'receipt pair '+f)
 elfs={p:dict(describe(p,r),needed=r['needed'],soname=r['soname'],runpath=r['runpath'],rpath=r['rpath']) for p,r in m['ELFs'].items()}
 for p in [B/'work/fd_bridge']:
  row=describe(p);text=subprocess.check_output(['/usr/bin/readelf','-dW',str(p)],text=True)
  needed=re.findall(r'\(NEEDED\).*?\[(.*?)\]',text);need(needed==['libc.so.6'],'launcher dependency changed')
  elfs[str(p.resolve())]=dict(row,needed=[],soname=[],runpath=[],rpath=[],launcher_only=True)
 mounts={}
 def mount(dest,source,kind):
  need(Path(dest).is_absolute() and '..' not in Path(dest).parts,'unsafe destination')
  source=str(Path(source).resolve(strict=True));row=elfs.get(source)
  if row is None:row={'real_path':source,'sha256':sha(source),'device':os.stat(source).st_dev,'inode':os.stat(source).st_ino}
  entry=dict(row,source=source,kind=kind)
  if dest in mounts:need(mounts[dest]['source']==source and mounts[dest]['inode']==entry['inode'],'conflicting alias '+dest)
  mounts[dest]=entry
 for p in elfs:mount(p,p,'ELF_canonical')
 # Preserve actual host alias identity; never conflate identical copied DSOs.
 edges=[]
 for p,r in m['ELFs'].items():
  search=[Path(x.replace('$ORIGIN',str(Path(p).parent))) for value in r['runpath'] for x in value.split(':')]
  search += [Path(m['compiled_stack_prefix'])/'lib',ROOT/'validation/gazebo-joint-closure-v1/work/deps/usr/lib/x86_64-linux-gnu',Path('/usr/lib/x86_64-linux-gnu'),Path('/lib/x86_64-linux-gnu'),Path('/usr/lib')]
  for edge in r['needed']:
   alias=next((d/edge['soname'] for d in search if (d/edge['soname']).is_file()),None)
   need(alias is not None and str(alias.resolve())==edge['path'],'changed static edge '+p+' '+edge['soname'])
   dest=str(alias)
   if dest.startswith('/lib/'):dest='/usr/lib/'+dest[len('/lib/'):]
   mount(dest,edge['path'],'SONAME_alias');edges.append({'consumer':p,'soname':edge['soname'],'mount':dest,'provider':edge['path']})
  for soname in r['soname']:
   alias=Path(p).parent/soname
   if alias.exists():need(alias.resolve()==Path(p),'canonical alias changed');mount(str(alias),p,'SONAME_alias')
 for row in json.loads(SCHEMAS.read_text())['schema_files']:
  need(sha(row['path'])==row['sha256'],'schema hash changed');mount(row['path'],row['path'],'SDF_schema_candidate')
 need(sha(m['world']['path'])==m['world']['sha256'],'world changed');mount(m['world']['path'],m['world']['path'],'world_review')
 allow=B/'inputs/joint-elf.sha256';allow.write_text(''.join(r['sha256']+' '+p+'\n' for p,r in sorted(elfs.items()) if not r.get('launcher_only')))
 mount('/input/joint-elf.sha256',allow,'anchor_allowlist')
 stack=Path(m['compiled_stack_prefix']);ode=next(p for p in elfs if p.endswith('/libdart-collision-ode.so.6.13.2'))
 native_external=next(p for p in elfs if p.endswith('/libdart-external-odelcpsolver.so.6.13.2'))
 ode_external=next(p for p in elfs if p.endswith('/libode.so.8.0.2'))
 required=[native_external,ode_external,m['executable'],m['plugins']['physics_system'],m['plugins']['dartsim_engine'],str(stack/'lib/libdart.so.6.13.2'),str(stack/'lib/libaero-joint-probe.so.1.0'),ode]
 need(all(p in elfs for p in required),'required mapping missing')
 plan={'status':'STATIC_PLAN_COMPLETE_RUNTIME_BLOCKED','build_manifest_sha256':sha(BUILD),'candidate_elfs':elfs,'mounts':mounts,'edges':edges,'required_canonical_mappings':required,'engine_provider':m['plugins']['dartsim_engine'],'ode_provider':ode,'payload':[str(B/'work/fd_bridge'),m['executable'],m['plugins']['physics_system'],m['plugins']['dartsim_engine']],'resources':limits,'host_tools':{str(Path(x).resolve()):sha(Path(x).resolve()) for x in ['/usr/bin/bwrap','/usr/bin/systemd-run','/usr/bin/systemctl','/usr/bin/python3']},'outputs':['reports/runtime','reports/runtime_integrity.json'],'one_shot':['work/runtime_collection_attempt.json','work/runtime_attempt.json'],'blockers':['DYNAMIC_RESOURCE_CLOSURE_UNVERIFIED: schema candidates are pinned, but sdformat/config/plugin runtime lookup coverage is not certified','LIVE_SUPERVISOR_INTEGRATION_UNVERIFIED: no allowed native/service fixture execution in this scope','FINAL_MAPPING_HANDSHAKE_UNVERIFIED: current harness may exit before final live mapping snapshot; fail rather than waive' ],'risk_acceptance':'UNDECIDED','stage_b':'BLOCKED','dynamic_coverage':'CANDIDATES_ONLY'}
 validate(plan);return plan

def validate(plan):
 mounts=plan['mounts'];elfs=plan['candidate_elfs']
 need(sha(BUILD)==plan['build_manifest_sha256'],'build manifest changed')
 for path,digest in plan['host_tools'].items():need(sha(path)==digest,'host tool changed '+path)
 for dest,row in mounts.items():
  need(row['source']==row['real_path'] and sha(row['source'])==row['sha256'],'mount SHA/path mismatch '+dest)
  st=os.stat(row['source']);need((st.st_dev,st.st_ino)==(row['device'],row['inode']),'mount inode changed '+dest)
  need(not dest.startswith(('/home/','/usr/local/')) and not dest.endswith('/libgz-physics-dartsim-plugin.so'),'forbidden destination')
  if dest.startswith('/usr/') and re.match(r'lib(?:dart|gz-(?:sim8|physics7))',Path(dest).name):raise ValueError('installed subject mount '+dest)
 for p in plan['required_canonical_mappings']:need(p in mounts and p in elfs and not elfs[p].get('launcher_only'),'missing required mapping')
 for edge in plan['edges']:
  row=mounts.get(edge['mount']);need(row is not None and row['source']==edge['provider'],'wrong/missing alias')
  need(row['inode']==elfs[edge['provider']]['inode'],'alias inode mismatch')
 need(any(x['kind']=='SDF_schema_candidate' for x in mounts.values()),'dynamic schema inputs missing')
 need('/input/joint-elf.sha256' in mounts,'anchor allowlist missing')
 return True

def argv(plan,fd_by_source):
 validate(plan)
 # Same namespace/root/dev model as the existing stage. Runtime FD limits are
 # applied by fd_bridge after bwrap consumes mount FDs (more than 256 inputs).
 a=['/usr/bin/bwrap','--unshare-all','--die-with-parent','--new-session','--cap-drop','ALL','--size','67108864','--tmpfs','/','--dir','/usr/lib64','--symlink','usr/lib','/lib','--symlink','usr/lib64','/lib64','--symlink','../lib/x86_64-linux-gnu/ld-linux-x86-64.so.2','/usr/lib64/ld-linux-x86-64.so.2','--proc','/proc','--dev','/dev','--size','1048576','--tmpfs','/dev/shm','--remount-ro','/dev']
 parents=set()
 for dest in plan['mounts']:
  for parent in Path(dest).parents:
   if str(parent) not in ('/','.'):parents.add(str(parent))
 for parent in sorted(parents,key=lambda s:(len(Path(s).parts),s)):a+=['--dir',parent]
 for dest,row in sorted(plan['mounts'].items()):a+=['--ro-bind-fd',str(fd_by_source[row['source']]),dest]
 a+=['--dir','/cwd','--size','16777216','--tmpfs','/scratch','--size','16777216','--tmpfs','/run','--remount-ro','/','--chdir','/cwd','--clearenv','--setenv','LC_ALL','C','--setenv','TMPDIR','/scratch','--setenv','HOME','/scratch','--setenv','AERO_JOINT_ELF_ALLOWLIST','/input/joint-elf.sha256','--setenv','SDF_PATH','/usr/share/sdformat14/1.10','--']+plan['payload']
 return a

def runtime_ready(plan,risk):
 validate(plan);need(not plan['blockers'] and plan['dynamic_coverage']=='COMPLETE','runtime technical blocker before marker/service')
 decision=Path(risk)
 need(decision==B/'reports/approved_execution.json' and decision.is_file() and not decision.is_symlink(),'explicit approval record missing')
 record=json.loads(decision.read_text())
 need(record.get('configuration_sha256')==plan['build_manifest_sha256'] and record.get('scope')=='ONE_JOINT_INSTRUMENTED_RUN_100x1ms','approval scope/configuration mismatch')
 need(record.get('risk_acceptance')=='EXPLICITLY_RECORDED' and all(record.get('risks',{}).get(k)=='ACCEPTED' for k in ('Bullet_lifetime','individual_destructors','allocator_balance','exception_cleanup')),'risk acceptance missing')

def read_plan():
 path=B/'reports/plan.json';need(sha(path)==(B/'reports/plan.sha256').read_text().strip(),'plan pin changed')
 pin=B/'reports/source_pin.json';need(sha(pin)==(B/'inputs/source_pin.sha256').read_text().strip(),'source pin changed')
 for name,digest in json.loads(pin.read_text())['files'].items():need(sha(ROOT/name)==digest,'implementation changed '+name)
 return json.loads(path.read_text())
if __name__=='__main__':
 plan=create();dump(B/'reports/plan.json',plan);sources=sorted({r['source'] for r in plan['mounts'].values()});dump(B/'reports/ordered_argv.json',{'argv':argv(plan,dict(zip(sources,range(10,10+len(sources))))),'symbolic_FDs':dict(zip(range(10,10+len(sources)),sources))});(B/'reports/plan.sha256').write_text(sha(B/'reports/plan.json')+'\n');print('PASS FD plan',len(plan['mounts']),'mounts;',len(sources),'source FDs; runtime BLOCKED')
