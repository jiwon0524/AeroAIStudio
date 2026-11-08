from pathlib import Path
import json,subprocess,re,hashlib
r=Path(__file__).resolve().parents[1]
seeds=[Path(x) for x in ['/usr/bin/g++-13','/usr/bin/gcc-13','/usr/bin/as','/usr/bin/ld.bfd','/usr/bin/ar','/usr/bin/ranlib','/usr/bin/cmake','/usr/bin/ninja','/usr/bin/protoc','/usr/bin/python3','/usr/bin/pkg-config','/usr/libexec/gcc/x86_64-linux-gnu/13/cc1','/usr/libexec/gcc/x86_64-linux-gnu/13/cc1plus','/usr/libexec/gcc/x86_64-linux-gnu/13/collect2','/usr/lib/x86_64-linux-gnu/libstdc++.so.6','/usr/lib/x86_64-linux-gnu/libcrypto.so.3']]
queue=seeds[:];seen={};missing=[]
dirs=[Path('/usr/lib/x86_64-linux-gnu'),Path('/lib/x86_64-linux-gnu'),Path('/usr/lib/gcc/x86_64-linux-gnu/13')]
while queue:
 p=queue.pop().resolve()
 if str(p) in seen:continue
 if not p.is_file():missing.append(str(p));continue
 dyn=subprocess.run(['readelf','-d',str(p)],text=True,capture_output=True)
 needed=re.findall(r'Shared library: \[(.*?)\]',dyn.stdout)
 rows=[]
 for name in needed:
  choices=[d/name for d in [p.parent]+dirs if (d/name).is_file()]
  if not choices:missing.append(name);rows.append({'soname':name,'resolved':None})
  else:rows.append({'soname':name,'resolved':str(choices[0].resolve())});queue.append(choices[0])
 seen[str(p)]={'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'needed':rows,'readelf_rc':dyn.returncode}
(r/'reports/tool_elf_closure.json').write_text(json.dumps({'method':'readelf-only default-directory static resolution, no loader; not runtime map proof','missing':missing,'files':list(seen.values())},indent=2)+'\n')
print('ELF closure files',len(seen),'missing',missing)
