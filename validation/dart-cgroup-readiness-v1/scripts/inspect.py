"""Read-only cgroup/systemd evidence collector. Never starts/stops/sets units."""
import datetime,json,os,shutil,subprocess,time,xml.etree.ElementTree as ET
from pathlib import Path
B=Path(__file__).resolve().parents[1];R=B/'reports';CG=Path('/sys/fs/cgroup')
PROPS=('Id','LoadState','ActiveState','SubState','ControlGroup','Delegate','DelegateControllers','DelegateSubgroup','DisableControllers','CPUAccounting','MemoryAccounting','TasksAccounting','CPUQuotaPerSecUSec','EffectiveCPUs','EffectiveMemoryNodes')
def command(args):
 t=time.monotonic()
 try:
  r=subprocess.run(args,capture_output=True,text=True,timeout=8);return {'rc':r.returncode,'stdout':r.stdout,'stderr':r.stderr,'seconds':round(time.monotonic()-t,3)}
 except (OSError,subprocess.TimeoutExpired) as e:return {'rc':None,'error':str(e)}
def read(p):
 try:return {'value':p.read_text().strip(),'owner_uid':p.stat().st_uid,'mode':oct(p.stat().st_mode&0o777),'writable_access':os.access(p,os.W_OK)}
 except OSError as e:return {'error':str(e),'exists':p.exists()}
def group(path):
 data={'path':str(path),'directory_writable':os.access(path,os.W_OK),'files':{}}
 for name in ('cgroup.controllers','cgroup.subtree_control','cgroup.type','cgroup.events','memory.max','memory.swap.max','pids.max','cpu.max'):
  data['files'][name]=read(path/name)
 p=path/'cgroup.procs'
 try:
  values=p.read_text().split();data['files']['cgroup.procs']={'count':len(values),'contains_inspector':str(os.getpid()) in values,'writable_access':os.access(p,os.W_OK),'owner_uid':p.stat().st_uid}
 except OSError as e:data['files']['cgroup.procs']={'error':str(e)}
 return data
raw=Path('/proc/self/cgroup').read_text().strip();rel=next(s.split('::',1)[1] for s in raw.splitlines() if s.startswith('0::'))
current=CG/rel.lstrip('/');ancestors=[];p=current
while True:
 ancestors.append(group(p))
 if p==CG:break
 if CG not in p.parents:raise RuntimeError('unsafe cgroup path')
 p=p.parent
shows={}
for user,unit in ((True,None),(True,'app.slice'),(True,'init.scope'),(False,'user@1000.service'),(False,'user-1000.slice')):
 args=['/usr/bin/systemctl']+(['--user'] if user else [])+['show']+([unit] if unit else [])
 properties=PROPS if unit else ('Version','SystemState','ControlGroup','DefaultCPUAccounting','DefaultMemoryAccounting','DefaultTasksAccounting','DefaultTasksMax')
 args += [f'--property={v}' for v in properties]
 shows[('user:' if user else 'system:')+(unit or 'manager')]=command(args)
x={'observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'uid':os.getuid(),'scope':'approved same-user host read-only, no cgroup/unit writes','tools':{n:shutil.which(n) for n in ('systemd-run','systemctl','busctl','bwrap')},'systemd_version':command(['/usr/bin/systemd-run','--version']),'mount':command(['/usr/bin/findmnt','-n','-o','TARGET,FSTYPE,OPTIONS',str(CG)]),'current_cgroup':str(current),'ancestors_leaf_to_root':ancestors,'systemd_show':shows,'transient_API_support':{},'static_user_service':read(Path('/usr/lib/systemd/system/user@.service')),'creation_attempted':False,'resource_excess_tests_run':False,'permissions_note':'access(W_OK) is a current permission observation, not proof mkdir/write/controller activation or StartTransientUnit authorization succeeds'}
api=command(['/usr/bin/busctl','--user','--xml-interface','introspect','org.freedesktop.systemd1','/org/freedesktop/systemd1','org.freedesktop.systemd1.Manager'])
try:
 method=ET.fromstring(api.get('stdout','')).find(".//method[@name='StartTransientUnit']")
 x['transient_API_support']={'rc':api['rc'],'method_found':method is not None,'args':[a.attrib for a in method.findall('arg')] if method is not None else [],'semantics':'introspection only; no StartTransientUnit call, no authorization test'}
except ET.ParseError as e:x['transient_API_support']={'rc':api['rc'],'error':str(e),'stderr':api.get('stderr','')}
(R/'cgroup_capabilities.json').write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'current':str(current),'ancestor_controllers':[(a['path'],a['files']['cgroup.controllers'].get('value'),a['files']['cgroup.subtree_control'].get('value')) for a in ancestors],'show':shows,'transient_API':x['transient_API_support']},ensure_ascii=False))
