"""Static source/ELF and Python OS/transport mocks. No native output is run."""
from pathlib import Path
import ast,copy,hashlib,json,os,re,sys,struct,subprocess
from types import SimpleNamespace
from unittest.mock import patch,Mock
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'scripts'))
import collector as C
sys.modules.pop("collector",None)  # leave sealed SourceLoader namespace clean
N=C.N;CH=C.channel;P=C.placement
import receipts
source_manifest=json.loads((R/'reports/source_manifest.json').read_text());receipts.verify(source_manifest)
build_receipt_hash=receipts.sha(R/'reports/build_receipt.json')
checks=[]
def ok(name,yes=True):
    assert yes,name
    checks.append(dict(case=name,status='PASS_STATIC_MOCK'))
def reject(name,fn):
    try:fn()
    except (ValueError,OSError,KeyError,TypeError):ok(name)
    else:raise AssertionError(name)
# Previous certified calculations/results are reused by artifact hashes only.
prior=R.parent/'gazebo-request-guard-v7';arts=json.loads((prior/'reports/artifacts.json').read_text())
for name in ('reports/resource_decision.json','reports/tests.json','scripts/layout.py'):
    path=prior/name;ok('prior_hash_'+name,hashlib.sha256(path.read_bytes()).hexdigest()==arts[str(path.relative_to(R.parents[1]))])
ok('prior654_reused_not_rerun',json.loads((prior/'reports/tests.json').read_text())['new_checks']==654)
c,m,seal=CH.S.catalog.load_contract();prev=json.loads((R.parent/'gazebo-request-guard-v3/reports/copy_contract.json').read_text())
spec=__import__('importlib').util.spec_from_file_location('v4_classify',R.parent/'gazebo-request-guard-v4/scripts/inputs.py');v4=__import__('importlib').util.module_from_spec(spec);spec.loader.exec_module(v4)
records=v4.classify(m,prev);policy=json.loads((R/'reports/policy.json').read_text());candidate,rows=C.candidate_inputs(m,records,policy)
paths={p['path'] for p in policy['paths']}
ok('468_exact_required_paths',len(paths)==468 and paths=={p for r in records if r['required'] for p in r['aliases']})
for i,row in enumerate(policy['paths']):
    old=m['mounts'][row['path']];replacement=row['source'] in {policy['native_replacement']['source'],policy['allowlist_replacement']['source']}
    ok('policy_binding_'+str(i), (row['original']['sha256']==old['sha256'] or replacement) and row['size']==Path(row['source']).stat().st_size)
    if replacement:ok('native_replacement_only_'+str(i),old['source'] in {m['mounts'][m['roles']['native']]['source'],m['mounts']['/input/joint-elf.sha256']['source']})
ok('candidate_ELF_allowlist_native_hash_updated',Path(policy['allowlist_replacement']['source']).read_text()==candidate['allowlist_text'] and policy['native_replacement']['sha256']+' '+m['roles']['native'] in candidate['allowlist_text'])
# Synthetic303 same-FD pins; no kernel memfd or mount creation.
pins={}
for i,row in enumerate(r for r in rows if r['required']):
    o=row['original'];record=next(p for p in policy['paths'] if p['path']==row['aliases'][0])
    pins[o['device'],o['inode']]=dict(fd=1000+i,receipt=dict(original=copy.deepcopy(o),sha256=o['sha256'],executable_intent=row['executable'],object=dict(device=777,inode=10000+i,size=record['size']),seals=0x2f))
