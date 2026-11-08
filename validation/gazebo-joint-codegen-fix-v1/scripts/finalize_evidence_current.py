from pathlib import Path
import json,hashlib,subprocess,re,difflib,tempfile
b=Path.cwd();p=b/'validation/gazebo-joint-codegen-fix-v1';old=b/'validation/gazebo-joint-physics-fix-v1';root=p/'work/config-01'
def sha(f):return hashlib.sha256(Path(f).read_bytes()).hexdigest()
art=[]
for folder in [root/'build',root/'prefix']:
 for f in folder.rglob('*'):
  if not f.is_file() or f.is_symlink():continue
  with f.open('rb') as s:magic=s.read(4)
  if magic!=b'\x7fELF':continue
  text=subprocess.check_output(['readelf','-h','-d','-n',str(f)],text=True,stderr=subprocess.STDOUT)
  role='build/helper/object inventory'
  if f.name=='libgz-sim8.so.8.15.0':role='partial Sim core; not accepted/staged because Physics system failed'
  art.append({'path':str(f.relative_to(b)),'role':role,'sha256':sha(f),'size':f.stat().st_size,'type':re.findall(r'Type:\s+(.*)',text),'build_id':re.findall(r'Build ID: ([a-f0-9]+)',text),'soname':re.findall(r'Library soname: \[(.*?)\]',text),'needed':re.findall(r'Shared library: \[(.*?)\]',text),'rpath':re.findall(r'Library rpath: \[(.*?)\]',text),'runpath':re.findall(r'Library runpath: \[(.*?)\]',text)})
receipt=json.loads((root/'manifests/staged.json').read_text());identity=[]
for path,v in receipt.items():assert Path(path).read_bytes()==Path(v['source']).read_bytes() and sha(path)==v['sha256'];identity.append({'prefix':path,'source_build':v['source'],'sha256':v['sha256'],'status':'PASS_REUSED_BYTE_IDENTITY'})
(p/'reports/artifacts.json').write_text(json.dumps({'ELFs':art,'reused_build_prefix_identity':identity,'new_Sim_build_prefix_identity':'NOT_APPLICABLE_NOT_STAGED_GROUP_BUILD_FAILED','receipt':receipt},indent=2)+'\n')
lines=['|ELF|SHA-256|Build ID|Stage status|','|---|---|---|---|']
for x in art:
 if x['soname'] and 'libgz-sim8.so.8' in x['soname']:lines.append('|'+x['path']+'|'+x['sha256']+'|'+','.join(x['build_id'])+'|partial, not staged|')
(p/'reports/elf_summary.md').write_text('\n'.join(lines)+'\n')
reuse=json.loads((p/'reports/dart_reuse.json').read_text());changes={x['path']:x for x in json.loads((p/'reports/reuse_metadata_relocation.json').read_text())['changes']}
for x in reuse['files']:
 assert sha(x['source'])==x['sha256']
 if x['copy'] in changes:assert sha(x['copy'])==changes[x['copy']]['after_sha256'] and x['sha256']==changes[x['copy']]['before_sha256']
 else:assert sha(x['copy'])==x['sha256']
for x in json.loads((p/'reports/interface_header_additions.json').read_text()):assert sha(x['source'])==sha(x['prefix'])==x['sha256']
base=json.loads((old/'work/selected_files.json').read_text());lock=json.loads((p/'work/selected_files.json').read_text());extra=set(lock)-set(base);assert len(extra)==1 and all(lock[k]==v for k,v in base.items());assert sha(next(iter(extra)))==lock[next(iter(extra))]['sha256']
origin=json.loads((p/'reports/codegen_origin.json').read_text());assert sha(origin['descriptor_source'])==origin['descriptor_sha256']
config=reuse['generated_header'];assert sha(root/'prefix/include/dart/config.hpp')==config['sha256']
for oldelf,h in json.loads((root/'manifests/reused_elfs.json').read_text()).items():assert sha(oldelf)==h
trace={}
for label in ['sim','sim-02','sim-03']:
 f=root/'logs'/(label+'.trace.jsonl');rows=[json.loads(s) for s in f.read_text().splitlines()];calls=[x for x in rows if x.get('cmd','').lower()=='try_run'];assert all(x['file']=='/usr/share/cmake/gz-cmake3/cmake3/GzCheckSSE.cmake' for x in calls);trace[label]={'sha256':sha(f),'architecture_compile_error_protocol_calls':len(calls)}
(p/'reports/preservation_current.json').write_text(json.dumps({'reused_prefix_regular_files':len(reuse['files']),'old_files_unchanged':True,'new_copy_metadata_exception':list(changes),'input_lock_additions':sorted(extra),'base_lock_unchanged':True,'header_guard_sha256':{'source':sha(old/'inputs/compile_gate.py'),'current':sha(p/'inputs/compile_gate.py')},'traces':trace},indent=2)+'\n')
# Patch for the one new source-level metadata property. All C++ sources unchanged.
original=(old/'work/config-01/src/sim-02/CMakeLists.txt').read_text().replace(str(old),str(p));updated=(root/'src/sim/CMakeLists.txt').read_text();patch=p/'reports/sim_descriptor_property.patch';patch.write_text(''.join(difflib.unified_diff(original.splitlines(True),updated.splitlines(True),fromfile='a/CMakeLists.txt',tofile='b/CMakeLists.txt',n=0)))
with tempfile.TemporaryDirectory(prefix='aero-codegen-patch-',dir='/tmp') as folder:
 f=Path(folder)/'CMakeLists.txt';f.write_text(original);subprocess.run(['git','apply','--unidiff-zero','--check',str(patch)],cwd=folder,check=True);subprocess.run(['git','apply','--unidiff-zero',str(patch)],cwd=folder,check=True);assert f.read_text()==updated
(p/'reports/patch_validation.json').write_text(json.dumps({'status':'PASS_EXACT_REPLAY','patch_sha256':sha(patch)},indent=2)+'\n')
changed=[];count=0
for source_root,target_root in [(old/'work/config-01/src/sim-02',root/'src/sim'),(old/'work/config-01/src/physics',root/'src/physics')]:
 for f in source_root.rglob('*'):
  if not f.is_file():continue
  q=target_root/f.relative_to(source_root);expected=f.read_bytes()
  if f.name=='CMakeLists.txt':expected=expected.replace(str(old).encode(),str(p).encode())
  if q.read_bytes()!=expected:assert q==root/'src/sim/CMakeLists.txt';changed.append(str(q.relative_to(b)))
  count+=1
(p/'reports/source_preservation.json').write_text(json.dumps({'files_compared':count,'only_semantic_change':changed,'Cxx_sources_unchanged':True},indent=2)+'\n')
print(json.dumps({'ELF_count':len(art),'reused_ELF_pairs':len(identity),'Sim_core_variants':len(lines)-2,'source_files':count},indent=2))
