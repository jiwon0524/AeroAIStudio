"""Static and Python mock checks only. No native subject/supervisor execution."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import ast
from unittest.mock import Mock

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R/'scripts'))
from journal import JournalAdapter, AuditGate
import catalog
import launcher

checks = []
def ok(name, condition):
    assert condition, name
    checks.append(dict(case=name, status='PASS_STATIC_MOCK'))
def reject(name, fn):
    try:
        fn()
    except (ValueError, OSError, KeyError, TypeError):
        checks.append(dict(case=name, status='PASS_REJECTED'))
    else:
        raise AssertionError(name)

proof = dict(pre_loader=True, fd_attested=True, policy_applied=True,
             journal_private=True, lifetime_tracking=True)
binding = dict(run='mock', policy='sealed', supervisor='mock-private-owner', pid=100, start='mock')
def setup(p=None, persist=lambda row: True):
    s = Mock()
    s.finalize.return_value = {'status': 'PASS'}
    g = AuditGate(s, binding, persist)
    j = JournalAdapter(g, 100, dict(proof) if p is None else p)
    return j, g, s
def row(j, kind, pid=100, nr=-1):
    denied = j.denied + (kind == 'DENY')
    j.feed(f'{j.seq+1} {kind} {pid} {nr} {denied}\n'.encode())
def start(j):
    row(j, 'EXEC_STOP')
def finish(j):
    row(j, 'TASK_DEAD', nr=0)
    row(j, 'ALL_DEAD')
    row(j, 'COMPLETE')
    j.eof()

j,g,s = setup(); start(j); g.authorize()
row(j, 'REQUEST', nr=257); row(j, 'INPUT_PREPARED', nr=257); row(j, 'INPUT_DELIVERED', nr=257)
finish(j)
ok('normal_input_native_journal_existing_gate', g.finalize()['status'] == 'PASS')
for key in proof:
    p = dict(proof); p[key] = False
    j,g,s = setup(p)
    reject('GO_missing_'+key, lambda: start(j))
    reject('GO_stays_blocked_'+key, g.authorize)
for phase in ('initialization', 'running', 'after_EXIT_ACK'):
    j,g,s = setup(); start(j)
    if phase != 'initialization':
        g.authorize()
    if phase == 'after_EXIT_ACK':
        g.packet({'kind': 'final_wait'})
        s.mock_exit_ack_sent = True
    row(j, 'REQUEST', nr=41); row(j, 'DENY', nr=41); row(j, 'REPLIED_DENY', nr=41)
    finish(j)
    ok(phase+'_audit_drains_after_failure', j.closed and g.closed and g.denied == 1)
    reject(phase+'_denial_exit0_fails', g.finalize)

j,g,s = setup(); start(j); g.authorize()
row(j, 'TASK_BORN', 101, 100); row(j, 'TASK_BORN', 102, 101)
row(j, 'REQUEST', 101, 257); row(j, 'REQUEST', 102, 257)
row(j, 'INPUT_PREPARED', 102, 257); row(j, 'INPUT_DELIVERED', 102, 257)
row(j, 'INPUT_PREPARED', 101, 257); row(j, 'INPUT_DELIVERED', 101, 257)
row(j, 'TASK_DEAD', nr=0)
reject('root_death_does_not_end_children', lambda: row(j, 'ALL_DEAD'))

j,g,s = setup(); start(j); g.authorize()
row(j, 'TASK_BORN', 101, 100); row(j, 'TASK_BORN', 102, 101)
for pid in (101,102):
    row(j, 'REQUEST', pid, 257)
for pid in (102,101):
    row(j, 'INPUT_PREPARED', pid, 257); row(j, 'INPUT_DELIVERED', pid, 257)
row(j, 'TASK_DEAD', nr=0)
row(j, 'TASK_DEAD', 102, 0); row(j, 'TASK_DEAD', 101, 0)
row(j, 'ALL_DEAD'); row(j, 'COMPLETE'); j.eof()
ok('interleaved_requests_all_descendants_finish', g.finalize()['status'] == 'PASS')

for ending in ('CANCELLED', 'pending_death', 'nonzero_death'):
    j,g,s = setup(); start(j); g.authorize()
    row(j, 'REQUEST', nr=257)
    if ending == 'CANCELLED':
        row(j, 'CANCELLED', nr=257)
    row(j, 'TASK_DEAD', nr=256 if ending == 'nonzero_death' else 0)
    row(j, 'ALL_DEAD'); row(j, 'COMPLETE'); j.eof()
    reject(ending+'_fails_closed', g.finalize)

for bad in (b'2 EXEC_STOP 100 -1 0\n', b'1 EXEC_STOP 100 -1 1\n',
            b'1 EXEC_STOP 100 -1 0', b'1 OVERFLOW 100 -1 0\n', b'x'*193):
    j,g,s = setup()
    reject('malformed_loss_overflow_'+str(len(checks)), lambda: j.feed(bad))
for stage in ('empty', 'started', 'dead_without_complete'):
    j,g,s = setup()
    if stage != 'empty': start(j)
    if stage == 'dead_without_complete': row(j, 'TASK_DEAD', nr=0); row(j, 'ALL_DEAD')
    reject(stage+'_early_disconnect', j.eof)
    reject(stage+'_final_refusal', g.finalize)
j,g,s = setup(persist=lambda row: False)
reject('durable_write_failure', lambda: start(j))
reject('durable_failure_GO_latch', g.authorize)
j,g,s = setup(); start(j)
row(j, 'REQUEST', 100, 257)
reject('duplicate_pending_thread_request', lambda: row(j, 'REQUEST', 100, 257))
for kind,pid,nr in (('TASK_BORN',101,999), ('TASK_DEAD',999,0), ('INPUT_DELIVERED',100,257),
                    ('COMPLETE',100,-1), ('REQUEST',999,257)):
    j,g,s = setup(); start(j)
    reject('bad_transition_'+kind, lambda: row(j,kind,pid,nr))

# Real Python temporary file I/O only; kernel fs-verity is MOCKED, never set.
with tempfile.TemporaryDirectory(dir=R/'work') as tmp:
    p = Path(tmp)/'input'; p.write_bytes(b'approved bytes')
    old = Path(tmp)/'old'; old.write_bytes(b'replacement')
    st = p.stat()
    desc = dict(source=str(p), device=st.st_dev, inode=st.st_ino,
                sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    def check(fd, desc):
        st = os.fstat(fd)
        if (st.st_dev, st.st_ino) != (desc['device'], desc['inode']): raise ValueError('identity')
        if hashlib.sha256(os.pread(fd, st.st_size, 0)).hexdigest() != desc['sha256']: raise ValueError('hash')
    reject('RO_FD_without_immutable_proof', lambda: catalog.pin(desc, check, verity=lambda fd:False))
    fd = catalog.pin(desc, check, verity=lambda fd:True)
    old.replace(p)
    ok('path_replacement_keeps_verified_open_inode', os.pread(fd,100,0) == b'approved bytes')
    os.close(fd)
    reject('changed_path_reopen_identity_rejected', lambda: catalog.pin(desc,check,verity=lambda fd:True))

mapping = json.loads((R/'reports/input_mapping.json').read_text())
ok('all_594_sealed_mount_aliases_mapped', len(mapping['inputs']) == 594)
ok('sealed_contract_digest_preserved', mapping['contract_sha256'] == '789737d947f8c0ebd1466300792667fc9c838adba5834168e5c82bc6e4846aae')
broker = (R/'inputs/broker.c').read_text()
tree = (R/'inputs/tree.c').read_text()
for name,cond in {
    'atomic_ADDFD_SEND': '.flags=SECCOMP_ADDFD_FLAG_SEND' in broker,
    'no_CONTINUE_response': 'SECCOMP_USER_NOTIF_FLAG_CONTINUE' not in broker,
    'original_syscall_never_reopened': 'open(path' not in broker,
    'write_modes_default_denied': 'O_CLOEXEC|O_NONBLOCK|O_NOFOLLOW|O_LARGEFILE' in broker,
    'same_original_inode_and_fsverity': 'FS_VERITY_FL' in broker and '(uint64_t)st.st_ino==ino' in broker,
    'unknown_arch_killed': 'SECCOMP_RET_KILL_PROCESS' in broker and 'AUDIT_ARCH_X86_64' in broker,
    'no_exec_clone_relaxation': 'DIRECT(SYS_clone)' not in broker and 'DIRECT(SYS_execve)' not in broker,
    'v1_supervisor_source_reused': 'gazebo-request-guard-v1/inputs/guard.c' in tree,
    'all_tasks_wait': '__WALL|WNOHANG' in tree and 'PTRACE_O_TRACECLONE' in tree,
    'not_EXIT_ACK_limited': 'EXIT_ACK' not in tree,
    'terminal_ECHILD_required': 'errno==ECHILD && !t->live && t->root_dead' in tree,
    'no_direct_native_entry': (R/'inputs/entry.c').read_text().endswith('int main(void) { return 78; }\n'),
}.items(): ok(name, cond)
ok('launcher_refuses_before_service_marker', launcher.preflight()['exit_code']==78 and
   not launcher.preflight()['service_started'] and not launcher.preflight()['marker_created'])

# Reuse sealed NativeSession/ACK implementation, including final live mapping.
# No old script is run and no prior result file is overwritten.
c, manifest, seal = catalog.load_contract()
sys.path.insert(0, str(catalog.OLD/'scripts'))
sys.modules['contract'] = c
import source_loader
with source_loader.runtime(manifest) as (modules, loaded):
    scope = dict(m=manifest, AckWindow=modules['protocol'].AckWindow,
                 AckSession=modules['protocol'].AckSession, NativeSession=modules['native_gate'].NativeSession)
    tree_ast = ast.parse((catalog.OLD/'tests/test_contract.py').read_text())
    defs = [n for n in tree_ast.body if isinstance(n,ast.FunctionDef) and n.name in ('packets','setup','ready')]
    exec(compile(ast.Module(body=defs,type_ignores=[]),'sealed_mock_factories','exec'),scope)
    def full_protocol(violation=False, final_args=(True,True,0,True,True,True)):
        native, window, output = scope['setup']()
        g = AuditGate(native,binding,lambda row:True)
        j = JournalAdapter(g,100,dict(proof)); start(j)
        for packet in scope['packets'](): g.packet(packet)
        scope['ready'](g); g.authorize()
        for i in range(1,101):
            t=i*.001
            state={k:0 for k in ['x','y','z','vx','vy','vz','roll','pitch','yaw']}
            state.update(z=1-4.905*t*t,vz=-9.81*t)
            g.packet(dict(kind='sample',iteration=i,sim_time_ns=i*1000000,dt_ns=1000000,
                          paused=False,native_frame=i,native_time=t,init_count=1,
                          state_source='measured_live_components',state=state))
        g.packet(dict(kind='final_wait',iteration=100,sim_time_ns=100000000))
        window.send_ack()
        assert output==[b'GO\n',b'EXIT_ACK\n']
        if violation:
            row(j,'REQUEST',nr=41); row(j,'DENY',nr=41); row(j,'REPLIED_DENY',nr=41)
        finish(j)
        return g.finalize(*final_args)
    ok('original_GO_100samples_last_live_mapping_ACK_both_EOF_cleanup',full_protocol()['status']=='PASS')
    reject('native_journal_destructor_denial_after_actual_mock_ACK',lambda:full_protocol(True))
    for idx,name in ((0,'stdout_EOF'),(1,'stderr_EOF'),(3,'cleanup'),(4,'integrity'),(5,'last_live_mapping')):
        args=[True,True,0,True,True,True]; args[idx]=False
        reject('original_'+name+'_rejection_retained',lambda:full_protocol(final_args=tuple(args)))

before=json.loads((R/'work/preservation.json').read_text())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
ok('original_inputs_except_intended_worktree_handoff_preserved', all(sha(p)==v for p,v in before['files'].items()
    if Path(p)!=R.parents[1]/'handoff.md'))
main=Path('/home/jiwon/Projects/AeroAIStudio')
ok('main_HEAD_preserved',subprocess.check_output(['git','rev-parse','HEAD'],cwd=main,text=True).strip()==before['main_head'])
ok('main_status_preserved',subprocess.check_output(['git','status','--porcelain'],cwd=main,text=True)==before['main_status'])
link=R.parents[1]/'libgz-physics-dartsim-plugin.so';st=link.lstat()
ok('dangling_symlink_identity_preserved',[st.st_dev,st.st_ino,os.readlink(link)]==before['symlink'])
(R/'reports/tests.json').write_text(json.dumps(dict(status='PASS_STATIC_MOCK_ONLY',count=len(checks),checks=checks,
    native_execution=False,runtime='UNVERIFIED',preserved_files=len(before['files'])),indent=2)+'\n')
print('PASS',len(checks),'static/mock checks; no native execution')
