from pathlib import Path
import json,hashlib,subprocess
b=Path.cwd();p=b/'validation/gazebo-joint-harness-fix-v1';r=b/'validation/gazebo-joint-codegen-fix-v1';root=r/'work/config-01'
def sha(f):return hashlib.sha256(Path(f).read_bytes()).hexdigest()
receipt=json.loads((root/'manifests/staged.json').read_text());assert len(receipt)==13
for path,row in receipt.items():assert sha(path)==sha(row['source'])==row['sha256'],path
old=json.loads((b/'validation/gazebo-joint-feature-fix-v1/reports/elf_and_receipt.json').read_text())['build_prefix_pairs'];assert receipt=={x['path']:{k:v for k,v in x.items() if k!='path'} for x in old}
link=b/'libgz-physics-dartsim-plugin.so';assert link.is_symlink() and not link.exists();st=link.lstat()
main=Path('/home/jiwon/Projects/AeroAIStudio');status=subprocess.check_output(['git','-C',str(main),'status','--porcelain=v1','-z']);files=[]
for row in status.split(b'\x00'):
 if not row:continue
 name=row[3:].decode();f=main/name
 if f.is_file() and not f.is_symlink():files.append({'path':name,'sha256':sha(f)})
inputs=[r/'inputs/compile_gate.py',r/'inputs/toolchain.cmake',r/'work/selected_files.json',root/'logs/harness.trace.jsonl',root/'manifests/staged.json',r/'inputs/harness.cc',r/'inputs/fixture.hh',r/'inputs/fixture.sdf.in',b/'validation/gazebo-joint-feature-fix-v1/logs/harness.selection.log']
record={'status':'PASS','receipt_pairs':receipt,'fixed_inputs':{str(f):sha(f) for f in inputs},'root_symlink':{'target':str(link.readlink()),'inode':st.st_ino,'mtime_ns':st.st_mtime_ns},'main':{'head':subprocess.check_output(['git','-C',str(main),'rev-parse','HEAD'],text=True).strip(),'status_hex':status.hex(),'dirty_regular_files':files}}
(p/'reports/preflight.json').write_text(json.dumps(record,indent=2)+'\n');print('PASS13 reused receipt pairs, fixed input preservation baseline and main dirty hashes')
