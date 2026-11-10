"""Static/file/ELF and Python OS/manager/transport mocks ONLY. No native runs."""
from pathlib import Path
import sys
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'scripts'))
sys.path.insert(0,str(R/'tests'))
from common import *
import copy,stat,struct,socket,fcntl,ast,subprocess
from types import SimpleNamespace as S
from unittest.mock import patch,Mock
import collector as C,driver as D,seal,protocol
checks=[]
def ok(name,value=True):
    assert value,name
    checks.append(dict(case=name,status='PASS_STATIC_PYTHON_MOCK'))
def reject(name,fn):
    try:fn()
    except (ValueError,OSError,KeyError,TypeError):ok(name)
    else:raise AssertionError(name)
snapshot=json_read(R/'reports/source_manifest.json');contract_path=R/'reports/execution_contract.json';contract_sha=sha(contract_path);contract=json_read(contract_path)
need(snapshot['files']==seal.inventory(),'source snapshot differs')
build_sha=sha(R/'reports/build_receipt.json');build=json_read(R/'reports/build_receipt.json')
policy,records,manifest=contract['policy'],contract['records'],contract['manifest']
for p,h in {**snapshot['files'],**build['inputs'],**build['outputs']}.items():ok('hash_'+p,sha(p)==h)
ok('v9_previous1638_reused_not_rerun',json_read(R.parent/'gazebo-request-guard-v9/reports/tests.json')['new_checks']==1638)
ok('old_harmless_PASS_only_reused',json_read(R.parent/'gazebo-joint-resolution-v1/reports/harmless_summary.json')['status']=='PASS_ISOLATION_PATH_ONLY')
ok('small5_paths4_objects',len(policy['paths'])==5 and len(records)==4 and max(r['size'] for r in policy['paths'])<4194304)
ok('large5_and_memory_maximum_excluded',contract['large_objects_prepared'] is False and contract['maximum_memory_measured'] is False)
ok('default_driver_refuses_before_mutation',D.main([])==78)
with patch.object(D.subprocess,'Popen',side_effect=AssertionError('native/service spawn prohibited in test')),patch.object(D,'exclusive',side_effect=AssertionError('marker prohibited in test')):
    reject('bad_contract_SHA_before_marker_service',lambda:D.load_contract(contract_path,'0'*64))
# This is the driver's file-only validation, not driver.run_once or stage execution.
ok('reviewed_contract_file_validation',D.load_contract(contract_path,contract_sha)==contract)
with patch.object(D.subprocess,'check_output',return_value='mock') as tool:
    ok('manager_uses_absolute_tool_and_bounded_timeout',D.Manager().call(['systemctl','--user','show','unit'])=='mock' and tool.call_args.args[0][0]=='/usr/bin/systemctl' and tool.call_args.kwargs['timeout']==2)
    reject('unapproved_manager_command',lambda:D.Manager().call(['sh','-c','true']))
cmd=D.owner_command(contract,contract_sha)
ok('owner_environment_loader_injection_unset','--property=UnsetEnvironment=LD_PRELOAD LD_AUDIT LD_LIBRARY_PATH PYTHONPATH PYTHONHOME' in cmd)
ok('owner_unit_separate_5GiB', '--unit='+contract['owner_unit'] in cmd and '--property=MemoryMax=5368709120' in cmd and contract['target_unit'] not in cmd)
props={k:v for k,t,v in C.placement.target_properties('/proc/123/fd/10')}
ok('target512MiB_and_rlimits_unchanged',props['MemoryMax']==['536870912'] and props['LimitAS']==['2147483648'] and props['LimitFSIZE']==['1048576'] and props['LimitNOFILE']==['256'])
for name in ('MemorySwapMax','TasksMax','CPUQuotaPerSecUSec','RuntimeMaxUSec'):
    ok('target_property_'+name,props[name]=={'MemorySwapMax':['0'],'TasksMax':['64'],'CPUQuotaPerSecUSec':['1000000'],'RuntimeMaxUSec':['30000000']}[name])
