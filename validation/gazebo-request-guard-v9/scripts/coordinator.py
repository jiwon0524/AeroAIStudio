"""Callable pre-loader catalog -> placement -> audit/session coordinator.
No entrypoint invokes native owner, service, mount, target, marker or manager.
The owner must be separately created in its approved bounded domain; existing
owned target-unit creation receipt is mandatory. There is no ambient unit reuse.
"""
import time
from types import SimpleNamespace
from pathlib import Path
import importlib.util,sys
_spec=importlib.util.spec_from_file_location('guard_v8_coordinator_collector',Path(__file__).with_name('collector.py'))
_collector=importlib.util.module_from_spec(_spec);sys.modules[_spec.name]=_collector;_spec.loader.exec_module(_collector)
N,channel,placement,session,control=(_collector.N,_collector.channel,_collector.placement,_collector.session,_collector.control)
class Coordinator:
    def __init__(self,endpoint,catalog,unit,manager,owner,modules,manifest,go_stat,obs_stat,write,
                 stdout,stderr,persist,persist_raw,terminal):
        self.endpoint,self.catalog,self.unit,self.manager,self.owner=endpoint,catalog,unit,manager,owner
        self.modules,self.manifest=modules,manifest;self.go_stat,self.obs_stat,self.write=go_stat,obs_stat,write
        self.stdout,self.stderr,self.persist,self.persist_raw,self.terminal=stdout,stderr,persist,persist_raw,terminal
        self.phase='CATALOG';self.failed=False;self.controller=None;self.placed=None
        self.deadline=time.monotonic()+manifest['deadlines']['host_s']
    def readable(self):
        try:
            N.need(not self.failed and time.monotonic()<self.deadline,'coordinator failed/deadline')
            if self.phase=='CATALOG':
                if self.catalog.packet(self.endpoint):self.phase='PLACEMENT'
                return False
            if self.phase=='PLACEMENT':
                self.placed=placement.receive(self.endpoint,self.owner.pid,self.owner.start,self.owner.executable_sha256,self.unit,self.manager,N)
                self.phase='AUDIT';return False
            N.need(self.phase=='AUDIT','duplicate/out-of-phase owner handoff')
            fd,root=N.receive_audit(self.endpoint,self.owner.pid,self.owner.start,self.owner.executable_sha256,self.owner.run,self.owner.policy)
            try:
                N.need(root.root==self.placed['pid'] and root.root_start==self.placed['start'],'audit root differs from placed target')
                attestor=SimpleNamespace(pid=root.root,start=root.root_start,cgroup=self.unit.cgroup,go_stat=self.go_stat,obs_stat=self.obs_stat)
                native,window,a=session(self.modules,self.manifest,self.catalog,attestor,self.write)
                binding=dict(run=root.run,policy=root.policy,supervisor=self.owner.pid,pid=root.root,start=root.root_start)
                gate=N.old.AuditGate(native,binding,self.persist)
                reader=N.LiveReader(fd,N.NativeJournal(gate,root,self.persist_raw))
                def terminal():
                    args=self.terminal()
                    self.catalog.close()  # retained collector FD cleanup must succeed BEFORE V
                    N.need(time.monotonic()<self.deadline,'host deadline before final verdict')
                    return args
                self.controller=control.Controller(self.endpoint,reader,self.stdout,self.stderr,window,self.modules['protocol'].Lines,self.manifest,terminal)
            except Exception:
                import os
                os.close(fd);os.close(root.pidfd);raise
            self.phase='COLLECTING';return True
        except BlockingIOError:return False
        except Exception:self.failed=True;self.catalog.close();raise
    def collect(self):
        N.need(not self.failed and self.phase=='COLLECTING' and self.controller is not None,'collection before pre-loader handoff')
        try:
            remaining=self.deadline-time.monotonic()
            N.need(remaining>0,'host deadline before collection')
            self.controller.collection_s=min(self.controller.collection_s,remaining)
            return self.controller.run()
        except Exception:self.failed=True;raise
        finally:self.catalog.close()

class BootstrapCoordinator:
    """Initial OWNERV8 -> existing catalog/placement/audit/controller chain.
    Not an executable launcher. Parent must already be waiting at its private
    handoff after native preparation-domain gate. No service is created here.
    """
    def __init__(self,endpoint,parent_pid,parent_start,elf_sha,run,policy,contract_policy,records,
                 unit,manager,modules,manifest,go_stat,obs_stat,write,stdout,stderr,persist,persist_raw,terminal):
        self.endpoint=endpoint
        self.identity=(parent_pid,parent_start,elf_sha,run,policy)
        self.policy,self.records=contract_policy,records
        self.args=(unit,manager,modules,manifest,go_stat,obs_stat,write,stdout,stderr,persist,persist_raw,terminal)
        self.deadline=time.monotonic()+manifest['deadlines']['host_s']
        self.phase='OWNER';self.failed=False;self.coordinator=None
    def readable(self):
        try:
            N.need(not self.failed and time.monotonic()<self.deadline,'bootstrap failed/deadline')
            if self.phase=='OWNER':
                import os,owner,configuration
                parent,start,sha,run,policy=self.identity
                unit,manager,modules,manifest,go,obs,write,stdout,stderr,persist,raw,terminal=self.args
                group=configuration.domain(parent,os.getpid(),unit.cgroup,configuration.read_cgroup,placement.identity)
                bound=owner.bind(self.endpoint,parent,start,sha,group,run,policy,N)
                catalog=channel.Catalog(self.policy,self.records,manifest,bound.pid,bound.start,bound.executable_sha256,persist=persist)
                try:
                    self.coordinator=Coordinator(self.endpoint,catalog,unit,manager,bound,modules,manifest,go,obs,write,stdout,stderr,persist,raw,terminal)
                    self.coordinator.deadline=self.deadline # never reset the initial deadline
                except Exception:catalog.close();raise
                self.phase='CATALOG'
                return False
            result=self.coordinator.readable();self.phase=self.coordinator.phase
            return result
        except BlockingIOError:return False
        except Exception:
            self.failed=True
            if self.coordinator:self.coordinator.catalog.close()
            raise
    def collect(self):
        N.need(not self.failed and self.phase=='COLLECTING' and time.monotonic()<self.deadline,'collection before full handoff/deadline')
        try:return self.coordinator.collect()
        except Exception:self.failed=True;raise
