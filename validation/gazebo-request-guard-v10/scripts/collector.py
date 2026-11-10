"""Authenticated small owner-to-terminal chain using v9 native audit and v7 loop."""
from common import *
import time,select,socket
import catalog_channel as channel,placement,owner,configuration,protocol,mapping
N=load('v10_native_audit',R/'scripts/native_audit.py')
base=load('v10_reused_controller',R.parent/'gazebo-request-guard-v7/scripts/controller.py')
class Controller(base.Controller):
    def maybe_go(self):
        session=self.gate.session
        if not self.failed and not self.gate.failed and not self.gate.go and self.gate.started and len(session.ready)==2 and session.can_go():self.gate.authorize()
    def step(self,kind,data=None):
        if data is None and kind in ('stdout','stderr'):
            try:data=os.read(self.fds[kind],4096)
            except (BlockingIOError,InterruptedError):return
            except OSError as e:self.fail(e);return
        if kind in ('stdout','stderr') and data:
            try:need(self.stream_sink(kind,data) is True,'raw stream persistence failed')
            except Exception as e:self.fail(e)
        result=super().step(kind,data)
        try:self.maybe_go()
        except Exception as e:self.fail(e)
        return result
    def dispatch(self,kind,line):
        N.need(self.ready and not self.failed and not self.gate.failed,'protocol without independent healthy audit')
        if kind=='stdout':
            row=json.loads(line,object_pairs_hook=base.base.unique,parse_constant=base.base.nonfinite)
            N.need(type(row) is dict,'protocol schema');self.gate.session.packet(row)
        else:self.gate.session.stderr(line.decode('utf-8',errors='strict'))
        session=self.gate.session
        self.maybe_go()
        if self.window.waiting and not self.window.ack:
            started=time.monotonic();self.window.send_ack()
            N.need((time.monotonic()-started)*1000<self.ack_ms,'EXIT_ACK deadline')
class Journal(N.NativeJournal):
    def __init__(self,*a):super().__init__(*a);self.born=self.deaths=self.threads=self.forks=0
    def feed(self,raw):
        super().feed(raw)
        kind=raw.split()[1]
        if kind==b'TASK_BORN':self.born+=1
        elif kind==b'TASK_DEAD':self.deaths+=1
        elif kind==b'THREAD_ALLOWED':self.threads+=1
        elif kind==b'FORK_ALLOWED':self.forks+=1

def coordinate(endpoint,parent,parent_start,owner_sha,run,digest,policy,records,manifest,unit,manager,stdout,stderr,write,persist,raw,terminal,stream_sink):
    """Only the separately approved runtime driver calls this. Test boundaries mocked."""
    deadline=time.monotonic()+manifest['deadlines']['host_s']
    def receive(fn):
        while True:
            need(time.monotonic()<deadline,'pre-loader handoff deadline')
            try:return fn()
            except BlockingIOError:
                p=select.poll();p.register(endpoint.fileno(),select.POLLIN|select.POLLERR|select.POLLHUP)
                events=p.poll(20)
                need(not any(mask&(select.POLLERR|select.POLLHUP) for fd,mask in events),'owner handoff disconnect')
    group=configuration.domain(parent,os.getpid(),unit.cgroup,configuration.read_cgroup,placement.identity)
    bound=receive(lambda:owner.bind(endpoint,parent,parent_start,owner_sha,group,run,digest,N))
    cat=channel.Catalog(policy,records,manifest,bound.pid,bound.start,owner_sha,persist=persist)
    reader=None;root=None;ctl=None
    try:
        while not receive(lambda:cat.packet(endpoint)):pass
        placed=receive(lambda:placement.receive(endpoint,bound.pid,bound.start,owner_sha,unit,manager,N))
        fd,root=receive(lambda:N.receive_audit(endpoint,bound.pid,bound.start,owner_sha,run,digest))
        try:
            need((root.root,root.root_start)==(placed['pid'],placed['start']),'audit root differs from held placed child')
            def observe():
                ops=mapping.SmallProc(channel.S.validate_object,cat.pins)
                ops.catalog(root.root,cat.plan,cat.pins)
                result=mapping.verify(root.root,root.root_start,cat.plan,cat.pins,ops)
                result['map_files_unavailable']=ops.map_files_unavailable
                result['canonical_RO_paths_checked']=len(cat.plan['mounts'])
                need(persist(dict(kind='LIVE_MAPPING',result=result)) is True,'live mapping evidence persistence')
                return result
            window=protocol.AckWindow(write,observe,root.root_start,root.root)
            def initial():
                observe()
                need({1,2}<=set(index for pid,index in journal.delivered if pid==root.native_root),'both root fixed aliases not delivered by broker')
            session=protocol.Session(window,initial)
            session.can_go=lambda:{1,2}<=set(index for pid,index in journal.delivered if pid==root.native_root)
            gate=N.old.AuditGate(session,dict(run=run,policy=digest,supervisor=bound.pid,pid=root.root,start=root.root_start),persist)
            journal=Journal(gate,root,raw);reader=N.LiveReader(fd,journal)
        except Exception:
            os.close(fd);os.close(root.pidfd);raise
        def finish():
            need(journal.threads>=1 and journal.forks==1 and journal.born>=2 and journal.deaths==journal.born+1,'thread/descendant death audit missing')
            descendants={(pid,index) for pid,index in journal.delivered if pid!=root.native_root}
            need({1,2}<=set(index for pid,index in descendants) and len({pid for pid,index in descendants})>=2,'descendant/thread approved FD policy inheritance missing')
            args=terminal(root,placed)
            cat.close()
            need(time.monotonic()<deadline,'host deadline before final V')
            return args
        ctl=Controller(endpoint,reader,stdout,stderr,window,protocol.Lines,manifest,finish)
        ctl.stream_sink=stream_sink
        ctl.collection_s=min(ctl.collection_s,deadline-time.monotonic())
        need(ctl.collection_s>0,'collection host deadline')
        return ctl.run()
    finally:
        cat.close()
        if reader:reader.close()
