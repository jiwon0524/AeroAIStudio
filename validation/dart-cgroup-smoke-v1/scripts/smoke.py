"""One approved sleep5 transient service, with readback and owned-unit cleanup only."""
import datetime,hashlib,json,os,subprocess,time,uuid
from pathlib import Path
B=Path(__file__).resolve().parents[1];ROOT=B.parents[1];R=B/'reports';W=B/'work';CG=Path('/sys/fs/cgroup')
BASE_HEAD='ce1eb75d785680090ca6930d2390bd491e10b704'
KEYS=('cgroup.controllers','cgroup.subtree_control','memory.max','memory.swap.max','pids.max','cpu.max')
PROPS=('Id','LoadState','ActiveState','SubState','Transient','InvocationID','ControlGroup','MainPID','MemoryMax','MemorySwapMax','TasksMax','CPUQuotaPerSecUSec','CPUQuotaPeriodUSec','RuntimeMaxUSec','TimeoutStopUSec','KillMode','Result','ExecMainCode','ExecMainStatus')
def put(name,x):(R/name).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def cmd(argv,timeout=8):
 p=subprocess.run(argv,capture_output=True,text=True,timeout=timeout);return {'rc':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
def properties(unit=None,manager=False):
 args=['/usr/bin/systemctl','--user','show']+([unit] if unit else [])
 keys=('SystemState','ControlGroup') if manager else PROPS
 r=cmd(args+['--property='+k for k in keys]);r['values']=dict(line.split('=',1) for line in r['stdout'].splitlines() if '=' in line);return r
def read(p):
 try:return p.read_text().strip()
 except FileNotFoundError:return None

def identity(pid):
 try:
  s=Path(f'/proc/{pid}/stat').read_text().split(') ',1)[1].split()
  return {'pid':pid,'start':s[19],'state':s[0],'executable':os.readlink(f'/proc/{pid}/exe'),'cgroup':read(Path(f'/proc/{pid}/cgroup'))}
 except (OSError,IndexError):return None

def snapshot(manager):
 root=CG/manager.lstrip('/');paths={root};p=root
 for base,dirs,_ in os.walk(root):paths.add(Path(base));paths.update(Path(base)/d for d in dirs)
 while p!=CG:
  parent=p.parent;paths.add(parent)
  paths.update(c for c in parent.iterdir() if c.is_dir());p=parent
 return {str(p.relative_to(CG)) or '/':{k:read(p/k) for k in KEYS} for p in sorted(paths) if p.is_dir()}

def differences(before,after,own_relative):
 changes=[]
 for path in sorted(set(before)|set(after)):
  if path==own_relative or path.startswith(own_relative+'/'):continue
  if path not in before or path not in after:
   changes.append({'path':path,'kind':'other_topology_change','expected':False,'before':before.get(path),'after':after.get(path)});continue
  for k in KEYS:
   a,b=before[path][k],after[path][k]
   if a==b:continue
   expected=(k in ('cgroup.controllers','cgroup.subtree_control') and a is not None and b is not None and set(b.split())-set(a.split()) <= {'cpu'} and set(a.split())<=set(b.split())) or (k=='cpu.max' and a is None and b=='max 100000')
   changes.append({'path':path,'field':k,'before':a,'after':b,'expected_systemd_cpu_activation':expected,'expected':expected})
 return changes

def main():
 if not W.is_dir():raise RuntimeError('work directory must exist')
 marker=W/'attempt.json'
 if marker.exists():raise RuntimeError('one-shot guard: existing attempt; no second service permitted')
 checks=[];life={'creation_attempts':0,'payload':['/usr/bin/sleep','5'],'observations':[]};resources={};diff={}
 def check(name,ok,evidence):
  checks.append({'test_id':name,'status':'PASS' if ok else 'FAIL','evidence':evidence})
  if not ok:raise RuntimeError(name)
 try:
  plan_path=ROOT/'validation/dart-cgroup-readiness-v1/reports/approval_plan.json';plan=json.loads(plan_path.read_text())
  check('plan_scope',plan['creation_argv'][-2:]==['/usr/bin/sleep','5'] and plan['limits']['MemoryMax']=='64M' and plan['limits']['TasksMax']=='8' and plan['limits']['CPUQuota']=='25%','reports/plan_reconciliation.json')
  unit='aero-cgroup-smoke-v1-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:8]+'.service'
  argv=plan['creation_argv'].copy();argv[0]='/usr/bin/systemd-run';argv=[('--unit='+unit) if a.startswith('--unit=') else ('--wait' if a=='--no-block' else a) for a in argv]
  put('plan_reconciliation.json',{'source_sha256':hashlib.sha256(plan_path.read_bytes()).hexdigest(),'approved_payload':life['payload'],'limits':plan['limits'],'changes':['unique unit name required by current approval','absolute systemd-run executable path','--wait replaces --no-block; observer runs CLI asynchronously and captures true unit exit; payload unchanged'],'creation_argv':argv,'extra_workloads':False,'authorization':'current explicit user approval: single transient sleep5/readback/cleanup only'})
  git={'branch':cmd(['git','branch','--show-current'])['stdout'].strip(),'head':cmd(['git','rev-parse','HEAD'])['stdout'].strip(),'status':cmd(['git','status','--porcelain=v1'])['stdout']};mgr=properties(manager=True)
  check('preflight_git_manager',os.getuid()==1000 and git['branch']=='experiment/dart-internal-trace' and git['head']==BASE_HEAD and git['status']=='' and mgr['rc']==0 and mgr['values'].get('SystemState')=='running','reports/preflight.json')
  manager=mgr['values']['ControlGroup'];delegate=cmd(['/usr/bin/systemctl','show','user@1000.service','--property=Delegate','--property=DelegateControllers'])
  check('controller_delegation','Delegate=yes' in delegate['stdout'] and 'DelegateControllers=cpu memory pids' in delegate['stdout'],'reports/preflight.json')
  absent=properties(unit);candidate=CG/manager.lstrip('/')/'app.slice'/unit
  check('unique_unit_absent',absent['values'].get('LoadState')=='not-found' and not candidate.exists(),'reports/preflight.json')
  before=snapshot(manager);(W/'controllers_before.json').write_text(json.dumps(before,indent=2)+'\n')
  put('preflight.json',{'uid':os.getuid(),'git':git,'main':{'head':cmd(['git','-C','/home/jiwon/Projects/AeroAIStudio','rev-parse','HEAD'])['stdout'].strip(),'status':cmd(['git','-C','/home/jiwon/Projects/AeroAIStudio','status','--porcelain=v1'])['stdout']},'manager':mgr,'delegation':delegate,'unit_absence':absent,'controller_paths':len(before)})
  life['unit']=unit;life['started_at']=datetime.datetime.now(datetime.timezone.utc).isoformat();life['creation_attempts']=1
  with marker.open('x') as f:json.dump({'unit':unit,'started_at':life['started_at'],'retry_forbidden':True},f)
  with open(W/'systemd-run.stdout','w') as out,open(W/'systemd-run.stderr','w') as err:
   launcher=subprocess.Popen(argv,stdout=out,stderr=err)
   active=None
   for _ in range(60):
    observed=properties(unit);life['observations'].append(observed)
    if observed['values'].get('ActiveState')=='active' and observed['values'].get('SubState')=='running':active=observed['values'];break
    if launcher.poll() is not None:break
    time.sleep(.03)
   check('unit_running',active is not None and active.get('Transient')=='yes','reports/unit_lifecycle.json')
   rel=active['ControlGroup'];target=CG/rel.lstrip('/');life['control_group']=rel;life['invocation_id']=active['InvocationID']
   check('owned_cgroup_path',rel==manager+'/app.slice/'+unit and target.is_dir(),'reports/unit_lifecycle.json')
   actual={k:read(target/k) for k in ('memory.max','memory.swap.max','pids.max','cpu.max','cgroup.events','cgroup.procs')};pid=int(active['MainPID']);ident=identity(pid)
   resources={'requested':plan['limits'],'systemd_properties':active,'actual_cgroup':actual,'process':ident,'target_path':str(target),'excess_test':False};put('resource_readback.json',resources)
   check('memory_readback',active['MemoryMax']=='67108864' and actual['memory.max']=='67108864' and actual['memory.swap.max']=='0','reports/resource_readback.json')
   check('tasks_readback',active['TasksMax']=='8' and actual['pids.max']=='8','reports/resource_readback.json')
   quota,period=map(int,actual['cpu.max'].split());check('cpu_readback',quota==25000 and period==100000 and active['CPUQuotaPerSecUSec']=='250ms' and active['CPUQuotaPeriodUSec']=='100ms','reports/resource_readback.json')
   check('sleep_membership',ident is not None and ident['executable']=='/usr/bin/sleep' and ident['cgroup']=='0::'+rel and actual['cgroup.procs'].split()==[str(pid)],'reports/resource_readback.json')
   during=snapshot(manager);(W/'controllers_during.json').write_text(json.dumps(during,indent=2)+'\n')
   unexpected=[d for d in differences(before,during,rel.lstrip('/')) if not d['expected']]
   if unexpected:life['unexpected_during_changes']=unexpected # stop further tests; wait natural finite sleep, no parent edits
   for _ in range(60):
    state=properties(unit);life['observations'].append(state)
    if launcher.poll() is not None:break
    time.sleep(.1)
   try:rc=launcher.wait(timeout=5)
   except subprocess.TimeoutExpired:
    now=properties(unit)['values']
    if now.get('InvocationID')==life['invocation_id']:
     life['owned_stop']=cmd(['/usr/bin/systemctl','--user','stop','--',unit],timeout=5)
    rc=launcher.wait(timeout=3)
   life['launcher_returncode']=rc
  life['launcher_stdout']=(W/'systemd-run.stdout').read_text();life['launcher_stderr']=(W/'systemd-run.stderr').read_text()
  check('normal_exit',rc==0 and 'Finished with result: success' in life['launcher_stderr'],'reports/unit_lifecycle.json')
  for _ in range(40):
   final=properties(unit);remaining=identity(pid)
   if final['values'].get('LoadState')=='not-found' and not target.exists() and (remaining is None or remaining['start']!=ident['start']):break
   time.sleep(.05)
  life['final_state']=final;life['cgroup_removed']=not target.exists();life['remaining_identity']=remaining if remaining and remaining['start']==ident['start'] else None
  check('cleanup',final['values'].get('LoadState')=='not-found' and life['cgroup_removed'] and life['remaining_identity'] is None,'reports/unit_lifecycle.json')
  after=snapshot(manager);(W/'controllers_after.json').write_text(json.dumps(after,indent=2)+'\n')
  diff={'before_to_during':differences(before,during,rel.lstrip('/')),'before_to_after':differences(before,after,rel.lstrip('/')),'path_counts':{'before':len(before),'during':len(during),'after':len(after)},'snapshot_evidence':{n:{'path':'work/controllers_'+n+'.json','sha256':hashlib.sha256((W/('controllers_'+n+'.json')).read_bytes()).hexdigest()} for n in ('before','during','after')},'manual_controller_writes':False,'automatic_restore_attempted':False}
  put('controller_diff.json',diff);check('controller_change_review',not unexpected and all(d['expected'] for d in diff['before_to_after']),'reports/controller_diff.json')
  life['completed_at']=datetime.datetime.now(datetime.timezone.utc).isoformat()
 except Exception as e:
  life['error']=str(e)
  # No retries or global recovery. Only finite authorized service may need cleanup.
  if life.get('unit') and life['creation_attempts']:
   if 'launcher' in locals():
    try:life['launcher_returncode_on_error']=launcher.wait(timeout=12)
    except subprocess.TimeoutExpired:
     now=properties(life['unit'])['values']
     if life.get('invocation_id') and now.get('InvocationID')==life['invocation_id']:
      life['owned_stop_on_error']=cmd(['/usr/bin/systemctl','--user','stop','--',life['unit']],timeout=5)
      life['launcher_returncode_on_error']=launcher.wait(timeout=3)
   life['error_state']=properties(life['unit'])
   if 'target' in locals():life['cgroup_removed_on_error']=not target.exists()
   if 'ident' in locals() and ident:
    remaining=identity(ident['pid']);life['remaining_identity_on_error']=remaining if remaining and remaining['start']==ident['start'] else None
   for stream in ('stdout','stderr'):
    path=W/('systemd-run.'+stream)
    if path.exists():life['launcher_'+stream]=path.read_text()
   if 'before' in locals() and 'manager' in locals():
    after=snapshot(manager);(W/'controllers_after.json').write_text(json.dumps(after,indent=2)+'\n')
    diff={'before_to_after':differences(before,after,life.get('control_group','/NO_OWN_PATH').lstrip('/')),'complete_comparison':False,'manual_controller_writes':False}
    put('controller_diff.json',diff)
  if not resources:put('resource_readback.json',{'status':'SKIP','reason':str(e)})
  if not diff:put('controller_diff.json',{'status':'SKIP','reason':'complete snapshot comparison unavailable; see lifecycle error','manual_controller_writes':False})
 finally:
  put('unit_lifecycle.json',life);put('smoke_checks.json',{'tests':checks,'PASS':sum(c['status']=='PASS' for c in checks),'FAIL':sum(c['status']=='FAIL' for c in checks),'SKIP':0,'actual_DART_Gazebo_execution':False,'resource_excess_tests':'NOT_RUN'})
 print(json.dumps({'unit':life.get('unit'),'creation_attempts':life['creation_attempts'],'error':life.get('error'),'checks':[(c['test_id'],c['status']) for c in checks]}));return bool(life.get('error'))
if __name__=='__main__':
 import sys
 if sys.argv[1:]!=['--execute-approved-smoke']:raise SystemExit('explicit approved smoke flag required')
 raise SystemExit(main())
