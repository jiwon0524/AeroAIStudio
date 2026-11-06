"""Read-only ELF audit. Loader trace/relocation mode never calls ELF initializers."""
from pathlib import Path
import subprocess, json, hashlib, os, re
R=Path(__file__).resolve().parents[1]
V=R.parent/'dart-capability-abi-v2'
def run(args,env=None):
 p=subprocess.run(list(map(str,args)),capture_output=True,text=True,env=env,timeout=90)
 return dict(rc=p.returncode,stdout=p.stdout,stderr=p.stderr)
def sha(p):return hashlib.file_digest(open(p,'rb'),'sha256').hexdigest()
def save(n,x): (R/'reports'/n).write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n')
def elf(p):
 d=run(['readelf','-dW',p])['stdout']; notes=run(['readelf','-nW',p])['stdout']
 return dict(path=str(p),sha256=sha(p),build_id=(re.findall(r'Build ID: (\w+)',notes)or[None])[0],**{k:re.findall(r'\('+k+r'\).*?\[(.*?)\]',d) for k in ['SONAME','NEEDED','RPATH','RUNPATH']})
def symbols(p):
 out={}
 for line in run(['readelf','--dyn-syms','--wide',p])['stdout'].splitlines():
  a=line.split()
  if len(a)<8 or not a[0].rstrip(':').isdigit() or a[4]=='LOCAL':continue
  name=a[7]; base=name.split('@')[0]
  out[base]=dict(mangled=base,type=a[3],size=int(a[2]),binding=a[4],visibility=a[5],version=name[len(base):] or 'UNVERSIONED',section=a[6])
 return out
def closure(p,env):
 # glibc ldd invokes the trusted system loader with LD_TRACE_LOADED_OBJECTS.
 # -r performs relocations in trace mode, without transferring to init arrays.
 out=run(['/usr/bin/ldd','-r',p],env)
 out['resolved']={n:str(Path(v).resolve()) for n,v in re.findall(r'^\s*(\S+) => (/\S+)',out['stdout'],re.M)}
 out['issues']=re.findall(r'.*(?:not found|undefined symbol).*',out['stdout']+out['stderr'])
 return out
if __name__=='__main__':
 paths=set()
 # Discover installed Gazebo/ROS shared objects, not only a guessed plugin name.
 for root in ['/usr/lib/x86_64-linux-gnu','/opt/ros/jazzy/lib']:
  for p in Path(root).rglob('*.so*'):
   if ('gz-' in str(p) or 'gz_' in str(p)) and p.is_file(): paths.add(p.resolve())
 consumers=[];scan=[]
 for p in sorted(paths):
  if p.read_bytes()[:4]!=b'\x7fELF':continue
  e=elf(p);s=symbols(p)
  dart=[k for k,v in s.items() if v['section']=='UND' and '4dart' in k]
  scan.append(dict(path=str(p),needed=e['NEEDED'],dart_undefined=len(dart)))
  if dart or any('libdart' in n for n in e['NEEDED']):consumers.append((p,e,s))
 save('discovery.json',scan)
 libpaths={}
 for arm,tag in [('A',None),('B','baseline'),('C','trace')]:
  if tag: ps=list((V/f'work/build-{tag}-final').rglob('libdart*.so.6.13.2'))
  else:ps=list(Path('/usr/lib/x86_64-linux-gnu').glob('libdart*.so.6.13.2'))
  libpaths[arm]={str(p.resolve()):symbols(p) for p in ps}
 inventory=[];rows=[];loaders=[]
 for p,e,s in consumers:
  e['dart_symbols']=[]
  for name,v in s.items():
   if v['section']!='UND':continue
   providers={a:[path for path,syms in libs.items() if name in syms and syms[name]['section']!='UND'] for a,libs in libpaths.items()}
   if not ('4dart' in name or any(providers.values())):continue
   dem=run(['c++filt',name])['stdout'].strip()
   # B/C intentionally retain installed auxiliary DART modules not rebuilt in V2.
   effective={a:providers[a] or [q for q in providers['A'] if not any(Path(q).name==Path(x).name for x in libpaths[a])] for a in ['B','C']}
   row=dict(consumer=str(p),**v,demangled=dem,providers=providers,effective_providers=effective,actually_referenced=True,status='COMPATIBLE_WITH_LIMITATIONS' if all(effective.values()) else 'INCOMPATIBLE',basis='ELF name/provider only; call ABI and installed binary layout not proven')
   rows.append(row);e['dart_symbols'].append(name)
  for arm,tag in [('A',None),('B','baseline'),('C','trace')]:
   env={k:v for k,v in os.environ.items() if not k.startswith('LD_')}
   search=[]
   if tag:
    b=V/f'work/build-{tag}-final'; dep=V/'work/dependencies/usr'
    search=[b/'lib',b/'dart/external/odelcpsolver',dep/'lib/x86_64-linux-gnu',dep/'lib'];env['LD_LIBRARY_PATH']=':'.join(map(str,search))
   o=closure(p,env);o.update(consumer=str(p),arm=arm,search_path=list(map(str,search)),mode='glibc trace relocations; no constructors/dlopen')
   darts={n:q for n,q in o['resolved'].items() if n.startswith('libdart')}
   o['dart_closure']=darts;o['installed_auxiliary_modules']={n:q for n,q in darts.items() if tag and not q.startswith(str(V))}
   o['core_external_selected']=all((not tag or f'build-{tag}-final' in q) for n,q in darts.items() if n.startswith(('libdart.so','libdart-external-odelcpsolver')))
   loaders.append(o)
   if arm=='A':e['transitive_dependencies']=o['resolved'];e['direct_dependencies']={n:o['resolved'].get(n,'UNKNOWN') for n in e['NEEDED']}
  inventory.append(e)
 save('consumer_inventory.json',inventory);save('consumer_symbols.json',rows);save('loader_results.json',loaders)
 save('provider_inventory.json',{a:[elf(p) for p in libs] for a,libs in libpaths.items()})
 save('environment.json',{'os':Path('/etc/os-release').read_text(),'packages':run(['dpkg-query','-W','libdart-core+collisions+odelcpsolver6.13','libgz-physics7-dartsim','gz-sim8','ros-jazzy-ros-base']), 'compiler':run(['c++','--version']),'linker':run(['ld','--version']),'tools':{n:run(['which',n]) for n in ['readelf','nm','objdump','c++filt','abidiff','gdb']}})
 print('consumers',len(inventory),'references',len(rows),'loader issues',sum(bool(o['issues']) for o in loaders))
