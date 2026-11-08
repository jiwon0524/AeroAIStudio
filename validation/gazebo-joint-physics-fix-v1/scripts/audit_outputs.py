"""Future post-link static guard, no loader/ldd. Missing outputs are rejection."""
from pathlib import Path
import hashlib,json,re,subprocess,sys
r=Path(__file__).resolve().parents[1];root=r/'work/config-01';base=r.parents[1]
component=sys.argv[1];build=root/'build'/component;prefix=root/'prefix';deps=r/'work/deps/usr/lib/x86_64-linux-gnu'
lock=json.loads((r/'work/selected_files.json').read_text())
allowed={str(Path(p).resolve()):v['sha256'] for p,v in lock.items()}
for x in json.loads((base/'validation/gazebo-joint-inputs-v1/reports/tool_elf_closure.json').read_text())['files']:allowed[x['path']]=x['sha256']
expected={'probe':['aero-joint-probe'],'dart':['dart','dart-external-odelcpsolver','dart-collision-ode','dart-collision-bullet','dart-utils','dart-utils-urdf'],'physics':['gz-physics7','gz-physics7-dartsim-plugin'],'sim':['gz-sim8','gz-sim8-physics-system'],'harness':[]}[component]
outputs={};selected=[]
for name in expected:
 hits={p.resolve() for p in build.rglob('lib'+name+'.so*') if p.is_file()}
 if len(hits)!=1:raise SystemExit('BLOCKED missing/ambiguous output '+name)
 p=hits.pop();selected.append(p)
 text=subprocess.check_output(['readelf','-d',str(p)],text=True)
 soname=re.findall(r'Library soname: \[(.*?)\]',text)
 if len(soname)!=1:raise SystemExit('BLOCKED missing SONAME '+str(p))
 outputs[soname[0]]=p
if component=='harness':
 p=build/'aero-joint-harness'
 if not p.is_file():raise SystemExit('BLOCKED missing harness')
 selected.append(p)
staged_path=root/'manifests/staged.json'
staged=json.loads(staged_path.read_text()) if staged_path.exists() else {}
reused=json.loads((root/'manifests/reused_elfs.json').read_text())
reuse_prefix=Path(json.loads((r/'reports/dart_reuse.json').read_text())['original_prefix_runpath_retained']).resolve()
queue=selected[:];seen={};errors=[]
while queue:
 p=queue.pop().resolve()
 if str(p) in seen:continue
 reuse_sha=reused.get(str(p))
 if reuse_sha and hashlib.sha256(p.read_bytes()).hexdigest()!=reuse_sha:errors.append('reused predecessor changed '+str(p));continue
 own=p.is_relative_to(build) or p.is_relative_to(prefix) or bool(reuse_sha)
 if p.is_relative_to(build) and p not in selected:errors.append('unplanned built dependency '+str(p));continue
 if p.is_relative_to(prefix) and staged.get(str(p),{}).get('sha256')!=hashlib.sha256(p.read_bytes()).hexdigest():errors.append('unrecorded staged dependency '+str(p));continue
 if not own:
  if re.match(r'lib(?:dart|gz-physics7|gz-sim8)',p.name):errors.append('installed stack '+str(p));continue
  if allowed.get(str(p))!=hashlib.sha256(p.read_bytes()).hexdigest():errors.append('unlocked ELF '+str(p));continue
 text=subprocess.check_output(['readelf','-d','-n',str(p)],text=True)
 search=[]
 for path in re.findall(r'Library (?:rpath|runpath): \[(.*?)\]',text):
  if own and any(not x for x in path.split(':')):errors.append('empty owned RUNPATH '+str(p))
  search.extend(Path(x.replace('${ORIGIN}',str(p.parent)).replace('$ORIGIN',str(p.parent))) for x in path.split(':') if x)
 if own and any(not (d.resolve().is_relative_to(prefix) or d.resolve().is_relative_to((r/'work/deps').resolve()) or (reuse_sha and d.resolve()==reuse_prefix)) for d in search):errors.append('unexpected owned output RPATH '+str(p))
 needed=re.findall(r'Shared library: \[(.*?)\]',text);edges=[]
 for soname in needed:
  candidates=[d/soname for d in search+[prefix/'lib',deps,Path('/usr/lib/x86_64-linux-gnu'),Path('/lib/x86_64-linux-gnu'),Path('/usr/lib')] if (d/soname).is_file()]
  target=outputs.get(soname) or (candidates[0] if candidates else None)
  if target is None:errors.append('unresolved '+soname+' from '+str(p));continue
  edges.append({'soname':soname,'path':str(target.resolve())});queue.append(target)
 seen[str(p)]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'build_id':re.findall(r'Build ID: ([a-f0-9]+)',text),'needed':edges}
print(json.dumps({'status':'BLOCKED' if errors else 'PASS_STATIC_OUTPUT_CLOSURE','component':component,'errors':errors,'files':seen,'scope':'selected outputs and staged predecessor identity; not proof of actual loader selection/mapping'},indent=2))
raise SystemExit(1 if errors else 0)
