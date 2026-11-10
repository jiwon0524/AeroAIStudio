"""Reuse v6 collector; close ownership/transport fault paths without activation."""
from pathlib import Path
import importlib.util,os,time,selectors,select
p=Path(__file__).resolve().parents[2]/'gazebo-request-guard-v6/scripts/controller.py'
s=importlib.util.spec_from_file_location('guard_v6_controller',p);base=importlib.util.module_from_spec(s);s.loader.exec_module(base)
N=base.N
class Controller(base.Controller):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        N.need(self.gate.session.window is self.window,'mixed ACK/session window')
        N.need(len(set(self.fds.values()))==3,'shared stream descriptors')
    def step(self,kind,data=None):
        if data is None and kind in ('stdout','stderr'):
            try:data=os.read(self.fds[kind],4096)
            except (BlockingIOError,InterruptedError):return
            except OSError as e:self.fail(e);return
        return super().step(kind,data)
    def run(self):
        deadline=time.monotonic()+self.collection_s
        try:
            with selectors.DefaultSelector() as poller:
                for kind,fd in self.fds.items():
                    N.need(not os.get_blocking(fd),'controller requires nonblocking streams')
                    poller.register(fd,selectors.EVENT_READ,kind)
                while len(self.closed)<3:
                    remaining=deadline-time.monotonic()
                    if remaining<=0:self.fail('collection/drain deadline');break
                    try:events=poller.select(min(.05,remaining))
                    except InterruptedError:continue
                    for key,mask in events:
                        self.step(key.data)
                        if key.data in self.closed:poller.unregister(key.fd)
                    owner=select.poll()
                    owner.register(self.endpoint.fileno(),select.POLLIN|select.POLLHUP|select.POLLERR)
                    if owner.poll(0):self.fail('owner control channel data/disconnect before verdict')
            self.reader.close()  # descriptor release failure must precede final V
            return self.finish()
        except Exception as e:
            self.fail(e);raise
        finally:
            try:self.reader.close()
            except Exception as e:self.fail(e);raise

def receive(*args,**kwargs):
    # Existing receive_audit + LiveReader perform source authentication. Reuse
    # that factory, then validate session/window and descriptors before A/GO.
    old=base.receive(*args,**kwargs)
    try:return Controller(old.endpoint,old.reader,old.fds['stdout'],old.fds['stderr'],old.window,
        type(old.parsers['stdout']),kwargs.get('manifest',args[14] if len(args)>14 else None),old.terminal)
    except Exception:
        old.reader.close();raise
