"""Verify the prepared inputs without configuring/loading target code."""
from pathlib import Path
import json,hashlib,subprocess
base=Path.cwd();prepared=base/'validation/gazebo-joint-closure-v1';out=base/'validation/gazebo-joint-build-v1/reports';issues=[];counts={};seen={}
def check(path,sha,group,mode=None):
 p=Path(path);p=p if p.is_absolute() else base/p
 counts[group]=counts.get(group,0)+1
 if not p.is_file():issues.append({'group':group,'path':str(p),'error':'MISSING'});return
 key=str(p)
 actual=seen.get(key)
 if actual is None:actual=hashlib.sha256(p.read_bytes()).hexdigest();seen[key]=actual
 if actual!=sha:issues.append({'group':group,'path':str(p),'error':'HASH_MISMATCH','expected':sha,'actual':actual})
 if mode is not None and oct(p.stat().st_mode&0o777)!=mode:issues.append({'group':group,'path':str(p),'error':'MODE_MISMATCH'})
for name in ['input_files.json','reuse_files.json','local_inventory_index.json']:
 for row in json.loads((prepared/'reports'/name).read_text()):check(row['path'],row['sha256'],name,row.get('mode'))
plan=json.loads((prepared/'reports/source_plan.json').read_text())
for row in plan['sources']:check(row['archive'],row['sha256'],'source_archives')
for name,sha in plan['patch_sha256'].items():check(name,sha,'patches')
for row in json.loads((base/'validation/gazebo-joint-inputs-v1/reports/packages.json').read_text()):check(row['archive'],row['sha256'],'18_package_archives')
for row in json.loads((base/'validation/gazebo-joint-inputs-v1/reports/toolchain_files.json').read_text()):check(row['path'],row['sha256'],'toolchain_files')
for row in json.loads((base/'validation/gazebo-joint-inputs-v1/reports/tool_elf_closure.json').read_text())['files']:check(row['path'],row['sha256'],'toolchain_ELF_closure')
for path,row in json.loads((prepared/'work/selected_files.json').read_text()).items():check(path,row['sha256'],'selected_dependency_files')
config=prepared/'work/config-01'
for sub in ['src','build','prefix']:
 p=config/sub
 if p.exists() and any(p.iterdir()):issues.append({'group':'fresh_layout','path':str(p),'error':'NONEMPTY_PRESERVE_AND_STOP'})
head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip();branch=subprocess.check_output(['git','branch','--show-current'],text=True).strip();status=subprocess.check_output(['git','status','--porcelain'],text=True)
if head!='e272b2a8a6de5b517e888ad1b03c6991992efb36' or branch!='experiment/dart-internal-trace' or status:issues.append({'group':'git','error':'UNEXPECTED_HEAD_BRANCH_OR_DIRTY'})
main='/home/jiwon/Projects/AeroAIStudio';snapshot={'head':subprocess.check_output(['git','-C',main,'rev-parse','HEAD'],text=True).strip(),'status':subprocess.check_output(['git','-C',main,'status','--porcelain'],text=True)}
(out/'main_before.json').write_text(json.dumps(snapshot,indent=2)+'\n')
report={'head':head,'branch':branch,'status':'PASS' if not issues else 'BLOCKED_BEFORE_BUILD','counts':counts,'unique_hashed_files':len(seen),'issues':issues,'method':'SHA-256/file mode/Git/empty layout checks only; no compiler/loader/target execution'}
(out/'input_verification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(1 if issues else 0)
