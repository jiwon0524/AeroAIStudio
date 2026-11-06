from common import *
from elf_reader import *
import re,struct
TYPES=['ShapeNode','ShapeFrame','Node','NodeDestructor','CollisionObject','BulletCollisionObject','CollisionGroup','BulletCollisionGroup','CollisionDetector','BulletCollisionDetector','CollisionResult','Contact']
results={};fixtures={}
for arm,p in libs().items():
 e=Elf(p);syms=[v for v in e.symbols if v['section'] and any(re.search(str(len(t))+t+r'[CD][0123]E',v['name']) for t in TYPES)];rows=[];seen=set()
 for v in syms:
  key=(v['name'],v['address'])
  if key in seen:continue
  seen.add(key);rows.append(dict(**v,variant=variant(v['name']),demangled=run(['c++filt',v['name']])['stdout'].strip()))
 selected={}
 # Inspect actual allocator/deleter dispatch and compiler-internal destructor bodies.
 for v in e.symbols:
  if not v['section'] or v['type']!=2 or not v['size']:continue
  n=v['name']
  if not (re.search(r'14NodeDestructorD[12]E',n) or ('CollisionObjectDeleter' in n and 'clE' in n) or (arm=='Bullet' and 'createCollisionObjectE' in n)):continue
  if v['address'] in selected:continue
  text=run(['objdump','-d','-C','--no-show-raw-insn','--start-address='+hex(v['address']),'--stop-address='+hex(v['address']+v['size']),p])['stdout'];selected[v['address']]=dict(symbol=n,disassembly=text)
 # Include installed Bullet local destructor vtable entries despite missing names.
 local=[]
 if arm=='Bullet':
  for n in ['_ZTVN4dart9collision21BulletCollisionObjectE','_ZTVN4dart9collision20BulletCollisionGroupE','_ZTVN4dart9collision23BulletCollisionDetectorE']:
   t=e.table(n)
   for i,var in [(2,'D1'),(3,'D0')]:
    ent=t[i];addr=ent.get('address');s=e.sym(ent['name']) if ent['kind']=='symbol' else None
    if addr is None and s:addr=s['address']+ent['addend']
    f=frames(p)[0].get(addr);end=f['end'] if f else None
    out=run(['objdump','-d','-C','--no-show-raw-insn','--start-address='+hex(addr),'--stop-address='+hex(end),p])['stdout'] if end else ''
    local.append(dict(table=n,slot=i,variant_hypothesis=var,status='IDENTIFIED' if e.aliases(addr) else 'INFERRED',address=hex(addr),boundary='FDE' if f else 'UNKNOWN',disassembly=out,basis='Itanium primary vtable destructor pair + code; local stripped name not recovered'))
 results[arm]=dict(symbols=rows,selected_calls=list(selected.values()),Bullet_destructor_pairs=local)
for arm,tag in [('A',None),('B','baseline'),('C','trace')]:
 out=R/'work'/arm;out.mkdir(exist_ok=True);dep=V/'work/dependencies/usr/include';inc=[dep,V/'work/baseline-source'] if tag is None else [V/f'work/build-{tag}-final',V/f'work/{tag}-source',dep]
 cmd=['g++','-std=c++17','-O2','-g','-fPIC','-I/usr/include/eigen3','-I/usr/include/bullet']+['-I'+str(x) for x in inc]+['-c',R/'tests/lifetime.cpp','-o',out/'lifetime.o'];p=run(cmd);dis=run(['objdump','-drC','--no-show-raw-insn',out/'lifetime.o'])['stdout'] if p['rc']==0 else ''
 fixtures[arm]=dict(compile=p,disassembly=dis,execution='NOT_RUN')
 if p['rc']==0:fixtures[arm]['sizes']=list(struct.unpack('<QQQ',Elf(out/'lifetime.o').read_symbol('lifetime_sizes')))
save('destructor_contract.json',dict(libraries=results,compile_only=fixtures,variant_meaning={'C1':'complete object constructor','C2':'base object constructor','C3':'allocating constructor variant, if emitted','D0':'deleting destructor','D1':'complete object destructor','D2':'base object destructor'},limits=['Absent constructor/destructor symbol may be inline/optimized/abstract variant, not proof of missing runtime function','ELF calls and declarations do not prove actual lifetime ordering or allocator safety; no object created/deleted']))
base=V/'work/baseline-source';refs={}
for rel in ['dart/dynamics/Node.cpp','dart/dynamics/BodyNode.cpp','dart/dynamics/ShapeNode.hpp','dart/dynamics/ShapeFrame.cpp','dart/collision/CollisionDetector.cpp','dart/collision/bullet/BulletCollisionDetector.cpp','dart/collision/bullet/BulletCollisionObject.cpp']:
 p=base/rel;refs[rel]=dict(path=str(p),sha256=sha(p),lines=[dict(line=i,text=l.strip()) for i,l in enumerate(p.read_text().splitlines(),1) if re.search(r'delete |uniqueObject.release|~ShapeNode|~ShapeFrame|mNodeDestructors.clear|mCollisionObjectManager.reset|new BulletCollisionObject|notifyCollisionObjectDestroying',l)])
save('ownership_boundary.json',dict(source_refs=refs,edges=[dict(from_module='Bullet',operation='new BulletCollisionObject -> unique_ptr<CollisionObject>',to_module='core manager'),dict(from_module='core manager',operation='release unique -> shared with manager custom deleter',to_module='shared control block'),dict(from_module='core deleter',operation='virtual notify then delete CollisionObject* -> D0',to_module='Bullet derived destructor/operator delete'),dict(from_module='BodyNode core',operation='mNodeDestructors.clear -> NodeDestructor -> delete Node* -> ShapeNode adjusted D0 if dynamic ShapeNode',to_module='core ShapeNode')],required_lifetimes=['Detector/manager must outlive deleter callbacks','Bullet shared shape deleter requires detector map owner','BodyNode detach/destructor control blocks must avoid dangling/double deletion'],static_globals='Installed Bullet registrar; trace State/thread_local Context/once_flag are separate; shutdown ordering UNKNOWN',runtime='NOT_RUNTIME_VERIFIED',limits='Source paths are declared ownership design; binary call evidence in destructor_contract.json. No actual allocation/delete/copy/move/unwind performed'))
print('lifetime compiles',{a:v['compile']['rc'] for a,v in fixtures.items()})