plan=CH.L.project(candidate,rows,pins,lambda fd,r:True)
cat=SimpleNamespace(complete=True,closed=False,plan=plan,pins=pins)
projected=C.project_runtime(candidate,cat)
ok('native_uses_new_copy_identities_in_collector',all(v[1:]!=m['native']['expected'][k][1:] for k,v in projected['native']['expected'].items() if k!='world_bytes'))
ok('target_resource_limits_unchanged',projected['rlimits']==m['rlimits'] and projected['resources']==m['resources'])
ok('optional_original_mounts_not_required_in_candidate',len(projected['mounts'])==468)
ok('new_native_hash_buildid_in_attestation',all(v['sha256']==policy['native_replacement']['sha256'] and v['build_id']==policy['native_build_id'] for p,v in projected['attestation']['allowed_mappings'].items() if p==m['roles']['native']))
# Catalog handoff enforces count/credentials/FD seal verifier; mock OS only.
class Endpoint:
    def __init__(self,message):self.message=message;self.sent=[]
    def recvmsg(self,*a):return self.message
    def send(self,b,*a):self.sent.append(b);return len(b)
creds=[(N.socket.SOL_SOCKET,N.socket.SCM_CREDENTIALS,struct.pack('3i',500,os.geteuid(),os.getegid()))]
for fault in ('valid','wrong_sender','extra_fd','truncated','wrong_size','bad_seal','replay','early_end','persist_failure'):
    cl=CH.Catalog(policy,rows,candidate,500,'owner','elf',lambda *a:True,persist=lambda row:True);closed=[]
    if fault=='persist_failure':cl.persist=lambda row:False
    entry=policy['paths'][0];fds=[11,12] if fault=='extra_fd' else [11]
    data=b'CATV8\0\0\0'+struct.pack('4Q',0,777,10000,entry['size']+(fault=='wrong_size'))
    peer=copy.deepcopy(creds)
    if fault=='wrong_sender':peer=[(N.socket.SOL_SOCKET,N.socket.SCM_CREDENTIALS,struct.pack('3i',999,os.geteuid(),os.getegid()))]
    ancillary=peer+[(N.socket.SOL_SOCKET,N.socket.SCM_RIGHTS,struct.pack(str(len(fds))+'i',*fds))]
    if fault=='early_end':data=b'CATEND8\0';ancillary=peer
    ep=Endpoint((data,ancillary,N.socket.MSG_CTRUNC if fault=='truncated' else 0,None))
    def validate(fd,r):
        if fault=='bad_seal':raise ValueError('mock missing seal')
        return True
    with patch.object(CH.S,'validate_object',validate),patch.object(CH.os,'close',closed.append):
        if fault=='valid':ok('catalog_live_sameFD_mock',cl.packet(ep) is False and ep.sent==[b'C'] and len(cl.pins)==1)
        elif fault=='replay':cl.packet(ep);reject('catalog_replay',lambda:cl.packet(ep))
        else:reject('catalog_'+fault,lambda:cl.packet(ep))
        if fault not in ('valid','early_end'):ok('catalog_error_closes_owned_FDs_'+fault,bool(closed))
# Complete303 object transfer with real parser/projector and mocked FD kernel verifier.
full=CH.Catalog(policy,rows,candidate,500,'owner','elf',lambda *a:True,persist=lambda row:True);sent=[];next_fd=2000;groups=set()
with patch.object(CH.S,'validate_object',lambda fd,r:True),patch.object(CH.os,'close',lambda fd:None):
    for index,row in enumerate(policy['paths']):
        key=row['original']['device'],row['original']['inode']
        if key in groups:continue
        groups.add(key);next_fd+=1
        message=(b'CATV8\0\0\0'+struct.pack('4Q',index,777,next_fd,row['size']),creds+[(N.socket.SOL_SOCKET,N.socket.SCM_RIGHTS,struct.pack('i',next_fd))],0,None)
        endpoint=Endpoint(message);full.packet(endpoint);sent+=endpoint.sent
    endpoint=Endpoint((b'CATEND8\0',creds,0,None));full.packet(endpoint);sent+=endpoint.sent
ok('303_retained_FD_catalog_complete_468_aliases',len(full.pins)==303 and len(full.plan['mounts'])==468 and sent==[b'C']*303+[b'K'])
# Mapping proof does not trust deleted memfd pathname text.
required=plan['required_canonical_mappings'];all_objects={}
for path in required:
    o=plan['mounts'][path];all_objects[o['device'],o['inode']]=o
