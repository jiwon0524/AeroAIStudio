"""Separate harmless-only end-to-end driver. NEVER invoked by build/tests.
No-argument invocation returns78. Execution requires exact reviewed contract SHA
and explicit --execute-once; collector-stage additionally requires owned unit+
run marker identity. These flags do not grant permission by themselves.
"""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import *
import argparse,subprocess,socket,fcntl,stat,struct,time,signal,select
import collector as C
import diagnostics as DG

class Manager(C.placement.Manager):
    def call(self,args):
        tools={'systemctl':'/usr/bin/systemctl','busctl':'/usr/bin/busctl'}
        need(args[0] in tools,'unapproved manager tool')
        return subprocess.check_output([tools[args[0]],*args[1:]],text=True,timeout=2,env={'PATH':'/usr/bin:/bin','LC_ALL':'C','XDG_RUNTIME_DIR':'/run/user/'+str(os.getuid())})
    def inspect(self,unit):
        keys='Id,InvocationID,ControlGroup,MemoryMax,MemorySwapMax,TasksMax,CPUQuotaPerSecUSec,CPUQuotaPeriodUSec,KillMode,Delegate,LoadState,Description'
        raw=self.call(['systemctl','--user','show',unit,'--no-pager','--property='+keys])
        return dict(x.split('=',1) for x in raw.splitlines() if '=' in x)

def load_contract(path,digest):
    need(Path(path)==R/'reports/execution_contract.json','fixed contract path')
    need(type(digest) is str and len(digest)==64 and sha(path)==digest,'reviewed contract SHA mismatch')
    value=json_read(path)
    need(value['profile']=='SMALL_HARMLESS_ONLY' and not value['dart_gazebo_loading'] and value['physical_steps']==0,'forbidden profile')
    need(value['owner_memory_max']==5368709120 and value['target_memory_max']==536870912,'resource contract changed')
    for name,h in value['files'].items():need(sha(name)==h,'contract input/source/artifact hash changed: '+name)
    for row in value['policy']['paths']:
        st=Path(row['source']).stat();o=row['original']
        need((st.st_dev,st.st_ino,st.st_size)==(o['device'],o['inode'],row['size']),'source file identity changed')
    need(subprocess.check_output(['/usr/bin/git','branch','--show-current'],cwd=B,text=True).strip()=='experiment/dart-internal-trace','wrong branch')
    return value

def exclusive(path,data):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
    with os.fdopen(fd,'wb') as f:
        f.write(data);f.flush();os.fsync(f.fileno())

def persist_to(path,cap):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_APPEND|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
    count=0
    def write(row):
        nonlocal count
        data=canonical(row);need(count+len(data)<=cap,'durable collector log overflow')
        at=0
        while at<len(data):
            n=os.write(fd,data[at:]);need(n>0,'collector persistence short write');at+=n
        os.fdatasync(fd);count+=len(data);return True
    return fd,write

def check_source(fd,row):
    st=os.fstat(fd)
    need(stat.S_ISREG(st.st_mode) and (st.st_dev,st.st_ino,st.st_size)==(row['device'],row['inode'],row['size']) and C.channel.S.digest_fd(fd)==row['sha256'],'preparation source same-FD identity/hash')

def seal_executable(path,expected):
    st=Path(path).stat();row=dict(source=str(path),device=st.st_dev,inode=st.st_ino,size=st.st_size,sha256=expected)
    fd,receipt=C.channel.S.copy_one(row,check_source,True,limit=543979760)
    return dict(fd=fd,receipt=receipt)

def high(fd):
    copy=fcntl.fcntl(fd,fcntl.F_DUPFD_CLOEXEC,10);os.close(fd);return copy

def absent_unit(manager,name):
    need(manager.inspect(name).get('LoadState')=='not-found','unit already exists: '+name)

