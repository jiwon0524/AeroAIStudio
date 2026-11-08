from pathlib import Path
import json,subprocess,time,hashlib,socket,sys
b=Path.cwd();p=b/'validation/gazebo-joint-feature-fix-v1';old=b/'validation/gazebo-joint-codegen-fix-v1';root=old/'work/config-01';build=root/'build/sim-03'
rows=json.loads((old/'reports/commands_final.json').read_text());env=rows[0]['argv'][:rows[0]['argv'].index('/usr/bin/cmake')]
label=sys.argv[1]; assert label in ['physics.object','sim.build','sim.elf','sim.stage.0','sim.stage.1','sim.stage.2','sim.receipt','harness.configure','harness.selection','harness.build','harness.elf']
statefile=p/'reports/steps.json';state=json.loads(statefile.read_text()) if statefile.exists() else [];assert not any(x['returncode'] for x in state),'first failure latched'
if label=='physics.object':
 commands=subprocess.check_output(['/usr/bin/ninja','-C',str(build),'-t','commands','gz-sim8','gz-sim8-physics-system'],text=True)
 assert hashlib.sha256(commands.encode()).hexdigest()==json.loads((old/'reports/sim_selected_closure.json').read_text())['commands_sha256'],'selected commands changed'
 argv=env+['/usr/bin/ninja','-C',str(build),'-v','-j','1','src/systems/physics/CMakeFiles/gz-sim8-physics-system.dir/Physics.cc.o']
else: argv=next(x['argv'] for x in rows if x['step']==label)
# Static audits emit stdout only; receipts write new entries to current prefix manifest.
log=p/'logs'/(label+'.log');cwd=root/'build'/('harness' if label.startswith('harness.') else 'sim-03');cwd.mkdir(exist_ok=True)
with log.open('x') as out:
 start=time.time();proc=subprocess.Popen(argv,cwd=cwd,stdout=out,stderr=subprocess.STDOUT)
 try:identity=Path('/proc',str(proc.pid),'stat').read_text().split(') ',1)[1].split()[19]
 except OSError:identity='UNKNOWN'
 print(label,proc.pid,flush=True);code=proc.wait()
record={'step':label,'returncode':code,'host':socket.gethostname(),'pid':proc.pid,'start_identity':identity,'seconds':round(time.time()-start,2),'log':str(log.relative_to(b)),'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest()};state.append(record);statefile.write_text(json.dumps(state,indent=2)+'\n');print(record,flush=True)
raise SystemExit(code)
