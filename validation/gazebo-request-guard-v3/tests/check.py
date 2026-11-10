"""Static/Python mocks only; no native binary, filter, mapping, target or service."""
from pathlib import Path
import ast
import copy
import hashlib
import importlib.util
import json
import os
import stat
import struct
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R/'scripts'))
import snapshots as S
import policy
import launcher
path=R.parent/'gazebo-request-guard-v2/scripts/journal.py'
spec=importlib.util.spec_from_file_location('v2_journal',path)
J=importlib.util.module_from_spec(spec);spec.loader.exec_module(J)
checks=[]
def ok(name, result):
    assert result,name
    checks.append(dict(case=name,status='PASS_STATIC_MOCK'))
def reject(name,fn):
    try:fn()
    except (ValueError,OSError,KeyError,TypeError):checks.append(dict(case=name,status='PASS_REJECTED'))
    else:raise AssertionError(name)

class FakeIO:
    """Mock filesystem/FD operations; no kernel actions during these tests."""
    O_RDONLY=os.O_RDONLY;O_CLOEXEC=os.O_CLOEXEC;O_NOFOLLOW=os.O_NOFOLLOW
    O_ACCMODE=os.O_ACCMODE;O_PATH=os.O_PATH
    MFD_ALLOW_SEALING=os.MFD_ALLOW_SEALING;MFD_CLOEXEC=os.MFD_CLOEXEC
    def __init__(self, corrupt=False, seals=True, feature=True, mutate=False):
        self.data={1:bytearray(b'approved')};self.closed=[];self.log=[]
        self.corrupt,self.seals,self.feature,self.mutate=corrupt,seals,feature,mutate
        self.bits=0;self.read_count=0
    def open(self,path,flags):
        self.log.append(('open',path))
        return 3 if path.startswith('/proc/') else 1
    def memfd_create(self,name,flags):
        self.log.append(('create',flags))
        if not self.feature:raise OSError('unsupported flags')
        self.data[2]=bytearray();return 2
    def fchmod(self,fd,mode):self.mode=stat.S_IFREG|mode
    def fstat(self,fd):
        fd=2 if fd==3 else fd
        return SimpleNamespace(st_dev=10 if fd==1 else 20,st_ino=fd,st_size=len(self.data[fd]),
            st_mode=stat.S_IFREG|0o400 if fd==1 else self.mode)
    def pread(self,fd,n,off):
        self.log.append(('read',fd))
        fd=2 if fd==3 else fd
        if fd==1:
            self.read_count+=1
            if self.mutate and self.read_count>1:self.data[1][:]=b'changed!'
        return bytes(self.data[fd][off:off+n])
    def pwrite(self,fd,b,off):
        self.data[fd][off:off+len(b)]=b'corrupt!' if self.corrupt else b
        return len(b)
    def close(self,fd):self.closed.append(fd)
    def readlink(self,path):return '/memfd:aero-input (deleted)'
    def fcntl(self,fd,op,arg=None):
        if op==S.fcntl.F_ADD_SEALS:
            self.log.append(('seal',arg));self.bits=arg if self.seals else 0;return 0
        if op==S.fcntl.F_GET_SEALS:return self.bits
        if op==S.fcntl.F_GETFL:return os.O_RDONLY
        raise AssertionError(op)

desc=dict(source='/source',device=10,inode=1,sha256=hashlib.sha256(b'approved').hexdigest())
def fake_copy(fake, executable=False, limit=100):
    def check(fd,row):
        st=fake.fstat(fd)
        if (st.st_dev,st.st_ino)!=(row['device'],row['inode']):raise ValueError('source identity')
        if hashlib.sha256(fake.pread(fd,100,0)).hexdigest()!=row['sha256']:raise ValueError('source hash')
    with patch.object(S,'os',fake),patch.object(S.fcntl,'fcntl',fake.fcntl),patch.object(S,'elf_interpreter',lambda fd:'/lib64/ld-linux-x86-64.so.2'):
        fd,receipt=S.copy_one(desc,check,executable,limit)
        S.validate_object(fd,receipt)
        return fd,receipt

