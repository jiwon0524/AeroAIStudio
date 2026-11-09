"""Static artifact/header receipts and preservation; no loading or execution."""
from pathlib import Path
import json,hashlib,shlex,subprocess,importlib.util,sys
R=Path(__file__).resolve().parents[1];B=R.parents[1];N=B/'validation/gazebo-joint-native-resource-v1'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
m=json.loads((R/'reports/manifest.json').read_text());old=json.loads((N/'reports/deployment_receipt.json').read_text())
for path,row in old['ELFs'].items():assert sha(path)==row['sha256'],path
sdk=json.loads((N/'work/header_manifest.json').read_text());headers={};errors=[]
for dep in [R/'work/SimulationRunner.d',R/'work/Physics.d',R/'work/harness.d']:
 for item in shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1]):
  p=Path(item);p=p if p.is_absolute() else N/'work/build/sim'/p;p=p.resolve();value=sha(p);headers[str(p)]=value
  if p.is_relative_to(R/'work/src/sim'):
   rel=p.relative_to(R/'work/src/sim')
   if str(rel) not in ('src/SimulationRunner.cc','src/systems/physics/Physics.cc'):assert value==sha(N/'work/src/sim'/rel),p
  elif p.is_relative_to(R/'inputs'):pass
  elif sdk.get(str(p))!=value:errors.append(str(p))
assert not errors,errors
files={}
for role in ('harness','physics'):
 path=m['roles'][role];files[role]=m['elfs'][path]
path=str(R/'work/prefix/lib/libgz-sim8.so.8.15.0');files['sim']=m['elfs'][path]
for role,row in files.items():
 text=subprocess.check_output(['/usr/bin/readelf','-dW',row['source']],text=True)
 assert '(RPATH)' not in text and str(R/'work/prefix/lib')==row['runpath'][0].split(':')[0]
assert len({x['sha256'] for x in files.values()})==3
# Reuse the existing preservation checker, but write only a new phase report.
p=B/'validation/gazebo-joint-resource-gate-v1/scripts/verify_inputs.py';spec=importlib.util.spec_from_file_location('preserve_current',p);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);mod.BASE=R;mod.main()
report=dict(status='PASS_STATIC_DEPLOYMENT_CONTRACT_NO_EXECUTION',new_ELFs=files,reused_native_ELFs={p:row['sha256'] for p,row in old['ELFs'].items()},patch_sha256=sha(R/'inputs/ready_order.patch'),source_changes={rel:sha(R/'work/src/sim'/rel) for rel in ['src/SimulationRunner.cc','src/systems/physics/Physics.cc']},new_inputs={str(p.relative_to(R)):sha(p) for p in (R/'inputs').iterdir() if p.is_file()},headers=len(headers),headers_sha256=hashlib.sha256(json.dumps(headers,sort_keys=True).encode()).hexdigest(),object_reuse_sha256=sha(R/'reports/object_reuse.json'),manifest_sha256=sha(R/'reports/manifest.json'),canonical_manifest_sha256=(R/'inputs/manifest.sha256').read_text().strip(),mounts=len(m['mounts']),FD_sources=len(m['fd_sources']),ELF_aliases=len(m['elfs']),required_mappings=len(m['required_canonical_mappings']),code_files=len(m['code']),runtime_deployed=False,original_prefix_modified=False,actual_plan_modified=False,actual_runtime='UNVERIFIED',stage_b='BLOCKED',risk_acceptance='UNDECIDED',historical_tests={str(p):{'sha256':sha(p),'case_count':len(json.loads(p.read_text())['cases']),'rerun':False} for p in [B/'validation/gazebo-joint-resource-gate-v1/reports/tests.json',N/'reports/tests.json']})
(R/'reports/deployment_receipt.json').write_text(json.dumps(report,indent=2)+'\n');(R/'work/header_manifest.json').write_text(json.dumps(headers,indent=2)+'\n');print('PASS deployment receipt; new ELFs3, headers',len(headers))
