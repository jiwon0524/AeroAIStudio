"""Interpret the actual small C bridge body with a synthetic FD table, and run
owner.bind with injected kernel/transport observations. No native code, socket,
namespace, service, real pidfd or bridge syscall is executed.
"""
from pathlib import Path
from itertools import permutations
from types import SimpleNamespace
from unittest.mock import patch
import copy,errno,fcntl,os,re,socket,struct,sys
R=Path(__file__).resolve().parents[1]

def bridge(ops,go,observation,diagnostic):
    source=(R/'inputs/owner_bridge.h').read_text()
    source=re.sub(r'/\*.*?\*/','',source,flags=re.S)
    body=source.split('static int owner_fd_bridge(',1)[1].split('{',1)[1].split('\n}',1)[0]
    lines=[line.strip() for line in body.splitlines() if line.strip()]
    labels={line[:-1]:i for i,line in enumerate(lines) if line.endswith(':')}
    env=dict(ops=ops,go=go,observation=observation,diagnostic=diagnostic)
    def expression(text):
        text=re.sub(r'\bin\b','_c_in',text)
        text=text.replace('ops->','ops.').replace('&&',' and ').replace('||',' or ')
        text=re.sub(r'!(?!=)',' not ',text)
        return eval(text,{'__builtins__':{}},env)
    def statement(line):
        if line.startswith('goto '):return ('jump',labels[line[5:]])
        if line.startswith('return '):return ('return',expression(line[7:]))
        assignment=re.fullmatch(r'(?:int )?(\w+)=(.*)',line)
        if assignment:env['_c_in' if assignment[1]=='in' else assignment[1]]=expression(assignment[2]);return ('next',None)
        raise AssertionError('unreviewed C bridge syntax: '+line)
    pc=0
    while pc<len(lines):
        line=lines[pc];pc+=1
        if line.endswith(':'):continue
        assert line.endswith(';'),line
        line=line[:-1]
        condition=re.fullmatch(r'if\((.*)\) (.*)',line)
        if condition:
            if not expression(condition[1]):continue
            line=condition[2]
        action,value=statement(line)
        if action=='jump':pc=value
        elif action=='return':return value
    raise AssertionError('bridge fell through')

class FDTable:
    def __init__(self,go=7,obs=8,diag=9,holes=(),fault=None):
        self.table={i:dict(kind='file',inode=900+i,mode='r',cloexec=False) for i in range(5) if i not in holes}
        self.table[go]=dict(kind='fifo',inode=101,mode='r',cloexec=True)
        self.table[obs]=dict(kind='fifo',inode=102,mode='w',cloexec=True)
        self.table[diag]=dict(kind='fifo',inode=103,mode='w',cloexec=True)
        self.table[70]=dict(kind='unrelated',inode=9999,mode='r',cloexec=True)
        self.start=copy.deepcopy(self.table);self.fault=fault;self.calls=[];self.count={};self.null_slot=None
    def hit(self,kind):
        self.count[kind]=self.count.get(kind,0)+1
        return self.fault==(kind,self.count[kind])
    def copy(self,fd):
        self.calls.append(('copy',fd))
        if self.hit('copy') or fd not in self.table:return -1
        new=10
        while new in self.table:new+=1
        self.table[new]=dict(self.table[fd],cloexec=True);return new
    def open_null(self):
        self.calls.append(('open_null',))
        if self.hit('open_null'):return -1
        new=0
        while new in self.table:new+=1
        self.null_slot=new;self.table[new]=dict(kind='null',inode=0,mode='r',cloexec=True);return new
    def close_once(self,fd):
        self.calls.append(('close',fd));fail=self.hit('close')
        # EINTR may leave close's outcome uncertain: never retry a number.
        self.table.pop(fd,None)
        return -1 if fail else 0
    def layout(self,slots,cloexec):
        try:rows=[self.table[i] for i in slots]
        except KeyError:return -1
        return 0 if rows[0]['kind']=='null' and all(row['kind']=='fifo' for row in rows[1:]) and [row['mode'] for row in rows]==['r','w','w','r','w'] and all(row['cloexec'] is cloexec for row in rows) and rows[1]['inode']==rows[2]['inode'] and len({rows[i]['inode'] for i in (2,3,4)})==3 else -1
    def source_check(self,go,obs,diag,null):
        self.calls.append(('source_check',))
        if self.hit('source_check'):return -1
        return self.layout([null,diag,diag,go,obs],True)
    def redirect(self,source,target):
        self.calls.append(('redirect',source,target))
        if self.hit('redirect') or source not in self.table:return -1
        self.table[target]=dict(self.table[source],cloexec=False);return target
    def final_check(self):
        self.calls.append(('final_check',))
        return -1 if self.hit('final_check') else self.layout([0,1,2,3,4],False)