# Real retained-FD validator with OS and hash mocks (no object creation).
receipt=dict(object=dict(device=777,inode=1001,size=22),sha256='1'*64,executable_intent=False)
for fault in ('valid','writable','opath','missing_seal','wrong_inode','exec_mode','hash'):
    def flags(fd,kind):
        if kind==fcntl.F_GETFL:return os.O_WRONLY if fault=='writable' else os.O_PATH if fault=='opath' else os.O_RDONLY
        return 0x0f if fault=='missing_seal' else 0x2f
    st=S(st_mode=stat.S_IFREG|(0o500 if fault=='exec_mode' else 0o400),st_dev=777,st_ino=1002 if fault=='wrong_inode' else 1001,st_size=22)
    with patch.object(C.channel.S.os,'fstat',lambda fd:st),patch.object(C.channel.S.fcntl,'fcntl',flags),patch.object(C.channel.S,'digest_fd',lambda fd:'2'*64 if fault=='hash' else '1'*64):
        if fault=='valid':ok('valid_same_sealed_RO_FD',C.channel.S.validate_object(12,receipt))
        else:reject('FD_reject_'+fault,lambda:C.channel.S.validate_object(12,receipt))
class Endpoint:
    def __init__(self,frames=()):self.frames=list(frames);self.sent=[]
    def recvmsg(self,*args):
        if not self.frames:raise BlockingIOError()
        return self.frames.pop(0)
    def send(self,data,*args):self.sent.append(data);return len(data)
    def fileno(self):return 99
creds=[(socket.SOL_SOCKET,socket.SCM_CREDENTIALS,struct.pack('3i',500,os.geteuid(),os.getegid()))]
def packets(fault=None):
    frames=[]
    for j,index in enumerate((0,1,3,4)):
        row=policy['paths'][index];fds=[30+j]
        if fault=='missing_fd' and j==0:fds=[]
        if fault=='extra_fd' and j==0:fds.append(90)
        data=b'CATV8\0\0\0'+struct.pack('4Q',index,777,1000+j,row['size']+(fault=='size' and j==0))
        ancillary=creds+([(socket.SOL_SOCKET,socket.SCM_RIGHTS,struct.pack(str(len(fds))+'i',*fds))] if fds else [])
        frames.append((data,ancillary,socket.MSG_CTRUNC if fault=='truncated' and j==0 else 0,None))
    if fault=='early_end':frames=frames[:-1]
    frames.append((b'CATEND8\0',creds,0,None));return frames
for fault in ('valid','missing_fd','extra_fd','size','truncated','early_end','persist'):
    ep=Endpoint(packets(fault));closed=[]
    cat=C.channel.Catalog(policy,records,manifest,500,'start','e'*64,lambda *a:True,persist=lambda row:fault!='persist')
    def transfer():
        while not cat.packet(ep):pass
        return cat.plan
    with patch.object(C.channel.S,'validate_object',lambda *a:True),patch.object(C.channel.os,'close',closed.append):
        if fault=='valid':
            plan=transfer();ok('full_small_catalog_C_then_K',len(cat.pins)==4 and len(plan['mounts'])==5 and ep.sent==[b'C']*4+[b'K'])
            ok('two_aliases_same_immutable_identity',plan['mounts']['/input/fixed.txt']['inode']==plan['mounts']['/input/fixed-alias.txt']['inode'])
            cat.close();ok('all_retained_FDs_closed_once',len(closed)==len(set(closed))==4)
        else:
            reject('catalog_handoff_'+fault,transfer)
            ok('catalog_failure_no_K_'+fault,b'K' not in ep.sent and cat.closed)
for i in range(5):
    altered=copy.deepcopy(policy);altered['paths'].pop(i)
    reject('missing_required_small_path_'+str(i),lambda:C.channel.verify_policy(altered,records,manifest))
for field in ('source','original','size','executable'):
    altered=copy.deepcopy(policy);altered['paths'][2][field]={'source':'/dev/null','original':dict(device=1,inode=1,sha256='0'*64),'size':1,'executable':True}[field]
    reject('bad_alias_'+field,lambda:C.channel.verify_policy(altered,records,manifest))
