"""Static rejecting harness gate. argv: harness; JSON stdout, exit 0/1.
Consumes existing trace, File API, target snapshot, Ninja metadata and SHA locks.
Never configures, compiles, loads a subject, or executes the harness.
"""
from pathlib import Path
import hashlib,json,re,shlex,subprocess,sys
R=Path(__file__).resolve().parents[1]
ROOT=R/'work/config-01'
BUILD=ROOT/'build/harness'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
class Gate:
 def __init__(self):
  ns={'__file__':__file__}; policy=R/'scripts/check_selection_broad.py'
  exec(compile(policy.read_text().split('component=sys.argv[1];')[0],str(policy),'exec'),ns)
  self.original=ns['verify'];self.errors=ns['errors'];self.checked=ns['checked']
  self.receipt=json.loads((ROOT/'manifests/staged.json').read_text())
  self.reused=json.loads((ROOT/'manifests/reused_elfs.json').read_text())
  self.libraries={};self.paths=set()
 def verify(self,path):
  p=Path(path);real=p.resolve();name=str(real)
  if str(p).startswith('/usr/local/') or name.startswith('/usr/local/') or p.name=='libgz-physics-dartsim-plugin.so':
   self.errors.append('forbidden local/root-symlink input '+str(p));return
  if not p.exists():self.errors.append('missing input '+str(p));return
  self.paths.add(str(p))
  if p.is_file() and ('.so' in p.name or p.suffix=='.a'):
   row=self.receipt.get(name);expected=row['sha256'] if row else self.reused.get(name)
   if expected:
    if sha(p)!=expected:self.errors.append('receipt/reused SHA mismatch '+name)
    if row and (not Path(row['source']).is_file() or sha(row['source'])!=expected):self.errors.append('receipt source mismatch '+name)
    self.libraries[name]=sha(p);return
   if real.is_relative_to(ROOT):self.errors.append('unreceipted stack library '+name);return
  self.original(str(p))
  if p.is_file() and ('.so' in p.name or p.suffix=='.a'):self.libraries[name]=sha(p)
 def flags(self,value):
  if '$<' in value or '${' in value:self.errors.append('unresolved expression '+value)
  if re.search(r'-march=native|-mavx|-fno-rtti|-fno-exceptions|_GLIBCXX_USE_CXX11_ABI=0',value):self.errors.append('forbidden ABI/compiler option '+value)
 def link_tokens(self,tokens):
  i=0
  while i<len(tokens):
   t=tokens[i];self.flags(t);i+=1
   if t.startswith('/'):
    self.verify(t)
   elif t.startswith('-l') and not t.startswith('-l:'):
    name=t[2:];hits=[d/('lib'+name+ext) for d in [ROOT/'prefix/lib',R/'work/deps/usr/lib/x86_64-linux-gnu',Path('/usr/lib/x86_64-linux-gnu')] for ext in ['.so','.a'] if (d/('lib'+name+ext)).is_file()]
    if not hits:self.errors.append('unresolved link input '+t)
    else:self.verify(hits[0])
   elif t.startswith('-Wl,-rpath,'):
    expected=str(ROOT/'prefix/lib')+':'+str((R/'work/deps').resolve()/'usr/lib/x86_64-linux-gnu')
    if t[len('-Wl,-rpath,'):]!=expected:self.errors.append('unexpected RUNPATH '+t)
   elif t.startswith('-I') and len(t)>2:self.verify(t[2:])
   elif t in ['-o','-isystem','-I']:
    if i==len(tokens):self.errors.append('missing flag operand '+t);continue
    operand=tokens[i];i+=1
    if t=='-o':
     if operand!='aero-joint-harness':self.errors.append('unexpected output '+operand)
    else:self.verify(operand)
   elif t=='CMakeFiles/aero-joint-harness.dir/harness.cc.o':pass
   elif t in ['-fuse-ld=bfd','-fno-lto','-frtti','-fexceptions','-O2','-g','-DNDEBUG','-rdynamic','-pthread']:pass
   elif re.fullmatch(r'-D(?:_GLIBCXX_USE_CXX11_ABI=1|EIGEN_MAX_ALIGN_BYTES=16|EIGEN_MAX_STATIC_ALIGN_BYTES=16)',t):pass
   else:self.errors.append('unresolved link input '+t)
 def model(self,info):
  if info.get('name')!='aero-joint-harness' or info.get('type')!='EXECUTABLE':self.errors.append('wrong selected target')
  if info.get('dependencies'):self.errors.append('unplanned generated target dependency')
  if info.get('artifacts')!=[{'path':'aero-joint-harness'}]:self.errors.append('wrong harness artifact')
  if [s.get('path') for s in info.get('sources',[])]!=['harness.cc']:self.errors.append('wrong/missing source')
  if not info.get('compileGroups') or not info.get('link',{}).get('commandFragments'):self.errors.append('missing compile/link inputs')
  for group in info.get('compileGroups',[]):
   for inc in group.get('includes',[]):self.verify(inc['path'])
   for frag in group.get('compileCommandFragments',[]):self.flags(frag['fragment'])
   for definition in group.get('defines',[]):self.flags(definition['define'])
  for frag in info.get('link',{}).get('commandFragments',[]):self.link_tokens(shlex.split(frag['fragment']))
 def run(self):
  for name,row in self.receipt.items():
   if not Path(name).is_file() or not Path(row['source']).is_file() or sha(name)!=row['sha256'] or sha(row['source'])!=row['sha256']:self.errors.append('invalid receipt pair '+name)
  if len(self.receipt)!=13:self.errors.append('expected 13 predecessor receipt pairs')
  trace=ROOT/'logs/harness.trace.jsonl'
  rows=[json.loads(line) for line in trace.read_text().splitlines()]
  scratch={}
  for row in rows:
   f=row.get('file','')
   if re.fullmatch(re.escape(str(BUILD/'CMakeFiles/CMakeScratch'))+r'/TryCompile-[A-Za-z0-9]+/CMakeLists\.txt',f):scratch.setdefault(f,[]).append(row)
  # CMake deletes generated try_compile scripts; they are trace metadata, not
  # persistent consumer inputs. Require the recorded generated-project identity.
  for f,items in scratch.items():
   if not any(x.get('cmd')=='project' and x['args'][0]=='CMAKE_TRY_COMPILE' for x in items):self.errors.append('unknown scratch project '+f)
  for row in rows:
   if 'file' in row and row['file'] not in scratch:self.verify(row['file'])
   if row.get('cmd','').lower()=='try_run':self.errors.append('unexpected harness try_run')
  reply=BUILD/'.cmake/api/v1/reply';indexes=list(reply.glob('index-*.json'))
  if len(indexes)!=1:raise ValueError('missing/ambiguous File API index')
  index=json.loads(indexes[0].read_text());model=json.loads((reply/index['reply']['codemodel-v2']['jsonFile']).read_text())
  if len(model['configurations'])!=1 or model['configurations'][0]['name']!='RelWithDebInfo':raise ValueError('wrong configuration')
  targets=model['configurations'][0]['targets']
  if [t['name'] for t in targets]!=['aero-joint-harness']:raise ValueError('unplanned target set')
  info=json.loads((reply/targets[0]['jsonFile']).read_text());self.model(info)
  # Direct target contract; evaluated File API above covers transitive inputs.
  props=[f.parent for f in (BUILD/'joint-targets').rglob('target.txt') if f.read_text().strip()=='aero-joint-harness']
  if len(props)!=1 or (props[0]/'LINK_LIBRARIES.txt').read_text().strip()!='gz-sim8::gz-sim8':self.errors.append('direct Sim target contract mismatch')
  rows=json.loads((BUILD/'compile_commands.json').read_text())
  if len(rows)!=1 or rows[0]['file']!=str(R/'inputs/harness.cc'):self.errors.append('unexpected compile input')
  for row in rows:self.flags(row['command']);self.verify(row['file'])
  commands=subprocess.check_output(['/usr/bin/ninja','-C',str(BUILD),'-t','commands','aero-joint-harness'],text=True)
  lines=commands.splitlines()
  if len(lines)!=2:raise ValueError('unexpected command count')
  compile_tokens=shlex.split(lines[0]);prefix=['/usr/bin/python3',str(R/'inputs/compile_gate.py'),'/usr/bin/x86_64-linux-gnu-g++-13']
  if compile_tokens[:3]!=prefix or '-c' not in compile_tokens:self.errors.append('compiler launcher mismatch')
  for f in prefix:self.verify(f)
  for i,t in enumerate(compile_tokens):
   if t in ['-isystem','-I']:self.verify(compile_tokens[i+1])
   elif t.startswith('-I'):self.verify(t[2:])
  parts=[shlex.split(s.strip()) for s in lines[1].split('&&')]
  if len(parts)!=3 or parts[0]!=[':'] or parts[2]!=[':'] or parts[1][0]!='/usr/bin/x86_64-linux-gnu-g++-13':self.errors.append('unexpected link command')
  else:self.verify(parts[1][0]);self.link_tokens(parts[1][1:])
  return {'component':'harness','status':'BLOCKED' if self.errors else 'PASS_STATIC_SELECTED_CLOSURE','errors':sorted(set(self.errors)),'receipt_pairs':len(self.receipt),'checked_external_files':len(self.checked),'checked_paths':len(self.paths),'link_libraries':self.libraries,'commands_sha256':hashlib.sha256(commands.encode()).hexdigest(),'generated':info,'scope':'static selection only; no subject execution or loader'}
def main():
 try:
  if sys.argv[1:]!=['harness']:raise ValueError('expected single argument: harness')
  result=Gate().run()
 except (OSError,ValueError,KeyError,IndexError,StopIteration) as e:result={'component':'harness','status':'BLOCKED','errors':[str(e)]}
 print(json.dumps(result,indent=2));return result['status']=='BLOCKED'
if __name__=='__main__':raise SystemExit(main())
