from common import *
from elf_tables import Elf
import re
results=[];symbols=[]
consumers={k:libs()[k] for k in ['Gazebo','Bullet']}
for arm,tag in [('A',None),('B','baseline'),('C','trace')]:
 env={k:v for k,v in os.environ.items() if not k.startswith('LD_')};search=[]
 if tag:
  b=V/f'work/build-{tag}-final';dep=V/'work/dependencies/usr';search=[b/'lib',b/'dart/external/odelcpsolver',dep/'lib/x86_64-linux-gnu',dep/'lib'];env['LD_LIBRARY_PATH']=':'.join(map(str,search))
 for name,p in consumers.items():
  o=run(['/usr/bin/ldd','-r',p],env=env);o.update(arm=arm,consumer=name,search_path=list(map(str,search)))
  o['issues']=re.findall(r'.*(?:undefined symbol|not found).*',o['stdout']+o['stderr']);o['resolved']={n:str(Path(q).resolve()) for n,q in re.findall(r'^\s*(\S+) => (/\S+)',o['stdout'],re.M)};o['dart_closure']={n:q for n,q in o['resolved'].items() if n.startswith('libdart')};results.append(o)
  exports={n:v for q in o['dart_closure'].values() for n,v in Elf(q).syms.items() if v['section']!='UND'}
  imports={n:v for n,v in Elf(p).syms.items() if v['section']=='UND' and '4dart' in n}
  symbols.append(dict(arm=arm,consumer=name,count=len(imports),missing=[n for n in imports if n not in exports],metadata_differences={n:{k:[imports[n][k],exports[n][k]] for k in ['type','visibility','version'] if imports[n][k]!=exports[n][k]} for n in imports if n in exports and any(imports[n][k]!=exports[n][k] for k in ['type','visibility','version'])}))
 if tag:
  for part in ['optimizer-ipopt','optimizer-nlopt','collision-ode']:
   o=run(['/usr/bin/ldd','-r',b/f'lib/libdart-{part}.so.6.13.2'],env=env);o.update(arm=arm,consumer=part,issues=re.findall(r'.*(?:undefined symbol|not found).*',o['stdout']+o['stderr']));results.append(o)
save('loader_results.json',dict(checks=results,consumer_symbols=symbols,mode='Trusted glibc ldd trace/relocation, no init array/dlopen/plugin entry; system IFUNC resolution may execute resolver code, no physics API called',status='PASS' if all(o['rc']==0 and not o['issues'] for o in results) and all(not o['missing'] for o in symbols) else 'FAIL'))
print('loader checks',len(results),'issues',sum(bool(o['issues']) for o in results),'symbols',[(x['arm'],x['consumer'],x['count'],len(x['missing'])) for x in symbols])
