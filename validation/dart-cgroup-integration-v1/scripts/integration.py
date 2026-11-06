"""Exactly two authorized finite units; no retry, pressure or native-library load."""
import datetime,importlib.util,json,os,select,socket,subprocess,sys,tempfile,time,uuid
from pathlib import Path
B=Path(__file__).resolve().parents[1];ROOT=B.parents[1];R=B/'reports';W=B/'work'
spec=importlib.util.spec_from_file_location('smoke',ROOT/'validation/dart-cgroup-smoke-v1/scripts/smoke.py');smoke=importlib.util.module_from_spec(spec);spec.loader.exec_module(smoke)

def put(name,value):(R/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def require(ok,label):
    if not ok:raise RuntimeError(label)
def bwrap(cfg,target):
    return ['/usr/bin/prlimit','--cpu=2:2','--as=268435456:268435456','--fsize=65536:65536','--nofile=64:64','--core=0:0','--','/usr/bin/bwrap','--unshare-all','--die-with-parent','--new-session','--size','16777216','--tmpfs','/','--ro-bind','/usr','/usr','--symlink','usr/bin','/bin','--symlink','usr/lib','/lib','--symlink','usr/lib64','/lib64','--proc','/proc','--dev','/dev','--size','1048576','--tmpfs','/dev/shm','--remount-ro','/dev','--ro-bind',str(ROOT),'/project','--ro-bind',str(B/'tests'),'/fixture','--ro-bind',str(target),'/limits','--size','4194304','--tmpfs','/tmp','--size','4194304','--tmpfs','/run','--remount-ro','/','--chdir','/run','--clearenv','--setenv','PATH','/usr/bin:/bin','--setenv','LC_ALL','C','/usr/bin/python3','-I','-B','/fixture/fixture.py','0',json.dumps(cfg)]
def argv(unit,payload):
    props={'MemoryMax':'64M','MemorySwapMax':'0','TasksMax':'8','CPUQuota':'25%','CPUQuotaPeriodSec':'100ms','RuntimeMaxSec':'8s','TimeoutStopSec':'2s','KillMode':'control-group','OOMPolicy':'stop','Delegate':'no','Slice':'app.slice'}
    return ['/usr/bin/systemd-run','--user','--wait','--collect','--pipe','--unit='+unit]+['--property='+k+'='+v for k,v in props.items()]+payload

def run_case(sandbox,manager,cfg):
    label='bubblewrap' if sandbox else 'inheritance';unit='aero-cgroup-integration-v1-'+label+'-'+uuid.uuid4().hex[:10]+'.service'
    target=smoke.CG/manager.lstrip('/')/'app.slice'/unit;rel='/'+str(target.relative_to(smoke.CG))
    require(smoke.properties(unit)['values'].get('LoadState')=='not-found' and not target.exists(),'unit collision')
    cfg=dict(cfg,sandbox=sandbox,cgroup=rel)
    payload=bwrap(cfg,target) if sandbox else ['/usr/bin/python3','-I','-B',str(B/'tests/fixture.py'),'0',json.dumps(cfg)]
    command=argv(unit,payload);out=W/(label+'.stdout');err=W/(label+'.stderr');before=smoke.snapshot(manager)
    row={'test_id':label,'unit':unit,'cgroup':rel,'command':command,'status':'FAIL','body_entered':False};p=None
    with (W/(label+'_attempt.json')).open('x') as f:json.dump({'unit':unit,'retry_forbidden':True},f)
    try:
        with out.open('w') as o,err.open('w') as e:
            p=subprocess.Popen(command,stdout=o,stderr=e)
            deadline=time.monotonic()+6;records=[];observations=[];active=None
            while time.monotonic()<deadline:
                state=smoke.properties(unit)['values']
                if state.get('ActiveState')=='active':active=state
                try:records=[json.loads(line) for line in out.read_text().splitlines() if line.startswith('{')]
                except json.JSONDecodeError:records=[]
                if len(records)==3 and target.exists():
                    procs=smoke.read(target/'cgroup.procs').split();observations=[smoke.identity(int(pid)) for pid in procs];break
                if p.poll() is not None:break
                time.sleep(.04)
            row.update(records=records,host_processes=observations,properties=active,body_entered=bool(records))
            require(active is not None,'unit never active')
            require(active['ControlGroup']==rel,'unexpected unit cgroup')
            values={k:smoke.read(target/k) for k in ('memory.max','memory.swap.max','pids.max','cpu.max','cgroup.procs','cgroup.threads','memory.current','memory.peak','pids.current','memory.events')};row['readback']=values
            require(all(values[k]==v for k,v in (('memory.max','67108864'),('memory.swap.max','0'),('pids.max','8'),('cpu.max','25000 100000'))),'limit mismatch')
            require(len(records)==3 and [r['role'] for r in records]==['parent','child','grandchild'],'three roles missing')
            require(records[1]['ppid']==records[0]['pid'] and records[2]['ppid']==records[1]['pid'],'ancestry mismatch')
            require(all(v and v['cgroup']=='0::'+rel for v in observations),'cgroup inheritance mismatch')
            python_processes=[v for v in observations if v and Path(v['executable']).name.startswith('python3')]
            require(len(python_processes)==3,'host three-python mapping missing')
            # NSpid maps sandbox IDs to exact host IDs without trusting namespace PID equality.
            for v in observations:
                v['nspid']=next((line.split(':',1)[1].split() for line in Path('/proc',str(v['pid']),'status').read_text().splitlines() if line.startswith('NSpid:')),[])
            require({int(v['nspid'][-1]) for v in python_processes}=={r['pid'] for r in records},'namespace PID map mismatch')
            during=smoke.snapshot(manager);row['during_diff']=smoke.differences(before,during,rel.lstrip('/'))
            require(all(d['expected'] for d in row['during_diff']),'unexpected controller changes')
            row['returncode']=p.wait(timeout=8)
            require(row['returncode']==0,'nonzero unit exit')
        row['status']='PASS'
    except Exception as e:row['error']=str(e)
    finally:
        if p and p.poll() is None:
            try:p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                state=smoke.properties(unit)['values']
                if active and state.get('InvocationID')==active.get('InvocationID'):row['owned_stop']=smoke.cmd(['/usr/bin/systemctl','--user','stop','--',unit],timeout=5)
                p.wait(timeout=3)
        for _ in range(40):
            final=smoke.properties(unit)['values']
            if final.get('LoadState')=='not-found' and not target.exists():break
            time.sleep(.05)
        remaining=[v for v in row.get('host_processes',[]) if v and (now:=smoke.identity(v['pid'])) and now['start']==v['start']]
        row['cleanup']={'unit_state':final,'cgroup_removed':not target.exists(),'remaining_identities':remaining}
        row['cleanup']['status']='PASS' if final.get('LoadState')=='not-found' and not target.exists() and not remaining else 'FAIL'
        row['after_diff']=smoke.differences(before,smoke.snapshot(manager),rel.lstrip('/'))
        row['stdout']=out.read_text() if out.exists() else '';row['stderr']=err.read_text() if err.exists() else ''
        if row['cleanup']['status']!='PASS' or row['after_diff']:row['status']='FAIL'
        put(label+'.json',row)
    return row

def main():
    global R,W
    require(sys.argv[1:] in (['--execute-approved-integration'],['--execute-approved-revalidation']),'explicit approval flag required')
    if sys.argv[1:]==['--execute-approved-revalidation']:
        require((B/'work/campaign_attempt.json').exists(),'initial attempt missing')
        R=B/'reports/revalidation';W=B/'work/revalidation'
        R.mkdir(exist_ok=True);W.mkdir(exist_ok=True)
    require(not (W/'campaign_attempt.json').exists(),'one-shot campaign guard')
    require(smoke.cmd(['git','rev-parse','HEAD'])['stdout'].strip()=='b60d9f9c991579ac4694d108e10e8166f942392e','unexpected HEAD')
    require(smoke.cmd(['git','branch','--show-current'])['stdout'].strip()=='experiment/dart-internal-trace','unexpected branch')
    manager_state=smoke.properties(manager=True);require(manager_state['rc']==0 and manager_state['values'].get('SystemState')=='running','user manager unavailable')
    manager=manager_state['values']['ControlGroup'];before=smoke.snapshot(manager)
    estimate=smoke.cmd(['/usr/bin/python3','-I','-B','-c','import json,resource,socket,subprocess,pathlib; print(int(next(s.split()[1] for s in pathlib.Path("/proc/self/status").read_text().splitlines() if s.startswith("VmHWM:")))*1024*3+8388608)'])
    estimated=int(estimate['stdout']);require(estimate['rc']==0 and estimated<67108864,'64MiB unsafe estimate; no limit raise')
    put('preflight.json',{'manager':manager_state,'estimated_tree_bytes':estimated,'estimate_is_not_peak_guarantee':True,'baseline_controllers':before})
    with (W/'campaign_attempt.json').open('x') as f:json.dump({'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'no_retry':True},f)
    results=[]
    with tempfile.TemporaryDirectory(prefix='aero-cgroup-integration-') as d:
        hostdir=Path(d);canary=hostdir/'canary';canary.write_text('owned host canary')
        project_canary= B/'work/project_canary';project_canary.write_text('owned readonly canary')
        with socket.socket(socket.AF_INET6) as ip6,socket.socket(socket.AF_UNIX) as unix,socket.socket(socket.AF_UNIX) as abstract:
            absname='aero-cgroup-'+uuid.uuid4().hex;unixpath=str(hostdir/'host.sock')
            ip6.bind(('::1',0));ip6.listen();unix.bind(unixpath);unix.listen();abstract.bind('\0'+absname);abstract.listen()
            positive=[]
            for srv,addr,family in ((ip6,ip6.getsockname(),socket.AF_INET6),(unix,unixpath,socket.AF_UNIX),(abstract,'\0'+absname,socket.AF_UNIX)):
                with socket.socket(family) as c:c.connect(addr);conn,_=srv.accept();conn.close();positive.append(True)
            cfg={'host_ns':{k:os.readlink('/proc/self/ns/'+k) for k in ('user','mnt','pid','net')},'host_canary':str(canary),'unix_path':unixpath,'abstract':absname,'port6':ip6.getsockname()[1],'project_canary_name':str(project_canary.relative_to(ROOT))}
            for sandbox in (False,True):
                result=run_case(sandbox,manager,cfg);results.append(result)
                if result['status']!='PASS':break
            exposed=bool(select.select([ip6,unix,abstract],[],[],0)[0])
            put('socket_controls.json',{'host_positive_controls':positive,'sandbox_connection_received':exposed})
        project_canary.unlink()
    after=smoke.snapshot(manager)
    put('controller_diff.json',{'before_to_after':smoke.differences(before,after,'NO_OWN_PATH'),'cases':{r['test_id']:{'during':r.get('during_diff',[]),'after':r.get('after_diff',[])} for r in results},'manager_before':manager_state,'manager_after':smoke.properties(manager=True),'manual_controller_writes':False})
    put('process_cleanup.json',{'cases':{r['test_id']:r['cleanup'] for r in results},'host_temp_removed':not hostdir.exists(),'project_canary_removed':not project_canary.exists(),'pressure_or_SIGKILL_injection':False})
    put('resource_readback.json',{'cases':{r['test_id']:r.get('readback') for r in results},'limits':{'MemoryMax':'64M','TasksMax':8,'CPUQuota':'25%'},'excess_enforcement':'NOT_TESTED'})
    put('cgroup_inheritance.json',results[0] if results else {'status':'SKIP'})
    put('bubblewrap_integration.json',results[1] if len(results)>1 else {'status':'SKIP','reason':'prior case failed'})
    put('isolation_checks.json',{'bubblewrap_status':results[1]['status'] if len(results)>1 else 'SKIP','details':results[1].get('records',[]) if len(results)>1 else [],'host_socket_delivery':exposed})
    ok=len(results)==2 and all(r['status']=='PASS' for r in results) and not exposed and not smoke.differences(before,after,'NO_OWN_PATH')
    put('runtime_summary.json',{'status':'PASS' if ok else 'FAIL','cases_attempted':len(results),'cases_passed':sum(r['status']=='PASS' for r in results),'actual_DART_Gazebo':'NOT_RUN'})
    return 0 if ok else 1
if __name__=='__main__':raise SystemExit(main())
