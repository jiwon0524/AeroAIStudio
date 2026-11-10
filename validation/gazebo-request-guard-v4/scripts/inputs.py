"""Shared input catalog and request-to-FD router; native delivery not released.
RealFD only validates/reopens preparer-owned FDs. Tests inject MockFD operations.
Historical receipts NEVER recreate a live descriptor or namespace attestation.
"""
from dataclasses import dataclass
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from threading import RLock

R=Path(__file__).resolve().parents[1]
path=R.parent/'gazebo-request-guard-v3/scripts/snapshots.py'
spec=importlib.util.spec_from_file_location('reused_snapshots_v3',path)
snapshots=importlib.util.module_from_spec(spec);spec.loader.exec_module(snapshots)

def load_verified():
    c,m,seal=snapshots.catalog.load_contract()
    source=R.parent/'gazebo-request-guard-v3/reports/copy_contract.json'
    raw=source.read_bytes()
    need(hashlib.sha256(raw).hexdigest()=='0a7b6555f2b7d5f615a77560f9d02aa62f7af503909175335e4b1e04bd9e4c52',
         'historical copy receipt changed')
    return c,m,json.loads(raw),seal

def need(ok, why):
    if not ok:raise ValueError(why)

def classify(manifest, previous):
    need(previous['parent_contract_sha256']=='789737d947f8c0ebd1466300792667fc9c838adba5834168e5c82bc6e4846aae','copy/parent contract mismatch')
    roots=set(manifest['roles'].values())|set(manifest['required_canonical_mappings'])|set(manifest['payload'][:2])
    todo=list(sorted(roots));seen=set();via={p:'explicit root' for p in roots}
    while todo:
        p=todo.pop()
        if p in seen:continue
        seen.add(p)
        for e in manifest['soname_edges']:
            if e['consumer']==p:
                via.setdefault(e['mount'],'SONAME from '+p);todo.append(e['mount'])
    expected={tuple(v) for v in manifest['native']['expected'].values() if len(v)==3}
    records=[];all_aliases=set();objects=set()
    for prior in previous['objects']:
        key=(prior['original']['device'],prior['original']['inode'])
        need(key not in objects,'duplicate input object');objects.add(key)
        aliases=prior['aliases'];need(not all_aliases.intersection(aliases),'duplicate input alias')
        all_aliases.update(aliases)
        for p in aliases:
            row=manifest['mounts'][p]
            need(all(row[k]==prior['original'][k] for k in ('device','inode','sha256')),'alias original identity/hash mismatch')
        native=any((manifest['mounts'][p]['sha256'],*key) in expected for p in aliases)
        if prior['status']=='SEALED_BYTES_VERIFIED':
            receipt=prior['receipt']
            need(receipt['original']==prior['original'] and receipt['sha256']==prior['original']['sha256'],
                 'historical copy hash/source projection mismatch')
            need(receipt['seals']&snapshots.REQUIRED_SEALS==snapshots.REQUIRED_SEALS,'historical seal evidence missing')
        witnesses=[dict(path=p,reason=via[p]) for p in aliases if p in seen]
        required=bool(witnesses or native or '/input/joint-elf.sha256' in aliases)
        records.append(dict(original=copy.deepcopy(prior['original']),aliases=list(aliases),
            prepared=prior['status']=='SEALED_BYTES_VERIFIED',
            required=required,requirement='STATIC_REQUIRED' if required else 'SEALED_NOT_REACHED_BY_CURRENT_STATIC_ROOTS',
            witnesses=witnesses,native_expected=native,
            preparation_blocker=prior.get('reason'),
            executable=any(p in manifest['elfs'] for p in aliases)))
    need(all_aliases==set(manifest['mounts']),'input alias coverage')
    return records

@dataclass(frozen=True)
class Request:
    id:int
    task:int
    generation:int
    path:str
    flags:int=0

