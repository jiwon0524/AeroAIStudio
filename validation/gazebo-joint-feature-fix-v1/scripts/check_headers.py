from pathlib import Path
import json,hashlib,subprocess,shlex
b=Path.cwd();p=b/'validation/gazebo-joint-feature-fix-v1';old=b/'validation/gazebo-joint-codegen-fix-v1';root=old/'work/config-01';build=root/'build/sim-03'
text=subprocess.check_output(['/usr/bin/ninja','-C',str(build),'-t','deps'],text=True);(p/'logs/sim.actual_deps.txt').write_text(text)
headers={str((Path(s.strip()) if Path(s.strip()).is_absolute() else build/s.strip()).resolve()) for s in text.splitlines() if s.startswith('    ')}
assert not any(s.startswith('/usr/local/') for s in headers)
allowed={str(Path(k).resolve()):v['sha256'] for k,v in json.loads((old/'work/selected_files.json').read_text()).items()}
for row in json.loads((b/'validation/gazebo-joint-inputs-v1/reports/toolchain_files.json').read_text()):
 if row['path'].startswith(('/usr/include/c++/13/','/usr/include/x86_64-linux-gnu/c++/13/','/usr/lib/gcc/','/usr/share/cmake-3.28/')):allowed[row['realpath']]=row['sha256']
for name in headers:
 f=Path(name)
 if f.is_relative_to(root) or f.is_relative_to(old/'inputs'):continue
 assert allowed.get(name)==hashlib.sha256(f.read_bytes()).hexdigest(),name
worlds=[s for s in headers if s.endswith('/dartsim/src/World.hh')];assert len(worlds)==1,worlds
provider=b/'validation/gazebo-joint-physics-fix-v1/work/config-01/src/physics/dartsim/src/World.hh';assert Path(worlds[0]).read_bytes()==provider.read_bytes()
(p/'reports/actual_headers.json').write_text(json.dumps({'status':'PASS','object_records':len([s for s in text.splitlines() if s and not s.startswith(' ')]),'unique_dependencies':len(headers),'local_headers':[],'RetrieveWorld_header':worlds[0],'provider_header':str(provider),'header_sha256':hashlib.sha256(provider.read_bytes()).hexdigest(),'dep_metadata_sha256':hashlib.sha256(text.encode()).hexdigest()},indent=2)+'\n');print('PASS actual headers',len(headers),'dependencies; RetrieveWorld same bytes as provider')
