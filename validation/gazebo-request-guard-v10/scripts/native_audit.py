"""Private native journal live reader -> existing v2 JournalAdapter/AuditGate.
No launcher or target is run. Source ownership is verified before FD reads.
"""
from pathlib import Path
from dataclasses import dataclass
import fcntl,hashlib,importlib.util,os,socket,stat,struct,json

R=Path(__file__).resolve().parents[1]
_POLICY=json.loads((R/'reports/policy.json').read_text())
META_POLICIES=len(_POLICY['paths'])+len(_POLICY['directories'])+len(_POLICY['negative'])+len(_POLICY['links'])
_AUTHORITY=object()  # process-local capability; cannot arrive in target bytes
p=R.parent/'gazebo-request-guard-v2/scripts/journal.py'
s=importlib.util.spec_from_file_location('v2_journal',p);old=importlib.util.module_from_spec(s);s.loader.exec_module(old)

def need(ok,why):
    if not ok:raise ValueError(why)

def start_id(pid):return Path('/proc',str(pid),'stat').read_text().rsplit(')',1)[1].split()[19]

@dataclass(frozen=True)
class Owner:
    pid:int
    start:str
    executable_sha256:str
    root:int
    run:str
    policy:str
    root_start:str=''
    native_root:int=0
    pidfd:int=-1

def parse_pidfd_info(text,native_pid):
    fields=dict(line.split(':',1) for line in text.splitlines() if ':' in line)
    pid=int(fields.get('Pid','-1'))
    chain=[int(x) for x in fields.get('NSpid','').split()]
    need(pid>0 and chain and chain[0]==pid and chain[-1]==native_pid,'pidfd namespace identity missing/mismatch')
    return pid

def pidfd_identity(fd,native_pid):
    need(fd>=0,'root pidfd missing')
    need(os.readlink('/proc/self/fd/'+str(fd))=='anon_inode:[pidfd]','root descriptor is not pidfd')
    return parse_pidfd_info(Path('/proc/self/fdinfo',str(fd)).read_text(),native_pid)

