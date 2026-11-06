from common import *
from elf_reader import *
import re,collections
VT='_ZTVN4dart8dynamics9ShapeNodeE'
if __name__=='__main__':
 d=json.loads((R/'reports/shapenode_slots.json').read_text());header=json.loads((V2/'reports/boundary_fixture.json').read_text())['A'];cls=header['classes']['dart::dynamics::ShapeNode'];aps=sorted({int(n) for n in re.findall(re.escape(VT)+r'\) \+ (\d+)',cls)})
 es={a:Elf(p) for a,p in libs().items()};es.update({'external_A':Elf('/usr/lib/x86_64-linux-gnu/libdart-external-odelcpsolver.so.6.13.2'),'external_C':Elf(V/'work/build-trace-final/dart/external/odelcpsolver/libdart-external-odelcpsolver.so.6.13.2')});tab=es['A'].table(VT);ap_rows=[]
 for ap in aps:
  top=tab[ap//8-2]['address'];top=top if top<1<<63 else top-(1<<64)
  ap_rows.append(dict(address_point_byte_offset=ap,offset_to_top=top,rtti=tab[ap//8-1],evidence='Fresh installed table words; AP location from preserved compiler hierarchy, not installed debug'))
 for row in d['slots']:
  ap=max(n for n in aps if n<=row['abi_byte_offset']);row['address_point_byte_offset']=ap;row['offset_from_address_point']=row['abi_byte_offset']-ap;row['entry_kind']='function_pointer';row['header_slot_declaration']=next((l.strip() for l in header['header_vtables']['dart::dynamics::ShapeNode'].splitlines() if re.match(str(row['abi_byte_offset'])+r'\s',l)),None)
  row['consumer_usage']='INDIRECTLY_REACHABLE' if row['slot_index']==70 else 'UNKNOWN' if row['destructor_variant'] else 'NOT_OBSERVED'
  row['usage_basis']='Core NodeDestructor virtual delete through Node subobject (compiler Node AP552 +8 => slot70); requires actual dynamic ShapeNode, runtime unobserved' if row['slot_index']==70 else 'No proven per-slot call in bounded consumer scan; NOT_OBSERVED does not mean unreachable'
 # Actual selected virtual-call site from V2, freshly disassembled at its ELF address.
 calls=[]
 for a,start,end in [('Gazebo',0x235450,0x235630)]:
  text=run(['objdump','-d','-C','--no-show-raw-insn','--start-address='+hex(start),'--stop-address='+hex(end),libs()[a]])['stdout'];(R/'work/gazebo-contact-dispatch.asm').write_text(text)
  sites=[l.strip() for l in text.splitlines() if re.search(r'call\s+\*0x28\(%rax\)',l)]
  assert sites;calls.append(dict(consumer=a,sites=sites,static_receiver='ShapeFrame* returned by CollisionObject::getShapeFrame',ShapeNode_header_subobject_offset=272,address_point_byte_offset=816,dispatch_byte_offset=40,absolute_table_index=107,target=tab[107],in_V2_67=False,status='INDIRECTLY_REACHABLE',limits='Receiver dynamic type not proven at runtime; header-to-object mapping partial'))
 refs={a:[v for v in e.symbols if not v['section'] and ('9ShapeNode' in v['name'] or '10ShapeFrame' in v['name'])] for a,e in es.items() if a in ['Bullet','Gazebo','external_A','external_C']}
 core=Elf(libs()['A']);sel=[]
 for v in core.symbols:
  if v['section'] and re.search(r'14NodeDestructorD[12]E',v['name']):
   text=run(['objdump','-d','-C','--no-show-raw-insn','--start-address='+hex(v['address']),'--stop-address='+hex(v['address']+v['size']),core.path])['stdout'];sel.append(dict(symbol=v['name'],address=hex(v['address']),disassembly=text,slot_hypothesis=70))
 save('consumer_virtual_calls.json',dict(address_points=ap_rows,selected_sites=calls,core_NodeDestructor=sel,ShapeNode_ShapeFrame_imports=refs,slot_usage_counts=dict(collections.Counter(r['consumer_usage'] for r in d['slots'])),limits='Bounded real callsites + source/hierarchy; no complete whole-program callgraph, no dynamic execution. External LCP has no observed ShapeNode-specific refs; cannot prove general unreachability.'))
 def normalized(e,n):
  t=e.table(n);out=[]
  for x in t:
   if x['kind']=='symbol':out.append([x['name'],x['addend']])
   else:
    names=sorted({v['name'] for v in e.byaddr.get(x['address'],[]) if v['name'].startswith('_ZTI') or v['name'].startswith('_ZTS')})
    out.append(names[0] if names else x['address'])
  return out
 rtti={a:{n:normalized(e,n) for n in ['_ZTIN4dart8dynamics9ShapeNodeE','_ZTIN4dart8dynamics10ShapeFrameE']} for a,e in es.items() if a in ['A','B','C']}
 thunks=[dict(slot_index=r['slot_index'],candidate=r['arms']['B']['identity'],status=r['identity_status'],A_address=hex(r['arms']['A']['address']),path=r['arms']['A']['path'],kind='covariant' if r['arms']['B']['identity'].startswith('_ZTc') else 'virtual' if r['arms']['B']['identity'].startswith('_ZTv') else 'nonvirtual',demangled=r['arms']['B']['demangled_aliases'],evidence='B/C local symbol + actual bounded A thunk instructions; A names inferred only') for r in d['slots'] if r['thunk']]
 save('rtti_thunks.json',dict(rtti=rtti,thunks=thunks,counts=dict(collections.Counter(x['kind'] for x in thunks)),type_name={a:{n:e.read_symbol(n).rstrip(b'\0').decode() for n in ['_ZTSN4dart8dynamics9ShapeNodeE','_ZTSN4dart8dynamics10ShapeFrameE']} for a,e in es.items() if a in ['A','B','C']},runtime_cast='NOT_RUN',covariant_scope='No _ZTc target observed among selected67; not a proof none exists elsewhere',limits='RTTI identity/descriptors alone do not certify all dynamic-cast/EH paths or installed full member layout'))
 d['address_points']=ap_rows;save('shapenode_slots.json',d);print('AP',len(aps),'usage',dict(collections.Counter(r['consumer_usage'] for r in d['slots'])))
