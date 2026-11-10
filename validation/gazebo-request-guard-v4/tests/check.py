"""Python static/mocks only. No native supervisor/harness, filter or loader run."""
from pathlib import Path
import ast,copy,hashlib,json,os,subprocess,sys
from unittest.mock import Mock
R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R/'scripts'))
from inputs import Catalog,Router,Request,classify,snapshots,RealFD,load_verified
from lifetime import Lifetime
from channel import AuditChannel
import launcher

checks=[]
def ok(name,yes=True):
    assert yes,name
    checks.append(dict(case=name,status='PASS_STATIC_MOCK'))
def reject(name,fn):
    try:fn()
    except (ValueError,OSError,KeyError,TypeError):checks.append(dict(case=name,status='PASS_REJECTED'))
    else:raise AssertionError(name)

c,m,prior,seal=load_verified()
records=classify(m,prior)
historical={tuple(g['original'][k] for k in ('device','inode')):g for g in prior['objects']}
binding=dict(run='mock-v4',policy=seal,supervisor='synthetic-private-owner',pid=100,start='mock')
order=[('private_channel',dict(target_inherited=False,owner_bound=True)),
       ('preexec_stop',dict(root=100,trusted_stub=True)),
       ('ptrace_armed',dict(exitkill=True,all_tasks=True,before_exec=True)),
       ('filter_listener_bound',dict(before_exec=True,target_listener_closed=True,one_shot_exec=True,namespace_fd_attested=True)),
       ('exec_stop',dict(root=100,loader_not_started=True))]

class MockFD:
    """Synthetic open descriptions and namespace. No kernel FD values reused."""
    def __init__(self):
        self.fds={};self.paths={};self.next=10000;self.deliveries=[];self.denials=[]
        self.opens=[];self.closed=[];self.uncertain=False;self.replace_reopen=False
    def new(self,receipt):
        self.next+=1;self.fds[self.next]=copy.deepcopy(receipt);return self.next
    def verify(self,fd,receipt):
        if fd not in self.fds or self.fds[fd]!=receipt:raise ValueError('mock live FD changed')
        return True
    def reopen(self,fd,flags):
        out=self.new(self.fds[fd]);self.opens.append((fd,out,flags))
        if self.replace_reopen:self.fds[out]['object']['inode']+=1
        return out
    def close(self,fd):self.closed.append(fd);self.fds.pop(fd,None)
    def namespace_object(self,path,fd,receipt):return self.paths.get(path)
    def deliver(self,r,fd):
        self.deliveries.append((r,copy.deepcopy(self.fds[fd])))
        if self.uncertain:raise OSError('mock interrupted/uncertain ADDFD')
        return 20+len(self.deliveries)
    def deny(self,r):self.denials.append(r)

def setup(session=None,persist=None,preexec=True):
    rows=[]
    if session is None:
        session=Mock();session.finalize.return_value={'status':'PASS'}
    def save(row):
        if persist:return persist(row)
        rows.append(copy.deepcopy(row));return True
    life=Lifetime(session,binding,save)
    if preexec:
        for kind,data in order:life.preexec(kind,dict(data))
    ops=MockFD();catalog=Catalog(records,ops)
    for i,row in enumerate(records):
        if not row['prepared']:continue
        old=historical[tuple(row['original'][k] for k in ('device','inode'))]['receipt']
        receipt=copy.deepcopy(old)
        receipt['object']=dict(device=777,inode=1000+i,size=old['object']['size'])
        receipt['fd_lifetime']='SYNTHETIC_LIVE_FD_ONLY'
        fd=ops.new(receipt)
        for p in row['aliases']:ops.paths[p]=copy.deepcopy(receipt['object'])
        catalog.bind(row['aliases'][0],fd,receipt)
    return life,ops,catalog,Router(catalog,life),rows

def finish(life):
    for pid,generation in list(life.tasks.items()):life.death(pid,generation,0)
    life.terminal(wait_echild=True);life.eof()

# Representative ODE ELF + its sealed SONAME alias first; then ALL remaining
# prepared inputs under the same checks. The result is explicitly synthetic.
rep=next(r for r in records if m['roles']['ode'] in r['aliases'])
ok('representative_ELF_has_SONAME_alias',rep['prepared'] and len(rep['aliases'])>=2)
paths=rep['aliases']+[p for r in records if r['prepared'] for p in r['aliases'] if p not in rep['aliases']]
life,ops,cat,router,rows=setup();life.authorize()
linked=[]
for i,p in enumerate(paths,1):
    out=router.open(Request(i,100,1,p,os.O_CLOEXEC))
    ok('input_request_'+str(i),out>=0)
    linked.append(p)
