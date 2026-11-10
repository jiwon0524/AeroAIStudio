"""Static and injected Python I/O mocks only. Never runs any output ELF."""
from pathlib import Path
import ast,copy,hashlib,json,os,sys
from types import SimpleNamespace
from unittest.mock import Mock,patch
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'scripts'))
import reconcile as A
import controller as C
N=C.N
checks=[]
def ok(name,condition=True):
    assert condition,name
    checks.append(dict(case=name,status='PASS_STATIC_MOCK'))
def reject(name,fn):
    try:fn()
    except (ValueError,OSError,KeyError,TypeError):ok(name)
    else:raise AssertionError(name)
data=A.analyze();saved=json.loads((R/'reports/reconciliation.json').read_text())
ok('reconciliation_repeatable',data==saved)
ok('bidirectional_counts',data['counts']==dict(required_paths=468,required_objects=303,compiled_paths=452,compiled_objects=298))
ok('difference_16_vs_0',len(data['required_minus_compiled'])==16 and not data['compiled_minus_required'])
reject('duplicate_alias_not_hidden',lambda:A.compare(['a'],['a','a']))
ok('unexpected_path_detected',A.compare(['a'],['b'])==(['a'],['b']))
for row in data['paths']:
    ok('path_evidence:'+row['path'],row['in_approved_sealed_contract'] and bool(row['required_by'] or row['native_roles'] or row['path']=='/input/joint-elf.sha256') and row['mount']['mode']=='ro-file-fd')
for obj in data['resources']['blocked_objects']:
    ok('large_object:'+obj['source'],obj['approved_contract_aliases'] and obj['decision']=='DENY_LIMIT_CHANGE_DEFERRED' and obj['preparation_known_lower_bound']>obj['current_object_limit'])