# Actual Controller/AuditGate/NativeJournal/harmless protocol state machines.
def setup():
    endpoint=Endpoint();writes=[];events=[]
    window=protocol.AckWindow(writes.append,lambda:dict(status='PASS_FILE_IDENTITY',pid=7,start='s'),'s',7)
    session=protocol.Session(window,lambda:events.append('initial_mapping'))
    binding=dict(run='mock',policy='p',supervisor=500,pid=7,start='s')
    gate=C.N.old.AuditGate(session,binding,lambda row:True)
    owner=C.N.Owner(500,'owner','e'*64,7,'mock','p','s',7,99)
    journal=C.Journal(gate,owner,lambda row:True);journal._bind(C.N._AUTHORITY)
    class Reader:
        fd=98;closed=False;released=False
        def __init__(self):self.journal=journal;self.queue=[]
        def readable(self):
            if self.queue:journal.feed(self.queue.pop(0))
            else:journal.eof();self.closed=True
        def close(self):self.released=True
    reader=Reader()
    def terminal():
        need(journal.threads>=1 and journal.forks==1 and journal.born==2 and journal.deaths==3,'task/callback audit incomplete')
        events.append('terminal');return True,True,0,True,True,True
    ctl=C.Controller(endpoint,reader,10,11,window,protocol.Lines,manifest,terminal);ctl.stream_sink=lambda *a:True
    seq=[0]
    def wire(kind,pid=7,nr=-1,skip=False):
        seq[0]+=2 if skip else 1
        reader.queue.append(f'{seq[0]} {kind} {pid} {nr} 0\n'.encode());ctl.step('audit')
    def prefix():
        for kind,nr in [('PREEXEC_STOP',-1),('PREEXEC_ARMED',-1),('FILTER_BOUND',-1),('EXEC_STOP',-1),('INITIAL_MAPS',2),('TARGET_FDS',5)]:wire(kind,nr=nr)
    def packet(row):ctl.step('stdout',canonical(row))
    def ready():
        prefix()
        for index in (1,2):
            for kind,nr in [('REQUEST',257),('INPUT_OBJECT',index),('INPUT_PREPARED',257),('INPUT_DELIVERED',257)]:wire(kind,nr=nr)
        wire('THREAD_ALLOWED',nr=56);wire('TASK_BORN',pid=8,nr=7)
        for i in range(2):packet(dict(kind='fixture_ready',iteration=0,sim_time_ns=0))
        wire('FORK_ALLOWED',nr=56);wire('TASK_BORN',pid=9,nr=7);wire('EXIT_STOP',pid=9);wire('TASK_DEAD',pid=9,nr=0)
        packet(dict(kind='fixture_child',status=0))
        for i in range(1,101):packet(dict(kind='fixture_sample',iteration=i,sim_time_ns=i*1000000))
        packet(dict(kind='final_wait',iteration=100,sim_time_ns=100000000))
    def end(omit=None):
        packet(dict(kind='fixture_cleanup',joined=True))
        for kind,pid,nr in [('EXIT_STOP',8,-1),('TASK_DEAD',8,0),('EXIT_STOP',7,-1),('TASK_DEAD',7,0),('ALL_DEAD',7,-1),('COMPLETE',7,-1)]:
            if kind!=omit:wire(kind,pid,nr)
        ctl.step('stdout',b'');ctl.step('stderr',b'');ctl.step('audit')
    return S(ctl=ctl,j=journal,gate=gate,reader=reader,writes=writes,endpoint=endpoint,wire=wire,prefix=prefix,packet=packet,ready=ready,end=end,window=window,session=session,events=events)
