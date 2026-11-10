"""Native held-child -> already-owned target unit placement, not a launcher.
All mutating manager operations are reachable only through place() on a verified
private SCM pidfd handoff. This module is imported/tested with mock transport;
no service, resource property or live process is changed by preparation scripts.
"""
from pathlib import Path
from dataclasses import dataclass
import os,re,subprocess,socket,struct,hashlib,json

def need(ok,why):
    if not ok:raise ValueError(why)
def identity(pid):
    value=Path('/proc',str(pid),'stat').read_text().rsplit(')',1)[1].split()
    return dict(pid=pid,start=value[19],ppid=int(value[1]),state=value[0],cgroup=Path('/proc',str(pid),'cgroup').read_text().strip().split('::',1)[1])
@dataclass(frozen=True)
class Unit:
    name:str
    invocation:str
    cgroup:str
    run:str
class Manager:
    def call(self,args):
        return subprocess.check_output(args,text=True,timeout=5)
    def inspect(self,unit):
        raw=self.call(['systemctl','--user','show',unit,'--no-pager','--property=Id,InvocationID,ControlGroup,MemoryMax,MemorySwapMax,TasksMax,CPUQuotaPerSecUSec,CPUQuotaPeriodUSec,KillMode,Delegate,LoadState'])
        return dict(line.split('=',1) for line in raw.splitlines() if '=' in line)
    def attach(self,unit,pid):
        return self.call(['busctl','--user','call','org.freedesktop.systemd1','/org/freedesktop/systemd1',
            'org.freedesktop.systemd1.Manager','AttachProcessesToUnit','ssau',unit,'','1',str(pid)])

def limits(pid):
    text=Path('/proc',str(pid),'limits').read_text()
    expected={'Max cpu time':'10','Max file size':'1048576','Max open files':'256','Max core file size':'0','Max address space':'2147483648'}
    for label,v in expected.items():
        match=re.search('^'+label+r'\s+(\S+)\s+(\S+)',text,re.M)
        need(match and match.groups()==(v,v),'target inherited owner rlimit: '+label)
    return True

def cgroup_limits(group):
    root=Path('/sys/fs/cgroup')/group.lstrip('/')
    expected={'memory.max':'536870912','memory.swap.max':'0','pids.max':'64','cpu.max':'100000 100000'}
    for key,value in expected.items():need((root/key).read_text().strip()==value,'target cgroup readback: '+key)
    return True

def namespaces(pid,collector):
    for kind in ('mnt','pid','net','user'):
        need(os.stat('/proc/'+str(pid)+'/ns/'+kind).st_ino!=os.stat('/proc/'+str(collector)+'/ns/'+kind).st_ino,'target namespace not isolated: '+kind)
    text=Path('/proc',str(pid),'status').read_text()
    for field in ('CapInh','CapPrm','CapEff','CapAmb'):
        row=re.search('^'+field+r':\s*([0-9a-fA-F]+)',text,re.M)
        need(row and int(row[1],16)==0,'owner capabilities inherited into target')
    return True

def place(pid,start,owner_pid,owner_start,unit,manager,observe=identity,check_limits=limits,collector_pid=None,check_cgroup=cgroup_limits,check_namespaces=namespaces):
    need(type(unit) is Unit and re.fullmatch(r'aero-guard-v10-target-[a-zA-Z0-9-]+\.service',unit.name) and unit.invocation and unit.run,'owned target-unit receipt missing')
    owner=observe(owner_pid);child=observe(pid);collector=observe(collector_pid or os.getpid())
    need(owner['start']==owner_start and child['start']==start and child['ppid']==owner_pid and child['state'] in ('t','T'),'child not owned/held or PID reused')
    group=unit.cgroup.rstrip('/');need(group.startswith('/') and group!='','invalid target cgroup')
    for role in (owner,collector):need(role['cgroup']!=group and not role['cgroup'].startswith(group+'/'),'owner/collector inside target cleanup domain')
    before=manager.inspect(unit.name)
    need(before.get('Id')==unit.name and before.get('InvocationID')==unit.invocation and before.get('ControlGroup')==unit.cgroup and before.get('LoadState')=='loaded','target unit ownership changed')
    need(before.get('MemoryMax')=='536870912' and before.get('MemorySwapMax')=='0' and before.get('TasksMax')=='64' and before.get('Delegate')=='no' and before.get('KillMode')=='control-group','target unit resource policy differs')
    check_cgroup(unit.cgroup)
    check_namespaces(pid,collector['pid'])
    check_limits(pid)  # Exact child soft+hard limits, never owner proposal values.
    manager.attach(unit.name,pid)  # NO SetUnitProperties, Limit*, sudo or cgroup writes.
    after=manager.inspect(unit.name);now=observe(pid)
    need(after==before and now['pid']==pid and now['start']==start and now['state'] in ('t','T') and now['cgroup']==unit.cgroup,'placement/readback changed identity or limits')
    need(all(observe(role['pid'])[key]==role[key] for role in (owner,collector) for key in ('pid','start','cgroup')),'owner/collector migrated or identity changed')
    check_limits(pid);check_cgroup(unit.cgroup)
    if hasattr(manager,"anchors") and unit.name in manager.anchors:
        release_anchor(manager,unit,observe)
        need(observe(pid)["start"]==start and observe(pid)["cgroup"]==unit.cgroup,"target changed after anchor release")
    return dict(pid=pid,start=start,cgroup=unit.cgroup,invocation=unit.invocation,owner_cgroup=owner['cgroup'],collector_cgroup=collector['cgroup'],target_limits_verified=True)

