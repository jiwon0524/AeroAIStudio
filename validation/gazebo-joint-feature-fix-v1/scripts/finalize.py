from pathlib import Path
import json,hashlib,subprocess,re,os
b=Path.cwd();p=b/'validation/gazebo-joint-feature-fix-v1';old=b/'validation/gazebo-joint-codegen-fix-v1';root=old/'work/config-01'
def sha(f):return hashlib.sha256(Path(f).read_bytes()).hexdigest()
receipt=json.loads((root/'manifests/staged.json').read_text());pairs=[]
for path,row in receipt.items():
 assert sha(path)==sha(row['source'])==row['sha256']
 pairs.append({'path':path,**row})
artifacts={}
for f in {Path(row['source']) for row in receipt.values() if row['component']=='sim'}:
 text=subprocess.check_output(['readelf','-d','-n',str(f)],text=True)
 runpaths=re.findall(r'Library runpath: \[(.*?)\]',text);assert not re.findall(r'Library rpath:',text);assert runpaths==[str(root/'prefix/lib')+':'+str(b/'validation/gazebo-joint-closure-v1/work/deps/usr/lib/x86_64-linux-gnu')]
 artifacts[str(f)]={'sha256':sha(f),'build_id':re.findall(r'Build ID: ([a-f0-9]+)',text),'soname':re.findall(r'Library soname: \[(.*?)\]',text),'needed':re.findall(r'Shared library: \[(.*?)\]',text),'runpath':runpaths,'rpath':[]}
text=subprocess.check_output(['/usr/bin/ninja','-C',str(root/'build/sim-03'),'-t','commands','gz-sim8-physics-system'],text=True)
links=[line for line in text.splitlines() if ' -shared ' in line];assert len(links)==2
(p/'logs/selected_link_commands.txt').write_text('\n'.join(links)+'\n')
link_inputs=sorted(set(re.findall(r'(?<!\S)(/[^\s]+\.(?:so(?:\.[0-9.]+)?|a))(?=\s|$)',links[-1])))
link_records=[{'path':s,'realpath':str(Path(s).resolve()),'sha256':sha(s)} for s in link_inputs]
assert all('libgz-physics-dartsim-plugin.so' not in x['path'] for x in link_records)
source=root/'src/sim/src/systems/physics/Physics.cc';before=(p/'work/Physics.cc.before').read_text();after=source.read_text()
assert after.replace('          CollisionPairMaxContactsFeatureList,\n          // Optional native-world access for the isolated joint observer.\n          physics::FeatureList<physics::dartsim::RetrieveWorld>','          CollisionPairMaxContactsFeatureList')==before
entity=root/'src/sim/src/systems/physics/EntityFeatureMap.hh';provider=root/'src/physics/dartsim/src';orig=b/'validation/gazebo-joint-physics-fix-v1/work/config-01/src/physics/dartsim/src'
for name in ['CustomFeatures.hh','CustomFeatures.cc','World.hh','plugin.cc']:assert (provider/name).read_bytes()==(orig/name).read_bytes()
assert 'static_assert(HasFeatureList<ToFeatureList>::value' in entity.read_text()
assert 'if (!proxy) return false;' in after and 'if (!proxy || proxy->GetDartsimWorld() != this->jointWorld) return false;' in after
assert sha(old/'inputs/compile_gate.py')=='7446e7d3d4e6f542cf4a7b67c2997f7bd4f322593eb0054c6fe79f0e07f3489b'
(p/'reports/elf_and_receipt.json').write_text(json.dumps({'status':'PASS','build_prefix_pairs':pairs,'sim_artifacts':artifacts,'physics_system_link_inputs':link_records,'scope':'static link inputs/ELF closure and byte identity; no actual runtime mapping'},indent=2)+'\n')
(p/'reports/contract.json').write_text(json.dumps({'status':'PASS_COMPILE_AND_STATIC','request':'physics::FeatureList<physics::dartsim::RetrieveWorld>','change':'exact optional feature-list membership only in isolated instrumented WorldEntityMap','policy':'EntityFeatureMap3d -> FeaturePolicy3d; CustomFeatures Implements3d<CustomFeatureList>; GZ_PHYSICS_ADD_PLUGIN(Plugin, FeaturePolicy3d, DartsimFeatures)','provider':'DartsimFeatures contains CustomFeatureList containing RetrieveWorld; CustomFeatures implements GetDartsimWorld returning worlds.at(identity); compiled provider symbols recorded in reuse.json','same_provider_headers':True,'entity_map_static_assert_unchanged':True,'runtime_missing_proxy_rejection_unchanged':True,'JointValidate_identity_and_zero_time_checks_unchanged':True,'compiler_gate_unchanged':True,'source_before_sha256':sha(p/'work/Physics.cc.before'),'source_after_sha256':sha(source),'original_source_backup':'work/Physics.cc.before','NOT_RUNTIME_VERIFIED':True},indent=2)+'\n')
print(json.dumps(artifacts,indent=2));print('PASS',len(pairs),'build/prefix receipt pairs,',len(link_records),'explicit Physics system library inputs')
