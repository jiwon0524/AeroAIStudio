"""Pinned candidate ELF closure and concrete FD mount plan; never load a target."""
from pathlib import Path
import os,sys,json,hashlib,subprocess,re,importlib.util
B=Path(__file__).resolve().parents[1];ROOT=B.parents[1]
sys.path.insert(0,str(ROOT/'validation/dart-probe-a-harness-v1/scripts'))
from identity import describe_fd,open_checked
spec=importlib.util.spec_from_file_location('core_aliases',ROOT/'validation/dart-subject-notification-v1/scripts/readiness_fixed.py')
aliases=importlib.util.module_from_spec(spec);spec.loader.exec_module(aliases)
sys.path.insert(0,str(ROOT/'validation/dart-skeleton-lifetime-v2/scripts'))
spec=importlib.util.spec_from_file_location('elf_plan_check',ROOT/'validation/dart-skeleton-lifetime-v2/scripts/resolution.py')
check=importlib.util.module_from_spec(spec);spec.loader.exec_module(check)
sys.path.insert(0,str(B/'scripts'))
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def entry(path,sandbox=None):
 p=Path(path).resolve(strict=True);fd=os.open(p,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
 try:ident=describe_fd(fd)
 finally:os.close(fd)
 out=subprocess.check_output(['/usr/bin/readelf','-dW',str(p)],text=True)
 row={'real_path':str(p),'sandbox_path':sandbox or str(p),'required':True,**ident}
 for tag,key in [('NEEDED','needed'),('SONAME','soname'),('RPATH','rpath'),('RUNPATH','runpath')]:row[key]=re.findall(r'\('+tag+r'\).*?\[(.*?)\]',out)
 return row

def plan(m):
 base=m['profiles']['harmless_fixture_only'];core=m['profiles']['installed_core_future_only']
 cf=list(range(100,100+len(core)));bf=[5000+i for i in range(len(base))]
 cmd=check.layout.bwrap(base,bf,6000,6001,[])
 # Explicit candidate Gazebo limits; no skeleton-limit inheritance.
 for before,after in [('--cpu=2:2','--cpu=10:10'),('--as=268435456:268435456','--as=2147483648:2147483648'),('--fsize=65536:65536','--fsize=1048576:1048576'),('--nofile=64:64','--nofile=256:256')]:cmd[cmd.index(before)]=after
 # Capacity is a proposal, not measured sufficiency.
 for i in range(len(cmd)-2):
  if cmd[i:i+2]==['--size','16777216']:cmd[i+1]='67108864'
  if cmd[i:i+2]==['--size','4194304']:cmd[i+1]='16777216'
 i=cmd.index('--ro-bind-fd');cmd[i:i]=aliases.mount_arguments(core,cf)
 i=cmd.index('--harness');cmd[i:]=['--owned-gazebo-gated-once','/fixture/minimal.sdf']
 i=cmd.index('--ro-bind-fd');cmd[i:i]=['--ro-bind-fd','6002','/fixture/minimal.sdf']
 return cmd,dict(zip(cf+bf,core+base))

def validate_plan(m,cmd,fd_entries):
 # World is separately pinned non-ELF, never an arbitrary bind exception.
 i=cmd.index('/fixture/minimal.sdf')
 if cmd[i-2:i]!=['--ro-bind-fd','6002']:raise ValueError('world FD mount mismatch')
 if cmd.count('--ro-bind-fd')!=len([x for x in range(len(cmd)) if cmd[x]=='--ro-bind-fd']):raise ValueError('mount token mismatch')
 cleaned=cmd[:i-2]+cmd[i+1:]
 if cleaned[-3:]!=['/fixture/native_fixture','--owned-gazebo-gated-once','/fixture/minimal.sdf']:raise ValueError('payload mismatch')
 result=check.check_command(m,cleaned,fd_entries)
 if digest(B/'fixtures/minimal.sdf')!=m['world_sha256']:raise ValueError('world changed')
 return result

def prepare():
 target=B/'reports/elf_manifest.json'
 if target.exists() or (B/'work/manifest.sha256').exists():raise ValueError('no repin')
 native=B/'work/gazebo_gate_server';observer=B/'work/libaero_gate_observer.so'
 seeds=[observer,Path('/usr/lib/x86_64-linux-gnu/libgz-sim8-physics-system.so.8.15.0'),Path('/usr/lib/x86_64-linux-gnu/gz-physics-7/engine-plugins/libgz-physics7-dartsim-plugin.so.7.8.0')]
 exe=entry(native,'/fixture/native_fixture');queue=seeds[:];rows={};unresolved=[]
 for n in exe['needed']:queue.append(Path('/usr/lib/x86_64-linux-gnu')/n)
 while queue:
  p=queue.pop(0).resolve(strict=True)
  if str(p) in rows:continue
  if p==observer.resolve():sandbox='/fixture/libaero_gate_observer.so'
  else:
   if not str(p).startswith('/usr/lib/'):raise ValueError('non-installed dependency '+str(p))
   sandbox=str(p)
  row=entry(p,sandbox);rows[str(p)]=row
  for n in row['needed']:
   if '/' in n:raise ValueError('unsafe NEEDED')
   found=next((d/n for d in [Path('/usr/lib/x86_64-linux-gnu'),Path('/usr/lib')] if (d/n).exists()),None)
   if found:queue.append(found)
   else:unresolved.append({'consumer':str(p),'needed':n})
 m={'profiles':{'installed_core_future_only':list(rows.values()),'harmless_fixture_only':[exe]},'world_sha256':digest(B/'fixtures/minimal.sdf'),'unresolved_needed':unresolved,'closure_complete':False,'dynamic_resource_and_dlopen_coverage':'UNVERIFIED'}
 m['required_paths']={k:[x['real_path'] for x in v] for k,v in m['profiles'].items()}
 prior=json.loads((ROOT/'validation/dart-subject-notification-v1/reports/manifest.json').read_text())['profiles']['installed_core_future_only']
 for e in prior:
  if e['real_path'] not in rows or rows[e['real_path']]['sha256']!=e['sha256']:raise ValueError('installed Core16 changed/missing')
 target.write_text(json.dumps(m,indent=2)+'\n');(B/'work/manifest.sha256').write_text(digest(target)+'\n')
 cmd,fds=plan(m);result=validate_plan(m,cmd,fds);result['candidate_argv_symbolic_FDs']=cmd
 result['scope']='ELF-only FD plan; dynamic resources/init/real service integration NOT_VERIFIED'
 (B/'reports/mount_plan.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({'ELF_rows':len(rows)+1,'edges':len(result['edges']),'mounts':len(result['mounts']),'unresolved_needed':unresolved,'complete_runtime_closure':False}))

def preflight_static():
 raw=(B/'reports/elf_manifest.json').read_bytes()
 if hashlib.sha256(raw).hexdigest()!=(B/'work/manifest.sha256').read_text().strip():raise ValueError('manifest pin')
 m=json.loads(raw);fds=[]
 try:
  for profile in m['profiles'].values():
   for row in profile:
    if not row['real_path'].startswith('/usr/lib/') and row['real_path'] not in [str(B/'work/gazebo_gate_server'),str(B/'work/libaero_gate_observer.so')]:raise ValueError('local compare/trace or unapproved path')
    fds.append(open_checked(row))
  cmd,entries=plan(m);return validate_plan(m,cmd,entries)
 finally:
  for fd in fds:os.close(fd)
if __name__=='__main__':prepare()
