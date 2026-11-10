"""Startup failures through real Python functions with all runtime boundaries
mocked. Tempfile checks only create ordinary diagnostic files, never markers.
C behavior is compile/static checked, not claimed to be kernel validated.
"""
from common import *
import tempfile,stat,copy,select,io
from unittest.mock import patch,Mock
from types import SimpleNamespace as S
import diagnostics as DG,driver as D,collector as C

def run(ok,reject,c,digest):
    with tempfile.TemporaryDirectory(prefix='startup-files-',dir=R/'work') as temp:
        root=Path(temp)
        oldmask=os.umask(0)
        try:
            for name in ('host.stdout','host.stderr','native-parent.stderr'):
                with DG.private_log(root/name,True) as f:
                    ok('private_creation_'+name,stat.S_IMODE(os.fstat(f.fileno()).st_mode)==0o600 and not os.get_inheritable(f.fileno()))
                reject('exclusive_no_truncate_'+name,lambda:DG.private_log(root/name))
            (root/'link').symlink_to(root/'host.stdout')
            reject('private_log_symlink_rejected',lambda:DG.private_log(root/'link'))
        finally:os.umask(oldmask)
        progress=DG.Progress(root/'phases',c['run'],digest)
        progress.record('begin');progress.record('done');progress.close()
        ok('durable_progress_valid',DG.validate_progress(root/'phases',c['run'],digest,['begin','done']))
        reject('missing_stage_is_failure',lambda:DG.validate_progress(root/'phases',c['run'],digest,['absent']))
        reject('wrong_stage_order',lambda:DG.validate_progress(root/'phases',c['run'],digest,['done','begin']))
        reject('wrong_run_diagnostics',lambda:DG.validate_progress(root/'phases','other',digest,['begin']))
        reject('missing_diagnostic_file',lambda:DG.validate_progress(root/'missing',c['run'],digest,['begin']))
        failing=DG.Progress(root/'failure',c['run'],digest)
        with patch.object(DG.os,'fdatasync',side_effect=OSError('injected sync fault')):
            reject('diagnostic_sync_failure_propagates',lambda:failing.record('begin'))
        ok('failed_record_not_counted',failing.count==0);failing.close()
        overflow=DG.Progress(root/'overflow',c['run'],digest)
        reject('startup_cap_fail_closed',lambda:overflow.record('begin',reason='x'*DG.CAP));overflow.close()
        p=root/'native';parent=['entry','restore-control-cloexec','fd-bridge','domain','control-fds','initial-fds','catalog-prepare','userns','owner-send','owner-ack-resume','wait-status','parent-exit']
        worker=['worker-fork','worker-ready','worker-resumed','mount-proc','mount-tmp','mount-catalog','candidate-run-begin','candidate-run-end']
        records=[f'V10DIAG {pid} {i+1} {stage} 0 0\n' for pid,stages in ((400,parent),(1,worker)) for i,stage in enumerate(stages)]
        with DG.private_log(p) as f:f.write(''.join(records).encode())
        ok('native_success_diagnostic_parser',DG.validate_native(p,400))
        prefix=[x for x in records if not any(k in x for k in ('wait-status','parent-exit','candidate-run-end'))]
        p.write_text(''.join(prefix));ok('native_pre_V_diagnostics_valid',DG.validate_native(p,400,complete=False))
        reject('native_pre_V_not_terminal_evidence',lambda:DG.validate_native(p,400))
        for fault in ('missing','rc','sequence','pid','order','stderr_noise','mode'):
            lines=records.copy()
            if fault=='missing':lines.pop()
            if fault=='rc':lines[0]=lines[0].replace('entry 0','entry -1')
            if fault=='sequence':lines[0]=lines[0].replace('400 1','400 2')
            if fault=='pid':lines[0]=lines[0].replace('400','401')
            if fault=='order':lines[0]=lines[0].replace('entry','userns')
            if fault=='stderr_noise':lines.insert(0,'dynamic linker error\n')
            p.write_text(''.join(lines));p.chmod(0o664 if fault=='mode' else 0o600)
            reject('native_diagnostics_reject_'+fault,lambda:DG.validate_native(p,400))
    # Real collector-stage error handling, before any native/anchor execution.
    for fault in ('first_audit','second_audit','progress_write','progress_open'):
        events=[];results=[];opened=[]
        class Progress:
            def __init__(self,*a):
                if fault=='progress_open':raise OSError('injected startup open')
            def record(self,stage,**fields):
                if fault=='progress_write' and stage=='collector-begin':raise OSError('injected startup write')
                events.append((stage,fields));return True
            def close(self):pass
        def audit_open(path,cap):
            opened.append(str(path))
            if fault=='first_audit' or len(opened)==2:raise OSError('injected audit init')
            return 99,lambda *a:True
        state=dict(Id=c['owner_unit'],Description=c['description'],InvocationID='inv',ControlGroup='/owner',MemoryMax='5368709120')
        manager=Mock();manager.inspect.return_value=state
        with patch.object(D,'json_read',lambda p:dict(run=c['run'],contract_sha256=digest)),patch.object(D.C.placement,'identity',lambda p:dict(cgroup='/owner')),patch.object(D.Path,'is_dir',lambda p:True),patch.object(D.Path,'is_symlink',lambda p:False),patch.object(D,'absent_unit',lambda *a:None),patch.object(D.DG,'Progress',Progress),patch.object(D,'persist_to',audit_open),patch.object(D,'exclusive',lambda p,data:results.append(json.loads(data))),patch.object(D.os,'close',lambda fd:None),patch.object(D.subprocess,'Popen',side_effect=AssertionError('native spawn forbidden')):
            rc=D.collector_stage(c,digest,manager)
        ok('collector_audit_init_fail_closed_'+fault,rc==78 and results[0]['status']=='FAIL' and not results[0]['diagnostic_complete'])
        ok('collector_early_reason_persisted_'+fault,(fault=='progress_open' or any(e[0]=='collector-failed' for e in events)) and 'injected' in results[0]['reason'])
        ok('no_native_after_audit_init_failure_'+fault,not any(e[0]=='native-spawned' for e in events))
    # Coordinator receives no initial O and observes HUP; no ACK/GO/V possible.
    stages=[];ep=Mock();ep.fileno.return_value=99
    poll=Mock();poll.poll.return_value=[(99,select.POLLHUP)]
    with patch.object(C.configuration,'domain',lambda *a:'/owner'),patch.object(C.owner,'bind',side_effect=BlockingIOError()),patch.object(C.select,'poll',lambda:poll):
        reject('first_owner_handoff_HUP',lambda:C.coordinate(ep,400,'100','e'*64,c['run'],digest,c['policy'],c['records'],c['manifest'],S(cgroup='/target'),None,10,11,Mock(),Mock(),Mock(),Mock(),Mock(),lambda stage:stages.append(stage) or True))
    ok('early_disconnect_stage_recorded_no_ACK',stages==['owner-bind-begin'] and not ep.send.called)
    with patch.object(C.configuration,'domain',lambda *a:'/owner'),patch.object(C.owner,'bind',side_effect=AssertionError('must not ACK')):
        reject('missing_startup_persistence_before_O',lambda:C.coordinate(ep,400,'100','e'*64,c['run'],digest,c['policy'],c['records'],c['manifest'],S(cgroup='/target'),None,10,11,Mock(),Mock(),Mock(),Mock(),Mock(),lambda stage:False))
    source=(R/'inputs/launch.c').read_text();entry=(R/'inputs/owner_main.c').read_text();driver=(R/'scripts/driver.py').read_text()
    ok('native_diagnostic_before_bridge',entry.index('candidate_owner_diagnostic_fd')<entry.index('candidate_owner_fds('))
    ok('native_diagnostic_separate_empty_audit', 'st.st_size' in source and 'candidate_owner_diagnostic("control-fds",owner_control_fds' in source and 'diagnostic_fd<10' in source)
    ok('target_drops_native_diagnostic_FD','close_range(7,~0U,0)' in source and 'F_DUPFD_CLOEXEC,10' in entry)
    ok('diagnostic_C_write_sync_bounded','++diagnostic_count>32' in source and 'char line[192]' in source and 'fdatasync(diagnostic_fd)' in source)
    ok('host_no_default_mode_open',"(output/'host.stdout').open('xb')" not in driver and "DG.private_log(output/'host.stdout')" in driver)
    ok('native_stderr_not_devnull','stderr=native_diagnostic' in driver)
    ok('collector_diagnostics_before_audit_init',driver.index("progress.record('collector-begin')")<driver.index("persist_to(output/'collector-audit.jsonl'"))
    ok('missing_startup_diagnostic_cannot_PASS',"result.get('diagnostic_complete') is True" in driver and "DG.validate_native(output/'native-parent.stderr'" in driver)
