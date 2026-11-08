from pathlib import Path
import json,re,shlex,subprocess,hashlib
b=Path.cwd();p=b/'validation/gazebo-joint-codegen-fix-v1';root=p/'work/config-01';build=root/'build/sim-03'
def sha(f):return hashlib.sha256(Path(f).read_bytes()).hexdigest()
log=(p/'logs/sim.build.final.log').read_text();diagnostics=[line for line in log.splitlines() if 'static assertion failed' in line or 'required from here' in line];assert len([x for x in diagnostics if 'static assertion failed' in x])==1
commands=json.loads((build/'compile_commands.json').read_text());row=next(x for x in commands if x['file'].endswith('/src/systems/physics/Physics.cc'));args=shlex.split(row['command']);clean=[];i=0
while i<len(args):
 if args[i] in ['-o','-MF','-MT']:i+=2;continue
 if args[i] in ['-c','-MD','-MMD']:i+=1;continue
 clean.append(args[i]);i+=1
a=json.loads((p/'reports/commands_final.json').read_text())[0]['argv'];env=a[:a.index('/usr/bin/cmake')];dep=p/'logs/physics_system.preprocess.d';r=subprocess.run(env+clean+['-M','-MF',str(dep)],cwd=build,text=True,capture_output=True);assert r.returncode==0,r.stderr
headers=shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1]);real={str((Path(x) if Path(x).is_absolute() else build/x).resolve()) for x in headers};assert not any(x.startswith('/usr/local/') for x in real)
additions=json.loads((p/'reports/interface_header_additions.json').read_text());used=[]
for x in additions:
 if x['prefix'] in real:assert sha(x['prefix'])==x['sha256'];used.append(x)
assert any(x['prefix'].endswith('/mesh/MeshShape.hh') for x in used)
actual=subprocess.check_output(['/usr/bin/ninja','-C',str(build),'-t','deps'],text=True);(p/'logs/sim.actual_deps.txt').write_text(actual);actual_headers={str((Path(s.strip()) if Path(s.strip()).is_absolute() else build/s.strip()).resolve()) for s in actual.splitlines() if s.startswith('    ')};assert not any(s.startswith('/usr/local/') for s in actual_headers)
(p/'reports/compile_blocker.json').write_text(json.dumps({'status':'PHYSICS_SYSTEM_FEATURE_CONTRACT_BLOCKED','first_error':diagnostics,'source':row['file'],'line':1118,'request':'FeatureList<gz::physics::dartsim::RetrieveWorld>','rejecting_assertion':'EntityFeatureMap.hh:103 HasFeatureList<ToFeatureList>::value','reason':'requested feature-list type is not in WorldEntityMap OptionalFeatureLists','source_change':'no feature/cast guard changed or bypassed','preprocess_only_dependency_count':len(real),'preprocess_only_fixed_headers':used,'preprocess_only_local_headers':[],'preprocess_dep_sha256':sha(dep),'actual_successful_object_records':sum(bool(s) and not s.startswith(' ') for s in actual.splitlines()),'actual_successful_unique_headers':len(actual_headers),'actual_successful_local_headers':[],'whole_Sim_build':'FAIL; core linked, Physics system object not built, no full Sim audit/stage/receipt/harness'},indent=2)+'\n')
print('Current blocker recorded; successful objects',sum(bool(s) and not s.startswith(' ') for s in actual.splitlines()),'fixed interface headers parsed',len(used))
