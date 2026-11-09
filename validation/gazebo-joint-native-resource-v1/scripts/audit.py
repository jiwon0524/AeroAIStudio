from pathlib import Path
import json,hashlib,re,subprocess,shlex
R=Path(__file__).resolve().parents[1];B=R.parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
mounts=json.loads((R/'reports/candidate_mounts.json').read_text())['mounts'];receipt=json.loads((R/'reports/deployment_receipt.json').read_text());old=json.loads((B/'validation/gazebo-joint-resolution-v1/reports/actual_plan.json').read_text())
queue=list(receipt['ELFs'])+old['payload'];seen={};errors=[]
while queue:
 dest=queue.pop()
 if dest in seen:continue
 row=mounts.get(dest)
 if not row:errors.append('unmounted ELF '+dest);continue
 p=Path(row['source']);assert sha(p)==row['sha256']
 text=subprocess.check_output(['/usr/bin/readelf','-dW',str(p)],text=True);paths=[]
 for value in re.findall(r'\(RUNPATH\).*?\[(.*?)\]',text):paths+=value.split(':')
 deps={}
 for name in re.findall(r'Shared library: \[(.*?)\]',text):
  choices=[str(Path(d)/name) for d in paths+['/lib/x86_64-linux-gnu','/usr/lib/x86_64-linux-gnu','/lib','/usr/lib']]
  target=next((x for x in choices if x in mounts),None)
  if target is None:
   # Reuse a previously pinned required edge only for an unchanged consumer.
   original=old['candidate_elfs'].get(str(p))
   edge=next((e for e in old['edges'] if e['consumer']==str(p) and e['soname']==name),None)
   if original and sha(p)==original['sha256'] and edge and edge['mount'] in mounts and mounts[edge['mount']]['source']==edge['provider']:
    target=edge['mount']
  if target is None:errors.append('unresolved '+name+' from '+dest)
  else:deps[name]=target;queue.append(target)
 seen[dest]=dict(source=str(p),sha256=sha(p),needed=deps)
# Link-time native hook symbols must exist in the built observation DSO.
native=R/'work/prefix/lib/libaero-resource.so';exports=subprocess.check_output(['/usr/bin/nm','-D',str(native)],text=True)
exported={l.split()[-1] for l in exports.splitlines() if len(l.split())==3 and l.split()[1]!='U'}
for path in receipt['ELFs']:
 syms=subprocess.check_output(['/usr/bin/nm','-D',path],text=True)
 for line in syms.splitlines():
  if ' U ' in line and 'aero_resource' in line:assert line.split()[-1] in exported
headers={}
for log in (R/'logs').glob('headers-*.json'):headers.update(json.loads(log.read_text()))
for dep in [R/'work/native_resource.d',R/'work/harness_native.d']:
 for f in shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1]):
  p=Path(f).resolve();headers[str(p)]=sha(p)
assert not any(p.startswith('/usr/local/') for p in headers)
# Verify downloaded sources against all four previously reviewed sdformat files.
source_reuse={}
for name in ['parser.cc','Root.cc','SDF.cc','Converter.cc']:
 oldp=B/'validation/gazebo-joint-resource-gate-v1/work/source'/name;p=R/'work/sdformat-sdformat14_14.9.0/src'/name
 assert sha(p)==sha(oldp);source_reuse[name]=sha(p)
report=dict(status='PASS_STATIC_REQUIRED_EDGE_CLOSURE' if not errors else 'BLOCKED_STATIC_CLOSURE',errors=errors,ELFs=seen,header_count=len(headers),header_manifest_sha256=hashlib.sha256(json.dumps(headers,sort_keys=True).encode()).hexdigest(),reviewed_source_reuse=source_reuse,compiler_sha256=sha('/usr/bin/x86_64-linux-gnu-g++-13'),toolchain_sha256=sha(R/'inputs/toolchain.cmake'),native_symbol_binding=True,execution=False)
(R/'reports/static_audit.json').write_text(json.dumps(report,indent=2)+'\n');(R/'work/header_manifest.json').write_text(json.dumps(headers,indent=2)+'\n')
print(report['status'],len(seen),'ELF paths',len(headers),'headers',len(errors),'errors')
if errors:print('\n'.join(errors))
raise SystemExit(bool(errors))
