"""Offline regressions only. No executable from this phase is loaded or run."""
from pathlib import Path
import copy, hashlib, importlib.util, json, os, subprocess, sys
from unittest.mock import Mock, patch
R=Path(__file__).resolve().parents[1]; B=R.parents[1]
sys.path.insert(0,str(R/'scripts'))
from audit_gate import AuditGate
import launcher
checks=[]
def ok(name,fn):
    assert fn();checks.append({'case':name,'status':'PASS_MOCK_STATIC'})
def reject(name,fn):
    try:fn()
    except (ValueError, OSError, KeyError, TypeError):checks.append({'case':name,'status':'PASS_REJECTED'})
    else:raise AssertionError(name)
binding=dict(run='synthetic-1', policy='sealed-policy', supervisor='sealed-source', pid=100, start='mock-start')
start=dict(pre_loader=True,fd_attested=True,policy_applied=True,journal_private=True,lifetime_tracking=True)
def event(g,kind,payload,**kw):
    row=dict(seq=g.seq+1,kind=kind,binding=dict(binding),payload=payload)
    row.update(kw);g.event(row,authenticated=True)
def setup():
    s=Mock();s.authorize.return_value=None;s.finalize.return_value={'status':'PASS'}
    g=AuditGate(s,binding,lambda row:True)
    return g,s
def started():
    g,s=setup();event(g,'start',dict(start));return g,s
def running():
    g,s=started();g.authorize();return g,s
def complete(g):
    event(g,'all_dead',dict(live_tasks=0,wait_echild=True))
    event(g,'complete',dict(denied=g.denied,lost=0,pending=0));g.eof()
def normal():
    g,s=running();g.packet({'kind':'final_wait'});g.packet({'kind':'synthetic_post_ack'})
    complete(g);return g.finalize(True,True,0,True,True,True)=={'status':'PASS'}
ok('normal_independent_audit_plus_existing_session',normal)
g,s=setup();reject('empty_log_GO_refused',g.authorize)
g,s=setup();reject('empty_log_exit0_cannot_pass',lambda:g.finalize(True,True,0,True,True,True))
for key in start:
    g,s=setup();p=dict(start);p[key]=False
    reject('start_missing_'+key,lambda:event(g,'start',p))
    reject('start_failure_GO_latched_'+key,g.authorize)
g,s=setup();row=dict(seq=1,kind='start',binding=binding,payload=start)
reject('target_forged_audit_packet_not_authenticated',lambda:g.event(row))
g,s=setup();numeric=dict(start,pre_loader=1)
reject('integer_is_not_application_boolean',lambda:event(g,'start',numeric))
for key in binding:
    g,s=setup();other=dict(binding);other[key]='changed'
    reject('binding_'+key,lambda:event(g,'start',dict(start),binding=other))
for seq in (0,2,True,'1'):
    g,s=setup();reject('sequence_'+repr(seq),lambda:event(g,'start',dict(start),seq=seq))
g,s=started();reject('duplicate_start',lambda:event(g,'start',dict(start)))
for phase in ('init','running','post_ACK'):
    g,s=started() if phase=='init' else running()
    if phase=='post_ACK':g.packet({'kind':'final_wait'});s.window_ack=True
    event(g,'denial',{'nr':257,'reason':'forbidden open'})
    ok(phase+'_denial_latches',lambda:g.failed and g.denied==1)
    if phase=='init':reject('init_denial_GO_refused',g.authorize)
    # Independent collection continues to final death despite failed verdict.
    complete(g)
    ok(phase+'_audit_kept_collecting_through_death',lambda:g.complete and g.closed)
    reject(phase+'_exit0_EOF_cleanup_cannot_forgive',lambda:g.finalize(True,True,0,True,True,True))
for phase in ('before_start','init','post_ACK'):
    g,s=setup() if phase=='before_start' else running()
    reject(phase+'_premature_audit_EOF',g.eof)
for failure in ('lost','overflow','disconnect','initialization_failed','unknown'):
    g,s=running();reject(failure,lambda:event(g,failure,{}))
for payload in ({'denied':0,'lost':1,'pending':0},{'denied':0,'lost':0,'pending':1},{'denied':1,'lost':0,'pending':0}):
    g,s=running();event(g,'all_dead',dict(live_tasks=0,wait_echild=True))
    reject('final_counter_'+str(payload),lambda:event(g,'complete',payload))
g,s=running();reject('completion_before_death',lambda:event(g,'complete',dict(denied=0,lost=0,pending=0)))
for data in ({'live_tasks':1,'wait_echild':True},{'live_tasks':0,'wait_echild':False}):
    g,s=running();reject('child_lifetime_'+str(data),lambda:event(g,'all_dead',data))
for point in ('start','denial','complete'):
    g,s=setup()
    if point!='start':event(g,'start',dict(start));g.authorize()
    if point=='complete':event(g,'all_dead',dict(live_tasks=0,wait_echild=True))
    g.persist=lambda row:False
    payload={'start':start,'denial':{'nr':41},'complete':dict(denied=0,lost=0,pending=0)}[point]
    reject(point+'_journal_write_sync_overflow',lambda:event(g,point,payload))
    reject(point+'_failure_GO_or_final_refused',lambda:g.finalize(True,True,0,True,True,True))
g,s=running();event(g,'all_dead',dict(live_tasks=0,wait_echild=True));event(g,'complete',dict(denied=0,lost=0,pending=0))
reject('missing_channel_close_final_refused',lambda:g.finalize(True,True,0,True,True,True))
g,s=running();complete(g);reject('post_completion_denial_not_ignored',lambda:event(g,'denial',{}))
g,s=running();s.finalize.side_effect=ValueError('old cleanup fails');complete(g)
reject('old_cleanup_failure_retained',lambda:g.finalize(True,True,0,False,True,True))

