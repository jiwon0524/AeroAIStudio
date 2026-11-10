"""Real callback-only C unit mock plus pure/Python mocked flow tests.
No owner/probe/bwrap, service, namespace or mapping-file operation is executed.
"""
from pathlib import Path
import sys,json,hashlib,subprocess,socket,struct,fcntl,copy,stat,os,importlib.util
from unittest.mock import Mock,patch
from types import SimpleNamespace as S
R=Path(__file__).resolve().parents[1];B=R.parents[1]
OLD=R.parent/'gazebo-request-guard-v10-small02'
sys.path[:0]=[str(OLD/'scripts'),str(OLD/'tests'),str(R/'scripts')]
import ownership,map_records,collector as C,driver as D
import integration
spec=importlib.util.spec_from_file_location('closed_followup_driver',R/'scripts/driver.py')
closed=importlib.util.module_from_spec(spec);spec.loader.exec_module(closed)
checks=[]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def ok(name,value=True):
    assert value,name
    checks.append(dict(case=name,status='PASS_STATIC_OR_PYTHON_MOCK'))
def reject(name,fn):
    try:fn()
    except (ValueError,OSError,KeyError,TypeError):ok(name)
    else:raise AssertionError(name)
build=json.loads((R/'reports/build_receipt.json').read_text())
for u in build['translation_units']:
    assert sha(u['object'])==u['object_sha256']
    assert all(sha(p)==v for p,v in u['input_hashes'].items())
