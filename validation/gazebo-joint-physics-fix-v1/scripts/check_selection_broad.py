"""Future post-configure/compile static guard. Never invokes CMake or a target.
Only inspect files explicitly created by an already-authorized configure/build.
"""
from pathlib import Path
import json,re,sys,hashlib
base=Path(__file__).resolve().parents[3]; r=Path(__file__).resolve().parents[1]
lock=json.loads((r/'work/selected_files.json').read_text())
tools=json.loads((base/'validation/gazebo-joint-inputs-v1/reports/toolchain_files.json').read_text())
allowed={str(Path(p).resolve()):v['sha256'] for p,v in lock.items()}
allowed.update({x['realpath']:x['sha256'] for x in tools if x['path'].startswith(('/usr/include/c++/13/','/usr/include/x86_64-linux-gnu/c++/13/','/usr/lib/gcc/','/usr/libexec/gcc/','/usr/share/cmake-3.28/','/usr/bin/'))})
for x in json.loads((base/'validation/gazebo-joint-inputs-v1/reports/tool_elf_closure.json').read_text())['files']:allowed[x['path']]=x['sha256']
root=(r/'work/config-01').resolve(); known=[root,(r/'inputs').resolve()]
forbidden=re.compile(r'(^|/)(?:libdart[^/]*|libgz-(?:physics7|sim8)[^/]*|dart|gz-(?:physics7|sim8)[^/]*)($|/)')
errors=[]; checked={}
def verify(path):
 p=Path(path); real=p.resolve(); name=str(real)
 if any(real.is_relative_to(x) for x in known):return
 if forbidden.search(name) or re.search(r'/include/gz/(?:physics7|sim8)(?:/|$)',name):errors.append('forbidden installed stack path: '+name);return
 if p.is_dir():
  # Directory permission is only an include/search candidate; actual accessed
  # files must still be in the exact lock. /usr is not a library allowlist.
  if name not in ['/usr/include','/usr/lib/x86_64-linux-gnu'] and not any(Path(x).is_relative_to(real) for x in allowed):errors.append('unlocked directory: '+name)
  return
 if name not in allowed:errors.append('unlocked file: '+name);return
 if name not in checked:
  checked[name]=p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==allowed[name]
  if not checked[name]:errors.append('input changed/missing: '+name)
component=sys.argv[1]; build=root/'build'/component
trace=root/'logs'/f'{component}.trace.jsonl'
if not trace.is_file():raise SystemExit('BLOCKED: configure trace missing')
for line in trace.read_text().splitlines():
 try:row=json.loads(line)
 except json.JSONDecodeError:continue
 if 'file' in row:verify(row['file'])
cache=build/'CMakeCache.txt'
if component=='dart' and cache.is_file() and re.search(r'^BT_USE_DOUBLE_PRECISION:[^=]*=(?:1|ON|TRUE|YES)$',cache.read_text(),re.M):errors.append('unexpected Bullet double-precision branch')
props=list((build/'joint-targets').rglob('*.txt'))
if not props:errors.append('missing generated target property snapshot')
for p in props:
 if p.name=='target.txt':continue
 text=p.read_text().strip()
 text=re.sub(r'\$<INSTALL_INTERFACE:[^<>]*>','',text)
 for _ in range(10):
  newer=re.sub(r'\$<(?:BUILD_INTERFACE|LINK_ONLY|TARGET_NAME_IF_EXISTS):([^<>]*)>',r'\1',text)
  if newer==text:break
  text=newer
 for item in text.split(';'):
  if '$<' in item:errors.append('unevaluated target expression '+str(p))
  if item.startswith('/'):verify(item)
commands=build/'compile_commands.json'
if commands.is_file():
 for c in json.loads(commands.read_text()):
  if re.search(r'-march=native|-mavx|-fno-rtti|-fno-exceptions|_GLIBCXX_USE_CXX11_ABI=0',c.get('command','')):errors.append('forbidden ABI/compiler option')
  for path in re.findall(r'(?:-I|-isystem\s+)([^\s"]+)',c.get('command','')):
   verify(path)
# Compiler dependency files expose broad include-directory leakage.
for p in build.rglob('*.d'):
 text=p.read_text().replace('\\\n',' ')
 for name in re.findall(r'/[^\s:]+',text):verify(name)
print(json.dumps({'component':component,'status':'PASS_STATIC_SELECTION' if not errors else 'BLOCKED','checked_external_files':len(checked),'errors':sorted(set(errors))},indent=2))
raise SystemExit(1 if errors else 0)
