"""v9 transport reused with small-profile policy/projection only."""
from common import *
import copy
S=load('v10_snapshots',R.parent/'gazebo-request-guard-v3/scripts/snapshots.py')

def verify_policy(policy,records,manifest):
    rows=policy['paths'];need(len(rows)==5 and len({x['path'] for x in rows})==5,'small five-path policy')
    expected={p for r in records for p in r['aliases']}
    need({x['path'] for x in rows}==expected==set(manifest['mounts']),'missing/unexpected alias')
    for group in records:
        first=next(x for x in rows if x['path']==group['aliases'][0])
        need(first['original']==group['original'],'source object binding')
        for p in group['aliases']:
            x=next(x for x in rows if x['path']==p)
            need(all(x[k]==first[k] for k in ('original','source','size','executable')),'alias substitution')
    need(len(records)==4 and max(r['size'] for r in rows)<4194304,'small object bound')
    return True

class Layout:
    @staticmethod
    def project(manifest,records,pins,verify):
        need(set(pins)=={(x['original']['device'],x['original']['inode']) for x in records},'required pin missing/unexpected')
        mounts={};fds=set();ids=set()
        for row in records:
            key=row['original']['device'],row['original']['inode'];p=pins[key];receipt=p['receipt'];obj=receipt['object']
            need(p['fd']>=5 and p['fd'] not in fds and (obj['device'],obj['inode']) not in ids,'FD or original deduplication')
            need(receipt['original']==row['original'] and receipt['sha256']==row['original']['sha256'] and receipt['executable_intent'] is row['executable'],'pin hash/intent identity')
            need(verify(p['fd'],receipt) is True,'final same-FD immutable verification')
            need(obj['size']==row['size'],'pin size')
            fds.add(p['fd']);ids.add((obj['device'],obj['inode']))
            for name in row['aliases']:mounts[name]=dict(path=name,source_fd=p['fd'],sha256=receipt['sha256'],executable=row['executable'],**obj)
        return dict(mounts=mounts,required_canonical_mappings=manifest['required_canonical_mappings'])
L=Layout
# Materialized below from authenticated v9 source; only profile-specific edits.

import os,socket,struct,hashlib,json
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


class Catalog:
    def __init__(self,policy,records,manifest,owner_pid,owner_start,owner_sha,attest_owner=attest,persist=None):
        need(callable(persist),'durable catalog persistence required')
        verify_policy(policy,records,manifest)
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
                need(len(self.pins)==4 and len(self.plan['mounts'])==5,'catalog path coverage')
                self.plan['native_runtime_identity_consumer']='IMPLEMENTED_NATIVE_V8_FINAL_FD_IDENTITY; runtime unverified'
                self.plan['executable_mapping_policy']='IMPLEMENTED_V8_SERIALIZED_PRIVATE_SEALED_MAPS; runtime unverified'
                self.plan.pop('sha256',None)
                self.plan['sha256']=hashlib.sha256((json.dumps(self.plan,sort_keys=True,separators=(',',':'))+'\n').encode()).hexdigest()
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