def owned(manager,name,description,invocation=None):
    p=manager.inspect(name)
    need(p.get('Id')==name and p.get('Description')==description and p.get('InvocationID') and p.get('ControlGroup','').startswith('/') and p['ControlGroup']!='/','unit ownership not proven')
    if invocation:need(p['InvocationID']==invocation,'unit invocation changed')
    return p

def cleanup_owner(manager,name,description,receipt):
    if manager.inspect(name).get('LoadState')=='not-found':
        if receipt:need(not (Path('/sys/fs/cgroup')/receipt['ControlGroup'].lstrip('/')).exists(),'owner cgroup remains')
        return True
    current=owned(manager,name,description,receipt['InvocationID'] if receipt else None)
    manager.call(['systemctl','--user','stop','--',name])
    deadline=time.monotonic()+2
    while time.monotonic()<deadline:
        if manager.inspect(name).get('LoadState')=='not-found' and not (Path('/sys/fs/cgroup')/current['ControlGroup'].lstrip('/')).exists():return True
        time.sleep(.01)
    raise ValueError('owner unit/cgroup cleanup deadline')

def cleanup_target_owned(manager,c):
    state=manager.inspect(c['target_unit'])
    if state.get('LoadState')=='not-found':return True
    receipt_path=Path(c['output'])/'target-unit.json'
    need(receipt_path.is_file() and not receipt_path.is_symlink(),'target cleanup identity receipt missing; UNKNOWN, do not stop')
    receipt=json_read(receipt_path)
    need(receipt['name']==c['target_unit'] and receipt['run']==c['run'],'target cleanup receipt binding')
    state=owned(manager,c['target_unit'],c['target_description'],receipt['invocation'])
    need(state['ControlGroup']==receipt['cgroup'],'target cleanup cgroup changed')
    unit=C.placement.Unit(receipt['name'],receipt['invocation'],receipt['cgroup'],receipt['run'])
    return C.placement.cleanup_target(manager,unit)

def owner_command(c,digest):
    return ['/usr/bin/systemd-run','--user','--unit='+c['owner_unit'],'--wait','--pipe','--collect',
        '--property=Description='+c['description'],'--property=MemoryMax=5368709120',
        '--property=Environment=LC_ALL=C','--property=UnsetEnvironment=LD_PRELOAD LD_AUDIT LD_LIBRARY_PATH PYTHONPATH PYTHONHOME',
        '--property=KillMode=control-group','--property=OOMPolicy=stop','--property=RuntimeMaxSec=40s','--property=TimeoutStopSec=2s',
        '/usr/bin/python3','-I','-B',str(R/'scripts/driver.py'),'--collector-stage','--contract',str(R/'reports/execution_contract.json'),'--approved-contract-sha256',digest]

