from common import *
from elf_tables import Elf
import re,struct,difflib
f=json.loads((R/'reports/boundary_fixture.json').read_text());results={}
for a in ['A','B','C']:
 e=Elf(R/f'work/{a}/boundary.o',dynamic=False);values={}
 for n in ['boundary_sizes','contact_offsets','compiler_values']:
  v=e.syms[n];values[n]=list(struct.unpack('<'+'Q'*(v['size']//8),e.data[e.sections[int(v['section'])][4]+v['address']:e.sections[int(v['section'])][4]+v['address']+v['size']]))
 results[a]=values
base=V/'work/baseline-source';trace=V/'work/trace-source';dep=V/'work/dependencies/usr/include'
headers={}
for directory in ['collision','dynamics','common']:
 for p in (base/'dart'/directory).rglob('*.hpp'):
  rel=p.relative_to(base);installed=dep/rel
  headers[str(rel)]=dict(baseline=sha(p),trace=sha(trace/rel),packaged_header=sha(installed) if installed.exists() else None,packaged_matches=sha(p)==sha(installed) if installed.exists() else None)
source_refs={}
for rel in ['dart/collision/CollisionDetector.cpp','dart/collision/CollisionObject.cpp','dart/collision/CollisionGroup.cpp','dart/collision/CollisionResult.cpp','dart/collision/bullet/BulletCollisionDetector.cpp','dart/collision/bullet/BulletCollisionGroup.cpp','dart/collision/bullet/BulletCollisionObject.cpp','dart/dynamics/ShapeFrame.hpp','dart/dynamics/detail/ShapeNode.hpp']:
 p=base/rel;source_refs[rel]=dict(path=str(p),sha256=sha(p),key_lines=[dict(line=i,text=l.strip()) for i,l in enumerate(p.read_text().splitlines(),1) if re.search(r'new Bullet|delete object|uniqueObject.release|notifyCollisionObjectDestroying|mShapeFrame|mBulletCollisionObject|public virtual|ShapeNodeCompositeBase',l)])
core_bodies={}
for a,p in libs().items():
 if a not in ['A','B','C']:continue
 e=Elf(p);core_bodies[a]={}
 for n,v in e.syms.items():
  if v['section']!='UND' and any(k in n for k in ['CollisionObject13getShapeFrame','CollisionObject20getCollisionDetector']):core_bodies[a][n]={'code_sha256':hashlib.sha256(e.read(v['address'],v['size'])).hexdigest(),'address':hex(v['address']),'size':v['size']}
contract=dict(compile_only_constants=results,header_comparison=headers,source_references=source_refs,installed_simple_getters=core_bodies,ownership='Bullet factory returns unique_ptr<CollisionObject>; core wraps release() with shared_ptr custom deleter; deleter notifies virtual detector then delete object (virtual destructor). Detector/manager lifetime must outlive managed objects. Compile/source proof only; no actual lifetime/unwind test.',observations=[{'field':'CollisionObject::mCollisionDetector','offset':8,'evidence':'Installed/isolated getter mov 0x8(%rdi),%rax; compiler record layout','level':'BINARY_SELECTED_OFFSET'},{'field':'CollisionObject::mShapeFrame','offset':16,'evidence':'Installed/isolated getter mov 0x10(%rdi),%rax; Bullet updateEngineData consumes corresponding field','level':'BINARY_SELECTED_OFFSET'},{'field':'BulletCollisionObject::mBulletCollisionObject','offset':40,'evidence':'Installed Bullet getter mov 0x28(%rdi),%rax; header record layout','level':'BINARY_SELECTED_OFFSET'},{'field':'ShapeNode->ShapeFrame','offset':272,'evidence':'Fresh compile emits lea 0x110(%rdi); compiler layout only, installed binary complete base layout unproven','level':'COMPILE_ONLY'}],not_proven=['Complete installed object member/base layout','All allocations/deallocations and exception unwinding across modules','Every optimized consumer inline access','All ShapeNode local virtual targets'],installed_headers='DART dev package NOT_INSTALLED; extracted matching distribution core headers; Bullet declarations fallback to matching source, not installed type evidence')
save('bullet_core_contract.json',contract)
profiles={}
for tag in ['baseline','trace']:
 b=V/f'work/build-{tag}-final';profiles[tag]={n:(b/n).read_text() for n in ['dart/CMakeFiles/dart.dir/flags.make','dart/config.hpp']};profiles[tag]['cache_selected']=[l for l in (b/'CMakeCache.txt').read_text().splitlines() if re.match(r'(CMAKE_(?:CXX_COMPILER|BUILD_TYPE|CXX_FLAGS|SHARED_LINKER_FLAGS)|HAVE_(?:BULLET|IPOPT|NLOPT|ODE)|BULLET|EIGEN)',l)]
elfs={a:{k:run(args)['stdout'] for k,args in [('comment',['readelf','-p','.comment',p]),('sections',['readelf','-SW',p]),('dynamic',['readelf','-dW',p]),('versions',['readelf','-VW',p])]} for a,p in libs().items()}
save('compiler_abi.json',dict(current_compiler=run(['g++','--version']),secondary_compiler=run(['clang++','--version']),packages=run(['dpkg-query','-W','-f=${Package} ${Status} ${Version}\n','libdart6.13-dev','libbullet-dev','libeigen3-dev','libfmt-dev','libspdlog-dev']),profiles=profiles,fixture_macros={a:v['macros'] for a,v in f.items()},fixture_numeric_values={a:v['compiler_values'] for a,v in results.items()},ELF=elfs,installed_buildinfo='UNKNOWN: .comment producer strings are evidence of producers, not complete per-TU flags/compiler identity',limits='No inference of installed Eigen/RTTI/EH/alignment macro settings from current fixture alone; RTTI and unwind sections/symbols confirm only observed facilities'))
# Instrumentation object ABI: all existing declaration headers, not just targeted headers.
allheaders=[p for p in (base/'dart').rglob('*.hpp')];changed=[str(p.relative_to(base)) for p in allheaders if sha(p)!=sha(trace/p.relative_to(base))]
rec=trace/'dart/external/odelcpsolver/internal_trace.cpp';code=rec.read_text();delta={}
for rel in ['dart/simulation/World.cpp','dart/constraint/BoxedLcpConstraintSolver.cpp']:
 a=(base/rel).read_text();b=(trace/rel).read_text();delta[rel]=''.join(difflib.unified_diff(a.splitlines(True),b.splitlines(True)))
save('instrumentation_abi.json',dict(existing_hpp_checked=len(allheaders),changed_existing_hpp=changed,new_private_header=str(trace/'dart/external/odelcpsolver/internal_trace.h'),global_state=[l for l in code.splitlines() if re.search(r'^State st|^thread_local|^std::once_flag',l)],constructor_destructor_delta=delta,OFF='additional diagnostic entry, getDimension argument, ctor once/env and scope TLS/exception state; not original identical execution',ON='additional virtual metadata; global State owner/quiescent requirement, serialization allocation; runtime lifetime/lock/FP effects UNKNOWN',core_public_layout='No existing declaration/member/base/virtual changes; compiler fixture B/C matches',runtime='NOT_RUNTIME_VERIFIED'))
print('constants',results['A'],'header differences',len(changed))
