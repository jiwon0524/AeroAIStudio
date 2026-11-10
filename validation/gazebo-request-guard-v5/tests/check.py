"""Static/native-wire/OS mocks. No C binary, namespace, fork, loader or harness run."""
from pathlib import Path
import ast,copy,hashlib,json,os,re,stat,struct,sys
from types import SimpleNamespace
from dataclasses import replace
from unittest.mock import Mock,patch
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'scripts'))
import plan
import native_audit as N
import launcher
checks=[]
def ok(name,yes=True):
    assert yes,name
    checks.append(dict(case=name,status='PASS_STATIC_MOCK'))
def reject(name,fn):
    try:fn()
    except (ValueError,OSError,KeyError,TypeError):checks.append(dict(case=name,status='PASS_REJECTED'))
    else:raise AssertionError(name)
c,m,prior,seal=plan.old.load_verified();records=plan.old.classify(m,prior)
pattern=re.compile(r'\{("(?:[^"\\]|\\.)*"),(\d+)ULL,(\d+)ULL,("[a-f0-9]{64}"),([01]),("(?:[^"\\]|\\.)*")\},')
policy=[]
for line in (R/'inputs/allowlist.inc').read_text().splitlines():
    match=pattern.fullmatch(line)
    if match:
        p,dev,ino,sha,ex,source=match.groups();p=json.loads(p)
        row=m['mounts'][p]
        ok('native_policy_row_'+str(len(policy)),[int(dev),int(ino),json.loads(sha),json.loads(source)]==[row['device'],row['inode'],row['sha256'],row['source']] and
           any(r['required'] and r['prepared'] and int(r['executable'])==int(ex) and p in r['aliases'] for r in records))
        policy.append(p)
ok('452_required_paths_no_optional_expansion',len(policy)==452)
resources=json.loads((R/'reports/resources.json').read_text())
ok('5_mandatory_budget_blockers_preserved',len(resources['blocked_objects'])==5 and all(x['required'] and not x['meets_current_preparation_limit'] for x in resources['blocked_objects']))
for x in resources['blocked_objects']:
    ok('resource_size_'+str(len(checks)),os.stat(x['source']).st_size==x['bytes'] and x['bytes']>x['current_object_limit'])
    ok('resource_lower_bound_'+str(len(checks)),x['known_output_plus_buffer_bytes']==x['page_rounded_output']+2*1048576 and x['exact_peak'].startswith('UNKNOWN'))
ok('target_limits_preserved',resources['target_limits_unchanged']==m['rlimits'])
ok('preparer_FD_floor_separate',resources['minimum_preparer_NOFILE']==308 and resources['minimum_supervisor_NOFILE']==311 and resources['target_NOFILE']==256)

binding=dict(run='mock-v5',policy=seal,supervisor='synthetic-pinned-native',pid=100,start='mock-root')
owner=N.Owner(500,'mock-owner',hashlib.sha256(b'producer').hexdigest(),100,'mock-v5',seal,'mock-root',100,12)
def setup(session=None,persist=None,bound=True):
    if session is None:
        session=Mock();session.finalize.return_value={'status':'PASS'}
    gate=N.old.AuditGate(session,binding,lambda row:True)
    rows=[]
    def save(row):
        if persist:return persist(row)
        rows.append(row);return True
    journal=N.NativeJournal(gate,owner,save)
    if bound:
        with patch.object(N,'verify_endpoint',lambda fd,o:(7,9)):N.LiveReader(999,journal)
    return journal,gate,rows
def row(j,kind,pid=None,nr=-1):
    if pid is None:pid=j.source_root
    j.feed(f'{j.seq+1} {kind} {pid} {nr} {j.denied+(kind=="DENY")}\n'.encode())
def prefix(j):
    for kind in ('PREEXEC_STOP','PREEXEC_ARMED','FILTER_BOUND','EXEC_STOP','TARGET_FDS'):
        row(j,kind,nr=5 if kind=='TARGET_FDS' else -1)
def finish(j):
    row(j,'TASK_DEAD',nr=0);row(j,'ALL_DEAD');row(j,'COMPLETE');j.eof()
j,g,raw=setup();prefix(j);g.authorize()
for index in range(452):
    row(j,'REQUEST',nr=257);row(j,'INPUT_OBJECT',nr=index)
    row(j,'INPUT_PREPARED',nr=257);row(j,'INPUT_DELIVERED',nr=257)