assert all(sha(p)==v for p,v in build['outputs'].items())
ok('all_compiled_and_reused_object_input_ELF_hashes')
disassembly=Path(build['entry_disassembly']).read_text()
ok('compiled_owner_entry_inert_78','0x4e,%eax' in disassembly and 'ret' in disassembly)
symbols=Path(build['mock_binary']+'.readelf.txt').read_text()
import re
ok('C_mock_has_no_mapping_namespace_or_service_imports',not re.search(r'UND\s+(?:open|write|close|unshare|clone|fork|mount|execve|system)(?:@|\s)',symbols))
# This binary contains map_io.h and fake callback operations ONLY. The owner
# ELF is never run, nor is the old harmless trial or any namespace helper.
p=subprocess.Popen([build['mock_binary']],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
identity=dict(host=socket.gethostname(),pid=p.pid,start='UNKNOWN')
try:identity['start']=Path('/proc',str(p.pid),'stat').read_text().rsplit(')',1)[1].split()[19]
except OSError:pass
stdout,stderr=p.communicate(timeout=2)
mock_process_result=dict(identity,returncode=p.returncode)
ok('shared_C_map_io_14_callback_cases',p.returncode==0 and b'PASS 14' in stdout and not stderr)
for args in ([],['--execute-once'],['--collector-stage'],['--execute-once','--contract','old']):
    with patch.object(subprocess,'Popen',side_effect=AssertionError('must refuse before spawn')),patch.object(os,'open',side_effect=AssertionError('must refuse before marker')):
        ok('closed_entry_'+str(args),closed.main(args)==78 and closed.run_once()==78 and closed.collector_stage()==78)
native=(R/'inputs/launch.c').read_text();header=(R/'inputs/map_io.h').read_text()
ok('map_IO_captures_errno_before_emit_and_close',header.index('int write_errno=errno;')<header.index('int write_log=ops->emit')<header.index('int closed=ops->close_map(fd);',header.index('int write_log')))
ok('no_retry_of_close_or_map_write','while' not in header and 'for(' not in header)
ok('new_C_log_cap_not_raised','++diagnostic_count>32' in native and 'char line[192]' in native)
ok('all_mapping_adapters_keep_original_order',native.index('own_map("uid-map"')<native.index('own_map("setgroups"')<native.index('own_map("gid-map"'))
# Summaries and individual calls share one per-process sequence. A failed
# write followed by failed close must remain two separate observations.
sample=(b'V10DIAG 400 8 userns 0 0\n'
        b'V10IO 400 9 uid-map-open 41 9 0\n'
        b'V10IO 400 10 uid-map-write -1 9 1\n'
        b'V10IO 400 11 uid-map-close -1 9 9\n'
        b'V10DIAG 400 12 uid-map -1 1\n')
rows=map_records.parse(sample)
ok('mixed_IO_records_keep_return_request_and_immediate_errno',rows[1]['result']==41 and rows[2]['requested']==9 and rows[2]['errno']==1 and rows[3]['errno']==9)
for name,data in [('gap',sample.replace(b'400 10',b'400 15')),('overflow',b'x'*16385),('truncated',sample[:-1]),('wrong_op',sample.replace(b'uid-map-write',b'uid-map-unknown'))]:
    reject('mixed_record_reject_'+name,lambda data=data:map_records.parse(data))
failures=ownership.Failures()
failures.record('native','uid-map-write','EPERM');failures.record('native','uid-map','EPERM')
failures.record('native','uid-map-close','EBADF',cleanup=True)
failures.record('collector','owner-bind','disconnect');failures.record('host','ownership','missing cgroup')
failures.record('host','stop','readback failure',cleanup=True)
saved=failures.snapshot();saved['first']['native']['reason']='altered copy'
ok('cleanup_and_later_failures_cannot_replace_first',failures.first['native']['stage']=='uid-map-write' and len(failures.secondary)==1 and len(failures.cleanup)==2)
ok('failure_sources_remain_separate',set(failures.first)=={'native','collector','host'})
contract=json.loads((OLD/'reports/execution_contract.json').read_text());digest=sha(OLD/'reports/execution_contract.json')
host_rows=[json.loads(x) for x in (OLD/'work/runtime-small-02/host-startup.jsonl').read_text().splitlines()]
states=[x['state'] for x in host_rows if x['stage']=='owner-inspect']
name,desc=contract['owner_unit'],contract['description']
ok('historical_starting_snapshot_unproven',ownership.classify(states[0],name,desc)=='INCOMPLETE_BEFORE_RECEIPT')
ok('historical_owned_snapshot_bound',ownership.classify(states[1],name,desc)=='OWNED_SNAPSHOT')
ok('historical_teardown_snapshot_unproven',ownership.classify(states[2],name,desc,states[1])=='INCOMPLETE_AFTER_RECEIPT')
for label,change in [('foreign',dict(Id='other')),('invocation',dict(InvocationID='new')),('group',dict(ControlGroup='/different')),('cap',dict(MemoryMax='max'))]:
    row=dict(states[1],**change)
    ok('changed_ownership_rejected_'+label,ownership.classify(row,name,desc,states[1])!='OWNED_SNAPSHOT')
manager=Mock();manager.inspect.side_effect=[states[0],states[1]]
logged=manager.inspect(name);actual=D.owned(manager,name,desc)
ok('old_double_read_can_log_different_snapshot',not logged['InvocationID'] and bool(actual['InvocationID']) and manager.inspect.call_count==2)
manager=Mock();manager.inspect.side_effect=[states[1],states[2]]
logged=manager.inspect(name)
reject('old_owned_fails_on_second_teardown_read',lambda:D.owned(manager,name,desc,states[1]['InvocationID']))
ok('fresh_read_failure_is_not_mapping_diagnostic',bool(logged['ControlGroup']) and manager.inspect.call_count==2)
for i in (0,1,2):
    manager=Mock();manager.inspect.return_value=states[i];persisted=[]
    observe=lambda:ownership.inspect_bound(manager,name,desc,lambda row:persisted.append(row) or True,states[1] if i==2 else None)
    if i==1:ok('single_read_valid_bound_snapshot',observe()==states[1])
    else:reject('single_read_incomplete_rejected_'+str(i),observe)
    ok('logged_row_equals_validated_row_'+str(i),manager.inspect.call_count==1 and persisted[0]['state']==states[i] and not manager.call.called)
manager=Mock();manager.inspect.return_value=states[1]
reject('single_read_missing_persistence_fails',lambda:ownership.inspect_bound(manager,name,desc,lambda row:False))
# Exercise the real existing Owner.bind with kernel boundaries mocked. Default
# bwrap PID1, changed ELF parent and interposed parent all fail before O.
for fault in ('valid','bwrap_pid2','bwrap_bootstrap_ELF','interposed_parent','worker_ELF','wrong_domain'):
    ep=Mock();pid_native=2 if fault=='bwrap_pid2' else 1
    ep.recvmsg.return_value=(b'OWNERV8\0'+struct.pack('Q',pid_native),[
        (socket.SOL_SOCKET,socket.SCM_CREDENTIALS,struct.pack('3i',400,os.geteuid(),os.getegid())),
        (socket.SOL_SOCKET,socket.SCM_RIGHTS,struct.pack('i',99))],0,None)
    ep.send.return_value=1
    def observe(pid):return dict(pid=pid,start='100' if pid==400 else '101',ppid=(999 if fault=='interposed_parent' else 400) if pid==500 else 1,state='T' if pid==500 else 'R',cgroup='/other' if fault=='wrong_domain' and pid==500 else '/owner')
    def attest(pid,*args):return not ((fault=='bwrap_bootstrap_ELF' and pid==400) or (fault=='worker_ELF' and pid==500))
    disposed=[]
    with patch.object(C.owner,'identity',observe),patch.object(C.owner,'attest',attest),patch.object(C.owner.Path,'read_text',lambda *a,**kw:'5368709120'),patch.object(C.owner.fcntl,'fcntl',lambda *a:fcntl.FD_CLOEXEC),patch.object(C.N,'pidfd_identity',lambda *a:500),patch.object(C.owner.os,'close',disposed.append):
        call=lambda:C.owner.bind(ep,400,'100','e'*64,'/owner','mock',digest,C.N)
        if fault=='valid':ok('existing_owner_bind_valid_chain_mock',call().pid==500)
        else:reject('existing_owner_bind_rejects_'+fault,call)
    ok('owner_pidfd_disposed_'+fault,disposed==[99])
    ok('O_ACK_only_for_valid_chain_'+fault,ep.send.called==(fault=='valid'))
# Existing full Python coordinator/control tests, not the old check.py runner
# (which writes historical reports). Every runtime boundary is mocked there.
policy=contract['policy']
def packets():
    values=[]
    credentials=[(socket.SOL_SOCKET,socket.SCM_CREDENTIALS,struct.pack('3i',500,os.geteuid(),os.getegid()))]
    for j,index in enumerate((0,1,3,4)):
        data=b'CATV8\0\0\0'+struct.pack('4Q',index,777,1000+j,policy['paths'][index]['size'])
        values.append((data,credentials+[(socket.SOL_SOCKET,socket.SCM_RIGHTS,struct.pack('i',30+j))],0,None))
    values.append((b'CATEND8\0',credentials,0,None));return values
integration.run(ok,reject,contract,digest,packets)
baseline=json.loads((R/'work/baseline.json').read_text());changed=[]
for name,v in baseline['files'].items():
    p=B/name
    if sha(p)!=v['sha256'] or stat.S_IMODE(p.stat().st_mode)!=v['mode']:changed.append(name)
ok('historical_evidence_sources_markers_preserved',not changed)
main=Path('/home/jiwon/Projects/AeroAIStudio');main_changed=[]
for name,v in baseline['main'].items():
    p=main/name
    if 'link' in v:
        if not p.is_symlink() or str(p.readlink())!=v['link']:main_changed.append(name)
    elif sha(p)!=v['sha256'] or stat.S_IMODE(p.stat().st_mode)!=v['mode']:main_changed.append(name)
ok('main_nonignored_files_modes_symlinks_preserved',not main_changed)
ok('main_HEAD_status_preserved',subprocess.check_output(['git','rev-parse','HEAD'],cwd=main,text=True).strip()==baseline['main_head'] and subprocess.check_output(['git','--no-optional-locks','status','--porcelain'],cwd=main,text=True)==baseline['main_status'])
for p in (R/'scripts').glob('*.py'):compile(p.read_text(),str(p),'exec')
report=dict(status='PASS_STATIC_AND_MOCK_ONLY_RUNTIME_BLOCKED',python_checks=len(checks),callback_C_cases=14,
            checks=checks,callback_process=mock_process_result,
            callback_stdout=stdout.decode(),callback_stderr=stderr.decode(),
            historical_files_checked=len(baseline['files']),historical_changes=changed,
            main_nonignored_paths_checked=len(baseline['main']),main_changes=main_changed,
            build_receipt_sha256=sha(R/'reports/build_receipt.json'),owner_execution_count=0,
            bwrap_execution_count=0,services_started=0,markers_consumed=0,uid_map_files_opened=0,
            reused_coordinator_tests_sha256=sha(OLD/'tests/integration.py'))
(R/'reports/tests.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS',len(checks),'Python/static/mock checks;14 callback-only C cases; owner/bwrap/service/marker0')