def verify_endpoint(fd,owner):
    need(type(owner.pid) is int and owner.pid>0 and type(owner.root) is int and owner.root>0,'owner identity')
    st=os.fstat(fd);need(stat.S_ISSOCK(st.st_mode),'audit socket required')
    need(fcntl.fcntl(fd,fcntl.F_GETFD)&fcntl.FD_CLOEXEC,'audit endpoint not CLOEXEC')
    before=start_id(owner.pid)
    need(pidfd_identity(owner.pidfd,owner.native_root)==owner.root,'root pidfd mapping changed')
    need(owner.root_start and start_id(owner.root)==owner.root_start,'target PID/start missing or changed')
    with socket.socket(fileno=os.dup(fd)) as endpoint:
        need(endpoint.getsockopt(socket.SOL_SOCKET,socket.SO_TYPE)==socket.SOCK_SEQPACKET,'audit endpoint type')
        pid,uid,gid=struct.unpack('3i',endpoint.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
        need((pid,uid,gid)==(owner.pid,os.geteuid(),os.getegid()),'audit source peer mismatch')
    exe=os.open('/proc/'+str(owner.pid)+'/exe',os.O_RDONLY|os.O_CLOEXEC)
    try:
        h=hashlib.sha256();offset=0
        while True:
            b=os.pread(exe,1048576,offset)
            if not b:break
            h.update(b);offset+=len(b)
        need(h.hexdigest()==owner.executable_sha256,'untrusted audit producer executable')
    finally:os.close(exe)
    need(before==owner.start==start_id(owner.pid),'audit owner PID reused')
    need(start_id(owner.root)==owner.root_start,'target PID reused during channel binding')
    need(pidfd_identity(owner.pidfd,owner.native_root)==owner.root,'root pidfd changed during channel binding')
    return (st.st_dev,st.st_ino)

class NativeJournal:
    """feed() is separately testable with synthetic native bytes, not authority.
    Real FD reads must use LiveReader's verified endpoint. No target packet API.
    """
    MAX_BYTES=1048576
    def __init__(self,gate,owner,persist_raw):
        self.gate,self.owner,self.persist=gate,owner,persist_raw
        self.seq=self.denied=self.stage=self.total=0
        self.failed=self.closed=False;self.adapter=None
        self.bound=False
        self.objects={};self.delivered=[]
        self.source_root=owner.native_root
        self.initial_maps=False
        self.fd_transaction=None
        self.metadata={}
        need(gate.binding['pid']==owner.root and gate.binding['run']==owner.run and
             gate.binding['policy']==owner.policy and gate.binding['start']==owner.root_start,'collector binding mismatch')
    def _bind(self,authority):
        need(authority is _AUTHORITY and not self.bound,'private endpoint authority')
        self.bound=True
    def fail(self,reason):
        self.failed=self.gate.failed=True
        raise ValueError(reason)
    def feed(self,raw):
        try:
            need(self.bound and not self.failed and not self.closed,'native source unbound/closed/broken')
            self.total+=len(raw)
            need(self.total<=self.MAX_BYTES and len(raw)<=192 and raw.endswith(b'\n') and raw.count(b'\n')==1,'native frame/overflow')
            fields=raw.decode('ascii').split();need(len(fields)==5,'native schema')
            seq,kind,pid,nr,denied=fields;seq,pid,nr,denied=map(int,(seq,pid,nr,denied))
            need(seq==self.seq+1 and pid>0,'native sequence/task')
            need(denied==self.denied+(kind=='DENY'),'native denial counter')
            need(self.persist(dict(seq=seq,raw=raw.decode('ascii'),run=self.owner.run,policy=self.owner.policy,
                supervisor_pid=self.owner.pid,supervisor_start=self.owner.start)) is True,'native source persistence')
            if kind=='INITIAL_MAPS':
                need(self.stage==4 and not self.initial_maps and pid==self.source_root and nr==2 and denied==0,'initial executable/interpreter mappings missing')
                self.initial_maps=True;self.seq,self.denied=seq,denied;return
            prefix=('PREEXEC_STOP','PREEXEC_ARMED','FILTER_BOUND','EXEC_STOP','TARGET_FDS')
            if self.stage<len(prefix):
                need(kind==prefix[self.stage] and pid==self.source_root and denied==0,'preexec evidence order')
                need(nr==(5 if kind=='TARGET_FDS' else -1) and (kind!='TARGET_FDS' or self.initial_maps),'preexec FD/mapping evidence fields')
                self.stage+=1
                if self.stage==len(prefix):
                    proof=dict(pre_loader=True,fd_attested=True,policy_applied=True,journal_private=True,lifetime_tracking=True)
                    self.adapter=old.JournalAdapter(self.gate,self.source_root,proof)
                    self.adapter.feed(f'1 EXEC_STOP {self.source_root} -1 0\n'.encode())
            elif kind=='AUDIT_FAULT':self.fail('native controller failure')
            elif kind in {'MMAP_OBJECT','MPROTECT_OBJECT','FD_CLOSE_BEGIN','VMA_BEGIN'}:
                need(pid in self.adapter.live and not self.adapter.complete and self.fd_transaction is None and
                     pid not in self.adapter.pending,'unbound/overlapping FD transaction')
                need((kind in {'MMAP_OBJECT','MPROTECT_OBJECT'} and 0<=nr<len(_POLICY['paths'])) or (kind=='FD_CLOSE_BEGIN' and nr>=5) or (kind=='VMA_BEGIN' and nr in {9,10,11}),'FD policy binding')
                self.fd_transaction=(pid,kind,nr)
            elif kind in {'MMAP_DONE','MPROTECT_DONE','FD_CLOSE_DONE','VMA_DONE'}:
                expected={'MMAP_DONE':'MMAP_OBJECT','MPROTECT_DONE':'MPROTECT_OBJECT','FD_CLOSE_DONE':'FD_CLOSE_BEGIN','VMA_DONE':'VMA_BEGIN'}[kind]
                need(self.fd_transaction is not None and self.fd_transaction[:2]==(pid,expected),'FD exit transaction mismatch')
                need((kind in {'MMAP_DONE','MPROTECT_DONE','VMA_DONE'} and nr==0) or (kind=='FD_CLOSE_DONE' and -4095<=nr<=0),'FD syscall outcome')
                self.fd_transaction=None
            elif kind=='META_OBJECT':
                need(pid in self.adapter.pending and self.adapter.pending[pid][1]=='REQUEST' and
                     pid not in self.metadata and 0<=nr<META_POLICIES and self.adapter.pending[pid][0] in {2,257,262,332,21,269,439,89,267},'metadata object not bound')
                self.metadata[pid]=nr
            elif kind=='META_DONE':
                need(pid in self.metadata and pid in self.adapter.pending and
                     self.adapter.pending[pid][1]=='REQUEST' and nr in {0,-2,-13,-22}|set(range(1,4097)),'metadata completion mismatch')
                index=self.metadata[pid];call=self.adapter.pending[pid][0]
                negative_start=len(_POLICY['paths'])+len(_POLICY['directories']);link_start=negative_start+len(_POLICY['negative'])
                if negative_start<=index<link_start:need(nr==-2,'negative lookup response mismatch')
                elif index>=link_start:need(call in {89,267} and nr>0,'symlink response mismatch')
                else:need(nr in {0,-13,-22},'file/directory metadata response mismatch')
                del self.metadata[pid];del self.adapter.pending[pid]
            elif kind in {'THREAD_ALLOWED','FORK_ALLOWED'}:
                need(kind!='FORK_ALLOWED' or nr==56,'invalid fork scalar decision')
                need(pid in self.adapter.live and nr in {56,435} and not self.adapter.complete,'unbound native thread decision')
            elif kind=='THREAD_FAILED':
                need(pid in self.adapter.live and nr<0 and not self.adapter.complete,'invalid failed thread receipt')
                self.adapter.emit('denial',dict(task=pid,reason='native clone failed'))
            elif kind=='SCALAR_ALLOWED':
                need(pid in self.adapter.live and nr in {9,10,158,302} and not self.adapter.complete,'invalid scalar decision')
            elif kind=='INPUT_OBJECT':
                need(pid in self.adapter.pending and self.adapter.pending[pid][1]=='REQUEST' and
                     pid not in self.objects and 0<=nr<len(_POLICY['paths']),'unbound input policy index')
                self.objects[pid]=nr
            else:
                if kind in {'ALL_DEAD','COMPLETE'}:need(self.fd_transaction is None and not self.metadata,'incomplete loader/metadata transaction')
                if kind in {'INPUT_PREPARED','INPUT_DELIVERED'}:
                    need(pid in self.objects,'input lacks native policy binding')
                normalized=f'{self.adapter.seq+1} {kind} {pid} {nr} {denied}\n'.encode()
                self.adapter.feed(normalized)
                if kind=='INPUT_DELIVERED':self.delivered.append((pid,self.objects.pop(pid)))
                elif kind in {'DENY','CANCELLED','TASK_DEAD'}:self.objects.pop(pid,None)
            self.seq,self.denied=seq,denied
        except Exception:
            self.failed=self.gate.failed=True
            raise
    def eof(self):
        try:
            need(not self.failed and not self.closed and self.adapter is not None,'early/duplicate native EOF')
            self.adapter.eof();self.closed=True
        except Exception:
            self.failed=self.gate.failed=True
            raise

class LiveReader:
    def __init__(self,fd,journal):
        self.fd,self.journal=fd,journal
        self.identity=verify_endpoint(fd,journal.owner)
        journal._bind(_AUTHORITY)
        self.failed_drain=self.closed=False;self.discarded=0
        self.released=False
    def close(self):
        if self.released:return
        self.released=True;errors=[]
        for fd in (self.fd,self.journal.owner.pidfd):
            try:os.close(fd)
            except OSError as e:errors.append(e)
        if errors:raise errors[0]
    def readable(self):
        """Call from collector poll loop; no temporary regular-file EOF."""
        try:
            need((os.fstat(self.fd).st_dev,os.fstat(self.fd).st_ino)==self.identity,'audit FD substituted')
            with socket.socket(fileno=os.dup(self.fd)) as endpoint:
                try:raw,ancillary,flags,address=endpoint.recvmsg(193,0,socket.MSG_DONTWAIT)
                except BlockingIOError:return False
            need(not flags&(socket.MSG_TRUNC|socket.MSG_CTRUNC) and not ancillary,'audit packet truncated/ancillary')
            if not raw:
                self.closed=True
                if not self.failed_drain:self.journal.eof()
                return False
            if self.failed_drain:
                self.discarded+=len(raw);return True
            self.journal.feed(raw);return True
        except Exception:
            self.journal.failed=self.journal.gate.failed=True
            self.failed_drain=True
            raise

def receive_audit(endpoint,owner_pid,owner_start,executable_sha,run,policy):
    """Receive source-owned audit FD and kernel sender credentials. Root stays
    stopped until the dedicated owner receives collector readiness separately.
    Caller creates endpoint+enables SO_PASSCRED BEFORE candidate publication.
    """
    data,ancillary,flags,address=endpoint.recvmsg(8,socket.CMSG_SPACE(8)+socket.CMSG_SPACE(12),
                                                socket.MSG_DONTWAIT|socket.MSG_CMSG_CLOEXEC)
    descriptors=[];credential=None
    try:
        # Collect ALL installed SCM_RIGHTS first, even on framing/credential
        # errors, so truncated or extra-FD packets cannot leak descriptors.
        rights_malformed=False
        for level,kind,value in ancillary:
            if level==socket.SOL_SOCKET and kind==socket.SCM_RIGHTS:
                whole=len(value)//4*4
                if whole:descriptors.extend(struct.unpack(str(whole//4)+'i',value[:whole]))
                rights_malformed|=whole!=len(value)
        need(not flags&(socket.MSG_TRUNC|socket.MSG_CTRUNC) and len(data)==8,'audit handoff framing')
        need(not rights_malformed,'audit FD payload')
        for level,kind,value in ancillary:
            need(level==socket.SOL_SOCKET,'audit ancillary level')
            if kind==socket.SCM_RIGHTS:
                pass
            elif kind==socket.SCM_CREDENTIALS:
                need(credential is None and len(value)==12,'duplicate audit peer credentials')
                credential=struct.unpack('3i',value)
            else:raise ValueError('unexpected audit ancillary record')
        need(len(descriptors)==2 and credential==(owner_pid,os.geteuid(),os.getegid()),'audit handoff source/count')
        native_root=struct.unpack('Q',data)[0];need(native_root>0,'invalid audit root')
        root=pidfd_identity(descriptors[1],native_root)
        owner=Owner(owner_pid,owner_start,executable_sha,root,run,policy,start_id(root),native_root,descriptors[1])
        verify_endpoint(descriptors[0],owner)
        fd=descriptors[0];descriptors.clear();return fd,owner
    finally:
        for fd in descriptors:os.close(fd)

def collector_ready(endpoint,reader):
    need(reader.journal.adapter is not None and reader.journal.stage==5 and
         not reader.journal.failed,'collector not bound to complete pre-loader journal')
    need(endpoint.send(b'A',socket.MSG_DONTWAIT|socket.MSG_NOSIGNAL)==1,'collector ready ACK failed')

def collector_verdict(endpoint,reader,final_args):
    """Original NativeSession finalize owns stdout/stderr EOF/exit/cleanup
    evidence. A native source COMPLETE alone can NEVER send V."""
    need(reader.closed and reader.journal.closed and not reader.journal.failed,'final native collection missing')
    result=reader.journal.gate.finalize(*final_args)
    need(endpoint.send(b'V',socket.MSG_DONTWAIT|socket.MSG_NOSIGNAL)==1,'collector verdict ACK failed')
    return result