def run_once(c,digest,manager=None):
    manager=manager or Manager();output=Path(c['output']);marker=Path(c['marker'])
    need(not output.exists() and not output.is_symlink() and not marker.exists() and not marker.is_symlink(),'run output/marker already exists; no retry')
    absent_unit(manager,c['owner_unit']);absent_unit(manager,c['target_unit'])
    # First mutation; exact one-shot marker is NEVER deleted, including failure.
    exclusive(marker,canonical(dict(run=c['run'],contract_sha256=digest)))
    output.mkdir(mode=0o700)
    proc=None;receipt=None;ok=False;cleanup=False;reason=None;cleanup_errors=[];progress=None;last_state=None
    try:
        progress=DG.Progress(output/'host-startup.jsonl',c['run'],digest)
        progress.record('host-begin')
        with DG.private_log(output/'host.stdout') as out,DG.private_log(output/'host.stderr') as err:
            proc=subprocess.Popen(owner_command(c,digest),stdout=out,stderr=err,env={'PATH':'/usr/bin:/bin','LC_ALL':'C','XDG_RUNTIME_DIR':'/run/user/'+str(os.getuid())})
            progress.record('owner-client-spawned',pid=proc.pid)
            start=time.monotonic();deadline=start+c['deadlines']['host_s']
            while proc.poll() is None:
                need(time.monotonic()<deadline,'host40s deadline')
                need(sum(p.stat().st_size for p in (output/'host.stdout',output/'host.stderr'))<=1048576,'host output overflow')
                state=manager.inspect(c['owner_unit'])
                if state!=last_state:
                    progress.record('owner-inspect',state=state);last_state=state
                if state.get('LoadState')!='not-found':
                    current=owned(manager,c['owner_unit'],c['description'],receipt['InvocationID'] if receipt else None)
                    need(current.get('MemoryMax')=='5368709120','owner actual cap mismatch');receipt=receipt or current
                time.sleep(.01)
            progress.record('owner-client-exited',returncode=proc.returncode)
            need(proc.returncode==0 and receipt is not None,'owner/collector service failed or identity not captured')
        result=json_read(output/'collector-result.json')
        need(result['status']=='PASS_SMALL_HARMLESS_PATH_ONLY' and result['owner_wait_returncode']==0 and result['target_cleanup'] is True and result.get('diagnostic_complete') is True,'collector terminal failure')
        DG.validate_progress(output/'collector-startup.jsonl',c['run'],digest,['collector-begin','audit-initialized','native-spawned','owner-bound','catalog-complete','placement-complete','audit-bound','coordinate-complete','native-wait','diagnostics-complete','collector-final'])
        DG.validate_native(output/'native-parent.stderr',result['native_parent_pid'])
        need(all(sha(p)==h for p,h in c['files'].items()),'post-run source/artifact integrity changed')
        progress.record('host-verified')
        DG.validate_progress(output/'host-startup.jsonl',c['run'],digest,['host-begin','owner-client-spawned','owner-client-exited','host-verified'])
        ok=True
    except Exception as e:
        reason=str(e)
        if progress:
            try:progress.record('host-failed',reason=reason)
            except Exception as diagnostic_error:cleanup_errors.append('host diagnostic persistence: '+str(diagnostic_error))
    finally:
        owner_clean=target_clean=False
        try:owner_clean=cleanup_owner(manager,c['owner_unit'],c['description'],receipt)
        except Exception as e:cleanup_errors.append('owner cleanup: '+str(e))
        try:target_clean=cleanup_target_owned(manager,c)
        except Exception as e:cleanup_errors.append('target cleanup: '+str(e))
        cleanup=owner_clean and target_clean
        # Only the newly spawned systemd-run client belongs to this invocation.
        if proc and proc.poll() is None:
            proc.terminate()
            try:proc.wait(timeout=2)
            except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=2)
        if progress:
            try:progress.close()
            except Exception as e:ok=False;cleanup_errors.append('host diagnostic close: '+str(e))
        exclusive(output/'host-result.json',canonical(dict(status='PASS_SMALL_HARMLESS_PATH_ONLY' if ok and cleanup else 'FAIL',reason=reason,cleanup_errors=cleanup_errors,owner_client_returncode=proc.returncode if proc else None,owner_cleanup=cleanup,owner_invocation=receipt,contract_sha256=digest,physical_steps=0,large_objects_prepared=False)))
    return 0 if ok and cleanup else 78

