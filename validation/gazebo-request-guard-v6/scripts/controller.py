"""Unreleased multi-stream collector driver. No service/namespace/target creation.
Caller supplies private authenticated handoff and already owned nonblocking pipes.
Native owner runs candidate_run independently; this loop services its audit reader
through actual source EOF, including descendants/destructors after EXIT_ACK.
"""
import json, os, selectors, socket, time
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'gazebo-request-guard-v5/scripts'))
import native_audit as N

class Controller:
    def __init__(self,endpoint,reader,stdout,stderr,window,lines,manifest,terminal):
        self.endpoint,self.reader=endpoint,reader
        self.gate=reader.journal.gate;self.window=window
        self.fds={'stdout':stdout,'stderr':stderr,'audit':reader.fd}
        self.parsers={k:lines(manifest['stream_limits'][k+'_total'],manifest['stream_limits'][k+'_pending']) for k in ('stdout','stderr')}
        self.terminal=terminal
        self.closed=set();self.ready=False;self.failed=False;self.reasons=[]
        self.queued=[];self.queued_bytes=0
        self.queue_cap=sum(manifest['stream_limits'][k+'_total'] for k in ('stdout','stderr'))
        self.collection_s=manifest['deadlines']['collection_s']
        self.ack_ms=manifest['deadlines']['ack_ms'];self.barrier_at=None
        self.completed=False
    def fail(self,reason):
        self.failed=self.gate.failed=True
        if len(self.reasons)<16:self.reasons.append(str(reason))
    def dispatch(self,kind,line):
        N.need(self.ready and not self.failed and not self.gate.failed,'protocol without healthy private audit')
        # Pipe bytes can arrive AFTER audit ALL_DEAD: they are buffered output,
        # not proof of a live task. Existing NativeSession remains authoritative
        # for packet ordering, native identities, ACK and 100-sample criteria.
        if kind=='stdout':
            row=json.loads(line,object_pairs_hook=unique,parse_constant=nonfinite)
            N.need(type(row) is dict,'protocol packet object')
            self.gate.session.packet(row)
        else:self.gate.session.stderr(line.decode('utf-8',errors='strict'))
        session=self.gate.session
        if not self.gate.go and len(session.ready)==2 and len(session.worlds)>=2:self.gate.authorize()
        if self.window.waiting and not self.window.ack:
            self.barrier_at=time.monotonic()
            N.need(not self.failed and not self.gate.failed,'EXIT_ACK after audit failure')
            self.window.send_ack()  # existing live mappings/PID/start check
            N.need((time.monotonic()-self.barrier_at)*1000<self.ack_ms,'EXIT_ACK deadline')
    def step(self,kind,data=None):
        """Single readiness turn; bounded framing and permanent failure latch.
        After failure consume physical streams, never issue GO/ACK/V.
        """
        try:
            N.need(kind in self.fds and kind not in self.closed,'unknown/closed stream')
            if kind=='audit':
                self.reader.readable()
                if self.reader.closed:self.closed.add(kind)
                if self.reader.journal.stage==5 and not self.ready and not self.failed and not self.gate.failed:
                    N.collector_ready(self.endpoint,self.reader);self.ready=True
                    pending,self.queued=self.queued,[];self.queued_bytes=0
                    for k,line in pending:self.dispatch(k,line)
            else:
                if data is None:data=os.read(self.fds[kind],4096)
                if not data:
                    self.closed.add(kind)
                    if not self.failed:self.parsers[kind].finish()
                elif not self.failed:
                    for line in self.parsers[kind].feed(data):
                        if self.ready:self.dispatch(kind,line)
                        else:
                            self.queued_bytes+=len(line)+1
                            N.need(self.queued_bytes<=self.queue_cap,'pre-handoff queue overflow')
                            self.queued.append((kind,line))
        except Exception as e:self.fail(e)
        if self.gate.failed:self.failed=True
    def finish(self):
        try:
            N.need(not self.completed and not self.failed and not self.gate.failed and self.ready,'controller failed/incomplete')
            N.need(self.closed==set(self.fds) and not self.queued,'EOF/queued protocol evidence missing')
            # Observer must collect actual target exit, cleanup and integrity.
            # The owner waiting for V must be outside that cleanup domain.
            args=self.terminal()
            N.need(len(args)==6 and args[0] is True and args[1] is True and type(args[2]) is int and args[2]==0
                   and all(x is True for x in args[3:]),'terminal observation incomplete')
            result=N.collector_verdict(self.endpoint,self.reader,args)
            self.completed=True;return result
        except Exception as e:self.fail(e);raise
    def run(self):
        """Callable active poll loop, not invoked by a released entrypoint.
        No process stop/start operations. Caller retains owned cleanup on failure.
        """
        deadline=time.monotonic()+self.collection_s
        with selectors.DefaultSelector() as poller:
            for k,fd in self.fds.items():
                N.need(not os.get_blocking(fd),'controller requires nonblocking streams')
                poller.register(fd,selectors.EVENT_READ,k)
            while len(self.closed)<3:
                remaining=deadline-time.monotonic()
                if remaining<=0:self.fail('collection/drain deadline');break
                # One bounded read per ready stream avoids audit/protocol starvation.
                for key,mask in poller.select(min(.05,remaining)):
                    self.step(key.data)
                    if key.data in self.closed:poller.unregister(key.fd)
                if not self.completed:
                    # Private owner channel must stay quiet after publication/A.
                    import select
                    events=select.poll();events.register(self.endpoint.fileno(),select.POLLIN|select.POLLHUP|select.POLLERR)
                    if events.poll(0):self.fail('owner control channel data/disconnect before verdict')
        return self.finish()

def unique(pairs):
    result={}
    for k,v in pairs:
        N.need(k not in result,'duplicate protocol key');result[k]=v
    return result

def nonfinite(value):raise ValueError('nonfinite protocol number')

def receive(endpoint,owner_pid,owner_start,executable_sha,run,policy,session,binding,persist,persist_raw,
            stdout,stderr,window,lines,manifest,terminal):
    """Called only on readiness of the existing SO_PASSCRED handoff endpoint.
    Reuses v5 credential/FD-count/pidfd/PID-start/executable attestation.
    No API treats old receipts or a caller boolean as endpoint authentication.
    """
    fd,owner=N.receive_audit(endpoint,owner_pid,owner_start,executable_sha,run,policy)
    try:
        gate=N.old.AuditGate(session,binding,persist)
        journal=N.NativeJournal(gate,owner,persist_raw)
        reader=N.LiveReader(fd,journal)
    except Exception:
        os.close(fd);os.close(owner.pidfd);raise
    return Controller(endpoint,reader,stdout,stderr,window,lines,manifest,terminal)
