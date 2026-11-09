"""Generate one ordered, hash/FD-bound contract. No namespace/service invocation."""
from pathlib import Path
import json,os,re,subprocess,hashlib,sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import contract as C
R=C.R;B=C.ROOT;N=B/'validation/gazebo-joint-native-resource-v1';prior=B/'validation/gazebo-joint-resolution-v1'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def desc(p):
 p=Path(p).resolve(strict=True);s=p.stat();return dict(source=str(p),real_path=str(p),sha256=sha(p),device=s.st_dev,inode=s.st_ino,mode='ro-file-fd')
def meta(p):
 text=subprocess.check_output(['/usr/bin/readelf','-dW','-n',str(p)],text=True)
 return dict(build_id=re.search(r'Build ID: (\w+)',text)[1],needed=re.findall(r'Shared library: \[(.*?)\]',text),soname=re.findall(r'Library soname: \[(.*?)\]',text),runpath=re.findall(r'\(RUNPATH\).*?\[(.*?)\]',text))
old=json.loads((prior/'reports/actual_plan.json').read_text());receipt=json.loads((N/'reports/deployment_receipt.json').read_text());native=json.loads((N/'reports/native_contract.json').read_text());candidate=json.loads((N/'reports/candidate_mounts.json').read_text())['mounts']
assert sha(N/'reports/candidate_mounts.json')==receipt['candidate_mounts_sha256']
assert sha(N/'reports/native_contract.json')==receipt['native_contract_sha256']
mounts={d:dict(desc(row['source'])) for d,row in candidate.items()}
# Freshly check old candidate identities rather than silently updating a drifted inode.
for d,row in candidate.items():assert all(mounts[d][k]==row[k] for k in ['sha256','device','inode']),d
newcore=R/'work/prefix/lib/libgz-sim8.so.8.15.0';newphysics=R/'work/prefix/lib/libgz-sim8-physics-system.so.8.15.0';newexe=R/'work/aero-joint-harness'
replace={str(N/'work/prefix/lib/libgz-sim8.so.8.15.0'):newcore,str(N/'work/prefix/lib/libgz-sim8-physics-system.so.8.15.0'):newphysics,str(N/'work/prefix/lib/gz-sim-8/plugins/libgz-sim8-physics-system.so.8.15.0'):newphysics,str(N/'work/aero-joint-harness-native'):newexe}
# Use only new harness logical pathname; old ACK/native harness aliases disappear.
for d in list(mounts):
 src=mounts[d]['source']
 if src==str(N/'work/aero-joint-harness-native'):del mounts[d]
 elif src in replace:mounts[d]=desc(replace[src])
for p in (R/'work/prefix/lib').iterdir():mounts[str(p)]=desc(p)
mounts[str(newexe)]=desc(newexe)
elfs={}
for d,row in mounts.items():
 p=Path(row['source'])
 if p.read_bytes()[:4]==b'\x7fELF':
  row.update(meta(p));elfs[d]=dict(row)
roles=dict(harness=str(newexe),physics=old['payload'][2],dartsim=old['payload'][3],native=str(N/'work/prefix/lib/libaero-resource.so'),sdformat=str(N/'work/prefix/lib/libsdformat14.so.14.9.0'),dart=next(x for x in old['required_canonical_mappings'] if x.endswith('/libdart.so.6.13.2')),dart_ode=old['ode_provider'],ode=next(x for x in old['required_canonical_mappings'] if x.endswith('/libode.so.8.0.2')),odelcp=next(x for x in old['required_canonical_mappings'] if x.endswith('/libdart-external-odelcpsolver.so.6.13.2')),probe=next(x for x in old['required_canonical_mappings'] if x.endswith('/libaero-joint-probe.so.1.0')))
for name in ['physics','physics_provider']:
 row=elfs[roles['physics']];native['expected'][name]=[row['sha256'],row['device'],row['inode']]
native['status']='STATIC_BOUND_NO_RUNTIME_APPROVAL'
# Existing unchanged consumers retain exact verified predecessor edge selection.
oldedges={(e['consumer'],e['soname']):e for e in old['edges']};edges=[]
for d,row in elfs.items():
 for needed in row['needed']:
  paths=[str(Path(p)/needed) for path in row['runpath'] for p in path.split(':')]+['/usr/lib/x86_64-linux-gnu/'+needed,'/lib/x86_64-linux-gnu/'+needed]
  target=next((x for x in paths if x in elfs),None)
  if target is None:
   edge=oldedges.get((row['source'],needed));assert edge and edge['mount'] in elfs,(d,needed)
   original=old['candidate_elfs'][row['source']];assert row['sha256']==original['sha256'];target=edge['mount']
  edges.append(dict(consumer=d,soname=needed,mount=target,provider=elfs[target]['source']))