def receive(endpoint,owner_pid,owner_start,owner_sha,unit,manager,audit):
    data,ancillary,flags,address=endpoint.recvmsg(16,socket.CMSG_SPACE(4)+socket.CMSG_SPACE(12),socket.MSG_DONTWAIT|socket.MSG_CMSG_CLOEXEC)
    fds=[]
    try:
        credentials=[];bad=False
        for level,kind,value in ancillary:
            if level==socket.SOL_SOCKET and kind==socket.SCM_RIGHTS:
                n=len(value)//4
                if n:fds.extend(struct.unpack(str(n)+'i',value[:n*4]))
                bad|=len(value)%4!=0
            elif level==socket.SOL_SOCKET and kind==socket.SCM_CREDENTIALS and len(value)==12:credentials.append(struct.unpack('3i',value))
            else:bad=True
        need(not bad,'placement unknown/malformed ancillary')
        need(len(data)==16 and data[:8]==b'PLACEV8\0' and not flags&(socket.MSG_TRUNC|socket.MSG_CTRUNC) and len(fds)==1,'placement framing/FD count')
        need(credentials==[(owner_pid,os.geteuid(),os.getegid())] and identity(owner_pid)['start']==owner_start,'placement source credential/start')
        fd=os.open('/proc/'+str(owner_pid)+'/exe',os.O_RDONLY|os.O_CLOEXEC)
        try:
            h=hashlib.sha256();offset=0
            while True:
                chunk=os.pread(fd,65536,offset)
                if not chunk:break
                h.update(chunk);offset+=len(chunk)
            need(h.hexdigest()==owner_sha,'placement owner ELF hash')
        finally:os.close(fd)
        native=struct.unpack('Q',data[8:])[0];pid=audit.pidfd_identity(fds[0],native);start=identity(pid)['start']
        result=place(pid,start,owner_pid,owner_start,unit,manager)
        need(audit.pidfd_identity(fds[0],native)==pid and identity(pid)['start']==start,'placement pidfd changed')
        need(endpoint.send(b'P',socket.MSG_DONTWAIT|socket.MSG_NOSIGNAL)==1,'placement ACK failed')
        return result
    finally:
        for fd in fds:os.close(fd)

def target_properties(execfd_path):
    # Every value is target-specific and fixed; never merge owner properties.
    return [
      ('ExecStart','a(sasb)',['1',execfd_path,'1',execfd_path,'false']),
      ('Type','s',['exec']),('RemainAfterExit','b',['true']),
      ('MemoryMax','t',['536870912']),('MemorySwapMax','t',['0']),('TasksMax','t',['64']),
      ('CPUQuotaPerSecUSec','t',['1000000']),('CPUQuotaPeriodUSec','t',['100000']),
      ('RuntimeMaxUSec','t',['30000000']),('TimeoutStopUSec','t',['2000000']),
      ('KillMode','s',['control-group']),('OOMPolicy','s',['stop']),('Delegate','b',['false']),('Slice','s',['app.slice']),
      ('LimitCPU','t',['10']),('LimitCPUSoft','t',['10']),
      ('LimitAS','t',['2147483648']),('LimitASSoft','t',['2147483648']),
      ('LimitFSIZE','t',['1048576']),('LimitFSIZESoft','t',['1048576']),
      ('LimitNOFILE','t',['256']),('LimitNOFILESoft','t',['256']),
      ('LimitCORE','t',['0']),('LimitCORESoft','t',['0']),
      ('StandardInput','s',['null']),('StandardOutput','s',['null']),('StandardError','s',['null']),
      ('Environment','as',['1','LC_ALL=C']),('UnsetEnvironment','as',['5','LD_PRELOAD','LD_AUDIT','LD_LIBRARY_PATH','PYTHONPATH','PYTHONHOME'])]

