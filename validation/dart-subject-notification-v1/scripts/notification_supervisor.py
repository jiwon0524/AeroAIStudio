"""Prepared subject-notification one-shot; actual invocation requires separate approval."""
import hashlib,importlib.util,json,os,select,socket,subprocess,sys,tempfile,time,uuid
from pathlib import Path
from common import B,ROOT,R,W,load_manifest,validate,gate,check_prepared
CASE="accept"
def put(n,x):
 target=R/CASE;target.mkdir(exist_ok=True);(target/n).write_text(json.dumps(x,ensure_ascii=False,indent=2)+"\n")
from mapped import verify
from resolution import preflight
spec=importlib.util.spec_from_file_location('integration',ROOT/'validation/dart-cgroup-integration-v1/scripts/integration.py');old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old);s=old.smoke
LIMITS={'MemoryMax':'64M','TasksMax':8,'CPUQuota':'25%'}
CONFIG={'supervisor_ready':True,'mount_namespace':True,'network_namespace':True,'read_only':True,'limits':LIMITS}

def guard(config,manifest,launch):
    if not all(config.get(k) is True for k in ('supervisor_ready','mount_namespace','network_namespace','read_only')):raise ValueError('supervisor/sandbox configuration gate')
    if config.get('limits')!=LIMITS:raise ValueError('resource configuration gate')
    fds=[]
    try:
        fds+=validate(manifest,'installed_core_future_only')
        fds+=validate(manifest,'harmless_fixture_only')
        return launch()
    finally:
        for fd in fds:os.close(fd)


def lifetime_ok(text):
    try:events=[json.loads(line) for line in text.splitlines()]
    except (ValueError,TypeError):return False
    if len(events)!=4 or any(not isinstance(e,dict) for e in events):return False
    if [e.get('phase') for e in events]!=['post_open_ready','registered','notifications_observed','lifetime_success']:return False
    a,r,n,z=events
    def exact(e,k,v):return type(e.get(k)) is int and e[k]==v
    return (a.get('result')=='WAIT' and all(exact(r,k,v) for k,v in [('bodies',1),('shape_nodes',1),('subjects',2),('callbacks_before_release',0)])
      and exact(n,'shape_node_callbacks',1) and exact(n,'body_node_callbacks',1)
      and n.get('order')==['shape_node','body_node'] and n.get('within_owner_reset') is True
      and exact(n,'subjects_remaining',0) and z.get('scope')=='subject_notifications_only'
      and z.get('individual_destructors')=='NOT_OBSERVED' and z.get('allocator_balance')=='NOT_MEASURED')

def prepare_service():
    manager=s.properties(manager=True)
    if manager['rc'] or manager['values'].get('SystemState')!='running':raise ValueError('manager unavailable')
    managerpath=manager['values']['ControlGroup']
    unit='aero-notification-v1-runtime-'+uuid.uuid4().hex[:10]+'.service'
    target=s.CG/managerpath.lstrip('/')/'app.slice'/unit;rel='/'+str(target.relative_to(s.CG))
    if s.properties(unit)['values'].get('LoadState')!='not-found' or target.exists():raise ValueError('unit collision')
    return manager,managerpath,unit,target,rel

def main():
    global CASE
    if len(sys.argv)!=2 or sys.argv[1] not in ('--execute-approved-notification-once',):raise ValueError('explicit fixture case')
    CASE='runtime' if sys.argv[1]=='--execute-approved-notification-once' else sys.argv[1]
    attempt=CASE+'_attempt.json'
    check_prepared()
    if any(os.path.lexists(p) for p in (W/attempt,R/'runtime',W/'canary',W/'stdout',W/'stderr')):raise ValueError('one-shot already executed')
    if s.cmd(['git','branch','--show-current'])['stdout'].strip()!='experiment/dart-internal-trace':raise ValueError('unexpected branch')
    if s.cmd(['git','merge-base','--is-ancestor','9abcbff2cf1ef3f52a2c2d1a348779e87b304841','HEAD'])['rc']:raise ValueError('unexpected ancestry')
    if any(os.environ.get(k) for k in ('LD_PRELOAD','LD_AUDIT','LD_LIBRARY_PATH')):raise ValueError('loader environment')
    return guard(CONFIG,load_manifest(),lambda:run(load_manifest(),attempt))

