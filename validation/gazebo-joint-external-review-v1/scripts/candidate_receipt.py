"""Static candidate deployment delta; cannot grant execution authority."""
from pathlib import Path
import hashlib,json,subprocess
R=Path(__file__).resolve().parents[1];B=R.parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
old=B/'validation/gazebo-joint-execution-contract-v1'
m=json.loads((old/'reports/manifest.json').read_text())
r=json.loads((R/'reports/build_receipt.json').read_text())
original=B/'validation/gazebo-joint-header-fix-v1/work/config-01/build/dart/lib/libdart-collision-ode.so.6.13.2'
assert sha(original)==m['mounts'][m['roles']['dart_ode']]['sha256']
obj=R/'work/OdeCollisionDetector.o'
asm=subprocess.check_output(['objdump','-drC',str(obj)],text=True)
assert 'dInitODE2' in asm and 'dAllocateODEDataForThread' in asm and 'dWorldCreate' in asm
assert asm.count('R_X86_64_PLT32\taero_resource::Fail(char const*)')==3
(R/'work/ode_init.asm').write_text(asm)
target=r['elf']['path']
delta=dict(status='CANDIDATE_ONLY_NOT_RELEASED',prior_manifest_sha256=sha(old/'reports/manifest.json'),
  mappings=[dict(namespace=k,old_identity=v,new_backing=r['elf']) for k,v in m['mounts'].items() if v['source']==m['mounts'][m['roles']['dart_ode']]['source']],
  new_needed_dependency=r['native_observer'],original_deployed_matches_reused_build=True,
  checks=dict(init_failure_calls_in_compiled_object=3,unchanged_export_names=r['export_names_unchanged']),
  pending=['External ODE/crypto/transport/teardown pre-access coverage','Reseal full candidate ELF/SONAME/provider/allowlist/attestor projections only after closure review'],
  ready_go_exit_policy='Unchanged; native fatal always fails, including after EXIT_ACK.',
  stage_b='BLOCKED',risk_acceptance='UNDECIDED',runtime='UNVERIFIED')
raw=(json.dumps(delta,sort_keys=True,separators=(',',':'))+'\n').encode()
(R/'reports/candidate_deployment.json').write_text(json.dumps(delta,indent=2)+'\n')
(R/'reports/candidate_deployment.sha256').write_text(hashlib.sha256(raw).hexdigest()+'\n')
print('Candidate delta sealed; 2 aliases remain undeployed; 3 compiled failure callsites checked')