def collector_stage(c,digest,manager=None):
    manager=manager or Manager();output=Path(c['output'])
    need(json_read(c['marker'])==dict(run=c['run'],contract_sha256=digest),'one-shot stage marker binding')
    need(output.is_dir() and not output.is_symlink(),'owned output absent')
    logs=[];sockets=[];descriptors=[];proc=None;unit=None;anchor=None;owner_pin=None;success=False;target_clean=False;result={};reason=None;progress=None;diagnostic_complete=False;cleanup_errors=[]
    deadline=time.monotonic()+c['deadlines']['host_s']
    try:
        progress=DG.Progress(output/'collector-startup.jsonl',c['run'],digest)
        progress.record('collector-begin')
        self_id=C.placement.identity(os.getpid());state=owned(manager,c['owner_unit'],c['description'])
        need(state['MemoryMax']=='5368709120' and self_id['cgroup']==state['ControlGroup'],'collector outside owned bounded domain')
        need(output.is_dir() and not output.is_symlink(),'owned output absent')
        absent_unit(manager,c['target_unit'])
        progress.record('owner-domain-verified')
        audit_fd,persist=persist_to(output/'collector-audit.jsonl',8388608);logs.append(audit_fd)
        raw_fd,persist_raw=persist_to(output/'native-audit.jsonl',8388608);logs.append(raw_fd)
        progress.record('audit-initialized')
        # Known small executable copies only, not five large objects.
        anchor=seal_executable(c['anchor'],c['files'][c['anchor']]);owner_pin=seal_executable(c['owner_binary'],c['files'][c['owner_binary']])
        descriptors.extend([anchor['fd'],owner_pin['fd']])
        def target_receipt(u):
            exclusive(output/'target-unit.json',canonical(dict(name=u.name,invocation=u.invocation,cgroup=u.cgroup,run=u.run)))
            return True
        progress.record('target-create-begin')
        unit=C.placement.create_target(manager,c['run'],anchor,c['files'][c['anchor']],C.channel.S.validate_object,name=c['target_unit'],description=c['target_description'],receipt_callback=target_receipt)
        progress.record('target-created')
        left,right=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET|socket.SOCK_CLOEXEC|socket.SOCK_NONBLOCK);sockets=[left,right]
        left.setsockopt(socket.SOL_SOCKET,socket.SO_PASSCRED,1)
        go_r,go_w=os.pipe2(os.O_CLOEXEC|os.O_NONBLOCK);out_r,out_w=os.pipe2(os.O_CLOEXEC|os.O_NONBLOCK);err_r,err_w=os.pipe2(os.O_CLOEXEC|os.O_NONBLOCK)
        go_r,out_w,err_w=map(high,(go_r,out_w,err_w));descriptors.extend([go_w,out_r,err_r,go_r,out_w,err_w])
        journal=os.open(output/'owner-journal.raw',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_APPEND|os.O_NOFOLLOW|os.O_CLOEXEC,0o600);descriptors.append(journal)
        child=high(os.dup(right.fileno()));descriptors.append(child)
        argv=['/proc/self/fd/'+str(owner_pin['fd']),'--harmless-owner-v10',*[str(fd) for fd in (go_r,out_w,err_w,journal,child)]]
        progress.record('native-spawn-begin')
        with DG.private_log(output/'native-parent.stderr',True) as native_diagnostic:
            proc=subprocess.Popen(argv,pass_fds=(owner_pin['fd'],go_r,out_w,err_w,journal,child),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=native_diagnostic,env={'LC_ALL':'C'})
        parent=C.placement.identity(proc.pid)
        progress.record('native-spawned',pid=proc.pid,start=parent['start'],host=__import__('socket').gethostname())
        right.close()
        for fd in (go_r,out_w,err_w,journal,child):os.close(fd);descriptors.remove(fd)
        streams={}
        stream_counts={'stdout':0,'stderr':0}
        for key in stream_counts:
            fd=os.open(output/(key+'.raw'),os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
            streams[key]=fd;logs.append(fd)
        def stream_sink(key,data):
            stream_counts[key]+=len(data)
            need(stream_counts[key]<=c['stream_limits'][key+'_total'],'raw stream overflow')
            offset=0
            while offset<len(data):
                n=os.write(streams[key],data[offset:]);need(n>0,'raw stream write failed');offset+=n
            os.fdatasync(streams[key]);return True
        def write(data):need(os.write(go_w,data)==len(data),'GO/EXIT_ACK short write')
        def terminal(root,placed):
            nonlocal target_clean
            group=Path('/sys/fs/cgroup')/unit.cgroup.lstrip('/')
            need((group/'cgroup.procs').read_text().strip()=='','target processes remain after complete audit')
            try:
                current=C.placement.identity(root.root)
            except FileNotFoundError:current=None
            need(current is None or current['start']!=root.root_start,'target exit not observed')
            target_clean=C.placement.cleanup_target(manager,unit)
            DG.validate_native(output/'native-parent.stderr',proc.pid,complete=False)
            progress.record('pre-V-diagnostics-verified')
            integrity=all(sha(p)==h for p,h in c['files'].items())
            return True,True,0,target_clean,integrity,True
        result=C.coordinate(left,proc.pid,parent['start'],c['files'][c['owner_binary']],c['run'],digest,c['policy'],c['records'],c['manifest'],unit,manager,out_r,err_r,write,persist,persist_raw,terminal,stream_sink,progress.record)
        progress.record('coordinate-complete')
        need(time.monotonic()<deadline,'collector host deadline')
        proc.wait(timeout=min(5,max(.01,deadline-time.monotonic())))
        progress.record('native-wait',returncode=proc.returncode)
        need(proc.returncode==0,'native bootstrap/worker wait failed after V')
        DG.validate_native(output/'native-parent.stderr',proc.pid)
        progress.record('diagnostics-complete')
        DG.validate_progress(output/'collector-startup.jsonl',c['run'],digest,['collector-begin','audit-initialized','native-spawned','owner-bound','catalog-complete','placement-complete','audit-bound','coordinate-complete','native-wait','diagnostics-complete'])
        diagnostic_complete=True;success=True
    except Exception as e:
        reason=str(e)
        if progress:
            try:progress.record('collector-failed',reason=reason,native_returncode=proc.poll() if proc else None)
            except Exception as diagnostic_error:cleanup_errors.append('collector diagnostic persistence: '+str(diagnostic_error))
    finally:
        # Disconnect precedes bounded owner reap; failures never manufacture V.
        for sock in sockets:
            try:sock.close()
            except OSError:pass
        if unit and not target_clean:
            try:target_clean=C.placement.cleanup_target(manager,unit)
            except Exception as e:cleanup_errors.append('target cleanup: '+str(e))
        if proc and proc.poll() is None:
            try:proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.terminate()
                try:proc.wait(timeout=2)
                except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=2)
        for fd in descriptors+logs:
            try:os.close(fd)
            except OSError:success=False
        if getattr(manager,'pending_targets',{}) and not unit:
            try:
                created=getattr(manager,'created_units',{}).get(c['target_unit'])
                target_clean=C.placement.cleanup_target(manager,created) if created else cleanup_target_owned(manager,c)
            except Exception as e:cleanup_errors.append('owned target recovery failed: '+str(e))
            success=False
        if progress:
            try:progress.record('collector-final',native_returncode=proc.returncode if proc else None,target_cleanup=target_clean);progress.close()
            except Exception as e:success=False;cleanup_errors.append('collector diagnostic final: '+str(e))
        exclusive(output/'collector-result.json',canonical(dict(result,diagnostic_complete=diagnostic_complete,native_parent_pid=proc.pid if proc else None,cleanup_errors=cleanup_errors,status='PASS_SMALL_HARMLESS_PATH_ONLY' if success and target_clean else 'FAIL',reason=reason,target_cleanup=target_clean,owner_wait_returncode=proc.returncode if proc else None,contract_sha256=digest)))
    return 0 if success and target_clean else 78

def main(argv=None):
    parser=argparse.ArgumentParser()
    mode=parser.add_mutually_exclusive_group(required=True);mode.add_argument('--execute-once',action='store_true');mode.add_argument('--collector-stage',action='store_true')
    parser.add_argument('--contract',required=True);parser.add_argument('--approved-contract-sha256',required=True)
    if argv==[]:return 78
    args=parser.parse_args(argv)
    c=load_contract(args.contract,args.approved_contract_sha256)
    return run_once(c,args.approved_contract_sha256) if args.execute_once else collector_stage(c,args.approved_contract_sha256)
if __name__=='__main__':
    try:raise SystemExit(main(sys.argv[1:]))
    except Exception as error:
        print(type(error).__name__+': '+str(error),file=sys.stderr);raise SystemExit(78)
