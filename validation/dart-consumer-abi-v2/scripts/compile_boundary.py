from common import *
import re
TYPES=['dart::collision::'+x for x in ['CollisionObject','CollisionGroup','CollisionDetector','CollisionResult','Contact','BulletCollisionObject','BulletCollisionGroup','BulletCollisionDetector']]+['dart::dynamics::ShapeFrame','dart::dynamics::ShapeNode']
results={}
for arm,tag in [('A',None),('B','baseline'),('C','trace')]:
 out=R/'work'/arm;out.mkdir(exist_ok=True)
 dep=V/'work/dependencies/usr/include'
 includes=[dep,V/'work/baseline-source'] if not tag else [V/f'work/build-{tag}-final',V/f'work/{tag}-source',dep]
 flags=['-std=c++17','-O2','-g','-fPIC','-I/usr/include/eigen3','-I/usr/include/bullet']+['-I'+str(x) for x in includes]
 gcc=run(['g++',*flags,'-fdump-lang-class','-c',R/'tests/boundary.cpp','-o',out/'boundary.o']);(out/'compile.json').write_text(json.dumps(gcc,indent=2))
 row={'compile':gcc,'header_origin':'extracted matching distribution core headers + baseline source Bullet fallback' if not tag else 'existing isolated source/generated config','object_execution':'NOT_RUN; no executable generated'}
 if gcc['rc']==0:
  dumps=list(out.glob('*.class'));dump=dumps[0].read_text();(out/'boundary.disassembly').write_text(run(['objdump','-drC','--no-show-raw-insn',out/'boundary.o'])['stdout'])
  classes={};vtables={}
  for t in TYPES:
   m=re.search(r'^Class '+re.escape(t)+r'\n(.*?)(?=\n\n)',dump,re.M|re.S);classes[t]=m.group(1) if m else None
   m=re.search(r'^Vtable for '+re.escape(t)+r'\n(.*?)(?=\n\n)',dump,re.M|re.S);vtables[t]=m.group(1) if m else None
  # Eliminate compiler heap identities, preserve offsets/base/vptr details.
  row['classes']={t:re.sub(r'(?:0x)+[0-9a-f]+','<compiler-id>',v) if v else None for t,v in classes.items()};row['header_vtables']=vtables
  row['undefined']=run(['nm','-uC',out/'boundary.o'])['stdout']
 clang=run(['clang++',*flags,'-Xclang','-fdump-record-layouts','-fsyntax-only',R/'tests/boundary.cpp']);(out/'clang_layout.log').write_text(clang['stdout']+clang['stderr']);row['clang_layout_rc']=clang['rc']
 blocks=clang['stdout'].split('*** Dumping AST Record Layout');row['member_layouts']={t:next((b.strip() for b in blocks if re.search(r'^\s*0 \| (?:class|struct) '+re.escape(t)+r'\s*$',b,re.M)),None) for t in TYPES}
 macros=run(['g++',*flags,'-dM','-E',R/'tests/boundary.cpp']);row['macros']={k:v for k,v in re.findall(r'^#define (\S+) ?(.*)$',macros['stdout'],re.M) if re.search(r'__GXX_ABI|__GXX_RTTI|__EXCEPTIONS|__cplusplus|_GLIBCXX_(?:USE_CXX11_ABI|DEBUG)|EIGEN_(?:MAX.*ALIGN|.*VECTORIZE|.*VERSION)|BT_USE|BT_BULLET_VERSION|HAVE_(?:BULLET|ODE|IPOPT|NLOPT)|DART_VERSION|FMT_VERSION|SPDLOG_VER',k)}
 results[arm]=row
save('boundary_fixture.json',results);print({a:(v['compile']['rc'],v['clang_layout_rc']) for a,v in results.items()})
