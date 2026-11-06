"""x86_64 ELF table decoding, never dlopen. Numeric addresses are not ABI comparisons."""
from common import *
import struct,re
TARGETS=['CollisionObject','CollisionGroup','CollisionDetector','CollisionResult','Contact','BulletCollisionObject','BulletCollisionGroup','BulletCollisionDetector','ShapeFrame','ShapeNode']
class Elf:
 def __init__(self,path,dynamic=True):
  self.path=Path(path);self.data=self.path.read_bytes();d=self.data
  if d[:6]!=b'\x7fELF\x02\x01':raise ValueError('only ELF64 little endian supported')
  e=struct.unpack_from('<16sHHIQQQIHHHHHH',d);self.sections=[]
  for i in range(e[12]):self.sections.append(struct.unpack_from('<IIQQQQIIQQ',d,e[6]+i*e[11]))
  self.syms={};self.byaddr={}
  for l in run(['readelf','--dyn-syms' if dynamic else '--syms','--wide',path])['stdout'].splitlines():
   a=l.split()
   if len(a)>=8 and a[0].rstrip(':').isdigit():
    n=a[7].split('@')[0];v=dict(address=int(a[1],16),size=int(a[2]),type=a[3],binding=a[4],visibility=a[5],section=a[6],version=a[7][len(n):] or 'UNVERSIONED');self.syms[n]=v
    if a[6]!='UND':self.byaddr.setdefault(v['address'],[]).append(n)
  self.reloc={}
  for l in run(['readelf','-rW',path])['stdout'].splitlines():
   a=l.split()
   if len(a)<4 or not re.fullmatch('[0-9a-fA-F]+',a[0]) or not a[2].startswith('R_X86_64_'):continue
   off=int(a[0],16)
   if a[2]=='R_X86_64_RELATIVE':self.reloc[off]=('relative',int(a[3],16))
   elif len(a)>=5:
    add=int(a[6],16) if len(a)>6 and a[5]=='+' else 0
    self.reloc[off]=('symbol',a[4].split('@')[0],add)
 def read(self,addr,size):
  for s in self.sections:
   if s[1]!=8 and s[3]<=addr and addr+size<=s[3]+s[5]:return self.data[s[4]+addr-s[3]:s[4]+addr-s[3]+size]
  raise ValueError('unmapped address '+hex(addr))
 def pointer(self,addr):
  r=self.reloc.get(addr);raw=struct.unpack('<Q',self.read(addr,8))[0]
  if r and r[0]=='symbol':return dict(kind='symbol',name=r[1],addend=r[2])
  val=r[1] if r else raw
  if val in self.byaddr:return dict(kind='symbol',name=sorted(self.byaddr[val])[0],addend=0)
  signed=val if val<(1<<63) else val-(1<<64)
  if not r or signed<=0:return dict(kind='scalar',value=signed)
  return dict(kind='unresolved_address',value=hex(val))
 def table(self,n):
  s=self.syms[n];return [self.pointer(s['address']+i) for i in range(0,s['size'],8)]
def select(n):return n.startswith(('_ZTV','_ZTI')) and any(re.search(str(len(t))+t+r'(?:E|I)',n) for t in TARGETS)
if __name__=='__main__':
 es={a:Elf(p) for a,p in libs().items()};tables={}
 for a,e in es.items():
  tables[a]={n:dict(metadata=e.syms[n],entries=e.table(n),demangled=run(['c++filt',n])['stdout'].strip()) for n in e.syms if select(n) and e.syms[n]['section']!='UND' and e.syms[n]['size']%8==0}
 compare={}
 for a in ['B','C']:
  compare[a]={n:dict(status=('UNKNOWN_LOCAL_TARGETS' if any(x['kind']=='unresolved_address' for x in tables['A'][n]['entries']+tables[a][n]['entries']) else 'MATCH' if tables['A'][n]['entries']==tables[a][n]['entries'] else 'MISMATCH'),equal=(None if any(x['kind']=='unresolved_address' for x in tables['A'][n]['entries']+tables[a][n]['entries']) else tables['A'][n]['entries']==tables[a][n]['entries']),A=tables['A'][n]['entries'],candidate=tables[a][n]['entries']) for n in tables['A'] if n in tables[a]}
 for a,vs in compare.items():
  for n,v in vs.items():
   pairs=list(zip(v['A'],v['candidate']))
   v['entry_count_equal']=len(v['A'])==len(v['candidate'])
   v['unknown_slots']=[i for i,(x,y) in enumerate(pairs) if x['kind']=='unresolved_address' or y['kind']=='unresolved_address']
   v['known_slot_differences']=[i for i,(x,y) in enumerate(pairs) if i not in v['unknown_slots'] and x!=y]
 type_names={a:{n:e.read(v['address'],v['size']).rstrip(b'\0').decode('ascii',errors='replace') for n,v in e.syms.items() if n.startswith('_ZTS') and any(str(len(t))+t in n for t in TARGETS) and v['section']!='UND'} for a,e in es.items()}
 refs={a:{n:v for n,v in e.syms.items() if v['section']=='UND' and n.startswith(('_ZTV','_ZTI','_ZTS','_ZTh','_ZTv','_ZTc')) and ('4dart' in n)} for a,e in es.items() if a in ['Bullet','Gazebo']}
 save('vtable_rtti.json',dict(tables=tables,type_names=type_names,core_comparison=compare,consumer_refs=refs,scope='Actual relocated ELF pointer entries and Itanium RTTI descriptors; no runtime dispatch/dynamic_cast execution',unresolved={a:[n for n,v in ts.items() if any(x['kind']=='unresolved_address' for x in v['entries'])] for a,ts in tables.items()}))
 print('tables',{a:len(v) for a,v in tables.items()},'mismatches',{a:[n for n,v in vs.items() if v['status']=='MISMATCH'] for a,vs in compare.items()})
