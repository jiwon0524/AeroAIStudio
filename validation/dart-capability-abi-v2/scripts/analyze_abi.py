from common import *
import re,collections

def symbols(path):
 p=run(['readelf','--dyn-syms','--wide',path]);assert p['rc']==0
 out={}
 for line in p['stdout'].splitlines():
  a=line.split()
  if len(a)<8 or not a[0].rstrip(':').isdigit() or a[4]=='LOCAL':continue
  name=a[7].split('@')[0];out[name]={'name':a[7],'type':a[3],'size':a[2],'binding':a[4],'visibility':a[5],'version':a[7][len(name):] or 'UNVERSIONED','section':a[6]}
 return out

def compare(a,b):
 defs=lambda x:{k:v for k,v in x.items() if v['section']!='UND' and v['visibility'] in ('DEFAULT','PROTECTED')}
 undef=lambda x:{k:v for k,v in x.items() if v['section']=='UND'}
 ad,bd,au,bu=defs(a),defs(b),undef(a),undef(b)
 return {'export_count':len(bd),'missing_exports':sorted(ad.keys()-bd.keys()),'added_exports':sorted(bd.keys()-ad.keys()),'missing_undefined':sorted(au.keys()-bu.keys()),'added_undefined':sorted(bu.keys()-au.keys()),'undefined_versions_changed':{k:[au[k]['name'],bu[k]['name']] for k in au.keys()&bu.keys() if au[k]['name']!=bu[k]['name']},'shared_metadata_differences':{k:{f:[ad[k][f],bd[k][f]] for f in ('type','size','binding','visibility','version') if ad[k][f]!=bd[k][f]} for k in ad.keys()&bd.keys() if any(ad[k][f]!=bd[k][f] for f in ('type','size','binding','visibility','version'))}}
rels={'core':'lib/libdart.so.6.13.2','external':'dart/external/odelcpsolver/libdart-external-odelcpsolver.so.6.13.2','ode':'lib/libdart-collision-ode.so.6.13.2','ipopt':'lib/libdart-optimizer-ipopt.so.6.13.2','nlopt':'lib/libdart-optimizer-nlopt.so.6.13.2'}
libs={}
for part in ('core','external','ode'):
 libs['installed_'+part]=Path('/usr/lib/x86_64-linux-gnu')/Path(rels[part]).name
for part in ('ipopt','nlopt'):
 candidates=list((R/'work/reference-modules').rglob(Path(rels[part]).name));assert len(candidates)==1;libs['packaged_'+part]=candidates[0]
for tag in ('baseline','trace'):
 for part,rel in rels.items():libs[tag+'_'+part]=R/f'work/build-{tag}-final'/rel
inventory={}
for name,p in libs.items():
 inventory[name]={'path':str(p),'sha256':sha(p),'symbols':symbols(p),'dynamic':run(['readelf','-d',p])['stdout'],'versions':run(['readelf','-V',p])['stdout'],'sections':run(['readelf','-SW',p])['stdout']}
save('symbol_inventory.json',inventory)
differences={};instrumentation={}
for part in rels:
 ref=inventory[('packaged_' if part in ('ipopt','nlopt') else 'installed_')+part]['symbols']
 for tag in ('baseline','trace'):differences[tag+'_'+part]=compare(ref,inventory[tag+'_'+part]['symbols'])
 instrumentation[part]=compare(inventory['baseline_'+part]['symbols'],inventory['trace_'+part]['symbols'])
save('symbol_differences.json',differences);save('instrumentation_delta.json',instrumentation)
env=os.environ.copy();dep=R/'work/dependencies/usr';dep_libs=[dep/'lib/x86_64-linux-gnu',dep/'lib'];loaders={}
plugin=Path('/usr/lib/x86_64-linux-gnu/gz-physics-7/engine-plugins/libgz-physics7-dartsim-plugin.so.7.8.0')
for tag in ('baseline','trace'):
 b=R/f'work/build-{tag}-final';env['LD_LIBRARY_PATH']=':'.join(map(str,[b/'lib',b/'dart/external/odelcpsolver',*dep_libs]))
 for part in rels:
  p=libs[tag+'_'+part];out=run(['ldd','-r',p],env=env);out['issues']=re.findall(r'.*(?:not found|undefined symbol).*',out['stdout']+out['stderr']);loaders[tag+'_'+part]=out
 out=run(['ldd','-r',plugin],env=env);out['issues']=re.findall(r'.*(?:not found|undefined symbol).*',out['stdout']+out['stderr']);out['candidate_core_selected']=str(b/'lib') in out['stdout'];out['candidate_external_selected']=str(b/'dart/external/odelcpsolver') in out['stdout'];loaders[tag+'_plugin']=out
save('loader_checks.json',loaders)
consumers=json.loads((OLD/'reports/consumer_inventory.json').read_text());refs={}
for path in consumers:
 s=symbols(path);u={k:v for k,v in s.items() if v['section']=='UND'}
 refs[path]={'undefined':u,'unavailable_from_trace_exports':sorted(k for k in u if k in inventory['installed_core']['symbols'] and k not in inventory['trace_core']['symbols'])}
save('consumer_references.json',refs)
summary={k:{n:len(v[n]) if isinstance(v[n],(list,dict)) else v[n] for n in ('export_count','missing_exports','added_exports','missing_undefined','added_undefined','shared_metadata_differences')} for k,v in differences.items()}
save('abi_summary.json',summary);print(json.dumps(summary,indent=2));print('Loader issues',{k:v['issues'] for k,v in loaders.items() if v['rc'] or v['issues']})