maps='\n'.join(f'{0x100000+i*0x2000:x}-{0x101000+i*0x2000:x} r-xp 00000000 00:309 {ino} /memfd:aero-input (deleted)' for i,((dev,ino),o) in enumerate(all_objects.items()))
# 777 decimal =00:309 linux dev minor, while synthetic dev777 uses makedev(0,777).
# Use actual makedev tuple in synthetic receipts for map parser.
for item in pins.values():item['receipt']['object']['device']=os.makedev(0,777)
for obj in plan['mounts'].values():obj['device']=os.makedev(0,777)
seen=[]
ops=SimpleNamespace(start=lambda pid:'s',maps=lambda pid:maps,check=lambda path,r:seen.append(path))
ok('deleted_name_mapping_bound_by_map_files_and_root',C.mapping.verify(100,'s',plan,pins,ops)['status']=='PASS_FILE_IDENTITY' and any('/map_files/' in p for p in seen))
for fault in ('unknown_inode','wrong_start','writable_exec','mapfile_substitution','missing_required'):
    text=maps
    if fault=='unknown_inode':text=maps.replace(str(next(iter(all_objects))[1]),'999999',1)
    if fault=='writable_exec':text=maps.replace('r-xp','rwxp',1)
    if fault=='missing_required':text=''
    def verify(path,r):
        if fault=='mapfile_substitution':raise ValueError('mock inode changed')
    bad=SimpleNamespace(start=lambda pid:'wrong' if fault=='wrong_start' else 's',maps=lambda pid:text,check=verify)
    reject('mapping_'+fault,lambda:C.mapping.verify(100,'s',plan,pins,bad))
# Manager only attaches known held child; never changes target properties.
unit=P.Unit('aero-guard-v8-mock.service','invocation','/target','run')
original=dict(Id=unit.name,InvocationID='invocation',ControlGroup='/target',MemoryMax='536870912',MemorySwapMax='0',TasksMax='64',Delegate='no',KillMode='control-group',LoadState='loaded')
for fault in ('valid','owner_inside','collector_inside','reused_pid','owner_limit_leak','target_limit_leak','wrong_unit','not_stopped','attach_wrong_group'):
    state={500:dict(pid=500,start='owner',ppid=1,state='S',cgroup='/owner'),100:dict(pid=100,start='child',ppid=500,state='t',cgroup='/owner'),600:dict(pid=600,start='collector',ppid=1,state='S',cgroup='/owner')}
    properties=dict(original);called=[]
    if fault=='owner_inside':state[500]['cgroup']='/target'
    if fault=='collector_inside':state[600]['cgroup']='/target'
    if fault=='reused_pid':state[100]['start']='reused'
    if fault=='not_stopped':state[100]['state']='R'
    if fault=='target_limit_leak':properties['MemoryMax']='5368709120'
    if fault=='wrong_unit':properties['InvocationID']='other'
    def attach(name,pid):called.append(pid);state[pid]['cgroup']='/other' if fault=='attach_wrong_group' else '/target'
    manager=SimpleNamespace(inspect=lambda name:dict(properties),attach=attach)
    def limits(pid):
        if fault=='owner_limit_leak':raise ValueError('FSIZE owner value leaked')
        return True
    call=lambda:P.place(100,'child',500,'owner',unit,manager,lambda pid:copy.deepcopy(state[pid]),limits,600,lambda group:True,lambda pid,collector:True)
    if fault=='valid':ok('held_child_target_only_manager_placement',call()['target_limits_verified'] and called==[100] and state[500]['cgroup']=='/owner')
    else:reject('placement_'+fault,call)
