from common import *
from elf_reader import Elf
import re
checks=[];imports=[]
for arm,tag in [('A',None),('B','baseline'),('C','trace')]:
 env={k:v for k,v in os.environ.items() if not k.startswith('LD_')}
 if tag:
  b=V/f'work/build-{tag}-final';dep=V/'work/dependencies/usr';env['LD_LIBRARY_PATH']=':'.join(map(str,[b/'lib',b/'dart/external/odelcpsolver',dep/'lib/x86_64-linux-gnu',dep/'lib']))
 targets={n:libs()[n] for n in ['Gazebo','Bullet']}
 if tag:targets.update({n:b/f'lib/libdart-{n}.so.6.13.2' for n in ['optimizer-ipopt','optimizer-nlopt','collision-ode']})
 for name,p in targets.items():
  o=run(['/usr/bin/ldd','-r',p],env=env);resolved={n:str(Path(q).resolve()) for n,q in re.findall(r'^\s*(\S+) => (/\S+)',o['stdout'],re.M)};dart={n:q for n,q in resolved.items() if n.startswith('libdart')};o.update(arm=arm,target=name,issues=re.findall(r'.*(?:not found|undefined symbol).*',o['stdout']+o['stderr']),dart_closure=dart);checks.append(o)
  if name in ['Gazebo','Bullet']:
   refs={v['name'] for v in Elf(p).symbols if not v['section'] and '4dart' in v['name']};defs={v['name'] for q in dart.values() for v in Elf(q).symbols if v['section']};imports.append(dict(arm=arm,consumer=name,count=len(refs),missing=sorted(refs-defs)))
save('loader_results.json',dict(checks=checks,imports=imports,status='PASS' if all(x['rc']==0 and not x['issues'] for x in checks) and all(not x['missing'] for x in imports) else 'FAIL',mode='Trusted glibc trace/relocation only; no library init or plugin entry; IFUNC loader resolvers possible; no physics API'))
print('loader',len(checks),'errors',sum(bool(x['issues']) for x in checks))