fake=FakeIO();fd,receipt=fake_copy(fake)
ok('final_immutable_copy_hash_equals_parent_contract',receipt['sha256']==desc['sha256'])
ok('copy_identity_differs_and_original_preserved',receipt['object']['device']!=desc['device'] and receipt['original']['inode']==1)
ok('writable_copy_fd_closed_before_return',2 in fake.closed and 3 not in fake.closed)
seal_index=next(i for i,v in enumerate(fake.log) if v[0]=='seal')
ok('hash_reads_final_object_after_seal',any(v==('read',3) for v in fake.log[seal_index+1:]))
for name, fake in [('corrupt_copy',FakeIO(corrupt=True)),('missing_seals',FakeIO(seals=False)),
                   ('missing_memfd_feature',FakeIO(feature=False)),('source_mutation',FakeIO(mutate=True))]:
    reject(name,lambda:fake_copy(fake))
    ok(name+'_closes_all_owned_fds',1 in fake.closed and (2 not in fake.data or 2 in fake.closed))
reject('oversized_copy_admission',lambda:fake_copy(FakeIO(),limit=4))
fake=FakeIO();fake.data[1][:]=b'changed!'
reject('changed_original_before_preparation',lambda:fake_copy(fake))
elf=bytearray(180);elf[:6]=b'\x7fELF\x02\x01'
struct.pack_into('<H',elf,18,62);struct.pack_into('<Q',elf,32,64)
struct.pack_into('<HH',elf,54,56,1);struct.pack_into('<I',elf,64,3)
interp=b'/lib64/ld-linux-x86-64.so.2\0'
struct.pack_into('<Q',elf,72,120);struct.pack_into('<Q',elf,96,len(interp));elf[120:120+len(interp)]=interp
fake=FakeIO();fake.mode=stat.S_IFREG|0o500;fake.data[2]=elf
with patch.object(S,'os',fake):
    ok('PT_INTERP_read_as_bytes_without_loading',S.elf_interpreter(2)=='/lib64/ld-linux-x86-64.so.2')
    fake.data[2][5]=2
    reject('unsupported_ELF_encoding',lambda:S.elf_interpreter(2))
fake=FakeIO();fd,receipt=fake_copy(fake,True)
ok('ELF_explicit_exec_intent_not_implicit_default',any(v==('create',os.MFD_ALLOW_SEALING|os.MFD_CLOEXEC|S.MFD_EXEC) for v in fake.log))
fake=FakeIO();fd,receipt=fake_copy(fake)
with patch.object(S,'os',fake),patch.object(S.fcntl,'fcntl',fake.fcntl):
    other=copy.deepcopy(receipt);other['object']['inode']=999
    reject('wrong_copy_object',lambda:S.validate_object(fd,other))
    other=copy.deepcopy(receipt);other['sha256']='0'*64
    reject('wrong_sealed_copy_hash',lambda:S.validate_object(fd,other))
    other=copy.deepcopy(receipt);other['executable_intent']=True
    reject('wrong_exec_mode',lambda:S.validate_object(fd,other))

mount=dict(desc,real_path='/source')
manifest=dict(mounts={'/a':mount,'/alias':dict(mount)},elfs={'/a':{}})
group=S.groups(manifest)[0]
ok('same_inode_aliases_share_one_executable_object',len(S.groups(manifest))==1 and group['executable'])
table={a:receipt['object'] for a in group['aliases']}
ok('alias_table_same_pinned_object',S.check_aliases(group,receipt,table))
wrong=copy.deepcopy(table);wrong['/alias']['inode']=999
reject('alias_substitution',lambda:S.check_aliases(group,receipt,wrong))
reject('missing_alias',lambda:S.check_aliases(group,receipt,{'/a':receipt['object']}))
wrong=copy.deepcopy(manifest);wrong['mounts']['/alias']['sha256']='0'*64
reject('same_original_inode_conflicting_hash',lambda:S.groups(wrong))
other=copy.deepcopy(manifest);other['mounts']['/alias']['inode']=2
ok('same_bytes_distinct_original_objects_not_merged',len(S.groups(other))==2)

logical={'logical_path':'/a'}
ok('normal_open_plan_requires_object_and_canonical_delivery',policy.request_plan('openat',path='/a',row=logical,copy_verified=True,canonical_delivery=True)=='PLAN_ATOMIC_READONLY_FD_DELIVERY')
for flags in (1,2,0x40,0x200,0x200000):
    ok('forbidden_open_flags_'+str(flags),policy.request_plan('openat',path='/a',row=logical,copy_verified=True,canonical_delivery=True,flags=flags)=='DENY_ACCESS_MODE')