# Pin all actual import support, never an ambient old attestor/plan search path.
code={};todo=list((R/'scripts').glob('*.py'))
while todo:
 p=todo.pop().resolve()
 if str(p) in code:continue
 code[str(p)]=desc(p);text=p.read_text()
 for match in re.findall(r"['\"](validation/[^'\"]+\.py)['\"]",text):
  f=B/match
  if f.is_file():todo.append(f)
 # Recursive local imports in pinned reused helpers resolve against new scripts
 # first; their common module is deliberately the new phase's common.py.
 for mod in re.findall(r'^from (\w+) import|^import (\w+)\s*$',text,re.M):
  name=next(x for x in mod if x);f=R/'scripts'/(name+'.py')
  if f.is_file():todo.append(f)
for relative in ['validation/dart-probe-a-harness-v1/scripts/identity.py','validation/dart-probe-a-harness-v1/scripts/mapped.py']:code[str(B/relative)]=desc(B/relative)
required=[str(newexe) if p==old['payload'][1] else p for p in old['required_canonical_mappings']]
required=list(dict.fromkeys(required+list(roles.values())))
forbidden=set(replace)
for p,row in old['candidate_elfs'].items():
 if Path(p).name.startswith(('libgz-sim8','libsdformat14')) or p==old['payload'][1]:forbidden.add(p)
# No new native observer/sdformat/dartsim/DART/ODE build; reused hashes must match.
for p,row in receipt['ELFs'].items():assert sha(p)==row['sha256'],p
sources_report=json.loads((R/'reports/source_paths.json').read_text())
outputs=[str(R/'reports/joint_runtime'),str(R/'reports/joint_integrity.json')];markers=[str(R/'work/joint_collection_once.json'),str(R/'work/joint_stage_once.json')]
evidence={str(p):desc(p) for p in [N/'reports/native_contract.json',N/'reports/deployment_receipt.json',N/'reports/source_receipt.json',R/'reports/source_paths.json',R/'inputs/ready_order.patch',R/'inputs/plugin_expectations.hh']}
for path in sources_report['paths']:
 for row in path['evidence']:
  p=Path(row['path']);assert sha(p)==row['sha256'];evidence[str(p)]=desc(p)
for p in [*list((R/'inputs').glob('*.hh')),*list((R/'inputs').glob('*.h')),*list((R/'inputs').glob('*.cc')),R/'reports/object_reuse.json',R/'reports/build_steps.json',R/'reports/harness_commands.json',B/'validation/gazebo-joint-header-fix-v1/work/config-01/build/dart/compile_commands.json',B/'validation/gazebo-joint-physics-fix-v1/work/config-01/build/physics/compile_commands.json']:
 evidence[str(p)]=desc(p)
m=dict(schema=1,profile='actual',status='SEALED_STATIC_INPUTS_RESOURCE_BLOCKED',stage_b='BLOCKED',risk_acceptance='UNDECIDED',actual_runtime='UNVERIFIED',roles=roles,payload=[old['payload'][0],str(newexe),roles['physics'],roles['dartsim']],mounts=mounts,elfs=elfs,soname_edges=edges,required_canonical_mappings=required,engine_provider=roles['dartsim'],ode_provider=roles['dart_ode'],native=native,implementation={k:str(R/'scripts'/(k+'.py')) for k in ['launcher','collector','attestor','stage','contract']},code=code,evidence=evidence,host_tools={p:desc(p) for p in old['host_tools']},forbidden_backings=sorted(forbidden),preserved_contracts={str(p):sha(p) for p in [prior/'reports/actual_plan.json',N/'reports/native_contract.json',N/'reports/deployment_receipt.json',B/'validation/gazebo-joint-resource-gate-v1/reports/resource_contract.json']},ack_protocol=old['ack_protocol'],resources=old['resources'],stream_limits={'stdout_total':65536,'stdout_pending':16384,'stderr_total':1048576,'stderr_pending':65536},deadlines={'host_s':40,'collection_s':25,'ack_ms':5000},rlimits={'CPU':10,'AS':2147483648,'FSIZE':1048576,'NOFILE':256,'CORE':0},outputs=outputs,one_shot=markers,technical={'input_contract':'RESOLVED_STATIC','resource_paths':'BLOCKED'},blockers=[dict(path=x['path'],reason=x['reason']) for x in sources_report['paths'] if 'UNRESOLVED' in x['classification']])
# Derive all secondary views from the same logical namespace table.
m['allowlist_text']=C.allowlist(m);allow=R/'inputs/joint-elf.sha256';allow.write_text(m['allowlist_text']);m['mounts']['/input/joint-elf.sha256']=desc(allow)
m['provider_paths']=C.provider_paths(m)
m['fd_sources']=sorted({r['source'] for r in m['mounts'].values()});m['attestation']=C.attestation(m);m['ordered_bwrap_argv']=C.bwrap(m)
(R/'reports/manifest.json').write_bytes(C.canonical_bytes(m));(R/'inputs/manifest.sha256').write_text(C.digest(m)+'\n')
C.validate(m);print('PASS sealed static inputs:',len(m['mounts']),'RO mounts;',len(elfs),'ELF aliases;',len(code),'code inputs;',len(m['blockers']),'resource blockers')
