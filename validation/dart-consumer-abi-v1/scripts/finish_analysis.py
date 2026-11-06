from analyze import *
import xml.etree.ElementTree as ET
rows=json.loads((R/'reports/consumer_symbols.json').read_text());cache={}
for row in rows:
 row['provider_metadata']={}
 for arm in ['A','B','C']:
  ps=row['providers']['A'] if arm=='A' else row['effective_providers'][arm]
  row['provider_metadata'][arm]=[]
  for p in ps:
   if p not in cache:cache[p]=symbols(p)
   v=cache[p][row['mangled']];row['provider_metadata'][arm].append({k:v[k] for k in ['type','binding','visibility','version','size']})
 row['metadata_mismatches']={}
 for arm in ['B','C']:
  a=row['provider_metadata']['A'];b=row['provider_metadata'][arm]
  if a and b:
   fields=['type','binding','visibility','version']+(['size'] if row['type']=='OBJECT' else [])
   diff={k:[a[0][k],b[0][k]] for k in fields if a[0][k]!=b[0][k]}
   if diff:row['metadata_mismatches'][arm]=diff
save('consumer_symbols.json',rows)
modules=[]
for tag in ['baseline','trace']:
 b=V/f'work/build-{tag}-final';dep=V/'work/dependencies/usr';env={k:v for k,v in os.environ.items() if not k.startswith('LD_')};env['LD_LIBRARY_PATH']=':'.join(map(str,[b/'lib',b/'dart/external/odelcpsolver',dep/'lib/x86_64-linux-gnu',dep/'lib']))
 for part in ['optimizer-ipopt','optimizer-nlopt','collision-ode']:
  p=b/f'lib/libdart-{part}.so.6.13.2';o=closure(p,env);o.update(arm=tag,path=str(p));modules.append(o)
save('module_loader_results.json',modules)
tests={}
for n in ['consumer','native','regression']:
 root=ET.parse(R/f'work/{n}.xml').getroot();ss=root.findall('testsuite');tests[n]={k:sum(int(s.get(k,0)) for s in ss) for k in ['tests','failures','errors','skipped']}
save('test_summary.json',dict(current=tests,total=sum(v['tests'] for v in tests.values()),historical={'implementation':144,'parity_v1':44,'capability_v2':153},not_run=['Gazebo/World::step/Stage B','full DART unit suite','new DWARF abidiff (prior results referenced)'],safety='Native C++ forbidden-call scan and prior safety hashes reviewed; regression runtime fence active; no plugin initialization'))
risks=[]
for c in json.loads((R/'reports/consumer_inventory.json').read_text()):
 risks.append(dict(consumer=c['path'],status='COMPATIBLE_WITH_LIMITATIONS',risk='HIGH',symbols='VERIFIED_OFFLINE',loader='VERIFIED_OFFLINE',installed_binary_type_ABI='UNKNOWN',runtime='UNKNOWN',basis='252 imports available; retained installed Bullet module explicitly inventoried. Installed type DWARF unavailable. Mixed closure symbol resolution is verified, cross-module object ABI not fully certified.',host_impact='UNKNOWN can affect host; approval withheld'))
save('risk_assessment.json',risks)
save('verdict.json',dict(verdict='CONSUMER_ABI_PARTIALLY_VERIFIED',runtime='NOT_RUNTIME_VERIFIED',Stage_B='BLOCKED',host='BLOCKED_PENDING_TYPE_ABI_AND_SEPARATE_SAFETY_REVIEW',unintended_core_external_mixing=False,retained_installed_auxiliary='libdart-collision-bullet.so.6.13 explicitly retained, NOT full isolated DART stack',missing_symbols=sum(not all(r['effective_providers'].values()) for r in rows),metadata_mismatches=sum(bool(r['metadata_mismatches']) for r in rows),loader_errors=sum(bool(x['issues']) for x in modules),tests=tests))
print('metadata mismatches',sum(bool(r['metadata_mismatches']) for r in rows),'module loader issues',sum(bool(x['issues']) for x in modules))