finish(j)
normal_wire=[r['raw'].encode() for r in raw]
ok('all452_native_wire_indices_bound_to_requests',len(j.delivered)==452 and [i for pid,i in j.delivered]==list(range(452)))
ok('native_wire_to_existing_adapter_final_PASS',g.finalize()['status']=='PASS')
ok('normal_wire_bounded',j.total<1048576)
j,g,_=setup(bound=False)
reject('target_bytes_without_private_endpoint_cannot_start',lambda:prefix(j))
reject('unbound_source_GO_denied',g.authorize)
for cut in range(5):
    j,g,_=setup()
    for kind in ('PREEXEC_STOP','PREEXEC_ARMED','FILTER_BOUND','EXEC_STOP','TARGET_FDS')[:cut]:row(j,kind)
    reject('GO_before_handoff_stage_'+str(cut),g.authorize)
for defect in ('wrong_order','loss','replay','early_EOF','truncated','overflow','wrong_root','bad_FD_clean_count'):
    j,g,_=setup()
    def bad():
        if defect=='wrong_order':row(j,'EXEC_STOP')
        elif defect=='loss':j.feed(b'2 PREEXEC_STOP 100 -1 0\n')
        elif defect=='replay':row(j,'PREEXEC_STOP');j.feed(b'1 PREEXEC_STOP 100 -1 0\n')
        elif defect=='early_EOF':j.eof()
        elif defect=='truncated':j.feed(b'1 PREEXEC_STOP 100 -1 0')
        elif defect=='overflow':j.feed(b'x'*193)
        elif defect=='wrong_root':row(j,'PREEXEC_STOP',pid=101)
        else:
            for k in ('PREEXEC_STOP','PREEXEC_ARMED','FILTER_BOUND','EXEC_STOP'):row(j,k)
            row(j,'TARGET_FDS',nr=6)
    reject('native_prelude_'+defect,bad)
    reject('bad_prelude_final_'+defect,g.finalize)
for bad in ('alias_index','no_object','object_replay','request_mismatch'):
    j,g,_=setup();prefix(j);g.authorize();row(j,'REQUEST',nr=257)
    if bad=='alias_index':reject(bad,lambda:row(j,'INPUT_OBJECT',nr=452))
    if bad=='no_object':reject(bad,lambda:row(j,'INPUT_PREPARED',nr=257))
    if bad=='object_replay':
        row(j,'INPUT_OBJECT',nr=0);reject(bad,lambda:row(j,'INPUT_OBJECT',nr=1))
    if bad=='request_mismatch':
        row(j,'INPUT_OBJECT',nr=0);reject(bad,lambda:row(j,'INPUT_PREPARED',nr=2))
for throws in (False,True):
    def fail(record):
        if throws:raise OSError('mock full channel')
        return False
    j,g,_=setup(persist=fail)
    reject('native_durability_failure_'+str(throws),lambda:prefix(j))
    reject('durability_failure_GO_'+str(throws),g.authorize)
j,g,_=setup();prefix(j);g.authorize()
row(j,'THREAD_ALLOWED',nr=56);row(j,'TASK_BORN',101,100);row(j,'TASK_BORN',102,101)
row(j,'REQUEST',101,257);row(j,'REQUEST',102,257)
for pid,index in ((102,1),(101,0)):
    row(j,'INPUT_OBJECT',pid,index);row(j,'INPUT_PREPARED',pid,257);row(j,'INPUT_DELIVERED',pid,257)
row(j,'TASK_DEAD',nr=0)
ok('root_terminal_keeps_descendants_collection',j.adapter.live=={101,102})
row(j,'TASK_DEAD',102,0);row(j,'TASK_DEAD',101,0);row(j,'ALL_DEAD');row(j,'COMPLETE');j.eof()
ok('concurrent_native_requests_all_task_death',g.finalize()['status']=='PASS')
j,g,_=setup();prefix(j);g.authorize();row(j,'THREAD_ALLOWED',nr=435)
row(j,'TASK_BORN',101,100);row(j,'TASK_DEAD',101,0);finish(j)
ok('clone3_snapshot_native_wire_supported',g.finalize()['status']=='PASS')
j,g,_=setup();prefix(j)
reject('unsupported_fork_thread_decision',lambda:row(j,'THREAD_ALLOWED',nr=57))
for fault in ('cancel','pending_death','thread_failure','late_denial','missing_COMPLETE'):
    j,g,_=setup();prefix(j);g.authorize()
    if fault=='thread_failure':row(j,'THREAD_ALLOWED',nr=56);row(j,'THREAD_FAILED',nr=-11)
    elif fault=='late_denial':row(j,'REQUEST',nr=59);row(j,'DENY',nr=59);row(j,'REPLIED_DENY',nr=59)
    elif fault in ('cancel','pending_death'):
        row(j,'REQUEST',nr=257)
        if fault=='cancel':row(j,'CANCELLED',nr=257)
    if fault=='missing_COMPLETE':
        row(j,'TASK_DEAD',nr=0);row(j,'ALL_DEAD');reject(fault,j.eof)
    else:finish(j)
    reject('final_failure_'+fault,g.finalize)

