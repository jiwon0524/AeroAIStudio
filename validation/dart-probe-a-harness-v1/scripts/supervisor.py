"""Harmless native one-shot only. Reuses proven systemd/cgroup helpers and properties."""
import hashlib,importlib.util,json,os,select,socket,subprocess,sys,tempfile,time,uuid
from pathlib import Path
from allowlist import B,ROOT,R,W,load_manifest,validate,put
from mapped import verify
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

def main():
    if sys.argv[1:] not in (['--execute-approved-harmless-harness'],['--execute-approved-revalidation']):raise ValueError('explicit harmless harness flag required')
    attempt='revalidation_attempt.json' if sys.argv[1:]==['--execute-approved-revalidation'] else 'attempt.json'
    if attempt=='revalidation_attempt.json' and not (W/'attempt.json').exists():raise ValueError('initial attempt required')
    if (W/attempt).exists():raise ValueError('one-shot attempt already exists')
    if s.cmd(['git','rev-parse','HEAD'])['stdout'].strip()!='9d375b4b58aa6dc9d87afd436a0ddf1ebf671c27':raise ValueError('unexpected HEAD')
    if any(os.environ.get(k) for k in ('LD_PRELOAD','LD_AUDIT','LD_LIBRARY_PATH')):raise ValueError('loader environment not allowed')
    memory=json.loads((R/'memory_preflight.json').read_text())
    if memory.get('safe_to_attempt_harmless_fixture') is not True or memory.get('estimated_stage_plus8MiB_bytes',67108864)>=67108864:raise ValueError('memory preflight rejected')
    manifest=load_manifest();return guard(CONFIG,manifest,lambda:run(manifest,attempt))

def run(manifest,attempt):
    manager=s.properties(manager=True)
    if manager['rc'] or manager['values'].get('SystemState')!='running':raise ValueError('manager unavailable')
    managerpath=manager['values']['ControlGroup'];before=s.snapshot(managerpath)
    unit='aero-probe-a-harmless-v1-'+uuid.uuid4().hex[:10]+'.service';target=s.CG/managerpath.lstrip('/')/'app.slice'/unit;rel='/'+str(target.relative_to(s.CG))
    if s.properties(unit)['values'].get('LoadState')!='not-found' or target.exists():raise ValueError('unit collision')
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
            payload=['/usr/bin/python3','-I','-B',str(B/'scripts/stage.py'),'--owned-service-stage',rel]+ns+[str(ip6.getsockname()[1]),unixpath,absname]
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
                        if 'harness_ready' in text:break
                        if p.poll() is not None:break
                        time.sleep(.03)
                    if not active or 'harness_ready' not in text:raise ValueError('native ready gate not reached')
                    if active['ControlGroup']!=rel:raise ValueError('unexpected cgroup')
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
                    pid=candidates[0];mapping=verify(pid,manifest['profiles']['harmless_fixture_only']);row['fixture_host_pid']=pid
                    put('mapped_library_validation.json',mapping)
                    if mapping['status']!='PASS_FILE_IDENTITY':raise ValueError('mapping identity gate: '+mapping.get('error','unknown'))
                    during=s.snapshot(managerpath);changes=s.differences(before,during,rel.lstrip('/'));row['during_controller_diff']=changes
                    if any(not x['expected'] for x in changes):raise ValueError('unexpected controller mutation')
                    p.stdin.write('GO\n');p.stdin.flush();p.stdin.close();row['go_sent']=True
                    rc=p.wait(timeout=8);row['returncode']=rc
                    row['stdout']=(W/'stdout').read_text();row['stderr']=(W/'stderr').read_text();row['body_entered']='body_entered' in row['stdout']
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
                row['host_processes']=identities;row['cleanup']=cleanup;row['elapsed_seconds']=round(time.monotonic()-start,6)
                row['stdout']=(W/'stdout').read_text() if (W/'stdout').exists() else '';row['stderr']=(W/'stderr').read_text() if (W/'stderr').exists() else ''
                if cleanup['status']!='PASS':row['status']='FAIL'
                connections=bool(select.select([ip6,ux,abstract],[],[],0)[0]);row['socket_controls']={'positive_controls':controls,'sandbox_host_connections':connections}
                if connections:row['status']='FAIL'
        (W/'canary').unlink();row['canary_removed']=True
    row['host_temp_removed']=not folder.exists()
    after=s.snapshot(managerpath);afterdiff=s.differences(before,after,'NO_OWN_PATH')
    row['after_controller_diff']=afterdiff
    if afterdiff:row['status']='FAIL'
    put('controller_diff.json',{'before_to_after':afterdiff,'during':row.get('during_controller_diff'),'manager_before':manager,'manager_after':s.properties(manager=True),'compared_paths':len(before),'manual_writes':False})
    put('native_fixture_execution.json',row)
    put('supervisor_integration.json',{'status':row['status'],'unit':unit,'go_sent':row['go_sent'],'body_entered':row['body_entered'],'only_harmless_profile':True,'DART_loaded':False,'read_only_fd_binds':True})
    put('resource_readback.json',{'requested':LIMITS,'observed':row.get('resource_readback'),'excess_enforcement':'NOT_TESTED'})
    put('process_cleanup.json',{'cleanup':row['cleanup'],'host_temp_removed':row['host_temp_removed'],'canary_removed':row['canary_removed'],'intentional_SIGKILL':False})
    if mapping['status']=='NOT_RUN':put('mapped_library_validation.json',mapping)
    return 0 if row['status']=='PASS' else 1
if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as e:put('preflight_failure.json',{'status':'FAIL','error':str(e),'runtime_started':(W/'attempt.json').exists()});raise
