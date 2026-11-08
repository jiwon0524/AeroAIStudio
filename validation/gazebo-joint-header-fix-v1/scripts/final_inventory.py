"""Static ELF/source/input inventory after the authorized build stops."""
from pathlib import Path
import json,hashlib,subprocess,re
b=Path.cwd();p=b/'validation/gazebo-joint-header-fix-v1';old=b/'validation/gazebo-joint-selection-fix-v1';root=p/'work/config-01'
def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()
art=[]
for folder in [root/'build',root/'prefix']:
 for f in folder.rglob('*'):
  if not f.is_file() or f.is_symlink():continue
  with f.open('rb') as stream:magic=stream.read(4)
  if magic!=b'\x7fELF':continue
  text=subprocess.check_output(['readelf','-h','-d','-n',str(f)],text=True,stderr=subprocess.STDOUT)
  art.append({'path':str(f.relative_to(b)),'sha256':sha(f),'size':f.stat().st_size,'type':re.findall(r'Type:\s+(.*)',text),'build_id':re.findall(r'Build ID: ([a-f0-9]+)',text),'soname':re.findall(r'Library soname: \[(.*?)\]',text),'needed':re.findall(r'Shared library: \[(.*?)\]',text),'rpath':re.findall(r'Library rpath: \[(.*?)\]',text),'runpath':re.findall(r'Library runpath: \[(.*?)\]',text)})
receipt=json.loads((root/'manifests/staged.json').read_text());identity=[]
for path,v in receipt.items():
 f=Path(path);a=Path(v['source']);assert f.read_bytes()==a.read_bytes();assert sha(f)==v['sha256'];identity.append({'prefix':path,'build':str(a),'sha256':v['sha256'],'status':'PASS_BYTE_IDENTICAL'})
(p/'reports/artifacts.json').write_text(json.dumps({'ELFs':art,'build_prefix_identity':identity,'receipt':receipt},indent=2)+'\n')
count=0
for f in (old/'work/config-01/src').rglob('*'):
 if not f.is_file():continue
 expected=f.read_bytes()
 if f.name=='CMakeLists.txt':expected=expected.replace(str(old).encode(),str(p).encode())
 assert (root/'src'/f.relative_to(old/'work/config-01/src')).read_bytes()==expected;count+=1
oldart=json.loads((old/'reports/artifacts.json').read_text())
for x in oldart['elfs']:assert sha(b/x['path'])==x['sha256']
traces={}
for c in ['probe','dart','physics','sim','harness']:
 f=root/'logs'/f'{c}.trace.jsonl'
 if not f.exists():continue
 rows=[json.loads(l) for l in f.read_text().splitlines()];n=sum(x.get('cmd')=='try_run' for x in rows)
 if c in ['probe','dart']:assert n==0
 traces[c]={'sha256':sha(f),'try_run_count':n}
links=json.loads((p/'reports/header_overlay.json').read_text())
for x in links:assert Path(x['path']).resolve()==Path(x['source']).resolve() and sha(Path(x['path']))==x['sha256']
(p/'reports/preservation.json').write_text(json.dumps({'source_files_equal_after_path_relocation':count,'previous_ELF_hashes_preserved':True,'traces':traces,'overlay_links_checked':len(links),'guard_sha256':{'previous':sha(old/'inputs/compile_gate.py'),'current':sha(p/'inputs/compile_gate.py')},'input_hashes':{str(f.relative_to(b)):sha(f) for f in (p/'inputs').rglob('*') if f.is_file() and not f.is_symlink()}},indent=2)+'\n')
print(json.dumps({'ELF_count':len(art),'identical_staged_ELFs':len(identity),'sources_preserved':count},indent=2))
