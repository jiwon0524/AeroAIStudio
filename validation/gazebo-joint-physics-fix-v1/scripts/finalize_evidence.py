from pathlib import Path
import json,hashlib,subprocess,re,difflib,tempfile
b=Path.cwd();p=b/'validation/gazebo-joint-physics-fix-v1';old=b/'validation/gazebo-joint-header-fix-v1';root=p/'work/config-01'
def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()
art=[]
for directory in [root/'build',root/'prefix']:
 for f in directory.rglob('*'):
  if not f.is_file() or f.is_symlink():continue
  with f.open('rb') as stream:magic=stream.read(4)
  if magic!=b'\x7fELF':continue
  text=subprocess.check_output(['readelf','-h','-d','-n',str(f)],text=True,stderr=subprocess.STDOUT)
  art.append({'path':str(f.relative_to(b)),'sha256':sha(f),'size':f.stat().st_size,'type':re.findall(r'Type:\s+(.*)',text),'build_id':re.findall(r'Build ID: ([a-f0-9]+)',text),'soname':re.findall(r'Library soname: \[(.*?)\]',text),'needed':re.findall(r'Shared library: \[(.*?)\]',text),'rpath':re.findall(r'Library rpath: \[(.*?)\]',text),'runpath':re.findall(r'Library runpath: \[(.*?)\]',text)})
receipt=json.loads((root/'manifests/staged.json').read_text());identity=[]
for path,row in receipt.items():
 target=Path(path);source=Path(row['source']);assert sha(target)==sha(source)==row['sha256'];assert target.read_bytes()==source.read_bytes();identity.append({'prefix':path,'build':str(source),'sha256':row['sha256'],'component':row['component'],'reused_from':row.get('reused_from'),'status':'PASS_BYTE_IDENTICAL'})
(p/'reports/artifacts.json').write_text(json.dumps({'ELFs':art,'build_prefix_identity':identity,'receipt':receipt},indent=2)+'\n')
summary=['|SONAME|SHA-256|Build ID|Role|','|---|---|---|---|']
for row in identity:
 x=next(x for x in art if str(b/x['path'])==row['prefix']);summary.append('|'+x['soname'][0]+'|'+x['sha256']+'|'+','.join(x['build_id'])+'|'+('reused' if row.get('reused_from') else 'new physics')+'|')
(p/'reports/elf_summary.md').write_text('\n'.join(summary)+'\n')
reuse=json.loads((p/'reports/dart_reuse.json').read_text())
for row in reuse['unchanged_prefix_files']:assert sha(Path(row['source']))==sha(Path(row['copy']))==row['sha256']
config=reuse['generated_header'];assert sha(Path(config['source']))==sha(root/'prefix/include/dart/config.hpp')==config['sha256']
assert json.loads((old/'work/config-01/manifests/staged.json').read_text()).keys()=={x['reused_from'] for x in identity if x.get('reused_from')}
traces={}
for label in ['physics','sim','sim-02']:
 f=root/'logs'/(label+'.trace.jsonl');rows=[json.loads(l) for l in f.read_text().splitlines()];calls=[x for x in rows if x.get('cmd','').lower()=='try_run'];assert all(x['file']=='/usr/share/cmake/gz-cmake3/cmake3/GzCheckSSE.cmake' for x in calls);traces[label]={'sha256':sha(f),'architecture_try_run_calls':calls,'scope':'locked GzCheckSSE intentional compile-error protocol; review ConfigureLog, not subject execution'}
base_module=Path('/usr/share/cmake/gz-cmake3/cmake3/GzPackaging.cmake')
patches=[]
for name,before,after,rel in [
 ('physics_root', (old/'work/config-01/src/physics/CMakeLists.txt').read_text().replace(str(old),str(p)),(root/'src/physics/CMakeLists.txt').read_text(),'physics/CMakeLists.txt'),
 ('physics_install',(old/'inputs/install-selected.cmake').read_text(),(p/'inputs/install-selected.cmake').read_text(),'inputs/install-selected.cmake'),
 ('sim_root',(root/'src/sim/CMakeLists.txt').read_text(),(root/'src/sim-02/CMakeLists.txt').read_text(),'sim/CMakeLists.txt'),
 ('sim_install',(p/'inputs/install-selected.cmake').read_text(),(p/'inputs/install-selected-sim.cmake').read_text(),'inputs/install-selected.cmake'),
 ('sim_packaging',base_module.read_text(),(p/'inputs/GzPackaging-sim.cmake').read_text(),'GzPackaging.cmake')]:
  file=p/'reports'/(name+'.patch');file.write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='a/'+rel,tofile='b/'+rel,n=0)))
  with tempfile.TemporaryDirectory(prefix='aero-physics-patch-',dir='/tmp') as folder:
   target=Path(folder)/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(before);subprocess.run(['git','apply','--unidiff-zero','--check',str(file)],cwd=folder,check=True);subprocess.run(['git','apply','--unidiff-zero',str(file)],cwd=folder,check=True);assert target.read_text()==after
  patches.append({'patch':str(file.relative_to(b)),'status':'PASS_EXACT_REPLAY','sha256':sha(file)})
(p/'reports/patch_tests.json').write_text(json.dumps(patches,indent=2)+'\n')
(p/'reports/preservation.json').write_text(json.dumps({'reused_prefix_files_verified':len(reuse['unchanged_prefix_files']),'old_and_new_DART_ELFs_match_build_receipt':True,'same_build_config_sha256':config['sha256'],'guard_sha256':{'old':sha(old/'inputs/compile_gate.py'),'current':sha(p/'inputs/compile_gate.py')},'system_packaging_source_sha256':sha(base_module),'traces':traces,'inputs':{str(f.relative_to(b)):sha(f) for f in (p/'inputs').rglob('*') if f.is_file() and not f.is_symlink()}},indent=2)+'\n')
# Consumer proof from Sim's real configure, even though compilation stays blocked.
cache=(root/'build/sim-02/CMakeCache.txt').read_text();selected={k:re.search('^'+re.escape(k)+r':[^=]*=(.*)$',cache,re.M).group(1) for k in ['gz-physics7_DIR','gz-physics7-dartsim_DIR','gz-physics7-sdf_DIR','gz-physics7-mesh_DIR','gz-physics7-heightmap_DIR']};assert all(v.startswith(str(root/'prefix')) for v in selected.values())
(p/'reports/sim_consumer.json').write_text(json.dumps({'status':'PASS_CONFIGURE_PACKAGE_RESOLUTION','selected':selected,'physics_component_namespace':'gz-physics7::','Sim_attempt2_configure_generate':0,'Sim_build':'NOT_STARTED_OUT_OF_CONTRACT_DESCRIPTOR'},indent=2)+'\n')
print(json.dumps({'ELFs':len(art),'identical_prefix_files':len(identity),'reused_prefix_files':len(reuse['unchanged_prefix_files']),'patch_tests':len(patches)},indent=2))