# Complete original contract validation: read-only; no runtime or service.
spec=importlib.util.spec_from_file_location('sealed_contract',B/'validation/gazebo-joint-execution-contract-v1/scripts/contract.py')
C=importlib.util.module_from_spec(spec);spec.loader.exec_module(C)
ok('old_full_sealed_contract_valid',lambda:C.read() is not None)
with patch('subprocess.Popen',side_effect=AssertionError('spawn')),patch('subprocess.check_output',side_effect=AssertionError('manager')),patch('os.execve',side_effect=AssertionError('exec')):
    result=launcher.preflight()
ok('refusal_before_manager_service_marker_GO',lambda:result['exit_code']==78 and not any(result[k] for k in ('manager_queried','service_started','marker_created','go_sent')))
source=(R/'inputs/guard.c').read_text()
for term in ('SYS_open','SYS_openat','SYS_socket','SYS_connect','SYS_clone','SYS_clone3','SYS_fork','SYS_execve','SYS_ioctl','SYS_io_uring_enter','SYS_ptrace'):
    policy=source.split('struct journal')[0]
    ok('default_deny_'+term,lambda term=term:('case '+term+':') not in policy and 'default: return 0;' in policy)
ok('record_before_skip_before_resume',lambda:source.index('record(&j,"DENY"')<source.index('regs.orig_rax=UINT64_MAX'))
ok('wait_actual_death_not_exit_event',lambda:source.index('if(event==PTRACE_EVENT_EXIT)')<source.index('"ALL_DEAD"') and 'errno!=ECHILD' in source)
ok('fail_closed_arch_syscall_info_and_no_detach',lambda:'AUDIT_ARCH_X86_64' in source and 'PTRACE_DETACH' not in source and 'PTRACE_O_EXITKILL' in source)
ok('native_main_unconditional_78',lambda:'int main(void) { return 78; }' in source)
# Reuse the sealed source loader and original factories; do not rerun old tests.
import ast
old=B/'validation/gazebo-joint-execution-contract-v1'
sys.path.insert(0,str(old/'scripts'))
import source_loader
with source_loader.runtime(C.read()) as (modules, loaded):
    scope=dict(m=C.read(),AckWindow=modules['protocol'].AckWindow,
               AckSession=modules['protocol'].AckSession,NativeSession=modules['native_gate'].NativeSession)
    tree=ast.parse((old/'tests/test_contract.py').read_text())
    defs=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('packets','setup','ready')]
    exec(compile(ast.Module(body=defs,type_ignores=[]),str(old/'tests/test_contract.py'),'exec'),scope)
    def actual(after_ack=None,final_args=(True,True,0,True,True,True)):
        native,window,out=scope['setup']()
        g=AuditGate(native,binding,lambda row:True)
        event(g,'start',dict(start))
        for row in scope['packets']():g.packet(row)
        scope['ready'](g);g.authorize()
        for i in range(1,101):
            t=i*.001;state={k:0 for k in ['x','y','z','vx','vy','vz','roll','pitch','yaw']}
            state.update(z=1-4.905*t*t,vz=-9.81*t)
            g.packet(dict(kind='sample',iteration=i,sim_time_ns=i*1000000,dt_ns=1000000,paused=False,native_frame=i,native_time=t,init_count=1,state_source='measured_live_components',state=state))
        g.packet(dict(kind='final_wait',iteration=100,sim_time_ns=100000000))
        window.send_ack();assert out==[b'GO\n',b'EXIT_ACK\n']
        if after_ack:event(g,'denial',dict(nr=41,stage='destructor'))
        complete(g)
        return g.finalize(*final_args)
    ok('existing_GO_100_live_mapping_ACK_EOF_cleanup_with_independent_audit',lambda:actual()['status']=='PASS')
    reject('actual_protocol_destructor_denial_after_EXIT_ACK',lambda:actual(after_ack=True))
    for idx,name in ((0,'stdout_EOF'),(1,'stderr_EOF'),(3,'cleanup'),(4,'integrity'),(5,'mapping_final')):
        args=[True,True,0,True,True,True];args[idx]=False
        reject('old_'+name+'_failure_retained',lambda:actual(final_args=tuple(args)))
    ok('original_protocol_source_unchanged',lambda:modules['protocol'].__file__==str(old/'scripts/protocol.py'))

# Original tracked inputs, main dirty files and dangling symlink remain unchanged.
before=json.loads((R/'work/preservation_before.json').read_text())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert all(sha(p)==digest for p,digest in before['files'].items())
main=Path('/home/jiwon/Projects/AeroAIStudio')
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=main,text=True).strip()==before['main_head']
assert [os.fsdecode(x) for x in subprocess.check_output(['git','status','--porcelain','-z'],cwd=main).split(b'\0') if x]==before['main_status']
link=B/'libgz-physics-dartsim-plugin.so';st=link.lstat()
assert [st.st_dev,st.st_ino,os.readlink(link)]==before['symlink']
ok('original_main_and_1442_inputs_symlink_preserved',lambda:True)
report=dict(status='PASS_STATIC_MOCK_ONLY',count=len(checks),checks=checks,subject_execution=False,
            prior_results_reused_not_rerun={'boundary':90,'execution_contract':31},
            reused_reports={str(p.relative_to(B)):sha(p) for p in [B/'validation/gazebo-joint-boundary-v1/reports/tests.json',B/'validation/gazebo-joint-boundary-v1/reports/final_report.md']},
            preserved_files=len(before['files']),runtime='UNVERIFIED')
(R/'reports/tests.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS',len(checks),'static/mock checks; native candidate NOT RUN')
