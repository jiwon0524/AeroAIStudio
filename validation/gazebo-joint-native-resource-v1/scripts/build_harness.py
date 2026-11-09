from pathlib import Path
import hashlib,json,shlex,subprocess,shutil
R=Path(__file__).resolve().parents[1];B=R.parents[1];old=B/'validation/gazebo-joint-codegen-fix-v1';prefix=R/'work/prefix';prior=B/'validation/gazebo-joint-resolution-v1'
plan=json.loads((prior/'reports/actual_plan.json').read_text());system,engine=plan['payload'][2:4]
chosen={'physics':(system,prefix/'lib/gz-sim-8/plugins/libgz-sim8-physics-system.so.8.15.0'),'dartsim':(engine,Path(engine))}
header=''
for role,(dest,p) in chosen.items():
 s=p.stat();digest=hashlib.sha256(p.read_bytes()).hexdigest();header+='aero_resource::Expect('+','.join([json.dumps(role),json.dumps(dest),str(s.st_dev),str(s.st_ino),json.dumps(digest)])+');\n'
(R/'inputs/plugin_expectations.hh').write_text(header)
source=(prior/'inputs/harness_ack.cc').read_text().replace('// Candidate only: compilation/loading/execution has NOT been performed.', '// Native resource candidate: compile/link only; never executed.').replace('#include "fixture.hh"','#include "native_resource.hh"\n#include <tinyxml2.h>\n#include "fixture.hh"')
source=source.replace('  gz::sim::ServerConfig config;','''  #include "plugin_expectations.hh"
  const auto configBytes = aero_resource::Config();
  tinyxml2::XMLDocument configXml;
  const bool configOk = configXml.Parse(configBytes.data(), configBytes.size()) == tinyxml2::XML_SUCCESS;
  auto *configRoot = configXml.RootElement();
  aero_resource::Outcome("server_config_parse", configOk && configRoot &&
      std::string(configRoot->Name()) == "server_config" && !configRoot->FirstChildElement(), configOk ? 0 : 1);
  gz::sim::ServerConfig config;''')
(R/'inputs/harness_native.cc').write_text(source);shutil.copy2(prior/'inputs/exit_ack.h',R/'inputs/exit_ack.h')
row=json.loads((old/'work/config-01/build/harness/compile_commands.json').read_text())[0];a=shlex.split(row['command']);a[a.index('-c')+1]=str(R/'inputs/harness_native.cc');a[a.index('-o')+1]=str(R/'work/harness_native.o');a+=['-I'+str(R/'inputs'),'-MD','-MF',str(R/'work/harness_native.d')]
a=[str(prefix/'include/gz/sdformat14') if x=='/usr/include/gz/sdformat14' else x for x in a]
commands=[a]
text=subprocess.check_output(['/usr/bin/ninja','-C',str(old/'work/config-01/build/harness'),'-t','commands','aero-joint-harness'],text=True)
link=shlex.split(text.splitlines()[-1].split('&&')[1].strip());link=[str(R/'work/harness_native.o') if t=='CMakeFiles/aero-joint-harness.dir/harness.cc.o' else t for t in link];link[link.index('-o')+1]=str(R/'work/aero-joint-harness-native')
link=[str(prefix/'lib/libgz-sim8.so.8.15.0') if t.endswith('/lib/libgz-sim8.so.8.15.0') else str(prefix/'lib/libsdformat14.so.14.9.0') if t=='/usr/lib/x86_64-linux-gnu/libsdformat14.so.14.9.0' else t for t in link]
link=[('-Wl,-rpath,'+str(prefix/'lib')+':'+t.split(',',2)[2]) if t.startswith('-Wl,-rpath,') else t for t in link]
link+=['-Wl,-rpath,'+str(prefix/'lib'),str(prefix/'lib/libaero-resource.so'),'-ltinyxml2'];commands.append(link)
(R/'reports/harness_commands.json').write_text(json.dumps(commands,indent=2)+'\n')
for label,argv in zip(['compile','link'],commands):
 with (R/'logs'/('harness.'+label+'.log')).open('w') as f:code=subprocess.run(argv,cwd=old/'work/config-01/build/harness',stdout=f,stderr=subprocess.STDOUT).returncode
 print(label,code)
 if code:raise SystemExit(code)
