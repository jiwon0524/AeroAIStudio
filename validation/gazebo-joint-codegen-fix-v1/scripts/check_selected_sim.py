"""Rejecting static gate for the two Sim targets and generated build closure.
CMake File API and ninja -t commands are metadata only; no build or loader run.
"""
from pathlib import Path
import json,sys,hashlib,re,subprocess,shlex
r=Path(__file__).resolve().parents[1];root=r/'work/config-01';build=root/'build/sim-03'
# Reuse original hash/installed-stack rejection policy, unchanged.
policy=(r/'scripts/check_selection_broad.py').read_text().split('component=sys.argv[1];')[0]
exec(compile(policy,str(r/'scripts/check_selection_broad.py'),'exec'),globals())
checked_inputs=set();original_verify=verify
reused_elfs=json.loads((root/'manifests/reused_elfs.json').read_text())
def verify(path):
 if path in checked_inputs:return
 checked_inputs.add(path)
 real=str(Path(path).resolve())
 if real in reused_elfs:
  valid=Path(real).is_file() and hashlib.sha256(Path(real).read_bytes()).hexdigest()==reused_elfs[real]
  checked[real]=valid
  if not valid:errors.append('reused predecessor hash mismatch '+real)
  return
 original_verify(path)
rows=[json.loads(l) for l in (root/'logs/sim-03.trace.jsonl').read_text().splitlines()]
for row in rows:
 if 'file' in row:verify(row['file'])
 if row.get('cmd','').lower()=='try_run' and row.get('file')!='/usr/share/cmake/gz-cmake3/cmake3/GzCheckSSE.cmake':errors.append('unexpected try_run call')
reply=build/'.cmake/api/v1/reply';index=json.loads(next(reply.glob('index-*.json')).read_text())
model=json.loads((reply/index['reply']['codemodel-v2']['jsonFile']).read_text())
assert len(model['configurations'])==1
config=model['configurations'][0];assert config['name']=='RelWithDebInfo'
expected={'gz-sim8','gz-sim8-physics-system'}
byid={x['id']:x for x in config['targets']};byname={x['name']:x for x in config['targets']};assert expected<=byname.keys()
queue=[byname[n]['id'] for n in sorted(expected)];targets={};observations={}
while queue:
 tid=queue.pop()
 if tid in targets:continue
 info=json.loads((reply/byid[tid]['jsonFile']).read_text());name=info['name'];targets[tid]=info
 if name not in expected:errors.append('unplanned generated build dependency '+name)
 queue += [d['id'] for d in info.get('dependencies',[])]
 data={'compile_groups':info.get('compileGroups',[]),'link':info.get('link',{}),'artifacts':info.get('artifacts',[])}
 observations[name]=data
 for group in info.get('compileGroups',[]):
  for inc in group.get('includes',[]):verify(inc['path'])
  for key in ['defines','compileCommandFragments']:
   for entry in group.get(key,[]):
    value=entry.get('define',entry.get('fragment',''))
    if '$<' in value:errors.append('unresolved generated compile expression '+name)
    if re.search(r'-march=native|-mavx|-fno-rtti|-fno-exceptions|_GLIBCXX_USE_CXX11_ABI=0',value):errors.append('forbidden ABI/compiler option '+name)
 for fragment in info.get('link',{}).get('commandFragments',[]):
  value=fragment['fragment']
  if '$<' in value:errors.append('unresolved generated link expression '+name)
  for token in shlex.split(value):
   if token.startswith('/'):verify(token)
   elif token.startswith('-l') and not token.startswith('-l:'):
    namepart=token[2:];hits=[d/('lib'+namepart+ext) for d in [root/'prefix/lib',(r/'work/deps').resolve()/'usr/lib/x86_64-linux-gnu',Path('/usr/lib/x86_64-linux-gnu')] for ext in ['.so','.a']]
    hits=[f for f in hits if f.is_file()]
    if not hits and namepart=='stdc++fs':
     query=subprocess.check_output(['/usr/bin/x86_64-linux-gnu-g++-13','-print-file-name=libstdc++fs.a'],text=True).strip();hits=[Path(query)] if Path(query).is_absolute() and Path(query).is_file() else []
    if not hits:errors.append('unresolved link library '+token)
    else:verify(str(hits[0]))
# Compile configuration/header check must agree with staged generated header.
cache=(r/'reports/reused_physics_cache.txt').read_text()
if not re.search(r'^DART_HAS_CONTACT_SURFACE_HEADER:[^=]*=1$',cache,re.M):errors.append('ContactSurface header check did not pass')
reuse=json.loads((r/'reports/dart_reuse.json').read_text())['generated_header']
config_header=root/'prefix/include/dart/config.hpp'
if hashlib.sha256(config_header.read_bytes()).hexdigest()!=reuse['sha256']:errors.append('generated DART config header differs from same-build source')
expression='CMake File API evaluated build configuration'
commands=subprocess.check_output(['/usr/bin/ninja','-C',str(build),'-t','commands',*sorted(expected)],text=True)
(r/'logs/sim.selected_commands.txt').write_text(commands)
blocked=['libGLESv2','libflann_cpp','libgvc6-config-update','/usr/bin/dot']
if any(x in commands or x in json.dumps(observations) for x in blocked):errors.append('previously unpinned optional dependency selected')
import runpy
codegen=runpy.run_path(str(r/'scripts/codegen_inputs.py'))
generator_inputs=[]
for command in commands.splitlines():
 for segment in command.split('&&'):
  tokens=shlex.split(segment.strip())
  if not tokens or tokens==[':']:continue
  if '-c' in tokens:
   # Only the existing compiler launcher/compiler are allowed to compile.
   if tokens[:2]!=['/usr/bin/python3',str(r/'inputs/compile_gate.py')]:errors.append('unexpected compile launcher')
   verify(tokens[2])
  elif tokens[:1]==['cd']:
   if len(tokens)!=2 or Path(tokens[1]).resolve()!=(root/'src/sim').resolve():errors.append('unexpected command cwd')
  elif tokens[:1]==['/usr/bin/python3']:
   try:generator_inputs.append(codegen['validate'](tokens))
   except (AssertionError,KeyError,ValueError) as problem:errors.append('codegen input rejected '+str(problem))
  elif '-shared' in tokens:verify(tokens[0])
  elif tokens[:3]==['/usr/bin/cmake','-E','cmake_symlink_library']:verify(tokens[0])
  else:errors.append('unexpected selected command '+segment)
(r/'reports/generated_command_inputs.json').write_text(json.dumps(generator_inputs,indent=2)+'\n')
assert len(generator_inputs)==5,'expected four protocol generators and one factory'
# Compiler dependency hashes will additionally be checked by the original launcher.
result={'status':'PASS_STATIC_SELECTED_CLOSURE' if not errors else 'BLOCKED','configuration':config['name'],'selected_targets':sorted(expected),'generated_dependency_targets':sorted(v['name'] for v in targets.values()),'tinyxml2_raw':expression,'checked_external_files':len(checked),'errors':sorted(set(errors)),'generated':observations,'commands_sha256':hashlib.sha256(commands.encode()).hexdigest(),'scope':'only selected build closure; all executed configure file hashes still checked'}
(r/'reports/sim_selected_closure.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='generated'},indent=2))
raise SystemExit(bool(errors))
