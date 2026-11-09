from pathlib import Path
import json,hashlib,subprocess,shutil
R=Path(__file__).resolve().parents[1];B=R.parents[1];N=B/'validation/gazebo-joint-native-resource-v1'
old=json.loads((B/'validation/gazebo-joint-resolution-v1/reports/actual_plan.json').read_text());header=''
for role,dest,p in [('physics',old['payload'][2],R/'work/prefix/lib/libgz-sim8-physics-system.so.8.15.0'),('dartsim',old['payload'][3],Path(old['payload'][3]))]:
 s=p.stat();header+='aero_resource::Expect('+','.join([json.dumps(role),json.dumps(dest),str(s.st_dev),str(s.st_ino),json.dumps(hashlib.sha256(p.read_bytes()).hexdigest())])+');\n'
(R/'inputs/plugin_expectations.hh').write_text(header)
for name in ['harness_native.cc','fixture.hh','exit_ack.h','native_resource.hh']:shutil.copy2(N/'inputs'/name,R/'inputs'/name)
commands=json.loads((N/'reports/harness_commands.json').read_text())
for a in commands:
 for i,x in enumerate(a):
  if x==str(N/'inputs/harness_native.cc'):a[i]=str(R/'inputs/harness_native.cc')
  elif x==str(N/'work/harness_native.o'):a[i]=str(R/'work/harness.o')
  elif x==str(N/'work/harness_native.d'):a[i]=str(R/'work/harness.d')
  elif x==str(N/'work/aero-joint-harness-native'):a[i]=str(R/'work/aero-joint-harness')
  elif x==str(N/'work/prefix/lib/libgz-sim8.so.8.15.0'):a[i]=str(R/'work/prefix/lib/libgz-sim8.so.8.15.0')
 a+=['-I'+str(R/'inputs')] if '-c' in a else ['-Wl,-rpath,'+str(R/'work/prefix/lib')]
 if '-c' not in a:a[:]=[('-Wl,-rpath,'+str(R/'work/prefix/lib')+':'+x.split(',',2)[2]) if x.startswith('-Wl,-rpath,') and str(R/'work/prefix/lib') not in x else x for x in a]
for label,a in zip(['compile','link'],commands):
 with (R/'logs'/('harness.'+label+'.log')).open('x') as f:rc=subprocess.run(a,cwd=B/'validation/gazebo-joint-codegen-fix-v1/work/config-01/build/harness',stdout=f,stderr=subprocess.STDOUT,env={'PATH':'/usr/bin:/bin','LC_ALL':'C'}).returncode
 print('harness',label,rc)
 if rc:raise SystemExit(rc)
(R/'reports/harness_commands.json').write_text(json.dumps(commands,indent=2)+'\n')
