"""Execute Python coordinator/driver control flow with every runtime boundary mocked."""
from pathlib import Path
import io,copy,struct,socket,fcntl
from types import SimpleNamespace as S
from unittest.mock import Mock,patch
import collector as C,driver as D
from common import *

def run(ok,reject,contract,digest,packets):
    policy,records,manifest=contract['policy'],contract['records'],contract['manifest']
    def execute(fault=None):
        output=[];writes=[];released=[];events=[]
        creds=lambda pid:[(socket.SOL_SOCKET,socket.SCM_CREDENTIALS,struct.pack('3i',pid,os.geteuid(),os.getegid()))]
        owner_frame=(b'OWNERV8\0'+struct.pack('Q',1),creds(400)+[(socket.SOL_SOCKET,socket.SCM_RIGHTS,struct.pack('i',19))],0,None)
        frames=[owner_frame]+packets()+[(b'PLACE',[],0,None),(b'AUDIT',[],0,None)]
        if fault=='missing_owner':frames[0]=(b'bad',[],0,None)
        class Endpoint:
            def recvmsg(self,*a):
                if not frames:raise ValueError('mock unexpected receive after full handoff')
                return frames.pop(0)
            def send(self,data,*a):output.append(data);return len(data)
        ep=Endpoint();root=C.N.Owner(500,'w','e'*64,7,'mock',digest,'s',7,99)
        def identity(pid):return dict(pid=pid,start='100' if pid==400 else '101',ppid=1 if pid==400 else 400,state='R' if pid==400 else 'T',cgroup='/owner')
        def place(*a):
            need(ep.recvmsg()[0]==b'PLACE' and output==[b'O']+[b'C']*4+[b'K'],'placement before complete owner/catalog');ep.send(b'P');return dict(pid=7,start='s')
        def audit(*a):need(ep.recvmsg()[0]==b'AUDIT' and output[-1]==b'P','audit before placement');return 98,root
        class Reader:
            def __init__(self,fd,journal):self.fd=fd;self.journal=journal;self.closed=False;self.queue=[];journal._bind(C.N._AUTHORITY)
            def readable(self):
                if self.queue:self.journal.feed(self.queue.pop(0))
                else:self.journal.eof();self.closed=True
            def close(self):events.append('reader_close')
        def trace(ctl):
            seq=0
            def wire(kind,pid=7,nr=-1):
                nonlocal seq
                seq+=2 if fault=='audit_gap' and kind=='TASK_BORN' else 1
                ctl.reader.queue.append(f'{seq} {kind} {pid} {nr} 0\n'.encode());ctl.step('audit')
            def row(value):ctl.step('stdout',canonical(value))
            for k,n in [('PREEXEC_STOP',-1),('PREEXEC_ARMED',-1),('FILTER_BOUND',-1),('EXEC_STOP',-1),('INITIAL_MAPS',2),('TARGET_FDS',5)]:wire(k,nr=n)
            # Cross-channel readiness may overtake the durable audit receipts.
            for i in range(2):row(dict(kind='fixture_ready',iteration=0,sim_time_ns=0))
            need(not writes,'GO before independent input audit caught up')
            for index in (1,2):
                for k,n in [('REQUEST',257),('INPUT_OBJECT',index),('INPUT_PREPARED',257),('INPUT_DELIVERED',257)]:wire(k,nr=n)
            need(writes==[b'GO\n'] or ctl.failed,'GO did not resume after audit catch-up')
            wire('THREAD_ALLOWED',nr=56);wire('TASK_BORN',8,7)
            wire('FORK_ALLOWED',nr=56);wire('TASK_BORN',9,7)
            for k,n in [('REQUEST',257),('INPUT_OBJECT',1),('INPUT_PREPARED',257),('INPUT_DELIVERED',257)]:wire(k,9,n)
            wire('EXIT_STOP',9);wire('TASK_DEAD',9,0)
            row(dict(kind='fixture_child',status=0))
            for i in range(1,101):row(dict(kind='fixture_sample',iteration=i,sim_time_ns=i*1000000))
            row(dict(kind='final_wait',iteration=100,sim_time_ns=100000000))
            if fault=='audit_disconnect':ctl.step('audit')
            for k,n in [('REQUEST',257),('INPUT_OBJECT',2),('INPUT_PREPARED',257),('INPUT_DELIVERED',257)]:
                if fault!='missing_descendant_FD':wire(k,8,n)
            row(dict(kind='fixture_cleanup',joined=True))
            for k,pid,n in [('EXIT_STOP',8,-1),('TASK_DEAD',8,0),('EXIT_STOP',7,-1),('TASK_DEAD',7,0),('ALL_DEAD',7,-1),('COMPLETE',7,-1)]:wire(k,pid,n)
            ctl.step('stdout',b'');ctl.step('stderr',b'');ctl.step('audit')
            return ctl.finish()
        def terminal(*args):events.append('terminal');return (True,True,0,False if fault=='cleanup' else True,True,True)
        def close(fd):
            released.append(fd)
            if fault=='pin_close' and fd==30:raise OSError('mock retained pin close failed')
        with patch.object(C.configuration,'domain',lambda *a:'/owner'),patch.object(C.owner,'attest',lambda *a:True),patch.object(C.owner,'identity',identity),patch.object(C.owner.Path,'read_text',lambda *a,**kw:'5368709120'),patch.object(C.owner.fcntl,'fcntl',lambda *a:fcntl.FD_CLOEXEC),patch.object(C.N,'pidfd_identity',lambda *a:500),patch.object(C.channel,'attest',lambda *a:True),patch.object(C.channel.S,'validate_object',lambda *a:True),patch.object(C.placement,'receive',place),patch.object(C.N,'receive_audit',audit),patch.object(C.N,'LiveReader',Reader),patch.object(C.mapping,'verify',lambda *a:dict(status='PASS_FILE_IDENTITY',pid=7,start='s')),patch.object(C.mapping.SmallProc,'catalog',lambda *a:None),patch.object(C.Controller,'run',trace),patch.object(C.os,'close',close):
            # Catalog's default attester was bound at function definition.
            with patch.object(C.channel.Catalog.__init__,'__defaults__',(lambda *a:True,None)):
                try:
                    value=C.coordinate(ep,400,'100','e'*64,'mock',digest,policy,records,manifest,S(cgroup='/target'),None,10,11,writes.append,lambda r:True,lambda r:fault!='audit_persist',terminal,lambda *a:True)
                except (ValueError,OSError):
                    need(b'V' not in output,'failure emitted V')
                    if b'K' in output:need({30,31,32,33}<=set(released),'retained catalog leaked')
                    raise
        need(output==[b'O']+[b'C']*4+[b'K',b'P',b'A',b'V'],'full handshake sequence')
        need(writes==[b'GO\n',b'EXIT_ACK\n'] and {19,30,31,32,33}<=set(released),'token/FD cleanup missing')
        return value
    value=execute();ok('coordinator_actual_owner_bind_4FD_K_P_audit_GO_ACK_cleanup_V',value['status']=='PASS_SMALL_HARMLESS_PATH_ONLY')
    for fault in ('missing_owner','audit_gap','audit_disconnect','audit_persist','cleanup','pin_close','missing_descendant_FD'):reject('coordinator_fail_closed_'+fault,lambda:execute(fault))
    # Host path mocked throughout: no mkdir/marker/service/native action reaches OS.
    for fault in ('valid','owner_exit','collector_exit','owner_cleanup','target_cleanup','spawn'):
        c=copy.deepcopy(contract);c['files']={};mutations=[];calls=[]
        state=dict(Id=c['owner_unit'],Description=c['description'],InvocationID='inv',ControlGroup='/owner',MemoryMax='5368709120',LoadState='loaded')
        manager=Mock();lookups=[0]
        def inspect(name):
            lookups[0]+=1
            return dict(LoadState='not-found') if lookups[0]<=2 else state
        manager.inspect.side_effect=inspect
        proc=Mock();proc.returncode=1 if fault=='owner_exit' else 0;polls=[0]
        def poll():polls[0]+=1;return None if polls[0]==1 else proc.returncode
        proc.poll.side_effect=poll
        def spawn(*a,**kw):
            calls.append(a[0]);need(mutations and mutations[0][0]==c['marker'],'service before exclusive marker')
            if fault=='spawn':raise OSError('mock service client failed')
            return proc
        def own_clean(*a):
            mutations.append(('owner_cleanup',None))
            if fault=='owner_cleanup':raise ValueError('mock owner cleanup fail')
            return True
        def target_clean(*a):
            mutations.append(('target_cleanup',None))
            if fault=='target_cleanup':raise ValueError('mock target cleanup fail')
            return True
        with patch.object(D.Path,'exists',lambda p:False),patch.object(D.Path,'is_symlink',lambda p:False),patch.object(D.Path,'mkdir',lambda *a,**kw:mutations.append(('mkdir',None))),patch.object(D.Path,'open',lambda *a,**kw:io.BytesIO()),patch.object(D.Path,'stat',lambda p:S(st_size=0)),patch.object(D,'exclusive',lambda p,data:mutations.append((str(p),data))),patch.object(D.subprocess,'Popen',spawn),patch.object(D.time,'sleep',lambda n:None),patch.object(D,'cleanup_owner',own_clean),patch.object(D,'cleanup_target_owned',target_clean),patch.object(D,'json_read',lambda p:dict(status='FAIL' if fault=='collector_exit' else 'PASS_SMALL_HARMLESS_PATH_ONLY',owner_wait_returncode=0,target_cleanup=True)):
            rc=D.run_once(c,digest,manager)
        ok('host_driver_mock_'+fault,rc==(0 if fault=='valid' else 78))
        ok('host_always_attempts_both_cleanups_'+fault,all(any(x[0]==key for x in mutations) for key in ('owner_cleanup','target_cleanup')))
