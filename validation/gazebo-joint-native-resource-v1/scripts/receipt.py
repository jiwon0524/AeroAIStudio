"""Static deployment proposal and source/ELF receipts. No dynamic loading."""
from pathlib import Path
import json,hashlib,subprocess,re,difflib,xml.etree.ElementTree as ET
from collections import Counter
R=Path(__file__).resolve().parents[1];B=R.parents[1];old=B/'validation/gazebo-joint-codegen-fix-v1';prefix=R/'work/prefix'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def identity(p):
 p=Path(p).resolve();s=p.stat();return dict(source=str(p),sha256=sha(p),device=s.st_dev,inode=s.st_ino,size=s.st_size)
patch=[];sources=[]
for component,original in [('sim',old/'work/config-01/src/sim'),('sdformat',R/'work/sdformat-sdformat14_14.9.0')]:
 for p in (R/'work/src'/component).rglob('*'):
  if not p.is_file() or p.is_symlink():continue
  relative=p.relative_to(R/'work/src'/component);before=original/relative
  if not before.is_file() or sha(before)==sha(p):continue
  name=str(Path(component)/relative)
  patch.extend(difflib.unified_diff(before.read_text().splitlines(True),p.read_text().splitlines(True),fromfile=name,tofile=name,n=0))
  sources.append(dict(path=name,before=sha(before),after=sha(p)))
(R/'inputs/native.patch').write_text(''.join(patch))
(R/'reports/source_receipt.json').write_text(json.dumps(dict(status='STATIC_SOURCE_BINDING',archive=identity(R/'work/sdformat.tar.gz'),url='https://codeload.github.com/gazebosim/sdformat/tar.gz/refs/tags/sdformat14_14.9.0',patch_sha256=sha(R/'inputs/native.patch'),files=sources),indent=2)+'\n')
plan=json.loads((B/'validation/gazebo-joint-resolution-v1/reports/actual_plan.json').read_text());c=json.loads((B/'validation/gazebo-joint-resource-gate-v1/reports/resource_contract.json').read_text())
mounts=dict(plan['mounts']);changed={}
# Overlay source only in a future namespace; never replace the existing host files.
replacements={str(Path(c['schema']['provider_candidates'].keys().__iter__().__next__())):prefix/'lib/libsdformat14.so.14.9.0',plan['payload'][1]:R/'work/aero-joint-harness-native',plan['payload'][2]:prefix/'lib/gz-sim-8/plugins/libgz-sim8-physics-system.so.8.15.0'}
for dest,row in plan['mounts'].items():
 if Path(dest).name=='libgz-sim8.so.8.15.0':replacements[dest]=prefix/'lib/libgz-sim8.so.8.15.0'
# Every old alias backed by the replaced ELF must map to the new identity too.
for dest,row in plan['mounts'].items():
 for canonical,p in replacements.items():
  if row['source']==plan['mounts'].get(canonical,{}).get('source'):
   changed[dest]=identity(p);mounts[dest]=dict(changed[dest],real_path=str(p.resolve()),kind='NATIVE_CANDIDATE_RO')
new_files={p.resolve() for p in (prefix/'lib').rglob('*') if p.is_file() and not p.is_symlink() and p.read_bytes()[:4]==b'\x7fELF'}
new_files.add(R/'work/aero-joint-harness-native')
p=R/'work/aero-joint-harness-native';changed[str(p)]=identity(p);mounts[str(p)]=dict(changed[str(p)],real_path=str(p.resolve()),kind='NATIVE_CANDIDATE_RO')
elfs={}
for p in sorted(new_files):
 text=subprocess.check_output(['/usr/bin/readelf','-dW','-n',str(p)],text=True)
 elfs[str(p)]={**identity(p),'build_id':re.findall(r'Build ID: ([0-9a-f]+)',text),'needed':re.findall(r'Shared library: \[(.*?)\]',text),'runpath':re.findall(r'\(RUNPATH\).*?\[(.*?)\]',text)}
 assert 'libaero-resource.so' in elfs[str(p)]['needed'] or p.name=='libaero-resource.so'
 assert '(RPATH)' not in text
 if p.name!='libaero-resource.so':assert elfs[str(p)]['runpath'][0].split(':')[0]==str(prefix/'lib')
# Add new-prefix ELF aliases as RO mount candidates for the new RUNPATH.
for p in (prefix/'lib').rglob('*'):
 if p.is_file() and p.resolve() in new_files:changed[str(p)]=identity(p);mounts[str(p)]=dict(changed[str(p)],real_path=str(p.resolve()),kind='NATIVE_CANDIDATE_RO')
expected={}
for row in json.loads((R/'reports/identities.json').read_text()):expected[row['name']]=[row['sha256'],row['device'],row['inode']]
config=c['config']['mount'];expected['server_config']=[config['sha256'],config['device'],config['inode']]
for role,dest,p in [('physics',plan['payload'][2],prefix/'lib/gz-sim-8/plugins/libgz-sim8-physics-system.so.8.15.0'),('dartsim',plan['payload'][3],Path(plan['payload'][3]))]:
 x=identity(p);expected[role]=expected[role+'_provider']=[x['sha256'],x['device'],x['inode']]
expected['world_bytes']=[c['world']['rendered_reference']['sha256'],0,0]
paths={p.name:p for p in Path('/usr/share/sdformat14/1.11').glob('*.sdf')}
def walk(n,stack=()):
 assert n not in stack
 result=Counter({n:1})
 for e in ET.parse(paths[n]).iter('include'):
  if 'filename' in e.attrib:result.update(walk(e.attrib['filename'],stack+(n,)))
 return result
closure=walk('root.sdf')
contract=dict(status='UNSEALED_NATIVE_CANDIDATE_NO_LAUNCH',expected=expected,schema_closure=['schema/'+n for n in sorted(closure)],schema_root_unique=len(closure),schema_root_recursive_reads=sum(closure.values()),schema_root_includes=sum(closure.values())-1,unchanged_inventory=[129,135],runtime_verified=False)
(R/'reports/native_contract.json').write_text(json.dumps(contract,indent=2)+'\n')
receipt=dict(status='PASS_COMPILE_LINK_STATIC_CANDIDATE_ONLY',ELFs=elfs,RO_mount_replacements=changed,original_plan_sha256=sha(B/'validation/gazebo-joint-resolution-v1/reports/actual_plan.json'),actual_plan_changed=False,original_binary_changed=False,source_patch_sha256=sha(R/'inputs/native.patch'),deployment='PROPOSED_NAMESPACE_OVERLAYS_ONLY_NOT_APPLIED',subject_execution=False)
(R/'reports/deployment_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
(R/'reports/candidate_mounts.json').write_text(json.dumps(dict(status='UNSEALED_NO_LAUNCH',mounts=mounts),indent=2)+'\n')
receipt['candidate_mounts_sha256']=sha(R/'reports/candidate_mounts.json')
receipt['native_contract_sha256']=sha(R/'reports/native_contract.json')
(R/'reports/deployment_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print('PASS static source/ELF receipts',len(sources),'source patches',len(elfs),'new ELF files;',len(changed),'RO candidate aliases; root',len(closure),'unique',sum(closure.values()),'reads')
