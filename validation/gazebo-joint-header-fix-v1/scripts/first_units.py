"""Compile original failed object targets only; inspect Ninja's actual dependencies."""
from pathlib import Path
import json,shlex,subprocess,hashlib,socket,time
b=Path.cwd();p=b/'validation/gazebo-joint-header-fix-v1';root=p/'work/config-01';build=root/'build/dart';steps=json.loads((p/'reports/steps.json').read_text());assert steps[-1]['step']=='dart.selection' and all(x['returncode']==0 for x in steps)
line=next(x for x in (p/'reports/build_commands.txt').read_text().splitlines() if ' --build ' in x and '/build/dart ' in x);argv=shlex.split(line);env=argv[:argv.index('/usr/bin/cmake')];records=[];locked=json.loads((p/'work/selected_files.json').read_text());status='PASS'
for name in ['CAllocator','Aspect']:
 target='dart/CMakeFiles/dart.dir/common/'+name+'.cpp.o';log=p/'logs'/('first.'+name+'.log')
 with log.open('x') as stream:
  start=time.time();proc=subprocess.Popen(env+['/usr/bin/cmake','--build',str(build),'--target',target,'--parallel','1','--verbose'],stdout=stream,stderr=subprocess.STDOUT,cwd=b)
  try:identity=Path('/proc',str(proc.pid),'stat').read_text().split(') ',1)[1].split()[19]
  except OSError:identity='UNKNOWN'
  code=proc.wait()
 record={'unit':name,'returncode':code,'host':socket.gethostname(),'pid':proc.pid,'start_identity':identity,'seconds':round(time.time()-start,2),'log':str(log.relative_to(b)),'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest()};records.append(record)
 if code:status='BLOCKED_COMPILE';break
 text=subprocess.check_output(['/usr/bin/ninja','-C',str(build),'-t','deps',target],text=True);(p/'logs'/('first.'+name+'.deps.txt')).write_text(text)
 headers=[s.strip() for s in text.splitlines() if s.startswith('    ')];assert headers,'missing actual Ninja dependencies'
 logging=[];local=[]
 for s in headers:
  f=Path(s);f=f if f.is_absolute() else build/f;real=f.resolve()
  if str(real).startswith('/usr/local/'):local.append(str(real))
  if str(real).startswith(('/usr/include/spdlog/','/usr/include/fmt/')):
   sha=hashlib.sha256(f.read_bytes()).hexdigest();assert locked.get(str(real),{}).get('sha256')==sha
   logging.append({'dependency':str(f),'realpath':str(real),'sha256':sha})
 record.update({'dependency_count':len(headers),'local_headers':local,'logging_headers':logging,'object_sha256':hashlib.sha256((build/target).read_bytes()).hexdigest()})
 if local or not any('/spdlog/' in x['realpath'] for x in logging) or not any('/fmt/' in x['realpath'] for x in logging):status='BLOCKED_DEPENDENCIES';break
(p/'reports/first_units.json').write_text(json.dumps({'status':status,'units':records},indent=2)+'\n');print(json.dumps({'status':status,'units':[{k:v for k,v in x.items() if k!='logging_headers'} for x in records]},indent=2))
raise SystemExit(status!='PASS')