class RealFD:
    def verify(self,fd,receipt):return snapshots.validate_object(fd,receipt)
    def reopen(self,fd,flags):return os.open('/proc/self/fd/'+str(fd),os.O_RDONLY|os.O_CLOEXEC|(flags&os.O_NONBLOCK))
    def close(self,fd):os.close(fd)
    def namespace_object(self,path,fd,receipt):
        raise ValueError('canonical namespace/path FD attestor NOT_IMPLEMENTED')
    def deliver(self,request,fd):
        raise ValueError('live task binding/ADDFD transport NOT_RELEASED')
    def deny(self,request):
        raise ValueError('live denial transport NOT_RELEASED')

class Catalog:
    def __init__(self,records,ops):
        self.records=records;self.ops=ops;self.pins={};self.paths={};self.lock=RLock();self.closed=False
        for r in records:
            for p in r['aliases']:self.paths[p]=r
    def bind(self,path,fd,receipt):
        with self.lock:
            need(not self.closed,'catalog closed')
            row=self.paths[path];need(row['prepared'],'input preparation blocked')
            need(receipt['original']==row['original'],'source/copy relationship changed')
            need(receipt['sha256']==row['original']['sha256'],'copy hash changed')
            need(receipt['executable_intent'] is row['executable'],'copy execution mode changed')
            need(self.ops.verify(fd,receipt) is True,'live sealed FD verification failed')
            key=(row['original']['device'],row['original']['inode'])
            need(key not in self.pins,'object already bound')
            self.pins[key]=(fd,copy.deepcopy(receipt))
    def resolve(self,request):
        need(not self.closed,'catalog closed')
        need(type(request.path) is str and request.path.startswith('/') and
             '..' not in Path(request.path).parts,'unsafe request path')
        need(type(request.flags) is int and request.flags>=0 and
             not request.flags & ~(os.O_CLOEXEC|os.O_NONBLOCK|os.O_NOFOLLOW),'unsafe request mode')
        row=self.paths.get(request.path);need(row is not None,'unsealed input path')
        need(row['prepared'],'preparation budget/feature blocker')
        key=(row['original']['device'],row['original']['inode'])
        need(key in self.pins,'no retained live copy FD')
        fd,receipt=self.pins[key]
        need(self.ops.verify(fd,receipt) is True,'pinned FD changed')
        need(self.ops.namespace_object(request.path,fd,receipt)==receipt['object'],
             'canonical path references different object')
        opened=self.ops.reopen(fd,request.flags)
        try:
            need(self.ops.verify(opened,receipt) is True,'reopened FD changed')
        except Exception:
            self.ops.close(opened);raise
        return opened
    def close(self):
        with self.lock:
            self.closed=True;errors=[]
            for fd,receipt in self.pins.values():
                try:self.ops.close(fd)
                except Exception as e:errors.append(e)
            self.pins.clear()
            if errors:raise errors[0]

class Router:
    def __init__(self,catalog,audit):self.catalog,self.audit=catalog,audit
    def open(self,request):
        # Private audit validates task generation/request ID and commits BEFORE
        # any response. RLock protects FD lifetimes; it is not OS task proof.
        with self.catalog.lock:
            self.audit.request(request)
            try:fd=self.catalog.resolve(request)
            except ValueError:
                self.audit.prepare(request,denied=True)
                try:self.catalog.ops.deny(request)
                except Exception:
                    self.audit.transport_failure('uncertain denial reply; never retry');raise
                self.audit.reply(request,denied=True)
                return -1
            except Exception:
                self.audit.transport_failure('input FD verification/reopen failure');raise
            try:
                self.audit.prepare(request,denied=False)
                try:answer=self.catalog.ops.deliver(request,fd)
                except Exception:
                    self.audit.transport_failure('uncertain FD reply; never retry')
                    raise
                if type(answer) is not int or answer<0:
                    self.audit.transport_failure('invalid delivery receipt; never retry')
                    raise ValueError('invalid delivery result')
                self.audit.reply(request,denied=False)
                return answer
            finally:self.catalog.ops.close(fd)