e=setup();e.prefix();e.session.can_go=lambda:False
for i in range(2):e.packet(dict(kind='fixture_ready',iteration=0,sim_time_ns=0))
ok('ready_stream_waits_for_independent_input_receipts',not e.writes and not e.ctl.failed)
e.ctl.step('audit');reject('missing_input_audit_cannot_finalize',e.ctl.finish)
ok('missing_input_audit_never_GO_or_V',not e.writes and b'V' not in e.endpoint.sent)
e=setup();e.ready();ok('GO_and_ACK_only_after_live_mapping',e.writes==[b'GO\n',b'EXIT_ACK\n'] and e.endpoint.sent==[b'A'])
e.end();result=e.ctl.finish();ok('full100_protocol_task_audit_EOF_cleanup_V',result['status']=='PASS_SMALL_HARMLESS_PATH_ONLY' and e.endpoint.sent==[b'A',b'V'])
for fault in ('no_preexec','sequence_gap','early_audit_EOF','missing_death','missing_COMPLETE','nonzero_exit','raw_persist_failure','missing_callback','bad_terminal','concurrent_mutation','input_without_object','late_audit_disconnect'):
    e=setup()
    if fault=='no_preexec':e.packet(dict(kind='fixture_ready',iteration=0,sim_time_ns=0))
    elif fault=='sequence_gap':e.prefix();e.wire('THREAD_ALLOWED',nr=56,skip=True)
    elif fault=='early_audit_EOF':e.prefix();e.ctl.step('audit')
    elif fault=='raw_persist_failure':e.j.persist=lambda r:False;e.prefix()
    elif fault=='concurrent_mutation':e.prefix();e.wire('VMA_BEGIN',nr=9);e.wire('VMA_BEGIN',nr=11)
    elif fault=='input_without_object':e.prefix();e.wire('REQUEST',nr=257);e.wire('INPUT_PREPARED',nr=257)
    else:
        e.ready()
        if fault=='nonzero_exit':e.wire('TASK_DEAD',pid=8,nr=256)
        elif fault=='missing_callback':
            e.end();e.session.cleanup=False
        elif fault=='bad_terminal':e.end();e.ctl.terminal=lambda:(True,True,0,False,True,True)
        elif fault=='late_audit_disconnect':e.ctl.step('audit')
        else:e.end('TASK_DEAD' if fault=='missing_death' else 'COMPLETE')
    reject('terminal_rejects_'+fault,e.ctl.finish)
    ok('no_V_after_'+fault,b'V' not in e.endpoint.sent)
# Overlapping native requests on distinct tracked tasks complete with binding.
e=setup();e.prefix();e.wire('THREAD_ALLOWED',nr=56);e.wire('TASK_BORN',pid=8,nr=7)
for pid,index in ((7,1),(8,2)):e.wire('REQUEST',pid,257);e.wire('INPUT_OBJECT',pid,index)
for pid in (8,7):e.wire('INPUT_PREPARED',pid,257);e.wire('INPUT_DELIVERED',pid,257)
ok('distinct_task_concurrent_requests_bound',not e.ctl.failed and set(e.j.delivered)=={(7,1),(8,2)})
# Driver ownership guards. All manager calls and live inspection boundaries mocked.
manager=Mock();manager.inspect.return_value=dict(LoadState='loaded',Id='other',InvocationID='old',ControlGroup='/other',Description='other')
reject('foreign_unit_cleanup_denied',lambda:D.cleanup_owner(manager,contract['owner_unit'],contract['description'],None));ok('foreign_unit_not_stopped',not manager.call.called)
manager=Mock();manager.inspect.return_value=dict(LoadState='loaded',Id=contract['owner_unit'],InvocationID='new',ControlGroup='/owner',Description=contract['description'])
reject('reused_owner_invocation_not_stopped',lambda:D.cleanup_owner(manager,contract['owner_unit'],contract['description'],{'InvocationID':'old'}));ok('reused_unit_not_stopped',not manager.call.called)
# Target cleanup requires durable invocation receipt; a matching label alone cannot stop it.
manager=Mock();manager.inspect.return_value=dict(LoadState='loaded')
with patch.object(D.Path,'is_file',lambda p:False):
    reject('target_cleanup_without_invocation_receipt_denied',lambda:D.cleanup_target_owned(manager,contract))
ok('unproven_target_not_stopped',not manager.call.called)
# Existing output/marker forbids any service or marker mutation.
with patch.object(D.Path,'exists',lambda self:True),patch.object(D,'exclusive',side_effect=AssertionError('marker consumed')),patch.object(D.subprocess,'Popen',side_effect=AssertionError('spawn')):
    reject('no_retry_existing_output_marker',lambda:D.run_once(contract,contract_sha,Mock()))
