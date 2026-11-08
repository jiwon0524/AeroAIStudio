"""Run one exact prepared command and capture its result. Never auto-advance.
Any failure latches a stop; resuming/retrying requires a separate review.
"""
from pathlib import Path
import json,shlex,subprocess,sys,hashlib,socket,time
base=Path.cwd();phase=base/'validation/gazebo-joint-build-v1';prep=base/'validation/gazebo-joint-closure-v1'
lines=[shlex.split(x) for x in (prep/'reports/build_commands.txt').read_text().splitlines() if x.strip() and not x.startswith('#')]
cmds=json.loads((prep/'reports/build_commands.json').read_text());labels=['source']
for row in cmds['steps']:
 labels.extend([row['component']+'.configure',row['component']+'.selection',row['component']+'.build',row['component']+'.elf'])
 labels.extend(row['component']+'.stage.'+str(i) for i in range(len(row['stage_argvs'])))
 if row['stage_receipt_argv']:labels.append(row['component']+'.receipt')
if len(labels)!=len(lines):raise RuntimeError('command mapping mismatch')
name=sys.argv[1];index=labels.index(name);path=phase/'reports/steps.json';state=json.loads(path.read_text()) if path.exists() else []
if any(x['returncode']!=0 for x in state):raise RuntimeError('prior failure latched; stop')
if len(state)!=index:raise RuntimeError('out-of-order or repeated step')
if json.loads((phase/'reports/input_verification.json').read_text())['status']!='PASS':raise RuntimeError('inputs not verified')
log=phase/'logs'/(name+'.log')
if log.exists():raise RuntimeError('existing log preserved; no retry')
with log.open('x') as output:
 start=time.time();p=subprocess.Popen(lines[index],cwd=base,stdout=output,stderr=subprocess.STDOUT)
 try:identity=Path('/proc',str(p.pid),'stat').read_text().split(') ',1)[1].split()[19]
 except OSError:identity='UNKNOWN'
 print(json.dumps({'step':name,'host':socket.gethostname(),'pid':p.pid,'start_identity':identity,'output':str(log.relative_to(base))}),flush=True)
 code=p.wait()
row={'step':name,'command_index':index,'prepared_commands_sha256':hashlib.sha256((prep/'reports/build_commands.txt').read_bytes()).hexdigest(),'host':socket.gethostname(),'pid':p.pid,'start_identity':identity,'returncode':code,'elapsed_seconds':round(time.time()-start,3),'log':str(log.relative_to(base)),'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest(),'status':'PASS_COMMAND' if code==0 else 'STOPPED_AT_FIRST_FAILURE'}
state.append(row);path.write_text(json.dumps(state,indent=2)+'\n');print(json.dumps(row),flush=True)
raise SystemExit(code)
