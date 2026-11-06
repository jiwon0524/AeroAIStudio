"""Bounded ELF64 little-endian x86_64 reader; no loader or target execution."""
from common import *
import struct,re
class Elf:
 def __init__(self,path):
  self.path=Path(path);self.data=self.path.read_bytes();d=self.data
  if len(d)<64 or d[:6]!=b'\x7fELF\x02\x01':raise ValueError('unsupported/truncated ELF header')
  e=struct.unpack_from('<16sHHIQQQIHHHHHH',d)
  if e[2]!=62 or e[11]!=64 or not e[12] or e[13]>=e[12]:raise ValueError('unsupported machine/section geometry')
  self.etype=e[1];off=e[6];count=e[12]
  if off+count*64>len(d):raise ValueError('truncated section table')
  self.sections=[struct.unpack_from('<IIQQQQIIQQ',d,off+i*64) for i in range(count)]
  for s in self.sections:
   if s[1]!=8:self.bytes_at(s[4],s[5])
  names=self.sections[e[13]];strings=self.bytes_at(names[4],names[5]);self.names={}
  for i,s in enumerate(self.sections):self.names[self.cstring(strings,s[0])]=i
  self.symbols=[];self.tables={};self.byaddr={}
  for i,s in enumerate(self.sections):
   if s[1] not in (2,11):continue
   if s[9]!=24 or s[5]%24 or s[6]>=count:raise ValueError('invalid symbol section')
   st=self.sections[s[6]];strings=self.bytes_at(st[4],st[5]);rows=[]
   for j in range(s[5]//24):
    n,info,other,idx,value,size=struct.unpack_from('<IBBHQQ',d,s[4]+j*24);name=self.cstring(strings,n)
    v=dict(name=name,address=value,size=size,binding=info>>4,type=info&15,visibility=other&3,section=idx,table='dynamic' if s[1]==11 else 'full');rows.append(v)
    if name:self.symbols.append(v)
    if idx and name:self.byaddr.setdefault(value,[]).append(v)
   self.tables[i]=rows
  self.reloc={}
  for s in self.sections:
   if s[1]!=4:continue
   if s[9]!=24 or s[5]%24 or s[6] not in self.tables:raise ValueError('invalid RELA section')
   rows=self.tables[s[6]]
   for j in range(s[5]//24):
    at,info,add=struct.unpack_from('<QQq',d,s[4]+j*24);sym=info>>32;typ=info&0xffffffff
    if sym>=len(rows):raise ValueError('invalid relocation symbol index')
    self.reloc[at]=dict(type=typ,name=rows[sym]['name'],addend=add)
 def bytes_at(self,off,n):
  if off<0 or n<0 or off+n>len(self.data):raise ValueError('file offset out of range')
  return self.data[off:off+n]
 @staticmethod
 def cstring(data,off):
  if off>=len(data):raise ValueError('invalid string offset')
  end=data.find(b'\0',off)
  if end<0:raise ValueError('unterminated ELF string')
  return data[off:end].decode('utf8',errors='replace')
 def read(self,addr,n):
  if self.etype not in (2,3):raise ValueError('ET_REL needs section-relative addressing')
  for s in self.sections:
   if s[1]!=8 and s[2]&2 and s[3]<=addr and addr+n<=s[3]+s[5]:return self.bytes_at(s[4]+addr-s[3],n)
  raise ValueError('unmapped virtual address')
 def sym(self,name):
  vs=[v for v in self.symbols if v['name']==name and v['section']]
  if not vs:raise ValueError('missing symbol '+name)
  return vs[0]
 def read_symbol(self,name):
  v=self.sym(name)
  if self.etype in (2,3):return self.read(v['address'],v['size'])
  if v['section']>=len(self.sections):raise ValueError('non-file symbol')
  s=self.sections[v['section']]
  if v['address']+v['size']>s[5]:raise ValueError('symbol exceeds section')
  return self.bytes_at(s[4]+v['address'],v['size'])
 def pointer(self,addr):
  raw=struct.unpack('<Q',self.read(addr,8))[0];r=self.reloc.get(addr)
  if r:
   if r['type']==8:return dict(kind='address',address=r['addend'],relocation=r)
   if r['type'] in (1,6,7):return dict(kind='symbol',name=r['name'],addend=r['addend'],relocation=r)
   raise ValueError('unsupported pointer relocation '+str(r['type']))
  return dict(kind='raw',address=raw,relocation=None)
 def table(self,name):
  v=self.sym(name)
  if v['size']%8:raise ValueError('misaligned table size')
  return [self.pointer(v['address']+i) for i in range(0,v['size'],8)]
 def aliases(self,addr):return [v for v in self.byaddr.get(addr,[]) if v['type']==2]
 def section_summary(self):return {n:dict(address=self.sections[i][3],size=self.sections[i][5],sha256=hashlib.sha256(self.bytes_at(self.sections[i][4],self.sections[i][5])).hexdigest()) for n,i in self.names.items() if n in ['.eh_frame','.eh_frame_hdr','.gcc_except_table','.debug_info']}
def variant(n):
 m=re.search(r'(D[012]|C[123])E',n)
 return m.group(1) if m else None
def frames(path):
 p=run(['readelf','--debug-dump=frames-interp',path]);assert p['rc']==0
 fdes={int(a,16):dict(end=int(b,16),record=off,cie=cie) for off,cie,a,b in re.findall(r'^([0-9a-f]+).*?FDE cie=([0-9a-f]+) pc=([0-9a-f]+)\.\.([0-9a-f]+)',p['stdout'],re.M)}
 return fdes,p['stdout']
