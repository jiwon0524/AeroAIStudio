from pathlib import Path
import subprocess,shlex,runpy,json
p=Path(__file__).resolve().parents[1];build=p/'work/config-01/build/sim-03';text=subprocess.check_output(['/usr/bin/ninja','-C',str(build),'-t','commands','gz_msgs_gen/gz/sim/private_msgs/register.cc'],text=True)
cmd=next(shlex.split(x.strip()) for line in text.splitlines() for x in line.split('&&') if 'gz-msgs10_generate.py' in x);out=[]
for case in ['original_descriptor_path_rejected','extra_descriptor_rejected','changed_tool_hash_rejected']:
 v=runpy.run_path(str(p/'scripts/codegen_inputs.py'));argv=cmd[:];v['validate'](argv)
 if case=='original_descriptor_path_rejected':argv[argv.index('--dependency-proto-descs')+1]='/usr/share/gz/protos/gz-msgs10.gz_desc'
 elif case=='extra_descriptor_rejected':argv.insert(argv.index('--dependency-proto-descs')+2,'/usr/share/gz/protos/other.gz_desc')
 else:v['allowed'][str(Path('/usr/bin/gz-msgs10_protoc_plugin').resolve())]='0'*64
 try:v['validate'](argv)
 except (AssertionError,KeyError,ValueError) as error:out.append({'case':case,'status':'PASS_REJECTED','reason':str(error)})
 else:raise AssertionError('invalid codegen invocation accepted')
(p/'reports/negative_tests.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