# Mock OS-level endpoint provenance checks. Never create/read an actual socket.
class Endpoint:
    def __init__(self,peer=(500,10,20),kind=N.socket.SOCK_SEQPACKET):self.peer,self.kind=peer,kind
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def getsockopt(self,level,key,length=None):
        return self.kind if key==N.socket.SO_TYPE else struct.pack('3i',*self.peer)
fake_os=SimpleNamespace(fstat=lambda fd:SimpleNamespace(st_mode=stat.S_IFSOCK,st_dev=7,st_ino=9),
    dup=lambda fd:fd,open=lambda *a:10,close=lambda fd:None,pread=lambda fd,n,off:b'producer' if off==0 else b'',
    geteuid=lambda:10,getegid=lambda:20,O_RDONLY=os.O_RDONLY,O_CLOEXEC=os.O_CLOEXEC)
with patch.object(N,'os',fake_os),patch.object(N,'pidfd_identity',lambda fd,native:100),patch.object(N,'start_id',lambda pid:'mock-owner' if pid==500 else 'mock-root'),patch.object(N.fcntl,'fcntl',lambda *a:N.fcntl.FD_CLOEXEC):
    with patch.object(N.socket,'socket',lambda **kw:Endpoint()):ok('private_peer_start_executable_checked',N.verify_endpoint(9,owner)==(7,9))
    for peer in ((100,10,20),(500,99,20),(500,10,99)):
        with patch.object(N.socket,'socket',lambda **kw:Endpoint(peer)):
            reject('audit_peer_mismatch_'+str(peer),lambda:N.verify_endpoint(9,owner))
    with patch.object(N.socket,'socket',lambda **kw:Endpoint(kind=N.socket.SOCK_STREAM)):
        reject('audit_wrong_socket_type',lambda:N.verify_endpoint(9,owner))
    with patch.object(N.socket,'socket',lambda **kw:Endpoint()):
        wrong=replace(owner,start='stale')
        reject('audit_owner_PID_reuse',lambda:N.verify_endpoint(9,wrong))
        wrong=replace(owner,executable_sha256='0'*64)
        reject('audit_untrusted_executable',lambda:N.verify_endpoint(9,wrong))

class ReadSocket:
    def __init__(self,queue):self.queue=queue
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def recvmsg(self,*args):return self.queue.pop(0)

for defect in ('truncation','early_disconnect','loss','overflow'):
    j,g,_=setup(bound=False)
    if defect=='truncation':first=(b'1 PREEXEC_STOP 100 -1 0\n',[],N.socket.MSG_TRUNC,None)
    elif defect=='early_disconnect':first=(b'',[],0,None)
    elif defect=='loss':first=(b'2 PREEXEC_STOP 100 -1 0\n',[],0,None)
    else:first=(b'x'*193,[],0,None)
    queue=[first,(b'discard after failure\n',[],0,None),(b'',[],0,None)]
    with patch.object(N,'verify_endpoint',lambda fd,o:(7,9)),patch.object(N,'os',fake_os),patch.object(N.socket,'socket',lambda **kw:ReadSocket(queue)):
        reader=N.LiveReader(999,j)
        reject('live_reader_'+defect,reader.readable)
        ok('failed_channel_continues_drain_'+defect,reader.readable() and reader.discarded>0)
        ok('failed_channel_EOF_no_success_'+defect,reader.readable() is False and reader.closed and g.failed)

j,g,_=setup(bound=False)
queue=[(r,[],0,None) for r in normal_wire]+[(b'',[],0,None)]
with patch.object(N,'verify_endpoint',lambda fd,o:(7,9)),patch.object(N,'os',fake_os),patch.object(N.socket,'socket',lambda **kw:ReadSocket(queue)):
    reader=N.LiveReader(999,j)
    for i in range(5):reader.readable()
    g.authorize()
    while queue:reader.readable()
    ok('live_reader_mock452_native_records_final_EOF',reader.closed and g.finalize()['status']=='PASS')

