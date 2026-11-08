"""Rejecting static gate for the six DART targets and generated build closure.
CMake File API and ninja -t commands are metadata only; no build or loader run.
"""
from pathlib import Path
import json,sys,hashlib,re,subprocess,shlex
r=Path(__file__).resolve().parents[1];root=r/'work/config-01';build=root/'build/dart'
# Reuse original hash/installed-stack rejection policy, unchanged.
policy=(r/'scripts/check_selection_broad.py').read_text().split('component=sys.argv[1];')[0]
exec(compile(policy,str(r/'scripts/check_selection_broad.py'),'exec'),globals())
checked_inputs=set();original_verify=verify
def verify(path):
 if path in checked_inputs:return
 checked_inputs.add(path);original_verify(path)
rows=[json.loads(l) for l in (root/'logs/dart.trace.jsonl').read_text().splitlines()]
for row in rows:
 if 'file' in row:verify(row['file'])
 if row.get('cmd')=='try_run':errors.append('try_run encountered')
reply=build/'.cmake/api/v1/reply';index=json.loads(next(reply.glob('index-*.json')).read_text())
model=json.loads((reply/index['reply']['codemodel-v2']['jsonFile']).read_text())
assert len(model['configurations'])==1
config=model['configurations'][0];assert config['name']=='RelWithDebInfo'
expected={'dart','dart-external-odelcpsolver','dart-collision-ode','dart-collision-bullet','dart-utils','dart-utils-urdf'}
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
    if not hits:errors.append('unresolved link library '+token)
    else:verify(str(hits[0]))
# Confirm exact tinyxml2 expression was resolved by CMake, not a custom evaluator.
raw=list((build/'joint-targets').rglob('tinyxml2__tinyxml2/INTERFACE_COMPILE_DEFINITIONS.txt'))
assert len(raw)==1
expression=raw[0].read_text().strip()
assert expression=='$<$<CONFIG:Debug>:TINYXML2_DEBUG>;$<$<BOOL:yes>:TINYXML2_IMPORT>;_FILE_OFFSET_BITS=64'
for name in ['dart-utils','dart-utils-urdf']:
 defines={d['define'] for g in observations[name]['compile_groups'] for d in g.get('defines',[])}
 if not {'TINYXML2_IMPORT','_FILE_OFFSET_BITS=64'}<=defines or 'TINYXML2_DEBUG' in defines:errors.append('tinyxml2 effective definition mismatch '+name)
commands=subprocess.check_output(['/usr/bin/ninja','-C',str(build),'-t','commands',*sorted(expected)],text=True)
(r/'logs/dart.selected_commands.txt').write_text(commands)
blocked=['libGLESv2','libflann_cpp','libgvc6-config-update','/usr/bin/dot']
if any(x in commands or x in json.dumps(observations) for x in blocked):errors.append('previously unpinned optional dependency selected')
for command in commands.splitlines():
 for segment in command.split('&&'):
  tokens=shlex.split(segment.strip())
  if not tokens or tokens==[':']:continue
  if '-c' in tokens:
   # Only the existing compiler launcher/compiler are allowed to compile.
   if tokens[:2]!=['/usr/bin/python3',str(r/'inputs/compile_gate.py')]:errors.append('unexpected compile launcher')
   verify(tokens[2])
  elif '-shared' in tokens:verify(tokens[0])
  elif tokens[:3]==['/usr/bin/cmake','-E','cmake_symlink_library']:verify(tokens[0])
  else:errors.append('unexpected selected command '+segment)
# Compiler dependency hashes will additionally be checked by the original launcher.
result={'status':'PASS_STATIC_SELECTED_CLOSURE' if not errors else 'BLOCKED','configuration':config['name'],'selected_targets':sorted(expected),'generated_dependency_targets':sorted(v['name'] for v in targets.values()),'tinyxml2_raw':expression,'checked_external_files':len(checked),'errors':sorted(set(errors)),'generated':observations,'commands_sha256':hashlib.sha256(commands.encode()).hexdigest(),'scope':'only selected build closure; all executed configure file hashes still checked'}
(r/'reports/dart_selected_closure.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='generated'},indent=2))
raise SystemExit(bool(errors))
