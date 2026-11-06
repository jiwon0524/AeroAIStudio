from common import *
from elf_reader import *
from eh_reader import eh_records
from cleanup import cleanup_for
import re,collections
VT='_ZTVN4dart8dynamics9ShapeNodeE'

def instructions(text):return [(int(m[1],16),m[2]) for l in text.splitlines() if (m:=re.match(r'^\s*([0-9a-f]+):\s+(.*)$',l))]
def capture(e,start,end):
 text=run(['objdump','-d','--no-show-raw-insn','--start-address='+hex(start),'--stop-address='+hex(end),e.path])['stdout'];p=R/f'work/{e.path.name}-{start:x}.asm';p.write_text(text);return text,str(p)
def canonical(text,start,end):
 out=[];calls=[]
 for pc,asm in instructions(text):
  asm=asm.split('#')[0].strip();asm=re.sub(r'\s+',' ',asm);asm=re.sub(r'-?0x[0-9a-f]+\(%rip\)','<RIP>(%rip)',asm)
  m=re.match(r'((?:call|j\w+)\s+)([0-9a-f]+)(?:\s+<([^>]+)>)?',asm)
  if m:
   target=int(m[2],16);internal=start<=target<end;label='SELF+'+hex(target-start) if internal else m[3] if m[3] and '@plt' in m[3] else 'LOCAL_OR_DIRECT_CALLEE'
   if not internal:calls.append(dict(pc=hex(pc),target=hex(target),kind=m[1].strip(),label=m[3]))
   asm=m[1]+label
  out.append(asm)
 return out,calls

def metadata(e):
 notes=run(['readelf','-nW',e.path])['stdout'];return dict(path=str(e.path),sha256=sha(e.path),build_id=(re.findall(r'Build ID: (\w+)',notes)or[None])[0])
