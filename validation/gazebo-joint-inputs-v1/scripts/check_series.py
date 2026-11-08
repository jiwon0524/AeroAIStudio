"""Read-only exact-context simulation of ordered unified diffs in RAM.
No patched file/tree is written. Complements git apply --check on originals.
"""
from pathlib import Path
import json,re,hashlib
r=Path(__file__).resolve().parents[1]; base=Path.cwd()
dart=base/'validation/gazebo-source-materials-v1/work/extracted/dart/dart-6.13.2'; cache={}
patchdir=base/'validation/gazebo-source-materials-v1/work/extracted/dart-packaging/debian/patches'
series=json.loads((base/'validation/gazebo-source-materials-v1/reports/packaging_comparison.json').read_text())['dart_patch_series']
results=[]
for patch in [patchdir/x for x in series]+[r/'inputs/01-dart-typed-entry.patch']:
 lines=patch.read_text().splitlines(True); i=0; changes=[]
 try:
  while i<len(lines):
   if not lines[i].startswith('--- '):i+=1;continue
   if i+1>=len(lines) or not lines[i+1].startswith('+++ '):i+=1;continue
   oldname=lines[i][4:].split()[0]; name=lines[i+1][4:].split()[0]
   name='/'.join(name.split('/')[1:]); i+=2
   if name not in cache:cache[name]=(dart/name).read_text().splitlines(True) if oldname!='/dev/null' else []
   text=cache[name]; offset=0
   while i<len(lines) and lines[i].startswith('@@ '):
    h=re.match(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@',lines[i]); i+=1
    before=[];after=[]
    oldcount=int(h[2] or 1);newcount=int(h[4] or 1)
    while len(before)<oldcount or len(after)<newcount:
     line=lines[i];i+=1
     if line.startswith(' '):before.append(line[1:]);after.append(line[1:])
     elif line.startswith('-'):before.append(line[1:])
     elif line.startswith('+'):after.append(line[1:])
     else:raise ValueError('unsupported diff line')
    expected=max(0,int(h[1])-1)+offset
    spots=[j for j in range(len(text)-len(before)+1) if text[j:j+len(before)]==before]
    at=expected if expected in spots else spots[0] if len(spots)==1 else None
    if at is None:raise ValueError('nonunique/missing context '+name)
    text[at:at+len(before)]=after
    offset+=(at-expected)+len(after)-len(before)
    if i<len(lines) and lines[i].startswith('\\ No newline'):i+=1
   cache[name]=text;changes.append(name)
  results.append({'patch':str(patch.relative_to(base)),'status':'PASS_EXACT_CONTEXT_IN_MEMORY','files':changes})
 except Exception as e:
  results.append({'patch':str(patch.relative_to(base)),'status':'BLOCKED','error':str(e)});break
out={'method':'in-memory exact-context simulation only; no patch applied to any tree','results':results,'hypothetical_modified_file_sha256':{name:hashlib.sha256(''.join(text).encode()).hexdigest() for name,text in cache.items()}}
(r/'reports/ordered_patch_checks.json').write_text(json.dumps(out,indent=2)+'\n')
print([(x['patch'].split('/')[-1],x['status'],x.get('error')) for x in results])
