from pathlib import Path
import hashlib,json,subprocess,difflib,shutil
b=Path.cwd(); p=b/'validation/gazebo-joint-feature-fix-v1'; old=b/'validation/gazebo-joint-codegen-fix-v1'; root=old/'work/config-01'
def sha(f): return hashlib.sha256(Path(f).read_bytes()).hexdigest()
receipt=json.loads((root/'manifests/staged.json').read_text()); checked=[]
for path,row in receipt.items():
 assert sha(path)==sha(row['source'])==row['sha256'],path
 checked.append({'path':path,**row})
gen=json.loads((old/'reports/codegen_execution.json').read_text())['output_hashes']
for path,digest in gen.items(): assert sha(root/'build/sim-03'/path)==digest,path
core=root/'build/sim-03/lib/libgz-sim8.so.8.15.0'; assert sha(core)=='25b168676e55c1bfb847a92b0648802f916af96bd1730a9344e196632dea9128'
source=root/'src/sim/src/systems/physics/Physics.cc'; before=source.read_text(); backup=p/'work/Physics.cc.before'; assert not backup.exists(); shutil.copy2(source,backup)
needle='          CollisionPairMaxContactsFeatureList\n          >;'; assert before.count(needle)==1
replacement='          CollisionPairMaxContactsFeatureList,\n          // Optional native-world access for the isolated joint observer.\n          physics::FeatureList<physics::dartsim::RetrieveWorld>\n          >;'
after=before.replace(needle,replacement); source.write_text(after)
patch=''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='a/src/systems/physics/Physics.cc',tofile='b/src/systems/physics/Physics.cc',n=0))
(p/'reports/optional_retrieve_world.patch').write_text(patch)
plugin=Path(receipt[str(root/'prefix/lib/libgz-physics7-dartsim-plugin.so.7.8.0')]['source'])
symbols=subprocess.check_output(['nm','-D','-C',str(plugin)],text=True); hits=[line for line in symbols.splitlines() if 'CustomFeatures::GetDartsimWorld(' in line and ' T ' in line]; assert hits
(p/'reports/reuse.json').write_text(json.dumps({'status':'PASS','receipt_pairs':checked,'generated_outputs_checked':len(gen),'core':{'path':str(core),'sha256':sha(core)},'source_before':sha(backup),'source_after':sha(source),'provider_symbols':hits,'root_link':{'target':str((b/'libgz-physics-dartsim-plugin.so').readlink()),'target_exists':(b/'libgz-physics-dartsim-plugin.so').exists()},'staged_before':subprocess.check_output(['git','diff','--cached','--name-status'],text=True)},indent=2)+'\n')
print('PASS',len(checked),'receipt pairs,',len(gen),'generated files, core; minimal optional-list patch')