if __name__=='__main__':
 es={a:Elf(p) for a,p in libs().items() if a in ['A','B','C','Bullet']};all_fde={a:eh_records(e)[1] for a,e in es.items()};fdes={a:{f['start']:f for f in fs} for a,fs in all_fde.items()};records={};s18={};edges=[]
 for a in ['A','B','C']:
  e=es[a];t=e.table(VT);s18[a]={}
  for i,role in [(18,'ShapeNode_D1_candidate'),(19,'ShapeNode_D0_candidate'),(70,'Node_subobject_adjusted_ShapeNode_D0')]:
   start=t[i]['address'];f=fdes[a][start];text,path=capture(e,start,f['end']);norm,cs=canonical(text,start,f['end']);aliases=e.aliases(start)
   row=dict(role=role,slot_index=i,table_byte_offset=i*8,primary_AP=144 if i in [18,19] else 552,entry=e.pointer(e.sym(VT)['address']+i*8),address=hex(start),end=hex(f['end']),function_bytes=f['end']-start,symbol_aliases=aliases,normal_form=norm,call_edges=cs,disassembly_path=path,cleanup=cleanup_for(e,f),calling_convention='x86_64 SysV: this in RDI; local hidden VTT RSI for applicable base dtors; inferred from instructions/compiled ABI',identity_status='IDENTIFIED' if aliases else 'INFERRED' if i in [19,70] else 'UNRESOLVED')
   records[a+'_'+str(i)]=row
   if i==18:s18[a]=row
   for call in cs:
    names=[x['name'] for x in e.aliases(int(call['target'],16))];edges.append(dict(arm=a,from_role=role,**call,target_symbol_aliases=names))
  # Inventory Node/ShapeNode D2 variants, including absence/merging.
  s18[a]['other_variants']=[v for v in e.symbols if v['section'] and re.search(r'(?:9ShapeNode|4Node)D[012]E',v['name']) and not v['name'].startswith('.L')]
 compare={a:dict(normalized_body_equal=s18['A']['normal_form']==s18[a]['normal_form'],same_length=s18['A']['function_bytes']==s18[a]['function_bytes'],limits='Callee addresses and RIP data are normalized; not semantic equality') for a in ['B','C']}
 # Separate alias naming from ABI-pattern inference. Support with table role, D0 edge,
 # complete-object vptr resetting, and matching known base cleanup order.
 for a in ['A','B','C']:
  d0=records[a+'_19'];node0=records[a+'_70'];d1addr=s18[a]['address'];s18[a]['D0_directly_calls_entry']=any(c['target']==d1addr and c['kind']=='call' for c in d0['call_edges']);s18[a]['Node_adjusted_D0_directly_calls_entry']=any(c['target']==d1addr and c['kind']=='call' for c in node0['call_edges'])
 if all(x['normalized_body_equal'] for x in compare.values()) and s18['A']['D0_directly_calls_entry'] and s18['A']['Node_adjusted_D0_directly_calls_entry']:s18['A']['identity_status']='INFERRED'
 # Capture the two unexported direct helpers once, without unbounded recursion.
 helpers={}
 for a in ['A','B','C']:
  e=es[a];helpers[a]=[]
  for c in s18[a]['call_edges']:
   target=int(c['target'],16)
   if not c['label'] or '@plt' in c['label']:continue
   if e.aliases(target) and any(x['table']=='dynamic' for x in e.aliases(target)):continue
   f=fdes[a].get(target)
   if not f:continue
   text,path=capture(e,target,f['end']);norm,cs=canonical(text,target,f['end']);helpers[a].append(dict(address=hex(target),symbol_aliases=e.aliases(target),path=path,normal_form=norm,calls=cs,limits='Single helper boundary only; nested dynamic/virtual/cold cleanup remains unknown'))
 save('slot18_analysis.json',dict(binaries={a:metadata(e) for a,e in es.items()},arms=s18,comparison=compare,helper_observations=helpers,V3_reason='V3 local-call matcher could not prove CompositeNode base cleanup and RB-tree erase/cold targets recursively; not an observed ABI mismatch',status=s18['A']['identity_status'],ABI='COMPATIBLE_WITH_LIMITATIONS' if s18['A']['identity_status']=='INFERRED' else 'UNKNOWN',stop_condition='C: installed full type/debug and arbitrary nested cleanup semantics unavailable; bounded direct-edge analysis complete',limits='No A symbol name recovered; structural inference does not certify lifetime/exception/runtime neutrality'))
 bullet=es['Bullet'];b_rows=[]
 for n in ['_ZTVN4dart9collision21BulletCollisionObjectE','_ZTVN4dart9collision20BulletCollisionGroupE','_ZTVN4dart9collision23BulletCollisionDetectorE']:
  tab=bullet.table(n)
  for i,var in [(2,'D1'),(3,'D0')]:
   ent=tab[i];start=ent.get('address')
   if start is None:start=bullet.sym(ent['name'])['address']+ent['addend']
   f=fdes['Bullet'][start];text,path=capture(bullet,start,f['end']);norm,cs=canonical(text,start,f['end']);b_rows.append(dict(table=n,variant=var,address=hex(start),disassembly_path=path,call_edges=cs,assembly=text,cleanup=cleanup_for(bullet,f)))
 # factory throw-cleanup LSDA
 fac=next(v for v in bullet.symbols if v['section'] and '23BulletCollisionDetector21createCollisionObjectE' in v['name']);f=fdes['Bullet'][fac['address']];factory=cleanup_for(bullet,f);factory['function']=fac
 save('destructor_call_graph.json',dict(core_records=records,edges=edges,Bullet=b_rows,Node_D0_D1_interpretation='No generic Node D0 -> Node D1 assumption. NodeDestructor wrapper dispatches via dynamic vptr; ShapeNode Node-subobject D0 thunk adjusts this and calls ShapeNode entry18, then sized delete.',limits='Instructions show calls and conditional order, not all dynamic targets or actual object lifetimes'))
 save('exception_cleanup.json',dict(core={k:r['cleanup'] for k,r in records.items()},Bullet_destructors=[dict(table=r['table'],variant=r['variant'],**r['cleanup']) for r in b_rows],Bullet_factory=factory,limits='Decoded static callsites/actions and landing excerpts only; does not prove no double-free/missing cleanup/catch equivalence. No exception runtime test.'))
 print('slot18',s18['A']['identity_status'],compare,'factory sites',len(factory['sites']))