ok('sealed_copy_alone_does_not_allow_path',policy.request_plan('openat',path='/a',row=logical,copy_verified=True)=='BLOCKED_PATH_AND_IDENTITY_DELIVERY')
ok('wrong_logical_alias_denied',policy.request_plan('openat',path='/other',row=logical)=='DENY_UNKNOWN_PATH')
for kind in ('newfstatat','fstat','statx','access','readlink','read','pread64','close','mmap_file_exec',
             'mprotect_exec','clone','clone3','fork','futex','execveat'):
    ok(kind+'_unverified_path_stays_blocked',policy.request_plan(kind).startswith('BLOCKED'))
ok('unknown_request_default_denied',policy.request_plan('io_uring_setup')=='DENY_UNKNOWN_REQUEST')
for key in policy.REQUIRED:
    evidence={k:True for k in policy.REQUIRED};evidence[key]=False
    reject('preexec_missing_'+key,lambda:policy.deployment_ready(evidence))
reject('complete_mock_booleans_do_not_release',lambda:policy.deployment_ready({k:True for k in policy.REQUIRED}))

proof=dict(pre_loader=True,fd_attested=True,policy_applied=True,journal_private=True,lifetime_tracking=True)
binding=dict(run='mock-v3',policy='copy-contract-mock',supervisor='mock',pid=100,start='mock')
def setup():
    session=Mock();session.finalize.return_value={'status':'PASS'}
    gate=J.AuditGate(session,binding,lambda r:True)
    return J.JournalAdapter(gate,100,dict(proof)),gate
def row(j,kind,pid=100,nr=-1):j.feed(f'{j.seq+1} {kind} {pid} {nr} {j.denied+(kind=="DENY")}\n'.encode())
def finish(j):
    row(j,'TASK_DEAD',nr=0);row(j,'ALL_DEAD');row(j,'COMPLETE');j.eof()
j,g=setup();row(j,'EXEC_STOP');g.authorize()
row(j,'TASK_BORN',101,100);row(j,'TASK_BORN',102,101)
for pid in (101,102):row(j,'REQUEST',pid,257)
for pid in (102,101):
    row(j,'INPUT_PREPARED',pid,257);row(j,'INPUT_DELIVERED',pid,257);row(j,'TASK_DEAD',pid,0)
finish(j);ok('concurrent_alias_requests_all_tasks_complete',g.finalize()['status']=='PASS')
for phase in ('initialization','running','post_EXIT_ACK'):
    j,g=setup();row(j,'EXEC_STOP')
    if phase!='initialization':g.authorize()
    row(j,'REQUEST',nr=41);row(j,'DENY',nr=41);row(j,'REPLIED_DENY',nr=41);finish(j)
    ok(phase+'_denial_audit_still_drains',j.closed)
    reject(phase+'_violation_cannot_be_forgiven',g.finalize)
for stage in ('before_exec','after_exec','post_ACK'):
    j,g=setup()
    if stage!='before_exec':row(j,'EXEC_STOP')
    reject(stage+'_audit_disconnect',j.eof)
    reject(stage+'_no_final_success',g.finalize)
j,g=setup();row(j,'EXEC_STOP');row(j,'REQUEST',nr=257);row(j,'CANCELLED',nr=257);finish(j)
reject('request_thread_exit_cancelled_fails',g.finalize)
j,g=setup();row(j,'EXEC_STOP');row(j,'TASK_BORN',101,100);row(j,'TASK_DEAD',nr=0)
reject('remaining_child_blocks_final_receipt',lambda:row(j,'ALL_DEAD'))
for raw in (b'2 EXEC_STOP 100 -1 0\n',b'1 LOST 100 -1 0\n',b'x'*193,b'1 EXEC_STOP 100 -1 0'):
    j,g=setup();reject('journal_loss_or_overflow_'+str(len(checks)),lambda:j.feed(raw))

