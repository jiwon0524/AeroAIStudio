from common import *
from elf_reader import *
import re,collections
VT='_ZTVN4dart8dynamics9ShapeNodeE'
def normalize(text,start,end,known_targets):
 lines=[];masked=[]
 for line in text.splitlines():
  m=re.match(r'^\s*([0-9a-f]+):\s+(.*)$',line)
  if not m:continue
  addr=int(m[1],16);asm=m[2];asm=asm.split('#')[0].strip();asm=re.sub(r'\s+',' ',asm)
  asm=re.sub(r'-?0x[0-9a-f]+\(%rip\)', '<RIP>(%rip)',asm)
  if '<RIP>' in asm:masked.append('RIP-relative data address')
  b=re.match(r'((?:call|j\w+)\s+)([0-9a-f]+)(?:\s+<[^>]+>)?(.*)',asm)
  if b:
   target=int(b[2],16)
   if start<=target<end:label='SELF+'+hex(target-start)
   elif target in known_targets:label=known_targets[target]
   else:label='UNRESOLVED_CALLEE';masked.append('unnamed callee target')
   asm=b[1]+label+b[3]
  asm=re.sub(r'\s*<[^>]+>','',asm)
  lines.append(asm)
 return dict(instructions=lines,masked=sorted(set(masked)))
if __name__=='__main__':
 old=json.loads((V2/'reports/vtable_rtti.json').read_text());indices=old['core_comparison']['B'][VT]['unknown_slots'];assert len(indices)==67
 es={a:Elf(p) for a,p in libs().items() if a in ['A','B','C']};tabs={a:e.table(VT) for a,e in es.items()}
 raw={a:old['tables'][a][VT]['entries'] for a in es};assert all(len(t)==275 for t in tabs.values())
 frame={};targets={};snippets={};known={a:{} for a in es}
 for a,e in es.items():
  frame[a],text=frames(e.path);(R/f'work/{a}.frames').write_text(text)
  for addr,vs in e.byaddr.items():
   ns=sorted({v['name'] for v in vs if v['name'].startswith('_Z') and v['type']==2})
   if ns:known[a][addr]=ns[0]
  for i in indices:
   addr=tabs[a][i]['address'];assert raw[a][i]['value']==hex(addr)
   aliases=e.aliases(addr);ns=sorted({v['name'] for v in aliases if v['name'].startswith('_Z')});targets.setdefault(i,{})[a]=dict(address=addr,aliases=aliases,identity=ns[0] if ns else None)
 # Transport B names to A only as INFERENCE hypotheses, never symbol facts.
 for i in indices:
  if targets[i]['B']['identity']:known['A'][targets[i]['A']['address']]=targets[i]['B']['identity']
 cache={}
 for i,arms in targets.items():
  for a,v in arms.items():
   addr=v['address'];key=(a,addr)
   if key not in cache:
    fd=frame[a].get(addr);ends=[x['address']+x['size'] for x in v['aliases'] if x['size']]
    end=fd['end'] if fd else max(ends) if ends else None
    out=run(['objdump','-d','--no-show-raw-insn','--start-address='+hex(addr),'--stop-address='+hex(end),es[a].path]) if end else dict(stdout='',rc=1)
    text=out['stdout'];p=R/f'work/{a}-{addr:x}.asm';p.write_text(text)
    cache[key]=dict(end=end,boundary='FDE' if fd else 'symbol' if ends else 'UNKNOWN',fde=fd,path=str(p),code_sha256=hashlib.sha256(es[a].read(addr,end-addr)).hexdigest() if end else None,normalized=normalize(text,addr,end,known[a]) if end else None)
   v.update(cache[key]);v['demangled_aliases']=run(['c++filt',*sorted({x['name'] for x in v['aliases'] if x['name'].startswith('_Z')})])['stdout'].splitlines() if v['identity'] else []
   v['identity_status']='IDENTIFIED' if v['identity'] else 'UNRESOLVED'
 rows=[]
 for i,v in targets.items():
  b=v['B'];c=v['C'];a=v['A'];bn=b['normalized'];an=a['normalized'];cn=c['normalized'];same_ab=bool(an and bn and an['instructions']==bn['instructions']);same_bc=bool(cn and bn and cn['instructions']==bn['instructions'])
  if a['identity']:status='IDENTIFIED'
  elif same_ab and b['identity'] and c['identity']==b['identity'] and same_bc:status='INFERRED';a['identity']=b['identity'];a['identity_status']='INFERRED'
  else:status='UNRESOLVED'
  rows.append(dict(vtable=VT,slot_index=i,abi_byte_offset=i*8,identity_status=status,arms=v,A_B_normalized_code_equal=same_ab,B_C_normalized_code_equal=same_bc,thunk=bool(b['identity'] and b['identity'].startswith(('_ZTh','_ZTv','_ZTc'))),destructor_variant=variant(b['identity'] or ''),consumer_usage='UNKNOWN',basis='B/C exact full ELF symbol + FDE; A normalized bounded instructions and positional table hypothesis only',uncertainty='RIP data addresses and unnamed external call identities may be masked; not semantic or runtime proof'))
 save('shapenode_slots.json',dict(vtable=VT,total_table_entries=275,V2_unknown_indices=indices,reproduced_V2_count=len(rows),counts=dict(collections.Counter(x['identity_status'] for x in rows)),slots=rows,limits='Array index is absolute table word, NOT virtual function ordinal; AP/subtable classification in separate report; installed A identity inferred only where normalized instructions agree'))
 print('identity',dict(collections.Counter(x['identity_status'] for x in rows)),'unique addresses',len({r['arms']['A']['address'] for r in rows}),'BC code mismatches',sum(not r['B_C_normalized_code_equal'] for r in rows))
