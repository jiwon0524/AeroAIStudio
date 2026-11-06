from common import R,OLD,run,save
from pathlib import Path
import json
headers=R/'work/dependencies/usr/include';result={}
for tag in ('original','baseline','trace'):
 if tag=='original':
  inc=[headers,R/'work/trace-source'];core=Path('/usr/lib/x86_64-linux-gnu/libdart.so.6.13.2');ext=Path('/usr/lib/x86_64-linux-gnu/libdart-external-odelcpsolver.so.6.13.2');paths=[core.parent]
 else:
  build=R/f'work/build-{tag}-final';inc=[build,R/f'work/{tag}-source',headers];core=build/'lib/libdart.so.6.13.2';ext=build/'dart/external/odelcpsolver/libdart-external-odelcpsolver.so.6.13.2';paths=[core.parent,ext.parent]
 base=['g++','-std=c++17','-O2','-g','-I/usr/include/eigen3']+['-I'+str(p) for p in inc]
 for case,src in [('boxed','boxed_fixture.cpp'),('failure','dantzig_failure_fixture.cpp'),('metadata','metadata_call_fixture.cpp')]:
  cmd=base+(['-DTRACE_HARNESS'] if tag=='trace' else [])+[str(R/'tests'/src)]+([str(core)] if case in ('boxed','metadata') else [])+[str(ext),'-Wl,-rpath,'+':'.join(map(str,paths)),'-o',str(R/f'work/{tag}_{case}')]
  p=run(cmd);result[f'{tag}_{case}']=p
  if p['rc']:save('fixture_compile.json',result);raise RuntimeError(p['stderr'])
 if tag=='trace':
  for name,src in [('private_fields_fixture','private_fields_fixture.cpp'),('world_config_fixture','world_config_fixture.cpp')]:
   cmd=base+[str(R/'tests'/src),str(core),str(ext),'-Wl,-rpath,'+':'.join(map(str,paths)),'-o',str(R/'work'/name)]
   p=run(cmd);result[name]=p
   if p['rc']:save('fixture_compile.json',result);raise RuntimeError(p['stderr'])
save('fixture_compile.json',result);print('compiled',len(result),'fixtures')
