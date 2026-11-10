"""New static/Python mocks only; prior555 are authenticated and reused, not rerun."""
from pathlib import Path
import ast,copy,hashlib,json,os,sys,subprocess
from types import SimpleNamespace
from unittest.mock import patch
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'scripts'))
import resources as E
import layout as L
import controller as C
import preflight
N=C.N
checks=[]
def ok(name,yes=True):
    assert yes,name
    checks.append(dict(case=name,status='PASS_STATIC_MOCK'))
def reject(name,fn):
    try:fn()
    except (ValueError,OSError,KeyError,TypeError):ok(name)
    else:raise AssertionError(name)
x=json.loads((R/'reports/resource_decision.json').read_text())
ok('prior555_reused',x['reused_prior_checks']==555 and not x['observations']['usage_peaks_measured'])
ok('five_once_plus_one_buffer_pair',x['large_exact_bytes']==1805492144 and x['large_page_bytes']==1805500416 and x['large_known_preparation_bytes']==1805631488)
ok('298_not_counted_twice',x['prepared298_page_bytes']+x['large_page_bytes']==x['full303_page_bytes']==2159001600)
ok('cold_cache_validation_extra_included',x['all_validated_source_page_bytes']==2171359232 and x['full_preparation_with_cold_source_page_cache']==4330491904)
ok('resource_proposal_exact_unapplied',len(x['proposed_settings'])==3 and [r['proposed'] for r in x['proposed_settings']]==[543979760,2159132672,5368709120] and not x['applied'])
ok('source_verity_not_established',all(not r['read_only_observation']['fsverity_before'] and not r['read_only_observation']['fsverity_after'] for r in x['large_objects']))
ok('inherited_owner_FSIZE_NOFILE_not_target_limits',x['non_changes']['owner_FSIZE']==[-1,-1] and x['non_changes']['owner_NOFILE_observed'][0]>=316 and x['non_changes']['target_rlimits']['FSIZE']==1048576)
c,m,prior,seal=E.A.v5.old.load_verified();records=E.A.v5.old.classify(m,prior)
# Full mock pins are explicitly synthetic, never exported as live receipts.
def pins():
    out={}
    for i,row in enumerate(r for r in records if r['required']):
        o=row['original'];obj=next(r for r in x['objects'] if r['original']==o)
        out[o['device'],o['inode']]=dict(fd=1000+i,receipt=dict(original=copy.deepcopy(o),sha256=o['sha256'],executable_intent=row['executable'],
            object=dict(device=777,inode=10000+i,size=obj['bytes']),seals=0x2f))
    return out
p=pins();seen=[]
plan=L.project(m,records,p,lambda fd,r:seen.append(fd) or True)
ok('303_live_verifier_calls_synthetic',len(seen)==303)
ok('468_contract_path_projection_mock_only',len(plan['mounts'])==468 and set(plan['mounts'])==set(json.loads((R.parent/'gazebo-request-guard-v6/reports/reconciliation.json').read_text())['required_paths']))
ok('original_contract_not_execution_authorized',not plan['execution_authorized'] and plan['release_exit']==78)
for path,row in plan['mounts'].items():
    o=m['mounts'][path];pin=p[o['device'],o['inode']]
    ok('sameFD_alias_hash_projection:'+path,row['source_fd']==pin['fd'] and row['sha256']==o['sha256'] and row['inode']==pin['receipt']['object']['inode'])
for role,v in plan['native_expected'].items():
    if role=='world_bytes':ok('world_bytes_no_inode_rewrite',v==m['native']['expected'][role])
    else:
        old=m['native']['expected'][role];obj=p[old[1],old[2]]['receipt']['object']
        ok('native_expected_projection:'+role,v==[old[0],obj['device'],obj['inode']])
for fault in ('missing','extra','fd_shared','old_source_inode','wrong_hash','writable_exec_intent','missing_seals','merged_DART_by_hash','verifier_false','verifier_error'):
    bad=pins();keys=list(bad);a,b=keys[:2]
    if fault=='missing':bad.pop(a)
    elif fault=='extra':bad[999,999]=bad[a]
    elif fault=='fd_shared':bad[b]['fd']=bad[a]['fd']
    elif fault=='old_source_inode':bad[a]['receipt']['original']['inode']+=1
    elif fault=='wrong_hash':bad[a]['receipt']['sha256']='0'*64
    elif fault=='writable_exec_intent':bad[a]['receipt']['executable_intent']=not bad[a]['receipt']['executable_intent']
    elif fault=='missing_seals':bad[a]['receipt']['seals']=0
    elif fault=='merged_DART_by_hash':
        dart=[k for k,v in bad.items() if v['receipt']['sha256']=='42ff81108e013b45ed1b11a1433cea0ea18964d2280d09c61d05d0fbe49b4af4']
        bad[dart[1]]['receipt']['object']=copy.deepcopy(bad[dart[0]]['receipt']['object'])
    def verify(fd,r):
        if fault=='verifier_error':raise OSError('mock FD closed')
        return fault!='verifier_false'
    reject('projection_'+fault,lambda:L.project(m,records,bad,verify))