def run(checks):
    def ok(name,yes=True):
        assert yes,name
        checks.append(dict(case=name,status='PASS_STATIC_MOCK'))
    def reject(name,fn):
        try:fn()
        except (ValueError,OSError,KeyError,TypeError):ok(name)
        else:raise AssertionError(name)
    def success(go,obs,diag,holes,tag):
        f=FDTable(go,obs,diag,holes);code=bridge(f,go,obs,diag)
        ok('bridge_layout_'+tag,code==0 and f.final_check()==0 and f.table[3]['inode']==101 and f.table[4]['inode']==102 and f.table[1]['inode']==f.table[2]['inode']==103 and f.table[70]==f.start[70] and all(fd not in f.table for fd in (go,obs,diag) if fd>4) and set(f.table)<=set(range(5))|{70})
    for mask in range(32):success(7,8,9,[i for i in range(5) if mask>>i&1],str(mask))
    for index,(go,obs,diag) in enumerate(permutations(range(8),3)):
        success(go,obs,diag,[i for i in range(5) if i not in (go,obs,diag)],'overlap_'+str(index))
    # Copy/open/check/each dup2/final check and every successful-path close fail.
    close_count=sum(c[0]=='close' for c in (lambda f: (bridge(f,7,8,9),f.calls)[1])(FDTable()))
    faults=[('copy',i) for i in range(1,5)]+[('open_null',1),('source_check',1),('final_check',1)]+[('redirect',i) for i in range(1,6)]+[('close',i) for i in range(1,close_count+1)]
    for fault in faults:
        f=FDTable(fault=fault);code=bridge(f,7,8,9)
        ok('bridge_failure_'+str(fault),code==78 and f.table[70]==f.start[70])
        closes=[c[1] for c in f.calls if c[0]=='close']
        ok('bridge_no_close_retry_'+str(fault),len(closes)==len(set(closes)))
        if fault[0] in ('copy','open_null','source_check','redirect','final_check'):
            ok('bridge_failure_preserves_original_high_sources_'+str(fault),all(f.table[i]==f.start[i] for i in (7,8,9)))
    for fault in ('missing','wrong_mode','same_pipe','aliased_roles'):
        f=FDTable()
        if fault=='missing':f.table.pop(7)
        elif fault=='wrong_mode':f.table[7]['mode']='w'
        elif fault=='same_pipe':f.table[8]['inode']=f.table[7]['inode']
        if fault=='aliased_roles':result=bridge(f,7,7,9)
        else:result=bridge(f,7,8,9)
        ok('bridge_rejects_'+fault,result==78 and not any(c[0]=='redirect' for c in f.calls))
    launch=(R/'inputs/launch.c').read_text()
    ok('native_bridge_uses_checked_interpreted_body','owner_fd_bridge(&ops,go,observation,diagnostic)' in launch and 'F_DUPFD_CLOEXEC,10' in launch and 'check_layout(fds,1)' in launch)
    ok('bootstrap_control_gate_before_prepare',launch.index('if(owner_control_fds(journal,collector)||initial_fds()')<launch.index('catalog_prepare(rows,COMPILED_PATHS,536870912ULL)',launch.index('pid_t candidate_owner_bootstrap')))
    for token in ('journal==collector','SOCK_SEQPACKET','O_NONBLOCK','O_APPEND','st.st_nlink!=1','st.st_size','FD_CLOEXEC','getpeername','AF_UNIX','SO_PEERCRED'):
        ok('bootstrap_control_contract_'+token,token in launch[launch.index('static int owner_control_fds'):launch.index('pid_t candidate_owner_bootstrap')])
    # Execute the actual native parent's ACK condition with fake poll/recv/kill.
    # This preserves its short-circuit order; no process or signal is created.
    import select,signal
    fragment='!sent||poll('+launch.split('if(!sent||poll(',1)[1].split(') {',1)[0]
    condition=fragment.replace('NULL','None').replace('\n',' ').replace('&p,','p,').replace('sizeof ack','2').replace('||',' or ').replace('&&',' and ')
    condition=re.sub(r'!(?!=)',' not ',condition)
    for fault in ('valid','send_failed','poll_error','timeout','missing_readiness','hup','error','invalid_fd','empty','extra_byte','wrong_token','recv_error','resume_failed'):
        events=select.POLLIN;messages=[];signals=[]
        if fault=='missing_readiness':events=0
        if fault=='hup':events|=select.POLLHUP
        if fault=='error':events|=select.POLLERR
        if fault=='invalid_fd':events|=select.POLLNVAL
        def poll(fd,count,timeout):return -1 if fault=='poll_error' else (0 if fault=='timeout' else 1)
        def recv(fd,ack,width,flags):
            messages.append(True);ack[0]='X' if fault=='wrong_token' else 'O'
            return {'empty':0,'extra_byte':2,'recv_error':-1}.get(fault,1)
        def syscall(number,fd,sig,info,flags):signals.append((fd,sig));return -1 if fault=='resume_failed' else 0
        env=dict(sent=fault!='send_failed',p=SimpleNamespace(revents=events),ack=['',''],collector=99,worker=501,
            poll=poll,recv=recv,syscall=syscall,fd=99,SYS_pidfd_send_signal=424,SIGCONT=signal.SIGCONT,MSG_DONTWAIT=socket.MSG_DONTWAIT,
            POLLIN=select.POLLIN,POLLHUP=select.POLLHUP,POLLERR=select.POLLERR,POLLNVAL=select.POLLNVAL)
        failed=bool(eval(condition,{'__builtins__':{}},env))
        ok('native_owner_ACK_'+fault,failed==(fault!='valid') and (not signals if fault not in ('valid','resume_failed') else signals==[(99,signal.SIGCONT)]))
    bootstrap=launch[launch.index('pid_t candidate_owner_bootstrap'):launch.index('#include "owner_bridge.h"')]
    ok('PID1_no_self_SIGSTOP','raise(SIGSTOP)' not in bootstrap and 'SYS_pidfd_send_signal,fd,SIGSTOP' in bootstrap)
    ok('PID1_ready_before_parent_stop',bootstrap.index('read(ready[0],&token,1)')<bootstrap.index('SYS_pidfd_send_signal,fd,SIGSTOP'))
    ok('PID1_handler_and_block_before_ready',bootstrap.index('sigaction(SIGCONT,&action')<bootstrap.index('write(ready[1],"R",1)') and 'sigsuspend(&suspend_mask)' in bootstrap)
    ok('PID1_wait_is_bounded_and_pidfd_bound',bootstrap.index('SYS_pidfd_open,worker,0')<bootstrap.index('waitpid(worker') and 'WUNTRACED|WNOHANG' in bootstrap and 'now.tv_sec-begin.tv_sec>=5' in bootstrap)
    failure=bootstrap[bootstrap.index('owner_failed:'):]
    ok('owner_failure_never_numeric_signal_after_reap','kill(worker' not in failure and 'SYS_pidfd_send_signal,fd,SIGKILL' in failure)
    readiness=bootstrap.split('if(poll(&r,1,5000)',1)[1].split(')goto owner_failed;',1)[0]
    readiness=('poll(&r,1,5000)'+readiness).replace('&r,','r,').replace('&token','token').replace('NULL','None').replace('\n',' ').replace('||',' or ').replace('&&',' and ')
    readiness=re.sub(r'!(?!=)',' not ',readiness)
    for fault in ('valid','ready_and_EOF','timeout','no_readiness','pipe_error','bad_fd','empty_ready','wrong_ready','stop_failed'):
        events=select.POLLIN;calls=[]
        if fault=='ready_and_EOF':events|=select.POLLHUP
        if fault=='no_readiness':events=select.POLLHUP
        if fault=='pipe_error':events|=select.POLLERR
        if fault=='bad_fd':events|=select.POLLNVAL
        class Token:
            def __init__(self):self.value=''
            def __eq__(self,other):return self.value==other
            def __ne__(self,other):return self.value!=other
        token=Token()
        def read(fd,dst,size):dst.value='X' if fault=='wrong_ready' else 'R';return 0 if fault=='empty_ready' else 1
        def stop(number,fd,sig,info,flags):calls.append((fd,sig));return -1 if fault=='stop_failed' else 0
        env=dict(poll=lambda *a:0 if fault=='timeout' else 1,r=SimpleNamespace(revents=events),ready=[30,31],token=token,read=read,
            syscall=stop,SYS_pidfd_send_signal=424,fd=99,SIGSTOP=signal.SIGSTOP,POLLIN=select.POLLIN,POLLERR=select.POLLERR,POLLNVAL=select.POLLNVAL)
        failed=bool(eval(readiness,{'__builtins__':{}},env))
        ok('PID1_ready_gate_'+fault,failed==(fault not in ('valid','ready_and_EOF')) and (not calls if fault not in ('valid','ready_and_EOF','stop_failed') else calls==[(99,signal.SIGSTOP)]))
    stop_condition=re.search(r'if\((!WIFSTOPPED\(status\).*?)\)goto owner_failed;',bootstrap,re.S)[1].replace('||',' or ')
    stop_condition=re.sub(r'!(?!=)',' not ',stop_condition)
    for stopped,stop_signal in ((True,signal.SIGSTOP),(True,signal.SIGTRAP),(False,0),(False,signal.SIGKILL)):
        ok('PID1_terminal_wait_gate_'+str((stopped,stop_signal)),bool(eval(stop_condition,{'__builtins__':{}},dict(status=(stopped,stop_signal),WIFSTOPPED=lambda status:status[0],WSTOPSIG=lambda status:status[1],SIGSTOP=signal.SIGSTOP)))==(not stopped or stop_signal!=signal.SIGSTOP))
    # Actual owner.bind implementation with all OS/transport operations injected.
    import owner as O
    parent=500;worker=501;parent_start='100';worker_start='101';sha='a'*64;policy='b'*64
    def scenario(fault=None):
        frames=[];closed=[];events=[];reads=0;ids={};attempts={}
        credentials=(parent,os.geteuid(),os.getegid());rights=[20];flags=0
        data=b'OWNERV8\0'+struct.pack('Q',1)
        if fault=='missing_fd':rights=[]
        if fault=='extra_fd':rights=[20,21]
        if fault=='wrong_credential':credentials=(999,os.geteuid(),os.getegid())
        if fault=='wrong_uid':credentials=(parent,os.geteuid()+1,os.getegid())
        if fault=='wrong_gid':credentials=(parent,os.geteuid(),os.getegid()+1)
        if fault=='truncated':flags=socket.MSG_CTRUNC
        if fault=='payload':data=b'bad'
        if fault=='early_EOF':data=b''
        if fault=='native_pid':data=b'OWNERV8\0'+struct.pack('Q',2)
        ancillary=[(socket.SOL_SOCKET,socket.SCM_CREDENTIALS,struct.pack('3i',*credentials))]
        if rights:ancillary.append((socket.SOL_SOCKET,socket.SCM_RIGHTS,struct.pack(str(len(rights))+'i',*rights)))
        if fault=='malformed_credential':ancillary[0]=(socket.SOL_SOCKET,socket.SCM_CREDENTIALS,b'bad')
        if fault=='duplicate_credential':ancillary.append(ancillary[0])
        if fault=='malformed_rights':ancillary.append((socket.SOL_SOCKET,socket.SCM_RIGHTS,b'x'))
        if fault=='unknown_ancillary':ancillary.insert(0,(999,999,b'bad'))
        def close(fd):
            closed.append(fd);events.append(('close',fd))
            if fault in ('close_failure','extra_close_failure') and fd==20:raise OSError(errno.EINTR,'mock close uncertainty')
        def observe(pid):
            ids[pid]=ids.get(pid,0)+1
            row=dict(pid=pid,start=parent_start if pid==parent else worker_start,ppid=1 if pid==parent else parent,state='R' if pid==parent else 'T',cgroup='/owner')
            if fault=='wrong_parent_start' and pid==parent:row['start']='102'
            if fault=='wrong_ppid' and pid==worker:row['ppid']=999
            if fault=='not_held' and pid==worker:row['state']='R'
            if fault=='wrong_domain' and pid==worker:row['cgroup']='/target'
            if ids[pid]>1:
                if fault=='parent_reused' and pid==parent:row['start']='102'
                if fault=='worker_reused' and pid==worker:row['start']='103'
                if fault=='migrated' and pid==worker:row['cgroup']='/other'
                if fault=='resumed' and pid==worker:row['state']='R'
            return row
        def attest(pid,start,exe):return not ((fault=='parent_elf' and pid==parent) or (fault=='worker_elf' and pid==worker))
        def limit(path):
            nonlocal reads
            reads+=1
            if fault=='limit_unreadable':raise OSError('mock cgroup not visible')
            return {'unbounded':'max','limit_high':'5368709120','zero_limit':'0'}.get(fault,'268435456' if fault=='changed_limit' and reads>1 else '536870912')
        def pidfd(fd,native):
            attempts['pidfd']=attempts.get('pidfd',0)+1
            if fault=='not_pidfd':raise ValueError('mock wrong FD type')
            return 999 if fault=='pidfd_changed' and attempts['pidfd']>1 else worker
        if fault=='extra_close_failure':ancillary.append((socket.SOL_SOCKET,socket.SCM_RIGHTS,struct.pack('i',21)))
        class Endpoint:
            def recvmsg(self,*args):return data,ancillary,flags,None
            def send(self,value,*args):
                events.append(('send',value))
                if fault=='send_failure':raise OSError('mock peer disconnected')
                if fault=='short_send':return 0
                frames.append(value);return len(value)
        audit=SimpleNamespace(pidfd_identity=pidfd,Owner=lambda *args:SimpleNamespace(pid=args[0],root=args[3],run=args[4],policy=args[5]))
        cap=5368709120 if fault=='unapproved_ceiling' else 536870912
        group='/owner/../target' if fault=='invalid_group' else '/owner'
        with patch.object(O,'identity',observe),patch.object(O,'attest',attest),patch.object(O.os,'close',close),patch.object(O.fcntl,'fcntl',lambda *a:0 if fault=='not_cloexec' else fcntl.FD_CLOEXEC),patch.object(O.Path,'read_text',limit):
            try:result=O.bind(Endpoint(),parent,parent_start,sha,group,'run',policy,audit,cap)
            except Exception:
                assert not frames,'rejected handoff delivered success ACK'
                assert len(closed)==len(set(closed)),'received pidfd close retried'
                if fault not in ('unapproved_ceiling','invalid_group'):
                    expected={20,21} if fault in ('extra_fd','extra_close_failure') else (set() if fault=='missing_fd' else {20})
                    assert set(closed)==expected,'rejected handoff leaked installed rights'
                raise
        return result,frames,closed,events
    result,frames,closed,events=scenario()
    ok('owner_valid_identity_only_ACK_after_fd_release',result.pid==worker and result.root==0 and frames==[b'O'] and events.index(('close',20))<events.index(('send',b'O')) and closed==[20])
    for fault in ('missing_fd','extra_fd','wrong_credential','wrong_uid','wrong_gid','early_EOF','truncated','payload','native_pid','malformed_credential','duplicate_credential','malformed_rights','unknown_ancillary','wrong_parent_start','wrong_ppid','not_held','wrong_domain','parent_reused','worker_reused','migrated','resumed','parent_elf','worker_elf','limit_unreadable','unbounded','limit_high','zero_limit','changed_limit','not_pidfd','pidfd_changed','not_cloexec','close_failure','extra_close_failure','send_failure','short_send','unapproved_ceiling','invalid_group'):
        reject('owner_rejects_'+fault,lambda:scenario(fault))
    ok('owner_declares_identity_not_preparation','NOT preparation' in (R/'scripts/owner.py').read_text())
