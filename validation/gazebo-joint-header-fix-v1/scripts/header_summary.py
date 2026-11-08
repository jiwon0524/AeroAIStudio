"""Audit actual Ninja header dependency metadata after the build returns."""
from pathlib import Path
import subprocess,json,hashlib
p=Path(__file__).resolve().parents[1];build=p/'work/config-01/build/dart';text=subprocess.check_output(['/usr/bin/ninja','-C',str(build),'-t','deps'],text=True);(p/'logs/dart.all_header_deps.txt').write_text(text)
files=set();objects=[]
for line in text.splitlines():
 if line and not line.startswith(' '):objects.append(line)
 elif line.startswith('    '):
  f=Path(line.strip());files.add(f.resolve() if f.is_absolute() else (build/f).resolve())
local=sorted(str(f) for f in files if str(f).startswith('/usr/local/'));assert not local,local
lock=json.loads((p/'work/selected_files.json').read_text());headers=[]
for f in sorted(files):
 if not str(f).startswith(('/usr/include/spdlog/','/usr/include/fmt/')):continue
 sha=hashlib.sha256(f.read_bytes()).hexdigest();assert lock.get(str(f),{}).get('sha256')==sha
 headers.append({'path':str(f),'sha256':sha})
(p/'reports/actual_headers.json').write_text(json.dumps({'status':'PASS_NO_LOCAL_HEADERS','object_records':len(objects),'unique_dependency_files':len(files),'local_headers':local,'logging_headers':headers,'metadata_sha256':hashlib.sha256(text.encode()).hexdigest(),'scope':'Ninja actual compiler dependencies; original launcher hash gate also ran per compile'},indent=2)+'\n');print('PASS',len(objects),'objects',len(files),'dependencies',len(headers),'pinned logging headers')