# Existing sealed factories and real Python NativeSession/ACK/Lines.
c,m,prior,seal=A.v5.old.load_verified();sys.path.insert(0,str(A.v5.old.snapshots.catalog.OLD/'scripts'));sys.modules['contract']=c
import source_loader
with source_loader.runtime(m) as (modules,loaded):
    scope=dict(m=m,AckWindow=modules['protocol'].AckWindow,AckSession=modules['protocol'].AckSession,NativeSession=modules['native_gate'].NativeSession)
    tree=ast.parse((A.v5.old.snapshots.catalog.OLD/'tests/test_contract.py').read_text())
    defs=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('packets','setup','ready')]
    exec(compile(ast.Module(body=defs,type_ignores=[]),'reused_sealed_factories','exec'),scope)
    class Reader:
        fd=900
        def __init__(self,journal):self.journal=journal;self.closed=False;self.queue=[];self.failed_drain=False
        def readable(self):
            raw=self.queue.pop(0)
            if raw is None:
                self.closed=True
                if not self.failed_drain:self.journal.eof()
            elif not self.failed_drain:
                try:self.journal.feed(raw)
                except Exception:self.failed_drain=True;raise
    def setup(terminal=(True,True,0,True,True,True),persist=lambda r:True):
        native,window,writes=scope['setup']()
        binding=dict(run='mock6',policy=seal,supervisor='synthetic',pid=100,start='s')
        owner=N.Owner(500,'owner','synthetic',100,'mock6',seal,'s',100,12)
        gate=N.old.AuditGate(native,binding,persist)
        j=N.NativeJournal(gate,owner,persist)
        # Capability comes from explicitly mocked OS provenance, not target data.
        with patch.object(N,'verify_endpoint',lambda fd,o:(7,9)):N.LiveReader(999,j)
        reader=Reader(j);acks=[]
        endpoint=SimpleNamespace(send=lambda b,flags:acks.append(b) or len(b),fileno=lambda:901)
        ctl=C.Controller(endpoint,reader,902,903,window,modules['protocol'].Lines,m,lambda:terminal)
        return ctl,j,writes,acks
    def wire(ctl,kind,pid=100,nr=-1):
        j=ctl.reader.journal
        ctl.reader.queue.append(f'{j.seq+1} {kind} {pid} {nr} {j.denied+(kind=="DENY")}\n'.encode());ctl.step('audit')
    def prefix(ctl):
        for k in ('PREEXEC_STOP','PREEXEC_ARMED','FILTER_BOUND','EXEC_STOP','TARGET_FDS'):wire(ctl,k,nr=5 if k=='TARGET_FDS' else -1)
    def packet(ctl,row):ctl.step('stdout',(json.dumps(row)+'\n').encode())
    def initialized(ctl,stderr_late=False):
        prefix(ctl)
        for p in scope['packets']():packet(ctl,p)
        proxy=SimpleNamespace(packet=lambda row:packet(ctl,row),stderr=lambda s:ctl.step('stderr',(s+'\n').encode()))
        scope['ready'](proxy)
        assert ctl.gate.go and not ctl.failed
    def sample(ctl):
        for i in range(1,101):
            t=i*.001;state={k:0 for k in ['x','y','z','vx','vy','vz','roll','pitch','yaw']};state.update(z=1-4.905*t*t,vz=-9.81*t)
            packet(ctl,dict(kind='sample',iteration=i,sim_time_ns=i*1000000,dt_ns=1000000,paused=False,native_frame=i,native_time=t,init_count=1,state_source='measured_live_components',state=state))
        packet(ctl,dict(kind='final_wait',iteration=100,sim_time_ns=100000000))
    def end(ctl,complete=True):
        wire(ctl,'EXIT_STOP');wire(ctl,'TASK_DEAD',nr=0);wire(ctl,'ALL_DEAD')
        if complete:wire(ctl,'COMPLETE')
        ctl.reader.queue.append(None);ctl.step('audit');ctl.step('stdout',b'');ctl.step('stderr',b'')
    ctl,j,writes,acks=setup();initialized(ctl);sample(ctl)
    ok('GO_and_last_live_mapping_EXIT_ACK_retained',writes==[b'GO\n',b'EXIT_ACK\n'])
    # Root dies first, descendants still issue concurrent requests and callbacks.
    wire(ctl,'TASK_BORN',101,100);wire(ctl,'TASK_BORN',102,101)
    wire(ctl,'TASK_DEAD',100,0)
    for pid in (101,102):wire(ctl,'REQUEST',pid,257)
    for pid,index in ((102,1),(101,0)):
        wire(ctl,'INPUT_OBJECT',pid,index);wire(ctl,'INPUT_PREPARED',pid,257);wire(ctl,'INPUT_DELIVERED',pid,257)
    ok('root_death_keeps_controller_and_concurrent_descendants',not ctl.failed and j.adapter.live=={101,102})
    for pid in (102,101):wire(ctl,'EXIT_STOP',pid);wire(ctl,'TASK_DEAD',pid,0)
    wire(ctl,'ALL_DEAD');wire(ctl,'COMPLETE')
    # Valid buffered stderr remains collectable after audit all_dead.
    ctl.step('stderr',b'buffered exit diagnostic\n')
    ctl.reader.queue.append(None);ctl.step('audit');ctl.step('stdout',b'');ctl.step('stderr',b'')
    ok('full_controller_original_protocol_final_PASS',ctl.finish()['status']=='PASS' and acks==[b'A',b'V'])
    for fault in ('denial','disconnect','missing_complete','loss','overflow','pending_death','bad_index','missing_binding','wrong_task','persist','bad_mapping','stderr_overflow','truncated_stdout','duplicate_key','bad_ack_send','missing_protocol_eof'):
        ctl,j,writes,acks=setup();initialized(ctl)
        if fault=='bad_mapping':ctl.window.observe=lambda:dict(status='WRONG',pid=7,start='s')
        sample(ctl)
        if fault=='denial':wire(ctl,'REQUEST',nr=59);wire(ctl,'DENY',nr=59);wire(ctl,'REPLIED_DENY',nr=59)
        elif fault=='disconnect':ctl.reader.queue.append(None);ctl.step('audit')
        elif fault=='loss':ctl.reader.queue.append(f'{j.seq+2} EXIT_STOP 100 -1 0\n'.encode());ctl.step('audit')
        elif fault=='overflow':ctl.reader.queue.append(b'x'*193);ctl.step('audit')
        elif fault=='pending_death':wire(ctl,'REQUEST',nr=257)
        elif fault=='bad_index':wire(ctl,'REQUEST',nr=257);wire(ctl,'INPUT_OBJECT',nr=452)
        elif fault=='missing_binding':wire(ctl,'REQUEST',nr=257);wire(ctl,'INPUT_PREPARED',nr=257)
        elif fault=='wrong_task':wire(ctl,'REQUEST',pid=12345,nr=257)
        elif fault=='persist':j.persist=lambda r:False;wire(ctl,'EXIT_STOP')
        elif fault=='stderr_overflow':ctl.step('stderr',b'x'*65537)
        elif fault=='truncated_stdout':ctl.step('stdout',b'{')
        elif fault=='duplicate_key':ctl.step('stdout',b'{"kind":"x","kind":"y"}\n')
        elif fault=='bad_ack_send':ctl.endpoint.send=lambda *a:0
        if not ctl.reader.closed:end(ctl,complete=fault!='missing_complete')
        if fault=='missing_protocol_eof':ctl.closed.discard('stdout')
        reject('controller_final_rejects_'+fault,ctl.finish)
        ok('never_V_'+fault,b'V' not in acks and ctl.failed)
    for count in range(5):
        ctl,j,writes,acks=setup()
        kinds=('PREEXEC_STOP','PREEXEC_ARMED','FILTER_BOUND','EXEC_STOP','TARGET_FDS')
        for k in kinds[:count]:wire(ctl,k)
        ctl.reader.queue.append(None);ctl.step('audit')
        reject('handoff_cut_'+str(count),ctl.finish)
        ok('handoff_cut_no_A_GO_'+str(count),not acks and not writes)
    # run() is exercised only with injected selectors/read/nonblocking/control IO.
    ctl,j,writes,acks=setup();initialized(ctl);sample(ctl)
    wire(ctl,'EXIT_STOP');wire(ctl,'TASK_DEAD',nr=0);wire(ctl,'ALL_DEAD');wire(ctl,'COMPLETE')
    ctl.reader.queue.append(None)
    class Poller:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def register(self,*a):pass
        def unregister(self,*a):pass
        def select(self,timeout):return [(SimpleNamespace(data=k,fd=fd),1) for k,fd in ctl.fds.items() if k not in ctl.closed]
    with patch.object(C.selectors,'DefaultSelector',Poller),patch.object(C.os,'get_blocking',lambda fd:False),patch.object(C.os,'read',lambda fd,n:b''),patch('select.poll',lambda:SimpleNamespace(register=lambda *a:None,poll=lambda n:[])):
        ok('active_poll_loop_mocked_all_streams',ctl.run()['status']=='PASS')
    ctl,j,writes,acks=setup();initialized(ctl);sample(ctl)
    class DisconnectPoller(Poller):
        def select(self,timeout):
            ctl.closed=set(ctl.fds);return []
    with patch.object(C.selectors,'DefaultSelector',DisconnectPoller),patch.object(C.os,'get_blocking',lambda fd:False),patch('select.poll',lambda:SimpleNamespace(register=lambda *a:None,poll=lambda n:[(901,16)])):
        reject('owner_disconnect_during_shutdown',ctl.run)
