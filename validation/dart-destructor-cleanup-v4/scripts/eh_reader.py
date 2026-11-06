from common import *
from elf_reader import *
import struct,collections
class Cursor:
 def __init__(self,data,base=0):self.data=data;self.i=0;self.base=base
 def take(self,n):
  if n<0 or self.i+n>len(self.data):raise ValueError('truncated EH field')
  d=self.data[self.i:self.i+n];self.i+=n;return d
 def byte(self):return self.take(1)[0]
 def leb(self,signed=False):
  v=shift=0
  for j in range(10):
   b=self.byte();v|=(b&127)<<shift;shift+=7
   if not b&128:return v-(1<<shift) if signed and b&64 else v
  raise ValueError('oversized LEB128')
 def ptr(self,encoding):
  if encoding==255:return None
  start=self.base+self.i;fmt=encoding&15
  if fmt in (1,9):v=self.leb(fmt==9)
  else:
   widths={0:8,2:2,3:4,4:8,10:2,11:4,12:8}
   if fmt not in widths:raise ValueError('unsupported EH format')
   v=int.from_bytes(self.take(widths[fmt]),'little',signed=fmt>=10)
  app=encoding&0x70
  if app==0x10:v+=start
  elif app!=0:raise ValueError('unsupported EH application')
  return dict(value=v,indirect=bool(encoding&128),encoding=encoding)
def eh_records(e):
 s=e.sections[e.names['.eh_frame']];blob=e.bytes_at(s[4],s[5]);offset=0;cies={};fdes=[]
 while offset+4<=len(blob):
  length=int.from_bytes(blob[offset:offset+4],'little')
  if not length:break
  if length==0xffffffff or offset+4+length>len(blob):raise ValueError('bad EH record length')
  c=Cursor(blob[offset+4:offset+4+length],s[3]+offset+4);cid=int.from_bytes(c.take(4),'little')
  if cid==0:
   version=c.byte();aug=bytearray()
   while True:
    b=c.byte()
    if not b:break
    aug.append(b)
   aug=aug.decode();code=c.leb();data=c.leb(True);ra=c.byte() if version==1 else c.leb();info=dict(offset=offset,augmentation=aug,version=version,encoding=0,lsda_encoding=255,personality=None)
   if aug.startswith('z'):
    size=c.leb();end=c.i+size
    for ch in aug[1:]:
     if ch=='R':info['encoding']=c.byte()
     elif ch=='L':info['lsda_encoding']=c.byte()
     elif ch=='P':info['personality']=c.ptr(c.byte())
     elif ch=='S':pass
     else:raise ValueError('unknown CIE augmentation')
    if c.i>end:raise ValueError('CIE augmentation overrun')
   cies[offset]=info
  else:
   cieoff=offset+4-cid
   if cieoff not in cies:raise ValueError('unknown CIE pointer')
   cie=cies[cieoff];start=c.ptr(cie['encoding']);span=c.ptr(cie['encoding']&15);lsda=None
   if cie['augmentation'].startswith('z'):
    size=c.leb();end=c.i+size
    if cie['lsda_encoding']!=255 and size:lsda=c.ptr(cie['lsda_encoding'])
    if c.i>end:raise ValueError('FDE augmentation overrun')
   fdes.append(dict(offset=offset,start=start['value'],end=start['value']+span['value'],cie=cieoff,lsda=lsda))
  offset+=4+length
 return cies,fdes