# New unit creation command and sealed anchor lifecycle: command/signal mocks only.
props={key:(kind,values) for key,kind,values in P.target_properties('/proc/600/fd/55')}
ok('target_factory_does_not_merge_owner_proposals',props['MemoryMax'][1]==['536870912'] and props['LimitFSIZE'][1]==['1048576'] and props['LimitNOFILE'][1]==['256'] and all(value not in str(props) for value in ('5368709120','2159132672','543979760')))
anchor=dict(fd=55,receipt=dict(sha256='anchorhash',executable_intent=True))
calls=[];manager=SimpleNamespace(call=lambda argv:calls.append(argv) or 'job',inspect=lambda name:dict(original,Id=name))
observed=lambda pid:dict(pid=pid,start='anchor',state='T',cgroup='/target')
newunit=P.create_target(manager,'run',anchor,'anchorhash',lambda fd,r:True,observed,lambda name,r:(10,'anchor'))
ok('new_target_unit_requires_sealed_anchor_and_unique_receipt',newunit.invocation=='invocation' and newunit.name in manager.pending_targets and newunit.name in manager.anchors and 'StartTransientUnit' in calls[0] and '/proc/'+str(os.getpid())+'/fd/55' in calls[0])
reject('target_creation_wrong_anchor_sha',lambda:P.create_target(manager,'run',anchor,'wrong',lambda fd,r:True))
import signal,select
released=[]
with patch.object(P.os,'pidfd_open',lambda pid,flags:99),patch.object(P.os,'close',lambda fd:None),patch.object(signal,'pidfd_send_signal',lambda fd,sig:released.append((fd,sig))),patch.object(select,'poll',lambda:SimpleNamespace(register=lambda *a:None,poll=lambda ms:[(99,1)])):
    P.release_anchor(manager,newunit,observed)