for fault in ('valid','extra_fds','truncated','wrong_sender','wrong_payload'):
    closed=[]
    fake=SimpleNamespace(**fake_os.__dict__);fake.close=closed.append
    fds=[11,12,13] if fault=='extra_fds' else [11,12]
    peer=(999,10,20) if fault=='wrong_sender' else (500,10,20)
    payload=b'bad' if fault=='wrong_payload' else struct.pack('Q',100)
    flags=N.socket.MSG_CTRUNC if fault=='truncated' else 0
    message=(payload,[(N.socket.SOL_SOCKET,N.socket.SCM_RIGHTS,struct.pack(str(len(fds))+'i',*fds)),
                      (N.socket.SOL_SOCKET,N.socket.SCM_CREDENTIALS,struct.pack('3i',*peer))],flags,None)
    endpoint=SimpleNamespace(recvmsg=lambda *a:message)
    with patch.object(N,'os',fake),patch.object(N,'pidfd_identity',lambda fd,native:100),patch.object(N,'start_id',lambda pid:'mock-root'),patch.object(N,'verify_endpoint',lambda fd,o:(7,9)):
        call=lambda:N.receive_audit(endpoint,500,'mock-owner',owner.executable_sha256,owner.run,seal)
        if fault=='valid':
            fd,bound_owner=call();ok('native_audit_FD_handoff_mock',fd==11 and bound_owner.root_start=='mock-root' and not closed)
        else:
            reject('audit_FD_handoff_'+fault,call)
            ok('handoff_error_closes_received_FDs_'+fault,sorted(closed)==fds)

ok('pidfd_namespace_translation',N.parse_pidfd_info('Pid:\t900\nNSpid:\t900 2\n',2)==900)
for text,native in [('Pid:\t-1\nNSpid:\t-1\n',2),('Pid:\t900\nNSpid:\t900 3\n',2),('pos:\t0\n',2)]:
    reject('pidfd_bad_mapping_'+str(len(checks)),lambda:N.parse_pidfd_info(text,native))
cross=replace(owner,native_root=2)
gate=N.old.AuditGate(Mock(),binding,lambda row:True);gate.session.finalize.return_value={'status':'PASS'}
j=N.NativeJournal(gate,cross,lambda row:True)
with patch.object(N,'verify_endpoint',lambda fd,o:(7,9)):N.LiveReader(999,j)
prefix(j);gate.authorize();finish(j)
ok('native_PID2_to_observer_PID100_adapter',gate.finalize()['status']=='PASS' and gate.binding['pid']==100 and j.adapter.root==2)

# Full existing sealed NativeSession/ACK protocol factories are reused.
sys.path.insert(0,str(plan.old.snapshots.catalog.OLD/'scripts'));sys.modules['contract']=c
import source_loader
with source_loader.runtime(m) as (modules,loaded):
    scope=dict(m=m,AckWindow=modules['protocol'].AckWindow,AckSession=modules['protocol'].AckSession,NativeSession=modules['native_gate'].NativeSession)
    defs=[x for x in ast.parse((plan.old.snapshots.catalog.OLD/'tests/test_contract.py').read_text()).body if isinstance(x,ast.FunctionDef) and x.name in ('packets','setup','ready')]
    exec(compile(ast.Module(body=defs,type_ignores=[]),'sealed_factories','exec'),scope)
    def protocol(denial=False,final=(True,True,0,True,True,True)):
        native,window,out=scope['setup']();j,g,_=setup(native);prefix(j)
        acks=[];endpoint=SimpleNamespace(send=lambda b,flags:acks.append(b) or len(b))
        reader=SimpleNamespace(journal=j,closed=False)
        N.collector_ready(endpoint,reader)
        for packet in scope['packets']():g.packet(packet)
        scope['ready'](g);g.authorize()
        for i in range(1,101):
            t=i*.001;state={k:0 for k in ['x','y','z','vx','vy','vz','roll','pitch','yaw']};state.update(z=1-4.905*t*t,vz=-9.81*t)
            g.packet(dict(kind='sample',iteration=i,sim_time_ns=i*1000000,dt_ns=1000000,paused=False,native_frame=i,native_time=t,init_count=1,state_source='measured_live_components',state=state))
        g.packet(dict(kind='final_wait',iteration=100,sim_time_ns=100000000));window.send_ack();assert out==[b'GO\n',b'EXIT_ACK\n']
        if denial:row(j,'REQUEST',nr=59);row(j,'DENY',nr=59);row(j,'REPLIED_DENY',nr=59)
        finish(j);reader.closed=True
        result=N.collector_verdict(endpoint,reader,final)
        assert acks==[b'A',b'V']
        return result
    ok('native_prelude_original_GO_last_mapping_ACK_EOF_cleanup',protocol()['status']=='PASS')
    reject('actual_mock_ACK_then_destructor_denial',lambda:protocol(True))
    for i,name in ((0,'stdout_EOF'),(1,'stderr_EOF'),(3,'cleanup'),(4,'integrity'),(5,'last_live_mapping')):
        a=[True,True,0,True,True,True];a[i]=False
        reject('old_'+name,lambda:protocol(final=tuple(a)))

