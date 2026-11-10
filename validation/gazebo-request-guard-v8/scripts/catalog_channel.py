"""Owned retained FD catalog transfer, before fork or placement. No preparation.
Never manufactures authority from old receipt numbers. Every received FD passes
same-FD seal/mode/hash/identity validation; aliases project only from those FDs.
"""
from pathlib import Path
import os,socket,struct,hashlib,json,importlib.util,copy

def attest(pid,start,sha):
    before=Path("/proc",str(pid),"stat").read_text().rsplit(")",1)[1].split()[19]
    fd=os.open("/proc/"+str(pid)+"/exe",os.O_RDONLY|os.O_CLOEXEC)
    try:
        h=hashlib.sha256();at=0
        while True:
            block=os.pread(fd,65536,at)
            if not block:break
            h.update(block);at+=len(block)
    finally:os.close(fd)
    after=Path("/proc",str(pid),"stat").read_text().rsplit(")",1)[1].split()[19]
    return before==after==start and h.hexdigest()==sha

R=Path(__file__).resolve().parents[1]
p=R.parent/'gazebo-request-guard-v7/scripts/layout.py';s=importlib.util.spec_from_file_location('v7_layout_reused',p);L=importlib.util.module_from_spec(s);s.loader.exec_module(L)
p=R.parent/'gazebo-request-guard-v3/scripts/snapshots.py';s=importlib.util.spec_from_file_location('v3_snapshots_reused',p);S=importlib.util.module_from_spec(s);s.loader.exec_module(S)
def need(ok,why):
    if not ok:raise ValueError(why)
class Catalog:
    def __init__(self,policy,records,manifest,owner_pid,owner_start,owner_sha,attest_owner=attest,persist=None):
        need(callable(persist),'durable catalog persistence required')
        self.persist=persist
        self.policy,self.records,self.manifest=policy,records,manifest
        self.pid,self.start,self.sha,self.attest=owner_pid,owner_start,owner_sha,attest_owner
        self.pins={};self.closed=False;self.complete=False;self.plan=None
    def packet(self,endpoint):
        data,ancillary,flags,address=endpoint.recvmsg(40,socket.CMSG_SPACE(4)+socket.CMSG_SPACE(12),socket.MSG_CMSG_CLOEXEC|socket.MSG_DONTWAIT)
        fds=[]
        try:
            creds=[];bad=False
            # Collect received rights even if another ancillary record is bad.
            for level,kind,value in ancillary:
                if level==socket.SOL_SOCKET and kind==socket.SCM_RIGHTS:
                    n=len(value)//4
                    if n:fds.extend(struct.unpack(str(n)+'i',value[:n*4]))
                    bad|=len(value)%4!=0
                elif level==socket.SOL_SOCKET and kind==socket.SCM_CREDENTIALS and len(value)==12:creds.append(struct.unpack('3i',value))
                else:bad=True
            need(not self.closed and not self.complete and not bad and not flags&(socket.MSG_TRUNC|socket.MSG_CTRUNC),'catalog frame/source state')
            need(creds==[(self.pid,os.geteuid(),os.getegid())],'catalog credential')
            need(self.attest(self.pid,self.start,self.sha) is True,'catalog source owner identity')
            if data==b'CATEND8\0':
                need(not fds,'unexpected terminal catalog FD')
                self.plan=L.project(self.manifest,self.records,self.pins,S.validate_object)
                need(len(self.plan['mounts'])==468,'catalog path coverage')
                need(self.persist(dict(kind='CATALOG_COMPLETE',objects=len(self.pins),paths=len(self.plan['mounts']),owner_pid=self.pid,owner_start=self.start)) is True,'catalog final persistence')
                need(endpoint.send(b'K',socket.MSG_DONTWAIT|socket.MSG_NOSIGNAL)==1,'catalog complete ACK')
                self.complete=True;return True
            need(len(data)==40 and data[:8]==b'CATV8\0\0\0' and len(fds)==1,'catalog fields/FD count')
            index,dev,ino,size=struct.unpack('4Q',data[8:]);need(index<len(self.policy['paths']),'catalog policy index')
            row=self.policy['paths'][index];o=row['original'];key=(o['device'],o['inode'])
            need(key not in self.pins and size==row['size'],'catalog duplicate/size mismatch')
            receipt=dict(original=copy.deepcopy(o),sha256=o['sha256'],executable_intent=row['executable'],
                object=dict(device=dev,inode=ino,size=size),seals=0x2f)
            S.validate_object(fds[0],receipt)
            need(self.persist(dict(kind='CATALOG_OBJECT',index=index,receipt=copy.deepcopy(receipt),owner_pid=self.pid,owner_start=self.start)) is True,'catalog object persistence')
            self.pins[key]=dict(fd=fds[0],receipt=receipt);fds.clear()
            need(endpoint.send(b'C',socket.MSG_DONTWAIT|socket.MSG_NOSIGNAL)==1,'catalog per-object ACK')
            return False
        except Exception:
            self.close();raise
        finally:
            for fd in fds:os.close(fd)
    def close(self):
        if self.closed:return
        self.closed=True;errors=[]
        for item in self.pins.values():
            try:os.close(item['fd'])
            except OSError as e:errors.append(e)
        if errors:raise errors[0]
