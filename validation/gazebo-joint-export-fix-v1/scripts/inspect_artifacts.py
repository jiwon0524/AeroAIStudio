from pathlib import Path
import json,hashlib,subprocess,re
b=Path.cwd();p=b/'validation/gazebo-joint-export-fix-v1';old=b/'validation/gazebo-joint-scope-fix-v1';root=p/'work/config-01'
def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()
art=[]
for f in (root/'build').rglob('*'):
 if not f.is_file() or f.is_symlink():continue
 with f.open('rb') as stream:magic=stream.read(4)
 if magic!=b'\x7fELF':continue
 text=subprocess.check_output(['readelf','-h','-d','-n',str(f)],text=True,stderr=subprocess.STDOUT)
 art.append({'path':str(f.relative_to(b)),'sha256':sha(f),'size':f.stat().st_size,'type':re.findall(r'Type:\s+(.*)',text),'build_id':re.findall(r'Build ID: ([a-f0-9]+)',text),'soname':re.findall(r'Library soname: \[(.*?)\]',text),'needed':re.findall(r'Shared library: \[(.*?)\]',text),'rpath':re.findall(r'Library rpath: \[(.*?)\]',text),'runpath':re.findall(r'Library runpath: \[(.*?)\]',text)})
a=root/'build/probe/libaero-joint-probe.so.1.0';z=root/'prefix/lib/libaero-joint-probe.so.1.0';assert a.read_bytes()==z.read_bytes()
probe=next(x for x in art if x['path']==str(a.relative_to(b)));assert probe['rpath']==[];assert probe['runpath']==[str(root/'prefix/lib')+':'+str((p/'work/deps').resolve()/'usr/lib/x86_64-linux-gnu')]
assert 'RPATH_CHANGE' not in (root/'build/probe/cmake_install.cmake').read_text()
oldclosure=json.loads((old/'logs/probe.elf.log').read_text())['files'];newclosure=json.loads((p/'logs/probe.elf.log').read_text())['files'];external={k:v for k,v in newclosure.items() if not Path(k).is_relative_to(p)}
assert len(external)==6 and all(v['sha256']==oldclosure[k]['sha256'] for k,v in external.items())
(p/'reports/artifacts.json').write_text(json.dumps({'elfs':art,'probe_build_prefix_identical':True,'prefix_sha256':sha(z),'prefix_path':str(z),'external_closure':external,'receipt':json.loads((root/'manifests/staged.json').read_text())},indent=2)+'\n')
original=json.loads((old/'reports/artifacts.json').read_text())
for x in original['elfs']:assert sha(b/x['path'])==x['sha256']
changed=[];count=0
for f in (old/'work/config-01/src').rglob('*'):
 if not f.is_file():continue
 q=root/'src'/f.relative_to(old/'work/config-01/src');expected=f.read_bytes()
 if f.name=='CMakeLists.txt':expected=expected.replace(str(old).encode(),str(p).encode())
 if q.read_bytes()!=expected:
  assert f.relative_to(old/'work/config-01/src').as_posix()=='dart/cmake/Components.cmake'
  changed.append({'path':str(q.relative_to(b)),'before_sha256':sha(f),'after_sha256':sha(q)})
 count+=1
trace_audit={}
for c in ['probe','dart']:
 trace=root/'logs'/f'{c}.trace.jsonl';rows=[json.loads(l) for l in trace.read_text().splitlines()];n=sum(x.get('cmd')=='try_run' for x in rows);assert n==0;trace_audit[c]={'sha256':sha(trace),'try_run_count':n}
(p/'reports/preservation.json').write_text(json.dumps({'source_count':count,'semantic_source_changes':changed,'observer_paths_relocated':True,'previous_ELF_hashes_unchanged':True,'trace_audit':trace_audit},indent=2)+'\n')
print(json.dumps({'probe_sha256':sha(z),'build_id':probe['build_id'],'ELF_count':len(art),'source_count':count},indent=2))