owner=dict(pid=1,start='owner',cgroup='/owner',charge_domain='/owner')
target=dict(pid=2,start='target',cgroup='/target',memory_max=536870912,nofile=256,fsize=1048576,address_space=2147483648)
collector=dict(pid=3,start='collector',cgroup='/collector')
ok('owner_outside_target_cleanup_domain',L.placement(owner,target,collector))
for role,field,value in [('owner','cgroup','/target'),('owner','cgroup','/target/child'),('collector','cgroup','/target'),('owner','charge_domain','/elsewhere'),('target','memory_max',536870913),('target','fsize',543979760),('target','start','')]:
    args=copy.deepcopy([owner,target,collector]);idx=('owner','target','collector').index(role);args[idx][field]=value
    reject('placement_'+role+'_'+field+'_'+str(value),lambda:L.placement(*args))
# Reuse original sealed Python protocol factories, and only v6 test helpers.
sys.path.insert(0,str(E.A.v5.old.snapshots.catalog.OLD/'scripts'));sys.modules['contract']=c
import source_loader
with source_loader.runtime(m) as (modules,loaded):
    scope=dict(m=m,AckWindow=modules['protocol'].AckWindow,AckSession=modules['protocol'].AckSession,NativeSession=modules['native_gate'].NativeSession)
    t=ast.parse((E.A.v5.old.snapshots.catalog.OLD/'tests/test_contract.py').read_text())
    exec(compile(ast.Module(body=[n for n in t.body if isinstance(n,ast.FunctionDef) and n.name in ('setup','ready','packets')],type_ignores=[]),'sealed_factories','exec'),scope)
    t=ast.parse((R.parent/'gazebo-request-guard-v6/tests/check.py').read_text())
    context=next(n for n in t.body if isinstance(n,ast.With))
    defs=[n for n in context.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in ('Reader','setup','wire','prefix','packet','initialized','sample','end')]
    env=dict(N=N,C=C,m=m,seal=seal,scope=scope,modules=modules,patch=patch,SimpleNamespace=SimpleNamespace,json=json)
    exec(compile(ast.Module(body=defs,type_ignores=[]),'reused_v6_test_helpers','exec'),env)
    def close(self):self.released=True
    env['Reader'].close=close
    def complete():
        ctl,j,writes,acks=env['setup']();env['initialized'](ctl);env['sample'](ctl)
        env['end'](ctl);return ctl,j,writes,acks
    ctl,j,writes,acks=complete()
    ok('controller_original_GO_ACK_finalize',ctl.finish()['status']=='PASS' and writes==[b'GO\n',b'EXIT_ACK\n'] and acks==[b'A',b'V'])
    for fault in ('EAGAIN','EINTR'):
        ctl,j,writes,acks=env['setup']()
        exception=BlockingIOError() if fault=='EAGAIN' else InterruptedError()
        with patch.object(C.os,'read',side_effect=exception):ctl.step('stdout')
        ok('spurious_readiness_'+fault,not ctl.failed and not ctl.closed)
    ctl,j,writes,acks=env['setup']();env['initialized'](ctl);env['sample'](ctl)
    for kind in ('EXIT_STOP','TASK_DEAD','ALL_DEAD','COMPLETE'):env['wire'](ctl,kind,nr=0 if kind=='TASK_DEAD' else -1)
    ctl.reader.queue.append(None)
    class ReadyPoller:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def register(self,*a):pass
        def unregister(self,*a):pass
        def select(self,timeout):return [(SimpleNamespace(data=k,fd=fd),1) for k,fd in ctl.fds.items() if k not in ctl.closed]
    with patch.object(C.selectors,'DefaultSelector',ReadyPoller),patch.object(C.os,'get_blocking',lambda fd:False),patch.object(C.os,'read',lambda fd,n:b''),patch.object(C.select,'poll',lambda:SimpleNamespace(register=lambda *a:None,poll=lambda n:[])):
        ok('new_active_loop_success_releases_before_V',ctl.run()['status']=='PASS' and ctl.reader.released and acks==[b'A',b'V'])
    ctl,j,writes,acks=env['setup']();env['initialized'](ctl)
    with patch.object(C.selectors,'DefaultSelector',ReadyPoller),patch.object(C.os,'get_blocking',lambda fd:False),patch.object(C.time,'monotonic',side_effect=[0,26]):
        reject('active_loop_deadline_rejects',ctl.run)
    ok('deadline_failure_releases_audit_FDs_and_no_V',ctl.failed and ctl.reader.released and acks==[b'A'])
    ctl,j,writes,acks=env['setup']()
    with patch.object(C.os,'read',side_effect=OSError('mock invalid descriptor')):ctl.step('stdout')
    ok('direct_step_read_fault_latched',ctl.failed and ctl.gate.failed)
    ctl,j,writes,acks=env['setup']()
    reject('mixed_window_rejected',lambda:C.Controller(ctl.endpoint,ctl.reader,902,903,object(),modules['protocol'].Lines,m,ctl.terminal))
    reject('shared_protocol_audit_FD_rejected',lambda:C.Controller(ctl.endpoint,ctl.reader,900,903,ctl.window,modules['protocol'].Lines,m,ctl.terminal))
    class Poller:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def register(self,*a):pass
        def unregister(self,*a):pass
        def select(self,timeout):raise OSError('mock selector fault')
    ctl,j,writes,acks=env['setup']()
    with patch.object(C.selectors,'DefaultSelector',Poller),patch.object(C.os,'get_blocking',lambda fd:False):reject('selector_fault_latched',ctl.run)
    ok('selector_fault_closed_owned_audit_FDs',ctl.failed and ctl.gate.failed and ctl.reader.released and b'V' not in acks)
    ctl,j,writes,acks=complete();ctl.closed=set(ctl.fds)
    def badclose():raise OSError('mock descriptor release failure')
    ctl.reader.close=badclose
    with patch.object(C.selectors,'DefaultSelector',Poller),patch.object(C.os,'get_blocking',lambda fd:False):reject('descriptor_release_failure_before_V',ctl.run)
    ok('release_failure_no_V',ctl.failed and acks==[b'A'])
    # Factory forwards all authentication and closes if projection/session construction fails.
    ctl,j,writes,acks=env['setup']()
    with patch.object(C.base,'receive',lambda *a,**k:ctl):
        new=C.receive(manifest=m)
        ok('receive_reuses_authenticated_reader',new.reader is ctl.reader)
        ctl.window=object()
        reject('receive_constructor_error_closes_reader',lambda:C.receive(manifest=m))
        ok('receive_error_owned_FDs_released',ctl.reader.released)
