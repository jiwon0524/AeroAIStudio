"""One offline integration state machine around existing NativeSession/AuditGate.
Kernel/start/namespace evidence must eventually come from a private wait owner;
this module does not authenticate Python events or launch/trace any process.
"""
import importlib.util
from pathlib import Path

R=Path(__file__).resolve().parents[1]
path=R.parent/'gazebo-request-guard-v1/scripts/audit_gate.py'
spec=importlib.util.spec_from_file_location('v1_gate',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
AuditGate=module.AuditGate

class Lifetime:
    MAX_TASKS=64
    MAX_EVENTS=8192
    def __init__(self,session,binding,persist):
        self.gate=AuditGate(session,binding,lambda row:persist(dict(stream='gate',**row)))
        self.persist=persist;self.binding=dict(binding)
        self.raw_seq=0;self.stage=0;self.tasks={};self.pending={};self.seen=set()
        self.last_generation={binding['pid']:1};self.seen_ids=set()
        self.root=binding['pid'];self.failed=False;self.echild=False;self.closed=False
        self.channel_bound=False
    def need(self,ok,reason):
        if not ok:
            self.failed=self.gate.failed=True
            raise ValueError(reason)
    def record(self,kind,payload):
        self.need(not self.closed,'late event after EOF')
        self.need(self.raw_seq<self.MAX_EVENTS,'independent journal overflow')
        event=dict(stream='lifecycle',seq=self.raw_seq+1,kind=kind,binding=self.binding,payload=payload)
        try:self.need(self.persist(event) is True,'independent journal persistence failure')
        except Exception:
            self.failed=self.gate.failed=True
            raise
        self.raw_seq+=1
    def gate_event(self,kind,payload):
        self.gate.event(dict(seq=self.gate.seq+1,kind=kind,binding=self.binding,payload=payload),authenticated=True)
    def preexec(self,kind,payload):
        # Explicit ordered evidence, not inferred from an EXEC_STOP packet.
        order=('private_channel','preexec_stop','ptrace_armed','filter_listener_bound','exec_stop')
        self.need(self.stage<len(order) and kind==order[self.stage],'out-of-order/missing preexec evidence')
        expected={
            'private_channel':{'target_inherited':False,'owner_bound':True},
            'preexec_stop':{'root':self.root,'trusted_stub':True},
            'ptrace_armed':{'exitkill':True,'all_tasks':True,'before_exec':True},
            'filter_listener_bound':{'before_exec':True,'target_listener_closed':True,
                                     'one_shot_exec':True,'namespace_fd_attested':True},
            'exec_stop':{'root':self.root,'loader_not_started':True}}
        self.need(module.exact(payload,expected[kind]),'incomplete preexec evidence')
        self.record(kind,payload);self.stage+=1
        if kind=='private_channel':self.channel_bound=True
        if kind=='exec_stop':
            self.tasks[self.root]=1
            self.gate_event('start',dict(pre_loader=True,fd_attested=True,policy_applied=True,
                journal_private=True,lifetime_tracking=True))
    def authorize(self):
        self.need(self.stage==5 and self.channel_bound and not self.failed,'GO before complete private preexec boundary')
        return self.gate.authorize()
    def child(self,parent,child,generation,*,inherited):
        self.need(type(parent) is int and type(child) is int and child>0 and
                  parent in self.tasks and child not in self.tasks and len(self.tasks)<self.MAX_TASKS,
                  'unknown/duplicate/excess child')
        self.need(type(generation) is int and generation>0 and inherited is True,'unverified child policy')
        self.need(generation>self.last_generation.get(child,0),'reused PID requires new generation')
        self.record('task_born',dict(parent=parent,pid=child,generation=generation))
        self.tasks[child]=generation
        self.last_generation[child]=generation
    def request(self,r):
        self.need(not self.failed and self.stage==5 and type(r.task) is int and type(r.generation) is int and
                  self.tasks.get(r.task)==r.generation,'unbound task/generation')
        key=(r.task,r.generation,r.id)
        self.need(type(r.id) is int and r.id>=0 and r.id not in self.seen_ids and
                  key not in self.seen and r.task not in self.pending,
                  'request replay/overlapping task request')
        self.record('request',dict(task=r.task,generation=r.generation,id=r.id,path=r.path,flags=r.flags))
        self.seen.add(key);self.seen_ids.add(r.id);self.pending[r.task]=(key,'request')
    def prepare(self,r,*,denied):
        key=(r.task,r.generation,r.id)
        self.need(self.pending.get(r.task)==(key,'request'),'prepare mismatched request')
        self.record('denial' if denied else 'input_prepared',dict(task=r.task,id=r.id))
        self.pending[r.task]=(key,'denied' if denied else 'prepared')
        if denied:self.gate_event('denial',dict(task=r.task,id=r.id,reason='input denied'))
    def reply(self,r,*,denied):
        key=(r.task,r.generation,r.id);state='denied' if denied else 'prepared'
        self.need(self.pending.get(r.task)==(key,state),'reply mismatched request')
        self.record('replied_denied' if denied else 'input_delivered',dict(task=r.task,id=r.id))
        del self.pending[r.task]
    def transport_failure(self,reason):
        self.failed=self.gate.failed=True
        # Keep death/final receipt collection available after verdict failure.
        self.record('transport_failure',dict(reason=reason))
    def death(self,pid,generation,status):
        self.need(self.tasks.get(pid)==generation,'duplicate/unbound task death')
        self.record('task_dead',dict(pid=pid,generation=generation,status=status))
        if pid in self.pending or status!=0:
            self.gate_event('denial',dict(task=pid,reason='pending/abnormal terminal death'))
            self.pending.pop(pid,None)
        del self.tasks[pid]
    def terminal(self,*,wait_echild):
        self.need(self.stage==5 and not self.tasks and not self.pending and wait_echild is True,
                  'missing terminal all-task wait/ECHILD evidence')
        self.need(not self.echild,'duplicate terminal receipt')
        self.record('all_dead',dict(wait_echild=True));self.echild=True
        self.gate_event('all_dead',dict(live_tasks=0,wait_echild=True))
        self.gate_event('complete',dict(denied=self.gate.denied,lost=0,pending=0))
    def eof(self):
        self.need(self.echild and not self.closed,'early/duplicate private EOF')
        self.gate.eof();self.closed=True
    def packet(self,row):return self.gate.packet(row)
    def stderr(self,line):return self.gate.stderr(line)
    def finalize(self,*args):
        self.need(not self.failed and self.echild and self.closed,'missing independent final evidence')
        return self.gate.finalize(*args)
