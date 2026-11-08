"""Static byte comparisons only; no target loading or execution."""
from pathlib import Path
import hashlib,json,subprocess
root=Path(__file__).resolve().parents[1]; project=root.parents[1]
old=project/'validation/gazebo-source-materials-v1/work/extracted/physics-upstream/gz-physics-gz-physics7_7.8.0'
new=root/'work/extracted/upstream/gz-physics-7.8.0'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
common=[]; changes=[]
for p in new.rglob('*'):
 if not p.is_file(): continue
 rel=p.relative_to(new); other=old/rel
 if other.is_file():
  row=dict(path=str(rel),sha256=sha(p),upstream_tag_sha256=sha(other))
  (common if row['sha256']==row['upstream_tag_sha256'] else changes).append(row)
headers=[]
pkg=root/'work/extracted/libgz-physics7-core-dev_7.8.0-1~noble_amd64.deb'
for p in (pkg/'usr/include').rglob('*'):
 if not p.is_file(): continue
 target=Path('/')/p.relative_to(pkg)
 headers.append(dict(path=str(target),sha256=sha(p),installed_match=target.is_file() and sha(p)==sha(target)))
elfs=[]
for pkg in (root/'work/extracted').glob('*.deb'):
 for p in pkg.rglob('*'):
  if not p.is_file() or p.is_symlink() or p.read_bytes()[:4]!=b'\x7fELF':continue
  target=Path('/')/p.relative_to(pkg)
  notes=subprocess.check_output(['readelf','-n',str(p)],text=True)
  ids=[s.split('Build ID:')[1].strip() for s in notes.splitlines() if 'Build ID:' in s]
  elfs.append(dict(path=str(target),sha256=sha(p),build_ids=ids,installed_byte_match=target.is_file() and sha(p)==sha(target)))
prior=json.loads((project/'validation/gazebo-instrumented-prestep-v1/reports/input_audit.json').read_text())
checks=[dict(path=r['path'],expected=r['actual'],match=Path(r['path']).is_file() and sha(Path(r['path']))==r['actual']) for r in prior['checks']]
main=Path('/home/jiwon/Projects/AeroAIStudio'); inv=json.loads((project/'validation/gazebo-source-observation-review-v1/reports/material_inventory.json').read_text())
main_state=dict(head_match=subprocess.check_output(['git','-C',str(main),'rev-parse','HEAD'],text=True).strip()==inv['main_head'],status_match=subprocess.check_output(['git','-C',str(main),'status','--short'],text=True)==inv['main_status'])
result=dict(release_vs_tag=dict(same_count=len(common),different=changes,release_only=[str(p.relative_to(new)) for p in new.rglob('*') if p.is_file() and not (old/p.relative_to(new)).is_file()]),headers=headers,elfs=elfs,preservation=checks,main=main_state)
(root/'reports/static_comparison.json').write_text(json.dumps(result,indent=2)+'\n')
print('release/tag same',len(common),'different',len(changes),'header match',sum(x['installed_match'] for x in headers),'/',len(headers),'ELFs',elfs,'preservation',all(x['match'] for x in checks),main_state)