# Reuse v4 mocked FD operations and actual Catalog to reject alias/FD changes.
v4=A.v5.old
scope=dict(copy=copy)
tree=ast.parse((R.parent/'gazebo-request-guard-v4/tests/check.py').read_text())
node=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='MockFD')
exec(compile(ast.Module(body=[node],type_ignores=[]),'reused_MockFD','exec'),scope)
records=v4.classify(m,prior);historical={(r['original']['device'],r['original']['inode']):r for r in prior['objects']}
rep=next(r for r in records if r['prepared'] and len(r['aliases'])>1)
for fault in ('bad_alias','bad_FD','bad_hash','bad_source','writable_receipt','missing_required'):
    ops=scope['MockFD']();catalog=v4.Catalog(records,ops)
    receipt=copy.deepcopy(historical[rep['original']['device'],rep['original']['inode']]['receipt'])
    receipt['object']=dict(device=777,inode=1000,size=receipt['object']['size'])
    fd=ops.new(receipt)
    for p in rep['aliases']:ops.paths[p]=copy.deepcopy(receipt['object'])
    if fault=='bad_hash':receipt['sha256']='0'*64
    if fault=='bad_source':receipt['original']['inode']+=1
    if fault in ('bad_hash','bad_source'):
        reject('catalog_'+fault,lambda:catalog.bind(rep['aliases'][0],fd,receipt));continue
    catalog.bind(rep['aliases'][0],fd,receipt)
    path=rep['aliases'][1]
    if fault=='bad_alias':ops.paths[path]['inode']+=1
    elif fault=='bad_FD':ops.fds[fd]['object']['inode']+=1
    elif fault=='writable_receipt':ops.fds[fd]['executable_intent']=not receipt['executable_intent']
    elif fault=='missing_required':path=data['required_minus_compiled'][0]
    request=v4.Request(1,100,1,path,os.O_RDONLY)
    reject('catalog_'+fault,lambda:catalog.resolve(request))