def run(manifest,attempt):
    preflight(manifest)  # Also protect direct supervisor invocation before marker/service.
    manager,managerpath,unit,target,rel=prepare_service()
    before=s.snapshot(managerpath)
    row={'status':'FAIL','unit':unit,'body_entered':False,'go_sent':False};p=None;active=None;identities=[];mapping={'status':'NOT_RUN'};during=None
    start=time.monotonic()
    with tempfile.TemporaryDirectory(prefix='aero-native-harness-') as d:
        folder=Path(d)
        with socket.socket(socket.AF_INET6) as ip6,socket.socket(socket.AF_UNIX) as ux,socket.socket(socket.AF_UNIX) as abstract:
            unixpath=str(folder/'host.sock');absname='aero-harness-'+uuid.uuid4().hex
            ip6.bind(('::1',0));ip6.listen();ux.bind(unixpath);ux.listen();abstract.bind('\0'+absname);abstract.listen()
            controls=[]
            for server,address,family in ((ip6,ip6.getsockname(),socket.AF_INET6),(ux,unixpath,socket.AF_UNIX),(abstract,'\0'+absname,socket.AF_UNIX)):
                with socket.socket(family) as client:client.connect(address);conn,_=server.accept();conn.close();controls.append(True)
            ns=[os.readlink('/proc/self/ns/'+k) for k in ('mnt','net','user','pid')]
            (W/'canary').write_text('owned harness canary')
            payload=['/usr/bin/python3','-I','-B',str(B/'scripts/stage.py'),'--owned-runtime-stage' if CASE=='runtime' else '--owned-service-stage',rel]+ns+[str(ip6.getsockname()[1]),unixpath,absname]
            command=old.argv(unit,payload);command.insert(1,'--property=UnsetEnvironment=LD_PRELOAD LD_AUDIT LD_LIBRARY_PATH');row['command']=command
            with (W/attempt).open('x') as f:json.dump({'unit':unit,'no_retry':True},f)
            try:
                with (W/'stdout').open('w') as out,(W/'stderr').open('w') as err:
                    p=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=out,stderr=err,text=True)
                    deadline=time.monotonic()+5
                    while time.monotonic()<deadline:
                        state=s.properties(unit)['values']
                        if state.get('ActiveState')=='active':active=state
                        text=(W/'stdout').read_text()
                        if 'post_open_ready' in text:break
                        if p.poll() is not None:break
                        time.sleep(.03)
                    if not active or 'post_open_ready' not in text:raise ValueError('native ready gate not reached')
                    if active['ControlGroup']!=rel:raise ValueError('unexpected cgroup')
                    row['active_properties']=active
                    row['resource_readback']={k:s.read(target/k) for k in ('memory.max','memory.swap.max','pids.max','cpu.max','cgroup.procs','cgroup.threads','memory.current','memory.peak','pids.current','memory.events')}
                    if any(row['resource_readback'][k]!=v for k,v in (('memory.max','67108864'),('memory.swap.max','0'),('pids.max','8'),('cpu.max','25000 100000'))):raise ValueError('live limit gate')
                    identities=[s.identity(int(pid)) for pid in row['resource_readback']['cgroup.procs'].split()]
                    if not identities or any(not x or x['cgroup']!='0::'+rel for x in identities):raise ValueError('cgroup process identity gate')
                    fixture=manifest['profiles']['harmless_fixture_only'][0]
                    candidates=[]
                    for x in identities:
                        st=os.stat('/proc/'+str(x['pid'])+'/exe')
                        if (st.st_dev,st.st_ino)==(fixture['device'],fixture['inode']):candidates.append(x['pid'])
                    if len(candidates)!=1:raise ValueError('one native fixture required')
                    pid=candidates[0]
                    for kind,host in zip(('mnt','net','user','pid'),ns):
                        if os.readlink('/proc/'+str(pid)+'/ns/'+kind)==host:raise ValueError('namespace gate '+kind)
                    mapping=gate(pid,manifest,lambda _:None,require_core=CASE=='runtime',reject_fixture=CASE=='reject');row['fixture_host_pid']=pid
                    put('mapped_library_validation.json',mapping)
                    if mapping['status']!='PASS_FILE_IDENTITY':raise ValueError('mapping identity gate: '+mapping.get('error','unknown'))
                    during=s.snapshot(managerpath);changes=s.differences(before,during,rel.lstrip('/'));row['during_controller_diff']=changes
                    if any(not x['expected'] for x in changes):raise ValueError('unexpected controller mutation')
                    if CASE!='timeout':
                        p.stdin.write('GO\n');p.stdin.flush();p.stdin.close();row['go_sent']=True
                    deadline=time.monotonic()+8
                    row['last_cgroup_sample']=row['resource_readback']
                    while p.poll() is None and time.monotonic()<deadline:
                        if target.exists():
                            sample={k:s.read(target/k) for k in ('memory.current','memory.peak','memory.events','pids.current')}
                            if all(v is not None for v in sample.values()):row['last_cgroup_sample']=sample
                        time.sleep(.01)
                    rc=p.wait(timeout=1);row['returncode']=rc
                    row['stdout']=(W/'stdout').read_text();row['stderr']=(W/'stderr').read_text();row['body_entered']=lifetime_ok(row['stdout'])
                    if rc or not row['body_entered']:raise ValueError('fixture exit/body failure')
                    row['status']='PASS'
            except Exception as e:row['error']=str(e)
            finally:
                if p and p.poll() is None:
                    if p.stdin and not p.stdin.closed:p.stdin.close()
                    try:p.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        state=s.properties(unit)['values']
                        if active and state.get('InvocationID')==active.get('InvocationID'):row['owned_stop']=s.cmd(['/usr/bin/systemctl','--user','stop','--',unit],timeout=5)
                        p.wait(timeout=3)
                for _ in range(40):
                    final=s.properties(unit)['values']
                    if final.get('LoadState')=='not-found' and not target.exists():break
                    time.sleep(.05)
                remaining=[x for x in identities if x and (now:=s.identity(x['pid'])) and now['start']==x['start']]
                cleanup={'unit_state':final,'cgroup_removed':not target.exists(),'remaining_identities':remaining,'status':'PASS' if final.get('LoadState')=='not-found' and not target.exists() and not remaining else 'FAIL'}
                row['returncode']=p.returncode if p else None
                row['host_processes']=identities;row['cleanup']=cleanup;row['elapsed_seconds']=round(time.monotonic()-start,6)
                row['stdout']=(W/'stdout').read_text() if (W/'stdout').exists() else '';row['body_entered']=lifetime_ok(row['stdout']);row['stderr']=(W/'stderr').read_text() if (W/'stderr').exists() else ''
                if cleanup['status']!='PASS':row['status']='FAIL'
                connections=bool(select.select([ip6,ux,abstract],[],[],0)[0]);row['socket_controls']={'positive_controls':controls,'sandbox_host_connections':connections}
                if connections:row['status']='FAIL'
        (W/'canary').unlink();row['canary_removed']=True
    row['host_temp_removed']=not folder.exists()
    after=s.snapshot(managerpath);afterdiff=s.differences(before,after,'NO_OWN_PATH')
    row['after_controller_diff']=afterdiff
    if afterdiff:row['status']='FAIL'
    if CASE in ('reject','timeout'):
        expected=(row.get('returncode')==78 and not row['go_sent'] and not row['body_entered'] and cleanup['status']=='PASS' and not afterdiff)
        if CASE=='reject':expected=expected and mapping['status']=='FAIL'
        else:expected=expected and mapping['status']=='PASS_FILE_IDENTITY' and row['elapsed_seconds']>=3
        row['expected_rejection']=True;row['status']='PASS' if expected else 'FAIL'
    put('controller_diff.json',{'before_to_after':afterdiff,'during':row.get('during_controller_diff'),'manager_before':manager,'manager_after':s.properties(manager=True),'compared_paths':len(before),'manual_writes':False})
    events=[]
    for line in row['stdout'].splitlines():
        try:events.append(json.loads(line))
        except json.JSONDecodeError:pass
    put('runtime_observation.json',{'case':CASE,'Core_load_attempted':CASE=='runtime','object_execution_requested':True,'individual_destructor_calls':'NOT_OBSERVED','allocation_balance':'NOT_MEASURED','lifetime_events':[e for e in events if e.get('phase') in ('registered','notifications_observed','lifetime_success','exception')],'open_results':[e for e in events if e.get('phase')=='open_result'],'close_results':[e for e in events if e.get('phase')=='close_result'],'signal_events':[e for e in events if e.get('phase')=='signal'],'systemd_run_returncode':row.get('returncode'),'last_cgroup_sample':row.get('last_cgroup_sample',row.get('resource_readback')),'final_cgroup_sample_guaranteed':False,'service_timeout_result':'UNKNOWN_UNLESS_EXPLICIT_EVENT_OR_STDERR','raw_evidence':'native_fixture_execution.json','cleanup':cleanup})
    put('native_fixture_execution.json',row)
    put('supervisor_integration.json',{'status':row['status'],'unit':unit,'go_sent':row['go_sent'],'body_entered':row['body_entered'],'only_harmless_profile':CASE!='runtime','DART_load_attempted':CASE=='runtime','read_only_fd_binds':True})
    put('resource_readback.json',{'requested':LIMITS,'observed':row.get('resource_readback'),'excess_enforcement':'NOT_TESTED'})
    put('process_cleanup.json',{'cleanup':row['cleanup'],'host_temp_removed':row['host_temp_removed'],'canary_removed':row['canary_removed'],'intentional_SIGKILL':False})
    if mapping['status']=='NOT_RUN':put('mapped_library_validation.json',mapping)
    return 0 if row['status']=='PASS' else 1
if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as e:
        print('supervisor failed: '+str(e),file=sys.stderr);raise
