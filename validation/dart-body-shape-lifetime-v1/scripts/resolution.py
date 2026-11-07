"""Static readelf + exact bwrap argv preflight. Never executes a target ELF."""
import importlib.util,os,re,subprocess
from pathlib import Path
from common import ROOT,readiness,validate
from identity import open_checked
spec=importlib.util.spec_from_file_location('sandbox_layout',ROOT/'validation/dart-probe-a-harness-v1/scripts/stage.py')
layout=importlib.util.module_from_spec(spec);spec.loader.exec_module(layout)
LIB='/usr/lib/x86_64-linux-gnu/'

def build_command(m,corefds,basefds,canary,limits,args):
 core=m['profiles']['installed_core_future_only'];base=m['profiles']['harmless_fixture_only']
 cmd=layout.bwrap(base,basefds,canary,limits,args)
 pos=cmd.index('--ro-bind-fd');cmd[pos:pos]=readiness.mount_arguments(core,corefds)
 pos=cmd.index('--harness');cmd[pos:]=['--owned-body-shape-once']
 return cmd

def elf(entry):
 fd=open_checked(entry)
 try:
  out=subprocess.check_output(['/usr/bin/readelf','-dW','/proc/self/fd/'+str(fd)],pass_fds=(fd,),text=True,env={'LC_ALL':'C','PATH':'/usr/bin:/bin'})
 finally:os.close(fd)
 tags={tag:re.findall(r'\('+tag+r'\).*?\[(.*?)\]',out) for tag in ('NEEDED','SONAME','RPATH','RUNPATH')}
 if tags['RPATH'] or tags['RUNPATH']:raise ValueError('search path disallowed '+entry['real_path'])
 if tags['NEEDED']!=entry['needed'] or tags['SONAME']!=entry['soname']:raise ValueError('ELF dynamic metadata mismatch '+entry['real_path'])
 return tags

def identity(e):return tuple(e[k] for k in ('real_path','sha256','build_id','device','inode'))

def check_command(m,cmd,fd_entries):
 # Inspect the ordered ro-bind-fd plan actually used by stage, not only an abstract graph.
 core=m['profiles']['installed_core_future_only'];base=m['profiles']['harmless_fixture_only']
 entries={e['real_path']:e for e in core+base};providers={};dynamic={};mounts={}
 for e in entries.values():
  tags=elf(e);dynamic[e['real_path']]=tags
  for name in tags['SONAME']:
   if '/' in name or not name or name in providers:raise ValueError('ambiguous/unsafe SONAME '+name)
   providers[name]=e
 for i,token in enumerate(cmd):
  if token!='--ro-bind-fd':continue
  number=int(cmd[i+1]);target=cmd[i+2]
  if target in ('/input/canary','/limits'):continue
  if number not in fd_entries:raise ValueError('unknown FD target '+target)
  actual=fd_entries[number]
  if actual['real_path'] not in entries or identity(actual)!=identity(entries[actual['real_path']]):raise ValueError('unapproved mount target '+target)
  if target in mounts and identity(mounts[target])!=identity(actual):raise ValueError('conflicting mount '+target)
  mounts[target]=actual
 edges=[]
 for e in entries.values():
  # Canonical aliases are also used by post-open identity. Reject wrong approved targets.
  if e['sandbox_path'] not in mounts or identity(mounts[e['sandbox_path']])!=identity(e):raise ValueError('missing/wrong canonical '+e['sandbox_path'])
  for name in dynamic[e['real_path']]['NEEDED']:
   if '/' in name or name not in providers:raise ValueError('unknown NEEDED '+name)
   target=LIB+name
   if target not in mounts:raise ValueError('missing alias '+name)
   provider=providers[name]
   if identity(mounts[target])!=identity(provider):raise ValueError('wrong alias target '+name)
   edges.append({'consumer':e['real_path'],'needed':name,'sandbox_path':target,'provider':provider['real_path'],'sha256':provider['sha256']})
 # This sterile layout contains no cache, LD_LIBRARY_PATH or RUNPATH. /lib -> usr/lib;
 # /lib64 -> usr/lib64 -> ../lib/x86_64-linux-gnu resolves the pinned interpreter.
 fixture=base[0];fd=open_checked(fixture)
 try:ph=subprocess.check_output(['/usr/bin/readelf','-lW','/proc/self/fd/'+str(fd)],pass_fds=(fd,),text=True,env={'LC_ALL':'C','PATH':'/usr/bin:/bin'})
 finally:os.close(fd)
 if '[Requesting program interpreter: /lib64/ld-linux-x86-64.so.2]' not in ph:raise ValueError('unexpected interpreter')
 for link,target in (('usr/lib','/lib'),('usr/lib64','/lib64'),('../lib/x86_64-linux-gnu/ld-linux-x86-64.so.2','/usr/lib64/ld-linux-x86-64.so.2')):
  if not any(cmd[i:i+3]==['--symlink',link,target] for i in range(len(cmd))):raise ValueError('interpreter/layout symlink missing')
 if LIB+'ld-linux-x86-64.so.2' not in mounts:raise ValueError('interpreter missing')
 return {'status':'PASS_STATIC_RESOLUTION','edges':edges,'mounts':{p:{'real_path':e['real_path'],'sha256':e['sha256']} for p,e in mounts.items()},'limitation':'static default x86-64 search-dir/layout contract, not runtime loader execution or symbol-version certification'}

def plan(m):
 core=m['profiles']['installed_core_future_only'];base=m['profiles']['harmless_fixture_only']
 cf=list(range(100,100+len(core)));bf=list(range(200,200+len(base)))
 return build_command(m,cf,bf,300,301,[]),dict(zip(cf+bf,core+base))

def preflight(m):
 # Independent file validation and actual-argv generation happen before collection marker.
 fds=[]
 try:
  for profile in m['profiles']:fds+=validate(m,profile)
  cmd,entries=plan(m);return check_command(m,cmd,entries)
 finally:
  for fd in fds:os.close(fd)
