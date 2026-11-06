from common import R,OLD,run,save,sha
from pathlib import Path
headers=R/'work/dependencies/usr/include';results={}
for tag in ('installed','baseline','trace'):
 includes=[headers,R/'work/baseline-source'] if tag=='installed' else [R/f'work/build-{tag}-final',R/f'work/{tag}-source',headers]
 cmd=['g++','-std=c++17','-I/usr/include/eigen3','-I'+str(headers/'coin'),'-DHAVE_CSTDDEF','-DIPOPT_VERSION_MAJOR=3','-DIPOPT_VERSION_MINOR=11','-DIPOPT_VERSION_PATCH=9']+['-I'+str(p) for p in includes]+[str(R/'tests/abi_sizes_align.cpp'),'-o',str(R/f'work/abi-{tag}')]
 compiled=run(cmd);executed=run([str(R/f'work/abi-{tag}')]) if compiled['rc']==0 else None
 results[tag]={'compile':compiled,'execution':executed}
# All existing class declarations are unchanged by instrumentation.
a=R/'work/baseline-source';b=R/'work/trace-source';hdrs={str(p.relative_to(a)):[sha(p),sha(b/p.relative_to(a)) if (b/p.relative_to(a)).is_file() else None] for p in (a/'dart').rglob('*.hpp')}
results['declaration_headers']={'count':len(hdrs),'differences':{p:v for p,v in hdrs.items() if v[0]!=v[1]}}
results['limitations']=['Optional optimizer/ODE headers for installed-header arm come from matching distribution source fallback, not original installed binary type info','sizeof/alignof and same declarations are limited ABI evidence; no installed DWARF class layout was recovered','libabigail is isolated for separate DWARF comparison; installed original DWARF/buildinfo availability is checked separately']
save('abi_layout.json',results)
print({k:v['execution']['stdout'] if v['execution'] else v['compile']['stderr'] for k,v in results.items() if k in ('installed','baseline','trace')})