# Full original protocol source reused, no legacy report output modified.
c,m,seal=S.catalog.load_contract()
sys.path.insert(0,str(S.catalog.OLD/'scripts'));sys.modules['contract']=c
import source_loader
with source_loader.runtime(m) as (modules,loaded):
    scope=dict(m=m,AckWindow=modules['protocol'].AckWindow,AckSession=modules['protocol'].AckSession,
               NativeSession=modules['native_gate'].NativeSession)
    defs=[n for n in ast.parse((S.catalog.OLD/'tests/test_contract.py').read_text()).body
          if isinstance(n,ast.FunctionDef) and n.name in ('packets','setup','ready')]
    exec(compile(ast.Module(body=defs,type_ignores=[]),'sealed_factories','exec'),scope)
    def protocol(denial=False,final=(True,True,0,True,True,True)):
        native,window,out=scope['setup']();g=J.AuditGate(native,binding,lambda r:True)
        j=J.JournalAdapter(g,100,dict(proof));row(j,'EXEC_STOP')
        for packet in scope['packets']():g.packet(packet)
        scope['ready'](g);g.authorize()
        for i in range(1,101):
            t=i*.001;state={k:0 for k in ['x','y','z','vx','vy','vz','roll','pitch','yaw']}
            state.update(z=1-4.905*t*t,vz=-9.81*t)
            g.packet(dict(kind='sample',iteration=i,sim_time_ns=i*1000000,dt_ns=1000000,paused=False,
                          native_frame=i,native_time=t,init_count=1,state_source='measured_live_components',state=state))
        g.packet(dict(kind='final_wait',iteration=100,sim_time_ns=100000000));window.send_ack()
        assert out==[b'GO\n',b'EXIT_ACK\n']
        if denial:row(j,'REQUEST',nr=41);row(j,'DENY',nr=41);row(j,'REPLIED_DENY',nr=41)
        finish(j);return g.finalize(*final)
    ok('GO_100samples_last_live_mapping_ACK_EOF_cleanup_retained',protocol()['status']=='PASS')
    reject('actual_mock_ACK_then_shutdown_denial',lambda:protocol(True))
    for idx,name in ((0,'stdout_EOF'),(1,'stderr_EOF'),(3,'cleanup'),(4,'integrity'),(5,'last_live_mapping')):
        args=[True,True,0,True,True,True];args[idx]=False
        reject('original_'+name+'_refusal',lambda:protocol(final=tuple(args)))
    # Original mapping_entry rejects anonymous memfd spelling regardless of
    # matching copied bytes/inode. Never relax this to accept a new candidate.
    mapped=modules['common'].mapped
    reject('old_mapping_rejects_deleted_memfd',lambda:mapped.mapping_entry(
        {'path':'/memfd:aero (deleted)','device':20,'inode':2},[]))

copy_report=json.loads((R/'reports/copy_contract.json').read_text())
ok('594_input_aliases_accounted',copy_report['aliases_total']==594)
ok('no_blanket_input_permission',copy_report['allowed_aliases']==0 and all(not g['allowed_for_target'] for g in copy_report['objects']))
ok('closed_preparation_FDs_not_reusable_contract',all(not g['object_retained'] for g in copy_report['objects']))
broker=(R/'inputs/broker.c').read_text()
for name,check in {
    'compiled_broker_requires_delivery_proof':'!p->delivery_ready' in broker,
    'atomic_FD_reply_retained':'SECCOMP_ADDFD_FLAG_SEND' in broker,
    'no_pointer_CONTINUE':'SECCOMP_USER_NOTIF_FLAG_CONTINUE' not in broker,
    'immutable_copied_inode_and_mode':'F_SEAL_EXEC' in broker and '(uint64_t)st.st_ino==ino' in broker,
    'loader_exec_thread_not_silently_allowed':'DIRECT(SYS_clone)' not in broker and 'DIRECT(SYS_execve)' not in broker,
    'native_refusal_entry':(R/'inputs/entry.c').read_text().endswith('int main(void) { return 78; }\n'),
}.items():ok(name,check)
ok('launcher_before_service_marker_refusal',launcher.preflight()['exit_code']==78 and not launcher.preflight()['service_started'])

before=json.loads((R/'work/preservation.json').read_text());sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
ok('original_files_preserved_except_intended_handoff',all(sha(p)==v for p,v in before['files'].items() if Path(p)!=R.parents[1]/'handoff.md'))
main=Path('/home/jiwon/Projects/AeroAIStudio')
ok('main_HEAD_and_dirty_status_preserved',subprocess.check_output(['git','rev-parse','HEAD'],cwd=main,text=True).strip()==before['main_head'] and subprocess.check_output(['git','status','--porcelain'],cwd=main,text=True)==before['main_status'])
link=R.parents[1]/'libgz-physics-dartsim-plugin.so';st=link.lstat()
ok('dangling_symlink_preserved',[st.st_dev,st.st_ino,os.readlink(link)]==before['symlink'])
(R/'reports/tests.json').write_text(json.dumps(dict(status='PASS_STATIC_MOCK_ONLY',count=len(checks),checks=checks,
    native_execution=False,copy_tests='FAKE_IO_ONLY; actual preparation separately reported',preserved_files=len(before['files']),
    prior_results_not_rerun_or_summed=[84,70]),indent=2)+'\n')
print('PASS',len(checks),'static/mock checks; no native execution')
