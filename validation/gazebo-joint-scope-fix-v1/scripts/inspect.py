from pathlib import Path
import json,hashlib,subprocess,re
b=Path.cwd();p=b/'validation/gazebo-joint-scope-fix-v1';old=b/'validation/gazebo-joint-build-fix-v1';root=p/'work/config-01'
def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()
analysis=json.loads((p/'reports/scope_analysis.json').read_text());rows=[json.loads(l) for l in (root/'logs/dart.trace.jsonl').read_text().splitlines()]
props=list((root/'build/dart').rglob('joint-targets/*/*/target.txt'))
scopes={f.read_text().strip() for f in (root/'build/dart/joint-scopes').glob('*.txt')}
processed={str(Path(x['file']).parent) for x in rows if 'file' in x and Path(x['file']).name=='CMakeLists.txt' and Path(x['file']).is_relative_to(root/'src/dart')}
assert scopes==processed,(processed-scopes,scopes-processed)
summary={'cause':'directory-scoped imported targets queried from ancestor execution scope','failed_names':analysis['failed_names'],'definitions':analysis['definitions'],'recovered_targets':{},'processed_directory_count':len(processed),'scope_snapshot_count':len(scopes),'coverage':'PASS','observer_insertions':len(analysis['source_observer_insertions'])}
for name in analysis['failed_names']:
 hits=[f for f in props if f.read_text().strip()==name]
 assert hits,name
 summary['recovered_targets'][name]=[]
 for f in hits:
  values={q.stem:q.read_text().strip() for q in f.parent.glob('*.txt') if q.name!='target.txt'}
  summary['recovered_targets'][name].append({'path':str(f.parent.relative_to(b)),'properties':values})
assert 'non-existent target' not in (p/'logs/dart.configure.log').read_text()
# All original sources are preserved; new copies differ only by one observer include per CMakeLists.
count=0;changed=[]
for f in (old/'work/config-01/src').rglob('*'):
 if not f.is_file():continue
 q=root/'src'/f.relative_to(old/'work/config-01/src');data=q.read_bytes()
 if data!=f.read_bytes():
  assert f.name=='CMakeLists.txt';assert data.split(b'\n',1)[1]==f.read_bytes();changed.append(str(q.relative_to(b)))
 count+=1
summary['source_files_verified']=count;summary['source_files_with_observer_include']=len(changed)
# Selected external definition files retain their locked hashes.
lock=json.loads((p/'work/selected_files.json').read_text());allowed={str(Path(k).resolve()):v['sha256'] for k,v in lock.items()}
for x in json.loads((b/'validation/gazebo-joint-inputs-v1/reports/toolchain_files.json').read_text()):allowed[x['realpath']]=x['sha256']
for d in summary['definitions']:
 f=Path(d['file']);assert sha(f)==d['definition_sha256']
 d['lock_match']=allowed.get(str(f.resolve()))==sha(f) if not f.is_relative_to(old) else 'preserved source file'
 assert d['lock_match'] is not False,d
summary['duplicate_exports']=[{'file':x['file'],'line':x['line'],'args':x['args']} for x in rows if x.get('cmd')=='install' and x.get('args',[None])[0]=='EXPORT' and 'dart_component_external-odelcpsolver' in x['args']]
summary['trace_try_run_count']=sum(x.get('cmd')=='try_run' for x in rows);assert summary['trace_try_run_count']==0
(p/'reports/scope_result.json').write_text(json.dumps(summary,indent=2)+'\n')
artifacts=[]
for f in (root/'build').rglob('*'):
 if not f.is_file() or f.is_symlink():continue
 with f.open('rb') as s:magic=s.read(4)
 if magic!=b'\x7fELF':continue
 raw=subprocess.check_output(['readelf','-h','-d','-n',str(f)],text=True,stderr=subprocess.STDOUT)
 artifacts.append({'path':str(f.relative_to(b)),'sha256':sha(f),'size':f.stat().st_size,'type':re.findall(r'Type:\s+(.*)',raw),'build_id':re.findall(r'Build ID: ([a-f0-9]+)',raw),'needed':re.findall(r'Shared library: \[(.*?)\]',raw),'soname':re.findall(r'Library soname: \[(.*?)\]',raw),'rpath':re.findall(r'Library rpath: \[(.*?)\]',raw),'runpath':re.findall(r'Library runpath: \[(.*?)\]',raw)})
a=root/'build/probe/libaero-joint-probe.so.1.0';z=root/'prefix/lib/libaero-joint-probe.so.1.0';assert a.read_bytes()==z.read_bytes()
probe=next(x for x in artifacts if x['path']==str(a.relative_to(b)));assert not probe['rpath'];assert probe['runpath']==[str(root/'prefix/lib')+':'+str((p/'work/deps').resolve()/'usr/lib/x86_64-linux-gnu')]
assert 'RPATH_CHANGE' not in (root/'build/probe/cmake_install.cmake').read_text()
prior=json.loads((old/'reports/artifacts.json').read_text())
for path,v in prior.items():assert sha(b/path)==v['sha256']
oldclosure=json.loads((old/'logs/probe.elf.recheck.log').read_text())['files'];newclosure=json.loads((p/'logs/probe.elf.log').read_text())['files'];external={k:v for k,v in newclosure.items() if not Path(k).is_relative_to(p)}
assert len(external)==6 and all(oldclosure[k]['sha256']==v['sha256'] for k,v in external.items())
(p/'reports/artifacts.json').write_text(json.dumps({'elfs':artifacts,'probe_build_prefix_identical':True,'prefix_path':str(z),'prefix_sha256':sha(z),'external_closure_matches_prior':True,'external_files':external,'receipt':json.loads((root/'manifests/staged.json').read_text()),'helpers':'compiler identification/ABI and objects inventoried only; not executed or runtime-certified'},indent=2)+'\n')
inputs={str(f.relative_to(b)):sha(f) for f in (p/'inputs').rglob('*') if f.is_file()}
(p/'reports/input_hashes.json').write_text(json.dumps(inputs,indent=2)+'\n')
print(json.dumps({'scope_count':len(scopes),'observer_insertions':summary['observer_insertions'],'source_files':count,'elf_count':len(artifacts),'probe_sha256':sha(z),'build_id':probe['build_id'],'definition_files_locked':True},indent=2))