catalog=(R/'inputs/catalog.c').read_text();launch=(R/'inputs/launch.c').read_text();broker=(R/'inputs/broker.c').read_text();control=(R/'inputs/control.c').read_text()
for name,yes in {
    'canonical_same_object_hash':'RESOLVE_IN_ROOT|RESOLVE_NO_MAGICLINKS|RESOLVE_NO_SYMLINKS' in catalog and 'catalog_verify(p,fd)' in catalog,
    'hash_final_FD_not_path':'EVP_DigestUpdate' in catalog and 'pread(fd,buffer' in catalog,
    'retained_native_factory_bounded':'int catalog_prepare' in catalog and 'admitted>budget' in catalog,
    'no_preparer_limit_changes':'setrlimit' not in catalog and 'getrlimit(RLIMIT_FSIZE' in catalog,
    'five_objects_cannot_be_hidden_by_subset':'COMPILED_PATHS!=FULL_REQUIRED_PATHS' in catalog,
    'full_catalog_gate_before_fork':launch.index('catalog_full_ready')<launch.index('pid_t child=fork()'),
    'original_payload_and_environment_bound':'strcmp(argv[0],TARGET_EXECUTABLE)' in launch and 'target_environment[envcount]' in launch,
    'private_noninherited_child_FDs':'close_range(7,~0U,0)' in launch and 'target_fds(child)' in launch,
    'listener_credentials_and_truncation':'SCM_CREDENTIALS' in launch and 'MSG_CMSG_CLOEXEC' in launch and 'MSG_TRUNC|MSG_CTRUNC' in launch,
    'ack_before_initial_exec':'phase==2 && ack_sent' in launch,
    'reexec_runtime_denied':'r.orig_rax=UINT64_MAX' in launch and 't->trace_mode=1' in launch,
    'legacy_clone_exact_and_reserved':'r.rdi==flags' in launch and 'c->live+reserved<64' in launch,
    'clone3_snapshot_rewritten_to_scalar_not_continued':'r.orig_rax=SYS_clone;r.rdi=a.flags' in launch and '!a.set_tid_size' in launch and 'a.stack<=UINT64_MAX-a.stack_size' in launch,
    'protocol_FDs_cannot_be_closed_or_reallocated':'SYS_close,0,7' in launch and 'BPF_JMP|BPF_JGE|BPF_K,5' in launch and 'OK(SYS_close)' not in launch,
    'native_source_after_sync':control.index('if(record(&j')<control.index('sent=send('),
    'native_input_policy_binding':'INPUT_OBJECT' in broker and 't->object_bound' in control,
    'FD_added_and_replied_atomically':'SECCOMP_ADDFD_FLAG_SEND' in broker and 'SECCOMP_USER_NOTIF_FLAG_CONTINUE' not in broker,
    'monitor_retains_until_real_terminal':'candidate_supervise' in launch and 'control_finish(c)' in launch,
    'launcher_stays78':launcher.preflight()['exit_code']==78 and not launcher.preflight()['service_started'],
}.items():ok(name,yes)
before=json.loads((R/'work/preservation.json').read_text());sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
ok('original_files_except_intended_handoff',all(sha(p)==h for p,h in before['files'].items() if Path(p)!=R.parents[1]/'handoff.md'))
import subprocess
main=Path('/home/jiwon/Projects/AeroAIStudio')
ok('main_HEAD_dirty_status_preserved',subprocess.check_output(['git','rev-parse','HEAD'],cwd=main,text=True).strip()==before['main_head'] and subprocess.check_output(['git','status','--porcelain'],cwd=main,text=True)==before['main_status'])
l=R.parents[1]/'libgz-physics-dartsim-plugin.so';st=l.lstat();ok('dangling_symlink_preserved',[st.st_dev,st.st_ino,os.readlink(l)]==before['symlink'])
(R/'reports/tests.json').write_text(json.dumps(dict(status='PASS_STATIC_MOCK_ONLY',count=len(checks),checks=checks,
    native_policy_paths=452,native_wire_model_paths=452,runtime_verified_inputs=0,native_execution=False,
    prior_686_reused_not_rerun=True,preserved_files=len(before['files'])),indent=2)+'\n')
print('PASS',len(checks),'static/mock checks; native policy452; runtime input0')
