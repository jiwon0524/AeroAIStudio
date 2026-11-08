"""Run only the validated five codegen actions under file/exec tracing."""
from pathlib import Path
import json,hashlib,subprocess,shlex,time,socket,runpy,re,sys
b=Path.cwd();p=b/'validation/gazebo-joint-codegen-fix-v1';root=p/'work/config-01';build=root/'build/sim-03';policy=runpy.run_path(str(p/'scripts/codegen_inputs.py'))
state=json.loads((p/'reports/steps_final.json').read_text());assert state[-1]['step']=='sim.selection' and all(x['returncode']==0 for x in state)
target='gz_msgs_gen/gz/sim/private_msgs/register.cc';commands=subprocess.check_output(['/usr/bin/ninja','-C',str(build),'-t','commands',target],text=True);checked=[]
for command in commands.splitlines():
 for segment in command.split('&&'):
  argv=shlex.split(segment.strip())
  if not argv:continue
  if argv[0]=='cd':assert len(argv)==2 and Path(argv[1]).resolve()==(root/'src/sim').resolve()
  else:checked.append(policy['validate'](argv))
assert len(checked)==5
# Native codegen tool dependencies: statically pinned, no subject stack.
allowed=policy['allowed'];tool_records={};queue=[Path('/usr/bin/protoc').resolve(),Path('/usr/bin/gz-msgs10_protoc_plugin').resolve()]
while queue:
 f=queue.pop();name=str(f)
 if name in tool_records:continue
 assert allowed.get(name)==hashlib.sha256(f.read_bytes()).hexdigest(),name
 text=subprocess.check_output(['readelf','-d','-n',name],text=True);needed=re.findall(r'Shared library: \[(.*?)\]',text);assert not any(x.startswith(('libdart','libgz-sim','libgz-physics')) for x in needed)
 tool_records[name]={'sha256':allowed[name],'needed':needed}
 for lib in needed:
  hits=[Path(d)/lib for d in ['/usr/lib/x86_64-linux-gnu','/lib/x86_64-linux-gnu'] if (Path(d)/lib).is_file()];assert hits,lib;queue.append(hits[0].resolve())
(p/'reports/codegen_preflight.json').write_text(json.dumps({'commands':checked,'native_tool_closure':tool_records,'commands_sha256':hashlib.sha256(commands.encode()).hexdigest(),'target':target},indent=2)+'\n')
argv0=json.loads((p/'reports/commands_retry.json').read_text())[0]['argv'];env=argv0[:argv0.index('/usr/bin/cmake')]
# Escalation retries preserve failed traces; no build step retry on a codegen failure.
suffix=sys.argv[1] if len(sys.argv)>1 else 'first';trace=p/'logs'/('codegen.'+suffix+'.strace');log=p/'logs'/('codegen.'+suffix+'.log');assert not trace.exists() and not log.exists()
with log.open('x') as out:
 start=time.time();proc=subprocess.Popen(env+['/usr/bin/strace','-f','-qq','-e','trace=execve,openat,readlink,readlinkat','-o',str(trace),'/usr/bin/ninja','-C',str(build),'-v','-j','1',target],cwd=build,stdout=out,stderr=subprocess.STDOUT)
 try:identity=Path('/proc',str(proc.pid),'stat').read_text().split(') ',1)[1].split()[19]
 except OSError:identity='UNKNOWN'
 code=proc.wait()
record={'returncode':code,'host':socket.gethostname(),'pid':proc.pid,'start_identity':identity,'seconds':round(time.time()-start,2),'log':str(log.relative_to(b)),'trace':str(trace.relative_to(b))};(p/'reports'/('codegen_attempt_'+suffix+'.json')).write_text(json.dumps(record,indent=2)+'\n');print(record,flush=True)
if code:raise SystemExit(code)
text=trace.read_text();opens=[];execs=[]
for line in text.splitlines():
 if 'execve(' in line:execs.append(line)
 match=re.search(r'openat\([^,]+, "([^"]+)".*?= (\d+)',line)
 if match:opens.append(match.group(1))
descriptor=str(root/'prefix/share/gz/protos/gz-msgs10.gz_desc');assert descriptor in opens
assert not any(s.startswith('/usr/share/gz/') for s in opens),'unexpected original descriptor/template data read'
private=set(policy['protos']);assert {s for s in opens if s.endswith('.proto')}<=private
assert not any(re.search(r'lib(?:dart|gz-(?:sim|physics))[^/]*\.so',s) for s in opens),'subject ELF opened'
expected_execs=['/usr/bin/ninja','/bin/sh','/usr/bin/python3','/usr/bin/protoc','/usr/bin/gz-msgs10_protoc_plugin']
for line in execs:
 name=re.search(r'execve\("([^"]+)"',line).group(1);assert str(Path(name).resolve()) in {str(Path(s).resolve()) for s in expected_execs},name
outputs={str(f.relative_to(build)):hashlib.sha256(f.read_bytes()).hexdigest() for f in (build/'gz_msgs_gen').rglob('*') if f.is_file()};assert sum(k.endswith('.pb_index') for k in outputs)==4
result={'status':'PASS','descriptor_open_count':opens.count(descriptor),'source_proto_reads':sorted({s for s in opens if s.endswith('.proto')}),'factory_index_reads':sorted({s for s in opens if s.endswith('.pb_index')}),'exec_trace':execs,'output_hashes':outputs,'trace_sha256':hashlib.sha256(trace.read_bytes()).hexdigest(),'execution':record,'scope':'only five selected codegen actions; no subject build/execution/load'}
(p/'reports/codegen_execution.json').write_text(json.dumps(result,indent=2)+'\n');print('PASS codegen',len(outputs),'generated files; descriptor reads',opens.count(descriptor))