def create_target(manager,run,anchor,expected_anchor_sha,validate,observe=identity,inspect_anchor=None,name=None,description=None,receipt_callback=None):
    """Future explicitly authorized control action only. No call at import/tests.
    Anchor source must already be held sealed; never ExecStart a mutable work ELF.
    Returns the exact creation receipt consumed by place(), not an ambient unit.
    """
    import uuid
    need(type(run) is str and run and anchor['receipt']['sha256']==expected_anchor_sha and anchor['receipt']['executable_intent'] is True,'anchor policy')
    validate(anchor['fd'],anchor['receipt'])
    path=f'/proc/{os.getpid()}/fd/{anchor["fd"]}'
    name=name or ('aero-guard-v10-target-'+uuid.uuid4().hex+'.service')
    need(re.fullmatch(r'aero-guard-v10-target-[a-zA-Z0-9-]+\.service',name),'target name schema')
    need(manager.inspect(name).get('LoadState')=='not-found','target unit collision before creation')
    props=target_properties(path)
    props.append(('Description','s',[description or ('aero-v10-target:'+run)]))
    argv=['busctl','--user','call','org.freedesktop.systemd1','/org/freedesktop/systemd1',
        'org.freedesktop.systemd1.Manager','StartTransientUnit','ssa(sv)a(sa(sv))',name,'fail',str(len(props))]
    for key,kind,values in props:argv += [key,kind,*values]
    argv+=['0']
    job=manager.call(argv)
    if not hasattr(manager,'pending_targets'):manager.pending_targets={}
    manager.pending_targets[name]=dict(run=run,job=job,anchor_sha256=expected_anchor_sha)
    data=manager.inspect(name)
    need(data.get('Id')==name and data.get('InvocationID') and data.get('ControlGroup','').startswith('/'),'target creation receipt')
    created=Unit(name,data['InvocationID'],data['ControlGroup'],run)
    if not hasattr(manager,'created_units'):manager.created_units={}
    manager.created_units[name]=created
    if receipt_callback is not None:need(receipt_callback(created) is True,'target identity receipt persistence')
    # Service creation is asynchronous. Caller polls inspect_anchor, or retries
    # outside this function, without authorizing/releasing a different process.
    pid,start=(inspect_anchor(name,anchor['receipt']) if inspect_anchor is not None else attest_anchor(manager,name,anchor['receipt'],validate,observe))
    current=observe(pid);need(current['start']==start and current['state'] in ('t','T') and current['cgroup']==data['ControlGroup'],'anchor not held in new target')
    unit=Unit(name,data['InvocationID'],data['ControlGroup'],run)
    if not hasattr(manager,'anchors'):manager.anchors={}
    manager.anchors[name]=(pid,start,unit.invocation)
    return unit

def release_anchor(manager,unit,observe=identity):
    """Only newly created/recorded anchor; never signal arbitrary existing jobs."""
    import signal,select
    need(hasattr(manager,'anchors') and unit.name in manager.anchors,'new anchor ownership receipt missing')
    pid,start,invocation=manager.anchors[unit.name]
    need(invocation==unit.invocation and manager.inspect(unit.name).get('InvocationID')==invocation,'anchor unit reused')
    before=observe(pid);need(before['start']==start and before['cgroup']==unit.cgroup and before['state'] in ('t','T'),'anchor PID/start changed')
    fd=os.pidfd_open(pid,0)
    try:
        need(observe(pid)['start']==start,'anchor pidfd bind race')
        signal.pidfd_send_signal(fd,signal.SIGCONT)
        poll=select.poll();poll.register(fd,select.POLLIN)
        need(bool(poll.poll(5000)),'anchor exit missing; do not release child')
    finally:os.close(fd)
    del manager.anchors[unit.name]

def attest_anchor(manager,name,receipt,validate,observe=identity):
    import time
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        raw=manager.call(['systemctl','--user','show',name,'--property=MainPID','--value']).strip()
        if raw.isdigit() and int(raw)>0:
            pid=int(raw);before=observe(pid)
            if before['state'] in ('t','T'):
                fd=os.open('/proc/'+str(pid)+'/exe',os.O_RDONLY|os.O_CLOEXEC)
                try:validate(fd,receipt)
                finally:os.close(fd)
                need(observe(pid)['start']==before['start'],'anchor PID reused during sealed ELF attestation')
                return pid,before['start']
        time.sleep(.01)
    raise ValueError('new anchor stop/identity deadline')

def cleanup_target(manager,unit):
    before=manager.inspect(unit.name)
    need(before.get('Id')==unit.name and before.get('InvocationID')==unit.invocation and before.get('ControlGroup')==unit.cgroup,'cleanup unit ownership changed')
    manager.call(['systemctl','--user','stop','--',unit.name])
    after=manager.inspect(unit.name)
    need(after.get('LoadState')=='not-found' and not (Path('/sys/fs/cgroup')/unit.cgroup.lstrip('/')).exists(),'unit/cgroup cleanup missing')
    return True