ok('same_object_all_representative_aliases',len({(x[1]['object']['device'],x[1]['object']['inode']) for x in ops.deliveries[:len(rep['aliases'])]})==1)
ok('open_descriptions_independent',len({new for old,new,flags in ops.opens})==len(paths))
ok('424_objects_578_aliases_594_total',len(cat.pins)==424 and len(set(linked))==578 and len(cat.paths)==594)
ok('all_prepared_required_aliases_included',all(p in linked for r in records if r['prepared'] and r['required'] for p in r['aliases']))
ok('oversized_5_all_required',len([r for r in records if not r['prepared']])==5 and all(r['required'] for r in records if not r['prepared']))
finish(life);ok('full_input_model_final_audit',life.finalize()['status']=='PASS')
all_input_trace=list(rows)
cat.close();ok('all_pinned_model_FDs_closed',not ops.fds)

for r in records:
    if r['prepared']:continue
    life,ops,cat,router,rows=setup();life.authorize()
    ok('required_oversized_denied_'+str(r['original']['inode']),router.open(Request(1,100,1,r['aliases'][0]))==-1 and not ops.deliveries)
    finish(life);reject('required_budget_denial_final_'+str(r['original']['inode']),life.finalize)
    cat.close()

for flags in (1,2,os.O_CREAT,os.O_TRUNC,os.O_PATH):
    life,ops,cat,router,rows=setup();life.authorize()
    ok('forbidden_flags_'+str(flags),router.open(Request(1,100,1,paths[0],flags))==-1 and not ops.deliveries)
    finish(life);reject('forbidden_flags_final_'+str(flags),life.finalize);cat.close()
life,ops,cat,router,rows=setup();life.authorize()
ok('unlisted_path_denied',router.open(Request(1,100,1,'/unlisted/foreign.so'))==-1);cat.close()
for change in ('namespace_alias','live_object','copy_hash','reopen_object','closed_catalog'):
    life,ops,cat,router,rows=setup();life.authorize();p=paths[0]
    original=cat.paths[p]['original'];fd,receipt=cat.pins[(original['device'],original['inode'])]
    if change=='namespace_alias':ops.paths[p]={'device':777,'inode':99999,'size':1}
    if change=='live_object':ops.fds[fd]['object']['inode']+=1
    if change=='copy_hash':ops.fds[fd]['sha256']='0'*64
    if change=='reopen_object':ops.replace_reopen=True
    if change=='closed_catalog':cat.close()
    ok(change+'_denied',router.open(Request(1,100,1,p))==-1 and not ops.deliveries)
    finish(life);reject(change+'_final_failure',life.finalize);cat.close()
life,ops,cat,router,rows=setup();life.authorize();ops.uncertain=True
reject('uncertain_ADDFD_not_retried',lambda:router.open(Request(1,100,1,paths[0])))
ok('uncertain_exactly_one_delivery_attempt',len(ops.deliveries)==1)
reject('no_new_input_after_transport_failure',lambda:router.open(Request(2,100,1,paths[1])))
ok('transport_failure_does_not_authorize_more_FDs',len(ops.deliveries)==1)
finish(life);reject('uncertain_reply_final_failure',life.finalize);cat.close()

# Persistence failure at decision must precede and prevent actual delivery.
for throws in (False,True):
    life,ops,cat,router,rows=setup();life.authorize()
    original=life.persist
    def broken(row):
        if row['kind']=='input_prepared':
            if throws:raise OSError('mock journal full')
            return False
        return original(row)
    life.persist=broken
    reject('persist_before_response_'+str(throws),lambda:router.open(Request(1,100,1,paths[0])))
    ok('persist_failure_no_delivery_'+str(throws),not ops.deliveries and life.gate.failed);cat.close()

for idx,(kind,data) in enumerate(order):
    life,ops,cat,router,rows=setup(preexec=False)
    for k,d in order[:idx]:life.preexec(k,dict(d))
    reject('GO_missing_'+kind,life.authorize)
    cat.close()
life,ops,cat,router,rows=setup(preexec=False)
reject('exec_before_policy',lambda:life.preexec('exec_stop',order[-1][1]));cat.close()
for key in ('target_listener_closed','one_shot_exec','namespace_fd_attested'):
    life,ops,cat,router,rows=setup(preexec=False)
    for k,d in order[:3]:life.preexec(k,dict(d))
    data=dict(order[3][1]);data[key]=False
    reject('preexec_unproven_'+key,lambda:life.preexec('filter_listener_bound',data));cat.close()