ok('only_new_owned_anchor_released',released==[(99,signal.SIGCONT)] and newunit.name not in manager.anchors)
reject('anchor_cannot_release_twice',lambda:P.release_anchor(manager,newunit,observed))
failed=SimpleNamespace(call=lambda argv:'job',inspect=lambda name:dict(original,Id=name))
def no_stop(name,receipt):raise ValueError('mock initial stop missing')
reject('unit_creation_missing_stop_retains_pending_receipt',lambda:P.create_target(failed,'run',anchor,'anchorhash',lambda fd,r:True,observed,no_stop))
ok('failed_create_not_silently_restarted_or_forgotten',len(failed.pending_targets)==1)
# Original sealed protocol factories + extended native wire parser.
sys.path.insert(0,str(CH.S.catalog.OLD/'scripts'));sys.modules['contract']=c
import source_loader
with source_loader.runtime(m) as (modules,loaded):
    scope=dict(m=m,AckWindow=modules['protocol'].AckWindow,AckSession=modules['protocol'].AckSession,NativeSession=modules['native_gate'].NativeSession)
    tree=ast.parse((CH.S.catalog.OLD/'tests/test_contract.py').read_text());defs=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('setup','ready','packets')]
    exec(compile(ast.Module(body=defs,type_ignores=[]),'sealed_factories','exec'),scope)
    tree=ast.parse((R.parent/'gazebo-request-guard-v6/tests/check.py').read_text());context=next(n for n in tree.body if isinstance(n,ast.With));defs=[n for n in context.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in ('Reader','setup','wire','prefix','packet','initialized','sample','end')]
    env=dict(N=N,C=C.control,m=m,seal=seal,scope=scope,modules=modules,patch=patch,SimpleNamespace=SimpleNamespace,json=json)
    exec(compile(ast.Module(body=defs,type_ignores=[]),'reused_helpers','exec'),env)
    env['Reader'].close=lambda self:setattr(self,'released',True)
    def prefix8(ctl):
        for kind in ('PREEXEC_STOP','PREEXEC_ARMED','FILTER_BOUND','EXEC_STOP','INITIAL_MAPS','TARGET_FDS'):env['wire'](ctl,kind,nr=2 if kind=='INITIAL_MAPS' else (5 if kind=='TARGET_FDS' else -1))
    env['prefix']=prefix8
    attestor=SimpleNamespace(pid=7,start='s',cgroup='/target',go_stat=(1,3),obs_stat=(1,4))
    native,window,a=C.session(modules,candidate,full,attestor,lambda b:None)
    ok('collector_factory_expected_from_live_catalog',native.expected==full.plan['native_expected'] and a.plan['rlimits']==m['rlimits'] and a.plan['resources']==m['resources'])
    packet=copy.deepcopy(scope['packets']()[1])
    reject('old_original_inode_event_cannot_pass_copy_session',lambda:native.packet(packet))
    ctl,j,writes,acks=env['setup']();env['initialized'](ctl)
    for kind,nr in [('MMAP_OBJECT',467),('MMAP_DONE',0),('MPROTECT_OBJECT',0),('MPROTECT_DONE',0),('FD_CLOSE_BEGIN',5),('FD_CLOSE_DONE',0),('VMA_BEGIN',9),('VMA_DONE',0)]:env['wire'](ctl,kind,nr=nr)
    env['wire'](ctl,'REQUEST',nr=262);env['wire'](ctl,'META_OBJECT',nr=468);env['wire'](ctl,'META_DONE',nr=0)
    env['sample'](ctl);env['end'](ctl)
    ok('loader_metadata_journal_original_final_PASS',ctl.finish()['status']=='PASS' and acks==[b'A',b'V'])
    for fault in ('mmap_done_without_begin','overlapping_close','missing_map_exit','missing_metadata_reply','bad_policy_index','record_loss','native_fault'):
        ctl,j,writes,acks=env['setup']();env['initialized'](ctl)
        if fault=='mmap_done_without_begin':env['wire'](ctl,'MMAP_DONE',nr=0)
        elif fault=='overlapping_close':env['wire'](ctl,'MMAP_OBJECT',nr=1);env['wire'](ctl,'FD_CLOSE_BEGIN',nr=5)
        elif fault=='missing_map_exit':env['wire'](ctl,'MMAP_OBJECT',nr=1)
        elif fault=='missing_metadata_reply':env['wire'](ctl,'REQUEST',nr=262);env['wire'](ctl,'META_OBJECT',nr=468)
        elif fault=='bad_policy_index':env['wire'](ctl,'MMAP_OBJECT',nr=468)
        elif fault=='native_fault':env['wire'](ctl,'AUDIT_FAULT')
        else:ctl.reader.queue.append(f'{j.seq+2} VMA_BEGIN 100 9 0\n'.encode());ctl.step('audit')
        env['end'](ctl);reject('final_rejects_'+fault,ctl.finish);ok('no_V_'+fault,b'V' not in acks)
    ctl,j,writes,acks=env['setup']()
    for kind in ('PREEXEC_STOP','PREEXEC_ARMED','FILTER_BOUND','EXEC_STOP'):env['wire'](ctl,kind)
    env['wire'](ctl,'TARGET_FDS',nr=5)
    reject('initial_interpreter_mapping_evidence_mandatory',ctl.finish)
    ok('missing_initial_mapping_no_A_GO',not acks and not writes)
    for fault in ('negative_wrong_result','symlink_wrong_result','unknown_metadata_syscall'):
        ctl,j,writes,acks=env['setup']();env['initialized'](ctl)
        env['wire'](ctl,'REQUEST',nr=999 if fault=='unknown_metadata_syscall' else 262)
        index=468+len(policy['directories'])+(len(policy['negative']) if fault=='symlink_wrong_result' else 0)
        env['wire'](ctl,'META_OBJECT',nr=index)
        env['wire'](ctl,'META_DONE',nr=0)
        env['end'](ctl);reject('metadata_final_rejects_'+fault,ctl.finish)