# Same-FD final sealed-object validation; synthetic metadata/hash only.
S=v4.snapshots
receipt=copy.deepcopy(historical[rep['original']['device'],rep['original']['inode']]['receipt'])
for fault in ('valid','writable','wrong_inode','wrong_size','missing_seal','wrong_hash','wrong_exec'):
    st=SimpleNamespace(st_mode=0o100500 if receipt['executable_intent'] else 0o100400)
    ident=dict(receipt['object'])
    if fault=='wrong_inode':ident['inode']+=1
    if fault=='wrong_size':ident['size']+=1
    if fault=='wrong_exec':st.st_mode=(st.st_mode & ~0o111) if receipt['executable_intent'] else (st.st_mode | 0o111)
    def fcntl(fd,key):
        if key==S.fcntl.F_GETFL:return os.O_WRONLY if fault=='writable' else os.O_RDONLY
        return 0 if fault=='missing_seal' else S.REQUIRED_SEALS
    with patch.object(S.os,'fstat',lambda fd:st),patch.object(S,'identity',lambda fd:ident),patch.object(S.fcntl,'fcntl',fcntl),patch.object(S,'digest_fd',lambda fd:'0'*64 if fault=='wrong_hash' else receipt['sha256']):
        if fault=='valid':ok('final_sealed_FD_validation',S.validate_object(123,receipt))
        else:reject('final_sealed_FD_'+fault,lambda:S.validate_object(123,receipt))
# Reused handoff validates credentials/count/truncation and closes all rejected FDs.
import struct
for fault in ('valid','extra_fds','truncated','wrong_sender','wrong_payload'):
    closed=[];fds=[11,12,13] if fault=='extra_fds' else [11,12]
    peer=(999,10,20) if fault=='wrong_sender' else (500,10,20)
    payload=b'bad' if fault=='wrong_payload' else struct.pack('Q',100)
    flags=N.socket.MSG_CTRUNC if fault=='truncated' else 0
    message=(payload,[(N.socket.SOL_SOCKET,N.socket.SCM_RIGHTS,struct.pack(str(len(fds))+'i',*fds)),(N.socket.SOL_SOCKET,N.socket.SCM_CREDENTIALS,struct.pack('3i',*peer))],flags,None)
    endpoint=SimpleNamespace(recvmsg=lambda *a:message)
    fake=SimpleNamespace(geteuid=lambda:10,getegid=lambda:20,close=closed.append)
    with patch.object(N,'os',fake),patch.object(N,'pidfd_identity',lambda fd,native:100),patch.object(N,'start_id',lambda pid:'s'),patch.object(N,'verify_endpoint',lambda fd,o:(7,9)):
        call=lambda:N.receive_audit(endpoint,500,'owner','synthetic','mock6',seal)
        if fault=='valid':
            fd,owner=call();ok('handoff_exact_FDs_and_credential',fd==11 and owner.root==100 and not closed)
        else:
            reject('handoff_'+fault,call);ok('handoff_closes_rejected_FDs_'+fault,sorted(closed)==fds)
launch=(R/'inputs/launch.c').read_text();parent=(R.parent/'gazebo-request-guard-v5/inputs/catalog.c').read_text()
ok('full_catalog_gate_before_fork',launch.index('catalog_full_ready')<launch.index('pid_t child=fork'))
ok('native_loop_services_notifications_after_task_stop','/* Also service notifications' in launch and 'got>0?0:10' in launch)
ok('owner_disconnect_and_early_V_fail','if(p[2].revents&POLLIN) goto done;' in launch)
ok('no_limit_or_seal_relaxation', 'p->size>67108864' in parent and 'budget>536870912ULL' in parent and 'catalog_verify(rows+i,fd)' in parent)
baseline=json.loads((R/'work/baseline.json').read_text())
ok('all_old_tracked_files_preserved_except_handoff',all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in baseline['files'].items() if p!='handoff.md'))
ok('dangling_link_preserved',os.readlink('libgz-physics-dartsim-plugin.so')==baseline['link'] and not Path('libgz-physics-dartsim-plugin.so').exists())
import subprocess
base=json.loads((R.parent/'gazebo-request-guard-v5/work/preservation.json').read_text())
ok('prior_1767_evidence_baseline_preserved',all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in base['files'].items() if Path(p).name!='handoff.md'))
main='/home/jiwon/Projects/AeroAIStudio'
ok('main_HEAD_and_dirty_status_preserved',subprocess.check_output(['git','rev-parse','HEAD'],cwd=main,text=True).strip()==base['main_head'] and subprocess.check_output(['git','status','--porcelain'],cwd=main,text=True)==base['main_status'])
(R/'reports/tests.json').write_text(json.dumps(dict(status='PASS_STATIC_PYTHON_MOCK_ONLY',count=len(checks),checks=checks,native_execution=False,service_started=False,marker_consumed=False),indent=2)+'\n')
print('PASS',len(checks),'static/Python mock checks; no native runtime')