life,ops,cat,router,rows=setup();life.authorize()
life.child(100,101,2,inherited=True);life.child(101,102,3,inherited=True)
a=Request(10,101,2,paths[0]);b=Request(11,102,3,paths[1])
life.request(a);life.request(b);life.prepare(b,denied=False);life.reply(b,denied=False)
life.prepare(a,denied=False);life.reply(a,denied=False)
life.death(100,1,0)
ok('root_death_does_not_end_descendants',not life.echild and len(life.tasks)==2)
life.death(102,3,0);life.death(101,2,0);life.terminal(wait_echild=True);life.eof()
ok('concurrent_descendants_finish_after_root',life.finalize()['status']=='PASS');cat.close()
for fail in ('child_not_inherited','stale_generation','replay','pending_death','missing_ECHILD','child_remaining','overflow'):
    life,ops,cat,router,rows=setup();life.authorize()
    if fail=='child_not_inherited':reject(fail,lambda:life.child(100,101,2,inherited=False))
    if fail=='stale_generation':reject(fail,lambda:life.request(Request(1,100,2,paths[0])))
    if fail=='replay':
        router.open(Request(1,100,1,paths[0]));reject(fail,lambda:router.open(Request(1,100,1,paths[0])))
    if fail=='pending_death':
        life.request(Request(1,100,1,paths[0]));finish(life);reject(fail,life.finalize)
    if fail=='missing_ECHILD':
        life.death(100,1,0);reject(fail,lambda:life.terminal(wait_echild=False))
    if fail=='child_remaining':
        life.child(100,101,2,inherited=True);life.death(100,1,0);reject(fail,lambda:life.terminal(wait_echild=True))
    if fail=='overflow':
        life.MAX_EVENTS=life.raw_seq;reject(fail,lambda:life.request(Request(1,100,1,paths[0])))
    cat.close()
life,ops,cat,router,rows=setup();life.authorize()
for pid in range(101,164):life.child(100,pid,1,inherited=True)
reject('64_task_bound_overflow',lambda:life.child(100,164,1,inherited=True));cat.close()
life,ops,cat,router,rows=setup();life.authorize();life.child(100,101,1,inherited=True)
life.death(101,1,0)
reject('PID_reuse_old_generation_rejected',lambda:life.child(100,101,1,inherited=True));cat.close()
life,ops,cat,router,rows=setup();life.authorize();life.child(100,101,1,inherited=True)
life.death(101,1,0);life.child(100,101,2,inherited=True)
reject('request_from_old_task_generation',lambda:life.request(Request(3,101,1,paths[0])));cat.close()

# Independent framing: fragmented chunks, sequence spaces, binding, EOF, loss.
def decode(trace):
    seen=[];failed=[];ch=AuditChannel(binding,seen.append,failed.append)
    raw=b''.join((json.dumps(r,sort_keys=True)+'\n').encode() for r in trace)
    for i in range(0,len(raw),37):ch.feed(raw[i:i+37])
    ch.eof();return seen,failed
seen,failed=decode(all_input_trace)
ok('all_578_inputs_audit_fragmented_channel',len(seen)==len(all_input_trace) and not failed)
for defect in ('loss','replay','binding','early_EOF','partial_EOF','overflow','duplicate_JSON','trailing_after_complete'):
    trace=copy.deepcopy(all_input_trace[:2]);failures=[];channel=AuditChannel(binding,lambda r:None,failures.append)
    if defect=='loss':trace[0]['seq']=2
    if defect=='replay':trace.append(trace[0])
    if defect=='binding':trace[0]['binding']['run']='foreign'
    raw=b''.join((json.dumps(r)+'\n').encode() for r in trace)
    if defect=='partial_EOF':raw=raw[:-2]
    if defect=='overflow':raw=b'x'*(channel.MAX_LINE+1)
    if defect=='duplicate_JSON':raw=b'{"stream":"gate","stream":"lifecycle"}\n'
    if defect=='trailing_after_complete':
        raw=b''.join((json.dumps(r)+'\n').encode() for r in all_input_trace+[all_input_trace[-1]])
    def consume_bad():channel.feed(raw);channel.eof()
    reject('audit_channel_'+defect,consume_bad);ok('channel_failure_latched_'+defect,bool(failures))

