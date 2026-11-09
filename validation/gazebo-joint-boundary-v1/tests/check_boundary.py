"""Static evidence and pure Python mocks only; no bridge/harness/service run."""
from pathlib import Path
import copy,hashlib,json,os,stat,sys
from unittest.mock import patch
R=Path(__file__).resolve().parents[1];B=R.parents[1]
P=B/'validation/gazebo-joint-external-review-v1'
sys.path.insert(0,str(R/'scripts'))
import fd_policy as F
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
preserve=[P/'reports/tests.json',P/'reports/reused_tests.json',P/'reports/final_report.md',P/'reports/build_receipt.json',P/'reports/candidate_deployment.json']
before={str(p):sha(p) for p in preserve}
source=P/'tests/check_review.py';text=source.read_text()
text=text.replace("R/'reports/reused_tests.json'","NEW/'reports/reused_tests.json'")
text=text.replace("repr(str(R/'work'))","repr(str(NEW/'work'))")
text=text.replace("\n(R/'reports/tests.json').write_text(","\n(NEW/'reports/reused_external_tests.json').write_text(")
scope={'__file__':str(source),'__name__':'reused_static_mock','NEW':R}
exec(compile(text,str(source),'exec'),scope)
assert len(scope['scope']['cases'])==31 and len(scope['checks'])==25
assert before=={p:sha(Path(p)) for p in before}
base=scope['scope'];checks=[]
def good(name,fn):
    assert fn();checks.append(dict(case=name,status='PASS'))
def reject(name,fn):
    try:fn()
    except (ValueError,OSError,KeyError):checks.append(dict(case=name,status='PASS_REJECTED'))
    else:raise AssertionError(name)
def pipe(ino,mode):return dict(device=7,inode=ino,mode=stat.S_IFIFO|0o600,flags=mode)
entry={0:pipe(10,os.O_RDONLY),1:pipe(11,os.O_WRONLY),2:pipe(12,os.O_WRONLY)}
good('distinct_directional_PIPE_entry_accepted',lambda:F.endpoints(entry))
for fd in range(3):
    for kind in (stat.S_IFSOCK,stat.S_IFREG,stat.S_IFCHR):
        rows=copy.deepcopy(entry);rows[fd]['mode']=kind|0o600
        reject('input_'+str(fd)+'_type_'+str(kind),lambda:F.endpoints(rows))
    rows=copy.deepcopy(entry);rows[fd]['flags']=os.O_RDWR
    reject('input_'+str(fd)+'_bidirectional',lambda:F.endpoints(rows))
    rows=copy.deepcopy(entry);rows[fd]['flags']|=os.O_PATH
    reject('input_'+str(fd)+'_O_PATH',lambda:F.endpoints(rows))
for a,b in ((0,1),(0,2),(1,2)):
    rows=copy.deepcopy(entry);rows[b]['inode']=rows[a]['inode']
    reject('aliased_channels_'+str(a)+str(b),lambda:F.endpoints(rows))
rows=copy.deepcopy(entry);del rows[2]
reject('missing_stderr',lambda:F.endpoints(rows))
rows=copy.deepcopy(entry);rows[0]['flags']=os.O_WRONLY
reject('GO_pipe_wrong_direction',lambda:F.endpoints(rows))
rows={0:dict(mode=stat.S_IFCHR|0o666,rdev=os.makedev(1,3),flags=os.O_RDONLY),
      1:pipe(12,os.O_WRONLY),2:pipe(12,os.O_WRONLY),3:pipe(10,os.O_RDONLY),4:pipe(11,os.O_WRONLY)}
def handoff(q):return F.handoff(q,(7,10),(7,11),(7,12),os.makedev(1,3))
good('exact_0_to_4_target_handoff',lambda:handoff(rows))
for kind in (stat.S_IFSOCK,stat.S_IFREG):
    q=copy.deepcopy(rows);q[5]=dict(mode=kind,device=7,inode=15,flags=os.O_RDONLY)
    reject('ambient_handoff_'+str(kind),lambda:handoff(q))
q=copy.deepcopy(rows);q[0]['rdev']=os.makedev(1,5)
reject('stdin_not_null_device',lambda:handoff(q))
q=copy.deepcopy(rows);q[3]['inode']=12
reject('GO_handoff_identity_mismatch',lambda:handoff(q))
q=copy.deepcopy(rows);q[4]['flags']=os.O_RDONLY
reject('observation_handoff_mode_mismatch',lambda:handoff(q))

src=(R/'inputs/fd_bridge.c').read_text()
assert src.index('endpoint(2,O_WRONLY,&err)') < src.index('dup2(2,1)') < src.index('close_range(5') < src.index('execv(exe')
assert 'if(close_range(5,~0U,0)) return 78;' in src
assert 'if(setrlimit(bounds[i].kind,&lim)) return 78;' in src
checks.append(dict(case='candidate_entry_close_range_rlimit_fail_before_exec',status='PASS_STATIC_ONLY'))

# Same observed trace can contain an unreported foreign denied request. The
# collector cannot distinguish it; this counterexample is why release is refused.
s=scope['final_wait']()
assert s.finalize(True,True,0,True,True,True)['status']=='PASS'
checks.append(dict(case='absence_of_denial_packet_is_not_complete_access_evidence',status='PASS_COUNTEREXAMPLE_MOCK_ONLY'))
for when in ('dynamic_init','post_EXIT_ACK'):
    s=base['setup']()[0] if when=='dynamic_init' else scope['final_wait']()
    reject(when+'_observed_denial',lambda:s.packet(dict(kind='aux_resource_request',operation='open',path='/unexpected/config')))
    if when=='dynamic_init':reject('dynamic_init_GO_denied',s.authorize)
    else:reject('shutdown_denial_exit0_EOF_cleanup_still_FAIL',lambda:s.finalize(True,True,0,True,True,True))

with patch('subprocess.Popen',side_effect=AssertionError('spawn')),patch('subprocess.check_output',side_effect=AssertionError('manager')),patch('os.execve',side_effect=AssertionError('exec')):
    result=base['launcher'].preflight()
assert result['exit_code']==78 and not any(result[k] for k in ('manager_queried','service_started','marker_created','go_sent'))
checks.append(dict(case='unclosed_boundary_refuses_before_manager_service_marker',status='PASS_REFUSAL'))
assert before=={p:sha(Path(p)) for p in before}
base['C'].validate(base['m'])
assert scope['main_before']==scope['main_state']()
build=json.loads((R/'reports/build_receipt.json').read_text());assert sha(Path(build['elf']['source']))==build['elf']['sha256']
report=dict(status='PASS_STATIC_MOCK_ONLY',reused_cases=56,new_cases=len(checks),checks=checks,
    prior_evidence_preserved=before,sealed_inputs_revalidated=True,main_preserved=True,
    limitations=['Candidate C checks compiled but not executed','FD model is offline evidence validation, not a live attestor','No general syscall mediation/attempt log; silent denied request remains a technical blocker'],
    subject_execution=False,service_starts=0,marker_consumption=0)
(R/'reports/tests.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS: 56 reused +',len(checks),'new static/mock cases; boundary remains BLOCKED')
