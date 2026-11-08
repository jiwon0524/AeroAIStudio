from pathlib import Path
import json,subprocess,time,socket,hashlib,sys
b=Path.cwd();p=b/'validation/gazebo-joint-harness-fix-v1';r=b/'validation/gazebo-joint-codegen-fix-v1';build=r/'work/config-01/build/harness';label=sys.argv[1]
statefile=p/'reports/steps.json';state=json.loads(statefile.read_text()) if statefile.exists() else [];assert all(x['returncode']==0 for x in state),'first failure latched'
assert label==['harness.build','harness.elf'][len(state)]
assert json.loads((p/'reports/selection.json').read_text())['status']=='PASS_STATIC_SELECTED_CLOSURE'
assert len(json.loads((p/'reports/negative_tests.json').read_text())['negative_tests'])==11
rows=json.loads((r/'reports/commands_final.json').read_text());argv=next(x['argv'] for x in rows if x['step']=='harness.build')
if label=='harness.elf':argv=argv[:argv.index('/usr/bin/cmake')]+['python3',str(r/'scripts/audit_outputs_sim.py'),'harness']
log=p/'logs'/(label+'.log')
with log.open('x') as out:
 start=time.time();proc=subprocess.Popen(argv,cwd=build,stdout=out,stderr=subprocess.STDOUT)
 try:identity=Path('/proc',str(proc.pid),'stat').read_text().split(') ',1)[1].split()[19]
 except OSError:identity='UNKNOWN'
 print(label,proc.pid,flush=True);code=proc.wait()
record={'step':label,'returncode':code,'host':socket.gethostname(),'pid':proc.pid,'start_identity':identity,'seconds':round(time.time()-start,2),'log':str(log.relative_to(b)),'sha256':hashlib.sha256(log.read_bytes()).hexdigest()};state.append(record);statefile.write_text(json.dumps(state,indent=2)+'\n');print(record,flush=True);raise SystemExit(code)
