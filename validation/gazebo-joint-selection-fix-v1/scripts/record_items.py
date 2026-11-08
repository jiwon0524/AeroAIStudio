from pathlib import Path
import json,hashlib,subprocess,re
b=Path.cwd();p=b/'validation/gazebo-joint-selection-fix-v1';old=b/'validation/gazebo-joint-export-fix-v1';root=p/'work/config-01';build=root/'build/dart'
def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()
closure=json.loads((p/'reports/dart_selected_closure.json').read_text());commands=(p/'logs/dart.selected_commands.txt').read_text();reply=build/'.cmake/api/v1/reply';index=json.loads(next(reply.glob('index-*.json')).read_text());model=json.loads((reply/index['reply']['codemodel-v2']['jsonFile']).read_text());alltargets={x['name']:json.loads((reply/x['jsonFile']).read_text()) for x in model['configurations'][0]['targets']}
rows=[json.loads(l) for l in (root/'logs/dart.trace.jsonl').read_text().splitlines()]
result={}
items={'libGLESv2':('/usr/lib/x86_64-linux-gnu/libGLESv2.so','libgles2','OpenGL::GLES2/OpenGL::GLES3 metadata'),'libflann_cpp':('/usr/lib/x86_64-linux-gnu/libflann_cpp.so','libflann1.9','flann metadata; unselected dart-planning link'),'libgvc6-config-update':('/usr/bin/dot','libgvc6','Doxygen::dot imported executable metadata')}
for name,(alias,package,origin) in items.items():
 f=Path(alias).resolve();version=subprocess.check_output(['dpkg-query','-W','-f=${binary:Package}\t${Version}\t${source:Package}\t${source:Version}',package],text=True)
 linktargets=[n for n,t in alltargets.items() if any(alias in x['fragment'] for x in t.get('link',{}).get('commandFragments',[]))]
 executions=[x for x in rows if x.get('cmd')=='execute_process' and any(alias in s or str(f) in s for s in x.get('args',[]))]
 result[name]={'alias':alias,'realpath':str(f),'sha256':sha(f),'package':version,'origin':origin,'selected_build_closure':False,'selected_commands_contain_alias':alias in commands,'linking_generated_targets':linktargets,'execute_process_rows':executions,'decision':'NOT_SELECTED_METADATA_ONLY; no allowlist addition'}
 assert not executions and alias not in commands
f=Path('/usr/lib/x86_64-linux-gnu/cmake/tinyxml2/tinyxml2-shared-targets.cmake');location=next((build/'joint-targets').rglob('tinyxml2__tinyxml2/IMPORTED_LOCATION_NONE.txt'),None)
props={q.stem:q.read_text().strip() for q in next((build/'joint-targets').rglob('tinyxml2__tinyxml2/target.txt')).parent.glob('*.txt')}
libs=sorted({token for name in ['dart-utils','dart-utils-urdf'] for x in closure['generated'][name]['link']['commandFragments'] for token in x['fragment'].split() if 'tinyxml2' in token})
result['tinyxml2']={'declaration':str(f),'declaration_line':next(i for i,l in enumerate(f.read_text().splitlines(),1) if l.strip().startswith('INTERFACE_COMPILE_DEFINITIONS')),'definition_sha256':sha(f),'target':'tinyxml2::tinyxml2','raw':closure['tinyxml2_raw'],'configuration':closure['configuration'],'effective_definitions':{name:sorted({x['define'] for g in closure['generated'][name]['compile_groups'] for x in g.get('defines',[]) if 'TINYXML2' in x['define'] or '_FILE_OFFSET_BITS' in x['define']}) for name in ['dart-utils','dart-utils-urdf']},'generated_link_paths':[{'path':lib,'realpath':str(Path(lib).resolve()),'sha256':sha(Path(lib))} for lib in libs],'raw_imported_properties':props,'decision':'SELECTED; CMake-generated definitions/path validated; actual utils compilation not reached'}
(p/'reports/four_items.json').write_text(json.dumps(result,indent=2)+'\n')
count=0
for f in (old/'work/config-01/src').rglob('*'):
 if not f.is_file():continue
 q=root/'src'/f.relative_to(old/'work/config-01/src');expected=f.read_bytes()
 if f.name=='CMakeLists.txt':expected=expected.replace(str(old).encode(),str(p).encode())
 assert q.read_bytes()==expected,str(q);count+=1
trace={}
for c in ['probe','dart']:
 f=root/'logs'/f'{c}.trace.jsonl';n=sum(json.loads(l).get('cmd')=='try_run' for l in f.read_text().splitlines());assert n==0;trace[c]={'sha256':sha(f),'try_run_count':n}
oldart=json.loads((old/'reports/artifacts.json').read_text())
for x in oldart['elfs']:assert sha(b/x['path'])==x['sha256']
(p/'reports/preservation_current.json').write_text(json.dumps({'source_files_equal_after_observer_path_relocation':count,'prior_elf_hashes_unchanged':True,'trace':trace,'broad_policy_sha256':sha(p/'scripts/check_selection_broad.py'),'previous_policy_sha256':sha(old/'scripts/check_selection.py'),'checker_sha256':sha(p/'scripts/check_selected_dart.py')},indent=2)+'\n')
print(json.dumps({n:{'decision':v['decision'],'links':v.get('linking_generated_targets',v.get('generated_link_paths'))} for n,v in result.items()},indent=2))
