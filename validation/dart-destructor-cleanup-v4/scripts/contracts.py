from common import *
from elf_reader import Elf
import re,struct
results={}
for a,tag in [('A',None),('B','baseline'),('C','trace')]:
 out=R/'work'/a;out.mkdir(exist_ok=True);dep=V/'work/dependencies/usr/include';inc=[dep,V/'work/baseline-source'] if tag is None else [V/f'work/build-{tag}-final',V/f'work/{tag}-source',dep];cmd=['g++','-std=c++17','-O2','-fPIC','-I/usr/include/eigen3','-I/usr/include/bullet']+['-I'+str(p) for p in inc]+['-c',R/'tests/deletion_compile.cpp','-o',out/'deletion.o'];p=run(cmd);row=dict(compile=p,execution='NOT_RUN',origin='extracted packaged core headers + matching source Bullet fallback' if tag is None else 'existing isolated source/generated config')
 if p['rc']==0:row.update(sizes=list(struct.unpack('<QQQQ',Elf(out/'deletion.o').read_symbol('sizes'))),assembly=run(['objdump','-drC','--no-show-raw-insn',out/'deletion.o'])['stdout'])
 results[a]=row
core=json.loads((R/'reports/destructor_call_graph.json').read_text());sized={}
for a in ['A','B','C']:
 sized[a]={}
 for slot in [19,70]:
  text=Path(core['core_records'][a+'_'+str(slot)]['disassembly_path']).read_text();m=re.findall(r'mov\s+\$0x([0-9a-f]+),%esi',text);sized[a][slot]=dict(delete_sizes=[int(n,16) for n in m],assembly_path=core['core_records'][a+'_'+str(slot)]['disassembly_path'],has_sized_delete='_ZdlPvm@plt' in text)
bullet=[]
for row in core['Bullet']:
 if row['variant']!='D0':continue
 m=re.findall(r'mov\s+\$0x([0-9a-f]+),%esi',row['assembly']);bullet.append(dict(table=row['table'],address=row['address'],sized_delete_args=[int(n,16) for n in m],has_sized_delete='_ZdlPvm@plt' in row['assembly'],assembly_path=row['disassembly_path']))
versions={a:[l.strip() for l in run(['readelf','--dyn-syms','--wide',p])['stdout'].splitlines() if re.search(r'\b(?:_Znwm|_ZdlPvm|_ZdlPv)@',l)] for a,p in libs().items() if a in ['A','B','C','Bullet']}
source=V/'work/baseline-source/dart/collision/CollisionDetector.cpp';lines=source.read_text().splitlines();refs=[dict(line=i,text=l.strip()) for i,l in enumerate(lines,1) if re.search('uniqueObject.release|notifyCollisionObjectDestroying|delete object',l)]
save('ownership_contract.json',dict(compile_only=results,ShapeNode_sized_delete=sized,Bullet_sized_delete=bullet,allocator_symbol_versions=versions,source=dict(path=str(source),sha256=sha(source),lines=refs),cross_module='Bullet allocation -> core manager shared/custom deleter -> virtual derived D0 in Bullet -> sized operator delete via C++ runtime; detector/manager lifetime must outlive callback',limits='Current header sizeof matches selected deallocation arguments; no complete installed layout, allocator interposition, double-free, shutdown or exception safety proof. No object created/deleted.'))
save('analysis_stop.json',dict(items=[dict(item='Slot18',stop='C',reason='D1 INFERRED from AP, complete vptr reset and D0 calls/normalized997byte body; installed symbol/type and nested semantic proof unavailable'),dict(item='Node-subobject D0 to ShapeNode D1',stop='A',reason='Direct actual instruction edges and this -144 adjustment verified; not generic Node D0->Node D1'),dict(item='Sized delete',stop='A',reason='Selected size1664/48/368 and standard versioned delete contract verified offline; full lifetime excluded'),dict(item='Exception/lifetime neutrality',stop='C',reason='LSDA callsites/cleanup edges only; nested/indirect shutdown/catch behavior requires matching debug/build or separately approved targeted nonphysics probe')],next_evidence='Obtain matching debug/symbol map OR prepare a separate bounded nonphysics object-lifetime/allocator/unwind probe with explicit approval; no automatic further static phase',runtime='NOT_RUNTIME_VERIFIED'))
print('compile sizes',{a:x.get('sizes') for a,x in results.items()},'Bullet',bullet)