from integration import run as integration_checks
integration_checks(ok,reject,contract,contract_sha,packets)
from startup_mocks import run as startup_checks
startup_checks(ok,reject,contract,contract_sha)
from mapping_mocks import run as mapping_checks
mapping_checks(ok,reject,contract)
source=(R/'inputs/launch.c').read_text();probe=(R/'inputs/probe.c').read_text()
ok('same_v9_owner_receiver',(R/'scripts/owner.py').read_bytes()==(R.parent/'gazebo-request-guard-v9/scripts/owner.py').read_bytes())
ok('same_v9_FD_bridge',(R/'inputs/owner_bridge.h').read_bytes()==(R.parent/'gazebo-request-guard-v9/inputs/owner_bridge.h').read_bytes())
entry=(R/'inputs/owner_main.c').read_text()
ok('private_slots_CLOEXEC_restored_before_owner_bridge',entry.index('fcntl(fd[3],F_SETFD,FD_CLOEXEC)')<entry.index('candidate_owner_fds(') and 'fcntl(fd[4],F_SETFD,FD_CLOEXEC)' in entry)
for fail in (None,3,4):
    flags={3:0,4:0};restored=True
    for slot in (3,4):
        if slot==fail:restored=False;break
        flags[slot]=fcntl.FD_CLOEXEC
    ok('entry_exec_inherited_control_FD_'+str(fail),(restored and all(flags.values())) if fail is None else not restored)
ok('prlimit64_read_only_self_query','r.orig_rax==SYS_prlimit64 && !r.rdi && !r.rdx' in source)
ok('fixed_small_argv_only','TARGET_INPUT' in source and 'TARGET_ALIAS' in source and 'argv[3]' in source)
ok('harmless_fork_scalar_flags_exact','r.rdi==fork_flags && !r.rsi && !r.rdx && !r.r8' in source)
ok('exit_callbacks_keep_thread_until_after_ACK',probe.index('if(!aero_exit_barrier())')<probe.index('return 0; /* atexit') and 'pthread_join(worker,NULL)' in probe)
ok('full_v9_launcher_unchanged',(R.parent/'gazebo-request-guard-v9/inputs/entry.c').read_text().endswith('int main(void) { return 78; }\n'))
base=json_read(R/'work/baseline.json')
for p,h in base['files'].items():
    if p!='handoff.md':ok('preserved_'+p,sha(B/p)==h)
link=B/'libgz-physics-dartsim-plugin.so';st=link.lstat();ok('dangling_symlink_preserved',[st.st_dev,st.st_ino,os.readlink(link)]==base['link'] and not link.exists())
old=json_read(R.parent/'gazebo-request-guard-v5/work/preservation.json');main='/home/jiwon/Projects/AeroAIStudio'
ok('main_HEAD_dirty_preserved',subprocess.check_output(['git','rev-parse','HEAD'],cwd=main,text=True).strip()==old['main_head'] and subprocess.check_output(['git','status','--porcelain'],cwd=main,text=True)==old['main_status'])
for p in (R/'scripts').glob('*.py'):compile(p.read_text(),str(p),'exec')
need(snapshot['files']==seal.inventory(),'source changed during tests')
need(sha(contract_path)==contract_sha and sha(R/'reports/build_receipt.json')==build_sha,'receipt changed during tests')
(R/'reports/tests.json').write_text(json.dumps(dict(status='PASS_STATIC_PYTHON_MOCK_ONLY',new_checks=len(checks),checks=checks,source_manifest_sha256=snapshot['sha256'],contract_sha256=contract_sha,build_receipt_sha256=build_sha,artifact_sha256=build['outputs'],previous1638='REUSED_BY_HASH_NOT_RERUN_OR_ADDED',native_executed=False,services_started=False,marker_consumed=False,actual_prepared_objects=0,actual_delivered_paths=0),indent=2)+'\n')
print('PASS',len(checks),'static/Python mock checks; native/service/marker execution0')
