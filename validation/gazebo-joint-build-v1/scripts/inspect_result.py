"""Post-stop read-only ELF/selection/dependency inspection; no target loader."""
from pathlib import Path
import json,hashlib,subprocess,re,struct
base=Path.cwd();phase=base/'validation/gazebo-joint-build-v1';prep=base/'validation/gazebo-joint-closure-v1';config=prep/'work/config-01';out=phase/'reports'
paths=[config/'build/probe/libaero-joint-probe.so.1.0',config/'prefix/lib/libaero-joint-probe.so.1.0']
artifacts=[]
for p in paths:
 raw=subprocess.check_output(['readelf','-h','-d','-n','-W',str(p)],text=True)
 (phase/'logs'/('probe.'+('build' if 'build/probe' in str(p) else 'prefix')+'.readelf.txt')).write_text(raw)
 artifacts.append({'path':str(p.relative_to(base)),'realpath':str(p.resolve()),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size,'build_id':re.findall(r'Build ID: ([a-f0-9]+)',raw),'soname':re.findall(r'Library soname: \[(.*?)\]',raw),'needed':re.findall(r'Shared library: \[(.*?)\]',raw),'rpath':re.findall(r'Library rpath: \[(.*?)\]',raw),'runpath':re.findall(r'Library runpath: \[(.*?)\]',raw)})
(out/'artifacts.json').write_text(json.dumps(artifacts,indent=2)+'\n')
a,b=[p.read_bytes() for p in paths];differences=[i for i,(x,y) in enumerate(zip(a,b)) if x!=y]
# Decode ELF64LE section headers directly to locate changed bytes.
assert a[:6]==b'\x7fELF\x02\x01'
shoff=struct.unpack_from('<Q',a,40)[0];entsize,count,stringidx=struct.unpack_from('<HHH',a,58)
assert entsize==64
headers=[struct.unpack_from('<IIQQQQIIQQ',a,shoff+i*64) for i in range(count)]
st=headers[stringidx];strings=a[st[4]:st[4]+st[5]]
sections=[]
for h in headers:
 name=strings[h[0]:].split(b'\0',1)[0].decode(errors='replace');lo,size=h[4],h[5]
 if any(lo<=i<lo+size for i in differences):sections.append({'name':name,'offset':lo,'size':size})
diff={'equal_size':len(a)==len(b),'build_bytes':len(a),'prefix_bytes':len(b),'different_byte_count':len(differences),'changed_sections':sections,'changed_bytes':[{'offset':i,'build':a[i],'prefix':b[i]} for i in differences[:128]],'remaining_changes_omitted':max(0,len(differences)-128),'same_build_id':artifacts[0]['build_id']==artifacts[1]['build_id'],'same_soname':artifacts[0]['soname']==artifacts[1]['soname'],'same_needed':artifacts[0]['needed']==artifacts[1]['needed'],'stage_script':'validation/gazebo-joint-closure-v1/work/config-01/build/probe/cmake_install.cmake','cause':'Compare CMake RPATH_CHANGE and exact byte offsets; no receipt bypass or retry performed'}
(out/'staging_difference.json').write_text(json.dumps(diff,indent=2)+'\n')
# Ninja tool mode only reads its dep database, and does not build/run targets.
raw=subprocess.check_output(['/usr/bin/ninja','-C',str(config/'build/probe'),'-t','deps'],text=True)
(phase/'logs/probe.header_deps.txt').write_text(raw)
lock=json.loads((prep/'work/selected_files.json').read_text());allowed={str(Path(k).resolve()):v['sha256'] for k,v in lock.items()}
for x in json.loads((base/'validation/gazebo-joint-inputs-v1/reports/toolchain_files.json').read_text()):
 if x['path'].startswith(('/usr/include/c++/13/','/usr/include/x86_64-linux-gnu/c++/13/','/usr/lib/gcc/','/usr/share/cmake-3.28/')):allowed[x['realpath']]=x['sha256']
files={};errors=[]
for line in raw.splitlines():
 if not line.startswith('    '):continue
 p=Path(line.strip()).resolve()
 if not p.is_file():errors.append('missing '+str(p));continue
 sha=hashlib.sha256(p.read_bytes()).hexdigest();own=p.is_relative_to(prep/'inputs') or p.is_relative_to(config)
 ok=own or allowed.get(str(p))==sha
 if not ok:errors.append('unlocked '+str(p))
 files[str(p)]={'sha256':sha,'own':own,'allowlist_match':ok}
(out/'header_dependencies.json').write_text(json.dumps({'status':'PASS' if not errors else 'REVIEW_REQUIRED','files':files,'errors':errors},indent=2)+'\n')
# Only whitelisted cache fields, not a raw environment/cache dump.
cache={}
for line in (config/'build/probe/CMakeCache.txt').read_text().splitlines():
 if not line or line.startswith(('#','//')) or '=' not in line or ':' not in line.split('=',1)[0]:continue
 keytype,value=line.split('=',1);key=keytype.split(':',1)[0]
 if key.startswith(('CMAKE_C_COMPILER','CMAKE_CXX_COMPILER','CMAKE_LINKER','CMAKE_MAKE_PROGRAM','CMAKE_BUILD_TYPE','CMAKE_CXX_FLAGS','CMAKE_INSTALL_PREFIX','CMAKE_BUILD_RPATH','CMAKE_INSTALL_RPATH','OPENSSL_')):cache[key]=value
props=[]
for p in (config/'build/probe/joint-targets').rglob('target.txt'):
 props.append({'target':p.read_text().strip(),'properties':{q.stem:q.read_text().strip() for q in p.parent.glob('*.txt') if q.name!='target.txt'}})
(out/'actual_selection.json').write_text(json.dumps({'cache':cache,'targets':props,'selection_check':'probe.selection.log','command_and_link_line':'probe.build.log'},indent=2)+'\n')
closure=json.loads((phase/'logs/probe.elf.log').read_text());(out/'probe_link_closure.json').write_text(json.dumps(closure,indent=2)+'\n')
# Symlinks/provenance receipt status, do not create a staged receipt.
links=[{'path':str(p.relative_to(base)),'link':str(p.readlink()) if p.is_symlink() else None,'realpath':str(p.resolve())} for root in [config/'build/probe',config/'prefix/lib'] for p in sorted(root.glob('libaero-joint-probe.so*'))]
(out/'artifact_links.json').write_text(json.dumps({'links':links,'staged_receipt_exists':(config/'manifests/staged.json').exists(),'harness':'NOT_BUILT','DART_physics_Sim_plugins':'NOT_BUILT','runtime_world':'NOT_MATERIALIZED'},indent=2)+'\n')
print(json.dumps({'artifacts':artifacts,'difference':diff,'header_dependency_count':len(files),'header_errors':errors,'ELF_closure_nodes':len(closure['files'])},indent=2))