# Existing sealed protocol actual source/factories, unchanged GO/last mapping/
# EXIT_ACK/both EOF/exit/cleanup. This uses synthetic packets, not physical data.
sys.path.insert(0,str(snapshots.catalog.OLD/'scripts'));sys.modules['contract']=c
import source_loader
with source_loader.runtime(m) as (modules,loaded):
    scope=dict(m=m,AckWindow=modules['protocol'].AckWindow,AckSession=modules['protocol'].AckSession,NativeSession=modules['native_gate'].NativeSession)
    defs=[n for n in ast.parse((snapshots.catalog.OLD/'tests/test_contract.py').read_text()).body
          if isinstance(n,ast.FunctionDef) and n.name in ('packets','setup','ready')]
    exec(compile(ast.Module(body=defs,type_ignores=[]),'sealed_protocol_factories','exec'),scope)
    def protocol(violation=None,final=(True,True,0,True,True,True)):
        native,window,out=scope['setup']();life,ops,cat,router,rows=setup(native)
        for p in scope['packets']():life.packet(p)
        scope['ready'](life);life.authorize();router.open(Request(1,100,1,paths[0]))
        for i in range(1,101):
            t=i*.001;state={k:0 for k in ['x','y','z','vx','vy','vz','roll','pitch','yaw']}
            state.update(z=1-4.905*t*t,vz=-9.81*t)
            life.packet(dict(kind='sample',iteration=i,sim_time_ns=i*1000000,dt_ns=1000000,paused=False,
                native_frame=i,native_time=t,init_count=1,state_source='measured_live_components',state=state))
        life.packet(dict(kind='final_wait',iteration=100,sim_time_ns=100000000));window.send_ack()
        assert out==[b'GO\n',b'EXIT_ACK\n']
        if violation=='shutdown_denial':router.open(Request(2,100,1,'/forbidden/destructor.so'))
        if violation=='disconnect':life.eof()
        if violation=='missing_death':return life.finalize(*final)
        finish(life);decode(rows);cat.close();return life.finalize(*final)
    ok('normal_inputs_preexec_old_GO_last_mapping_ACK_EOF_cleanup',protocol()['status']=='PASS')
    for fault in ('shutdown_denial','disconnect','missing_death'):
        reject('old_protocol_'+fault,lambda:protocol(fault))
    for idx,name in ((0,'stdout_EOF'),(1,'stderr_EOF'),(3,'cleanup'),(4,'integrity'),(5,'last_live_mapping')):
        args=[True,True,0,True,True,True];args[idx]=False
        reject('old_protocol_'+name,lambda:protocol(final=tuple(args)))

reject('historical_receipt_never_real_FD_authority',lambda:RealFD().namespace_object(paths[0],0,{}))
control=(R/'inputs/control.c').read_text()
for name,condition in {
    'native_options_set_in_preexec_arm':control.index('PTRACE_SETOPTIONS')<control.index('int control_exec_stop'),
    'actual_initial_wait_stop':'waitpid(child,&status,__WALL|WNOHANG)' in control,
    'native_broker_callback_connected':'b->audit=broker_audit' in control,
    'native_task_notification_identity':'t->request!=id' in control,
    'native_child_event_bound':'PTRACE_GETEVENTMSG' in control,
    'native_journal_bounded':'c->journal_bytes+(size_t)n>1048576' in control,
    'no_preexec_auto_resume':'PTRACE_CONT,' not in control and 'PTRACE_DETACH,' not in control,
    'terminal_requires_ECHILD':'errno!=ECHILD' in control,
    'launcher_exit78_no_service':launcher.preflight()['exit_code']==78 and not launcher.preflight()['service_started'],
}.items():ok(name,condition)

before=json.loads((R/'work/preservation.json').read_text());sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
ok('prior_files_preserved_except_intended_handoff',all(sha(p)==h for p,h in before['files'].items() if Path(p)!=R.parents[1]/'handoff.md'))
main=Path('/home/jiwon/Projects/AeroAIStudio')
ok('main_HEAD_and_dirty_status_preserved',subprocess.check_output(['git','rev-parse','HEAD'],cwd=main,text=True).strip()==before['main_head'] and subprocess.check_output(['git','status','--porcelain'],cwd=main,text=True)==before['main_status'])
link=R.parents[1]/'libgz-physics-dartsim-plugin.so';s=link.lstat()
ok('dangling_symlink_preserved',[s.st_dev,s.st_ino,os.readlink(link)]==before['symlink'])
inventory=dict(parent_contract_sha256=seal,objects=records,representative=rep['aliases'],
    totals=dict(objects=429,historical_prepared_objects=424,prepared_aliases=578,all_paths=594,
        model_linked_paths=len(set(linked)),model_linked_required_paths=sum(len(r['aliases']) for r in records if r['prepared'] and r['required']),
        static_required_objects=sum(r['required'] for r in records),required_budget_blockers=5,runtime_verified_paths=0,target_permitted_paths=0),
    model_linked_paths=linked,live_production_catalog=False)
(R/'reports/input_integration.json').write_text(json.dumps(inventory,indent=2)+'\n')
(R/'reports/tests.json').write_text(json.dumps(dict(status='PASS_STATIC_MOCK_ONLY',count=len(checks),checks=checks,
    model_inputs=len(set(linked)),runtime_inputs=0,prior_input_preparation='REUSED_V3_RECEIPTS; NO_NEW_KERNEL_PREPARATION',
    native_execution=False,prior_tests_not_rerun_or_summed=[101,70,84],preserved_files=len(before['files'])),indent=2)+'\n')
print('PASS',len(checks),'static/mock cases;',len(set(linked)),'model input paths; runtime input paths 0')