base=json.loads((R/'work/baseline.json').read_text())
ok('all_previous_tracked_files_preserved_except_handoff',all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in base['files'].items() if p!='handoff.md'))
link=Path('libgz-physics-dartsim-plugin.so');st=link.lstat()
ok('dangling_symlink_preserved',[st.st_dev,st.st_ino,os.readlink(link)]==base['link'] and not link.exists())
before=json.loads((R.parent/'gazebo-request-guard-v5/work/preservation.json').read_text());main='/home/jiwon/Projects/AeroAIStudio'
ok('original_main_HEAD_dirty_status_preserved',subprocess.check_output(['git','rev-parse','HEAD'],cwd=main,text=True).strip()==before['main_head'] and subprocess.check_output(['git','status','--porcelain'],cwd=main,text=True)==before['main_status'])
ok('prior_local1767_evidence_preserved',all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in before['files'].items() if Path(p).name!='handoff.md'))
parent_build=json.loads((R.parent/'gazebo-request-guard-v6/reports/build_receipt.json').read_text())
ok('unchanged_native_ELF_hash_reused',hashlib.sha256((R.parent/'gazebo-request-guard-v6/work/candidate').read_bytes()).hexdigest()==parent_build['elf_sha256'])
for p in (R/'scripts').glob('*.py'):compile(p.read_text(),str(p),'exec')
ok('changed_Python_sources_compile_no_execution')
f=preflight.result();ok('preflight78_without_service_marker_or_approval',f['exit_code']==78 and not f['service_started'] and not f['marker_consumed'] and not f['runtime_approval_ready'] and len(f['pending_implementation'])==4)
result=dict(status='PASS_STATIC_PYTHON_MOCK_ONLY',new_checks=len(checks),prior_checks_reused=555,checks=checks,native_execution=False,services_started=False,limits_changed=False)
(R/'reports/tests.json').write_text(json.dumps(result,indent=2)+'\n')
print('PASS',len(checks),'new checks; prior555 reused, no native runtime')