# Pre-loader coordinator phase failures use mocked manager/transport; no process control.
import coordinator as K
owner=SimpleNamespace(pid=500,start='owner',executable_sha256='elf',run='mock8',policy=seal)
fakecat=SimpleNamespace(packet=Mock(side_effect=[False,True]),closed=False)
fakecat.close=lambda:setattr(fakecat,'closed',True)
coord=K.Coordinator(None,fakecat,unit,None,owner,None,candidate,(1,3),(1,4),lambda b:None,10,11,lambda r:True,lambda r:True,lambda:())
ok('coordinator_catalog_stays_before_END',coord.readable() is False and coord.phase=='CATALOG')
ok('coordinator_catalog_END_before_placement',coord.readable() is False and coord.phase=='PLACEMENT')
with patch.object(K.placement,'receive',lambda *a:dict(pid=100,start='s')):
    ok('coordinator_verified_placement_before_audit',coord.readable() is False and coord.phase=='AUDIT')
wrong=SimpleNamespace(root=101,root_start='s',pidfd=12)
with patch.object(K.N,'receive_audit',lambda *a:(11,wrong)),patch('os.close',lambda fd:None):
    reject('coordinator_audit_root_must_equal_placed_pidfd',coord.readable)
ok('coordinator_failure_closes_retained_catalog',coord.failed and fakecat.closed)
# Ancillary error before SCM_RIGHTS still closes every installed descriptor.
closed=[];ep=Endpoint((b'bad',[(0,999,b'bad')]+creds+[(N.socket.SOL_SOCKET,N.socket.SCM_RIGHTS,struct.pack('i',99))],0,None))
with patch.object(P.os,'close',closed.append):reject('placement_bad_ancillary_closes_later_rights',lambda:P.receive(ep,500,'owner','elf',unit,None,N))
ok('placement_ancillary_FD_not_leaked',closed==[99])
# Native source invariants and compile/link receipts (not C execution).
sources={p.name:p.read_text() for p in (R/'inputs').glob('*.c')}
checks_native={
 'caps_not_raised': 'p->size>67108864' in sources['catalog.c'] and 'budget>536870912ULL' in sources['catalog.c'],
 'stage_bounded_current_admission':'catalog_prepare(rows,COMPILED_PATHS,536870912ULL)' in sources['launch.c'],
 'factory_to_mount_to_run':'candidate_mount_catalog(root,rows,COMPILED_PATHS)' in sources['launch.c'] and 'candidate_run(c,&broker' in sources['launch.c'],
 'mount_from_verified_FD':'mount(src,dst,NULL,MS_BIND,NULL)' in sources['bound.c'] and 'bound_canonical(root,path,pin,sha' in sources['bound.c'],
 'mount_ro_noexec_enforced':'MOUNT_ATTR_RDONLY|MOUNT_ATTR_NOSUID|MOUNT_ATTR_NODEV' in sources['bound.c'] and 'ST_NOEXEC' in sources['bound.c'],
 'whole_catalog_prevalidated_before_first_mount':sources['catalog.c'].index('for(size_t i=0;i<count;i++)if(strcmp')<sources['catalog.c'].index('if(placeholder(root'),
 'bootstrap_close_single_use':'regs.rdi==7 && !listener_closed' in sources['launch.c'] and 'regs.rdi==6 && !socket_closed' in sources['launch.c'],
 'every_close_and_VMA_mutation_traced':'TR(SYS_close)' in sources['launch.c'] and 'TR(SYS_munmap)' in sources['launch.c'] and 'OK(SYS_munmap)' not in sources['launch.c'],
 'FD_mutation_blocked_through_syscall_exit':'file_tx.task?file_tx.task:-1' in sources['launch.c'] and 'if(file_tx.task) {' in sources['launch.c'] and 'PTRACE_SYSCALL_INFO_EXIT' in sources['launch.c'],
 'same_remote_FD_seal_hash_before_mmap':'SYS_pidfd_getfd' in sources['loader.c'] and 'bound_verify(copy,sha' in sources['loader.c'],
 'exec_mprotect_checks_pristine_bytes':'process_vm_readv(pid' in sources['loader.c'] and 'memcmp(original,actual,n)' in sources['loader.c'],
 'shared_or_WX_mapping_denied':'MAP_PRIVATE' in sources['loader.c'] and 'prot&PROT_WRITE' in sources['loader.c'] and 'prot&PROT_EXEC' in sources['loader.c'],
 'negative_lookup_no_ambient_fallback':'if(error!=ENOENT)return -1;' in sources['metadata.c'] and 'META_OBJECT' in sources['metadata.c'],
 'metadata_emulated_not_CONTINUE':'process_vm_writev' in sources['metadata.c'] and 'SECCOMP_USER_NOTIF_FLAG_CONTINUE' not in sources['metadata.c'],
 'child_limits_and_cap_drop_exact':'RLIMIT_AS,2147483648ULL' in sources['launch.c'] and 'RLIMIT_FSIZE,1048576' in sources['launch.c'] and 'RLIMIT_NOFILE,256' in sources['launch.c'] and 'SYS_capset' in sources['launch.c'],
 'placement_ACK_before_arm_and_exec':sources['launch.c'].index('place_held(placement,child,out->pidfd)')<sources['launch.c'].index('control_arm(c,child,journal,audit[1])'),
 'entry_refuses_before_service_marker':sources['entry.c'].endswith('int main(void) { return 78; }\n'),
 'no_manager_limit_mutation':'SetUnitProperties' not in (R/'scripts/placement.py').read_text().split('manager.attach')[0],
}
for name,condition in checks_native.items():ok(name,condition)
native=(R/'inputs/native_resource.cc').read_text()
ok('native_reads_final_sealed_copy_identity', 'bound_verify(fd,id.hash.c_str()' in native and 'uint64_t(a.st_dev)!=id.dev' not in native)
ok('provider_anchor_same_actual_FD','bound_anchor(vtable,providerFd)' in native)
build=json.loads((R/'reports/build_receipt.json').read_text())
ok('11_TUs_1_recompiled_10_attested_reused',len(build['translation_units'])==11 and build['recompiled_translation_units']==1 and build['reused_translation_units']==10 and not build['executed'])
for p,h in build['outputs'].items():ok('ELF_hash_'+Path(p).name,hashlib.sha256(Path(p).read_bytes()).hexdigest()==h)
base=json.loads((R/'work/baseline.json').read_text())
ok('old_tracked_preserved_except_intended_handoff',all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in base['files'].items() if p!='handoff.md'))
link=Path('libgz-physics-dartsim-plugin.so');st=link.lstat();ok('dangling_link_preserved',[st.st_dev,st.st_ino,os.readlink(link)]==base['link'] and not link.exists())
old=json.loads((R.parent/'gazebo-request-guard-v5/work/preservation.json').read_text());main='/home/jiwon/Projects/AeroAIStudio'
ok('main_HEAD_dirty_preserved',subprocess.check_output(['git','rev-parse','HEAD'],cwd=main,text=True).strip()==old['main_head'] and subprocess.check_output(['git','status','--porcelain'],cwd=main,text=True)==old['main_status'])
ok('old1767_evidence_preserved',all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in old['files'].items() if Path(p).name!='handoff.md'))
for p in (R/'scripts').glob('*.py'):compile(p.read_text(),str(p),'exec')
from fd_owner_mocks import run as focused_mocks
focused_mocks(checks)
receipts.verify(source_manifest)
assert receipts.sha(R/'reports/build_receipt.json')==build_receipt_hash
(R/'reports/tests.json').write_text(json.dumps(dict(schema=2,status='PASS_STATIC_PYTHON_MOCK_ONLY',new_checks=len(checks),checks=checks,source_manifest_sha256=source_manifest['sha256'],source_hashes=source_manifest['files'],external_python_hashes=source_manifest['external_python'],build_receipt_sha256=build_receipt_hash,artifact_sha256=build['outputs'],native_outputs_executed=False,services_started=False,limits_changed=False),indent=2)+'\n')
print('PASS',len(checks),'static/Python mock checks; no native execution')
