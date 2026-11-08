"""Static package/import/ELF inventory. Never configure or load a target."""
from pathlib import Path
import subprocess,json,hashlib,re,collections
base=Path.cwd(); r=base/'validation/gazebo-joint-closure-v1'; old=base/'validation/gazebo-joint-inputs-v1'; deps=old/'work/deps/usr'
raw=subprocess.check_output(['dpkg-query','-W','-f=${binary:Package}\t${Version}\t${Architecture}\t${db:Status-Status}\t${Depends}\t${Pre-Depends}\n'],text=True)
installed={}
for line in raw.splitlines():
 p=line.split('\t')
 if len(p)==6 and p[3]=='installed':installed[p[0].split(':')[0]]={'name':p[0],'version':p[1],'arch':p[2],'depends':p[4]+','+p[5]}
roots=['libgz-cmake3-dev','libgz-common5-dev','libgz-common5-graphics-dev','libgz-common5-geospatial-dev','libgz-plugin2-dev','libgz-utils2-dev','libgz-math7-dev','libgz-transport13-dev','libgz-msgs10-dev','libsdformat14-dev','libgz-fuel-tools9-dev','libgz-gui8-dev','libgz-rendering8-dev','libgz-sensors8-dev','qtbase5-dev','qtdeclarative5-dev','qtquickcontrols2-5-dev','libeigen3-dev','libassimp-dev','libtinyxml2-dev','libprotobuf-dev','protobuf-compiler','libssl-dev','libgtest-dev','libfmt-dev','libspdlog-dev','libboost-dev','pkgconf']
# The OSRF package spelling uses underscores in fuel-tools on this host.
for i,n in enumerate(roots):
 if n not in installed and n.replace('fuel-tools','fuel-tools') not in installed:
  alternatives=[x for x in installed if 'fuel' in x and x.endswith('-dev')] if 'fuel' in n else []
  if len(alternatives)==1:roots[i]=alternatives[0]
forbidden=lambda n: n.startswith(('libdart','libgz-physics7','libgz-sim8'))
queue=roots[:]; seen={}; missing=[]; forbidden_edges=[]
while queue:
 n=queue.pop()
 if n in seen:continue
 if forbidden(n):forbidden_edges.append(n);continue
 if n not in installed:missing.append(n);continue
 row=installed[n];seen[n]=row
 for expression in row['depends'].split(','):
  candidates=[re.split(r'[ (]',x.strip())[0].split(':')[0] for x in expression.split('|')]
  chosen=next((x for x in candidates if x in installed),None)
  if chosen:queue.append(chosen)
files={}; configs=[]; elfs={}
for name,row in sorted(seen.items()):
 listing=subprocess.check_output(['dpkg-query','-L',row['name']],text=True)
 for line in listing.splitlines():
  p=Path(line)
  if not p.is_file():continue
  relevant=('/include/' in line or '/usr/src/' in line or p.suffix in ('.cmake','.pc','.proto','.desc','.py','.a','.prl','.pri','.pro','.xml','.json','.in','.cc','.cpp','.hh','.hpp','.h','.j2','.jinja2') or bool(p.stat().st_mode & 0o111) or '.so' in p.name or p.name in ('protoc','pkgconf'))
  if not relevant:continue
  data=p.read_bytes();real=str(p.resolve());sha=hashlib.sha256(data).hexdigest()
  files[line]={'realpath':real,'sha256':sha,'owner':name}
  if p.suffix=='.cmake':
   text=data.decode(errors='replace')
   configs.append({'path':line,'sha256':sha,'owner':name,'find_calls':re.findall(r'(?:find_dependency|find_package|gz_find_package)\s*\(\s*([^\s)]+)',text,re.I),'target_refs':sorted(set(re.findall(r'[a-zA-Z0-9_+.-]+::[a-zA-Z0-9_+.-]+',text))),'import_locations':re.findall(r'IMPORTED_(?:LOCATION|IMPLIB)(?:_[A-Z]+)?\s+"([^"]+)"',text),'rebuilt_refs':sorted(set(re.findall(r'(?:libdart[^\s";]*|gz-physics7[^\s";)]*|gz-sim8[^\s";)]*)',text)))})
  if data[:4]==b'\x7fELF' and '/OGRE/' not in str(p):elfs[real]=Path(real)
# All extracted package files remain selected by exact existing manifest/hash.
for p in deps.rglob('*'):
 if p.is_file() and not p.is_symlink():
  data=p.read_bytes();files[str(p)]={'realpath':str(p.resolve()),'sha256':hashlib.sha256(data).hexdigest(),'owner':'extracted-18-package-set'}
  if data[:4]==b'\x7fELF' and '.so' in p.name:elfs[str(p.resolve())]=p.resolve()
search=[deps/'lib/x86_64-linux-gnu',Path('/usr/lib/x86_64-linux-gnu'),Path('/usr/lib'),Path('/lib/x86_64-linux-gnu')]
queue=list(elfs.values()); graph={};unresolved=[];bad=[]
while queue:
 p=queue.pop().resolve()
 if str(p) in graph:continue
 if re.match(r'lib(?:dart|gz-physics7|gz-sim8)',p.name):bad.append(str(p));continue
 out=subprocess.check_output(['readelf','-d','-n',str(p)],text=True)
 ns=re.findall(r'Shared library: \[(.*?)\]',out);edges=[]
 rpaths=[]
 for text in re.findall(r'Library (?:runpath|rpath): \[(.*?)\]',out):
  rpaths.extend(Path(x.replace('$ORIGIN',str(p.parent)).replace('${ORIGIN}',str(p.parent))) for x in text.split(':') if x)

 for n in ns:
  choices=[d/n for d in [p.parent]+rpaths+search if (d/n).is_file()]
  if not choices:unresolved.append({'from':str(p),'needed':n});continue
  dest=choices[0].resolve();edges.append({'needed':n,'path':str(dest)});queue.append(dest)
 sha=hashlib.sha256(p.read_bytes()).hexdigest(); files.setdefault(str(p),{'realpath':str(p),'sha256':sha,'owner':'transitive-ELF'})
 graph[str(p)]={'sha256':sha,'build_id':re.findall(r'Build ID: ([a-f0-9]+)',out),'needed':edges}
(r/'work/dependency_files.json').write_text(json.dumps(files,indent=2)+'\n')
(r/'reports/import_graph.json').write_text(json.dumps(configs,indent=2)+'\n')
(r/'reports/elf_graph.json').write_text(json.dumps(graph,indent=2)+'\n')
summary={'roots':roots,'packages':seen,'missing_roots':sorted(set(missing)),'blocked_package_edges':sorted(set(forbidden_edges)),'forbidden_elfs':sorted(set(bad)),'unresolved_elfs':unresolved,'file_count':len(files),'config_count':len(configs),'elf_count':len(graph),'files_manifest_sha256':hashlib.sha256((r/'work/dependency_files.json').read_bytes()).hexdigest(),'selection_status':'STATIC_CANDIDATE_LOCK_ACTUAL_CMAKE_SELECTION_REQUIRES_GUARD'}
(r/'reports/dependency_lock.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps({k:v for k,v in summary.items() if k!='packages'},indent=2))
