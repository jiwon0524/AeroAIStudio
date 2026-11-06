from common import *
import shutil
initial=json.loads((R/'reports/configure_results.json').read_text());fmt=R/'work/format-prefix/include'
fmt.mkdir(parents=True)
for name in ('fmt','spdlog'):shutil.copytree(R/'work/dependencies/usr/include'/name,fmt/name)
results=[]
for tag,record in zip(('baseline','trace'),initial):
 args=[a.replace(str(R/f'work/build-{tag}'),str(R/f'work/build-{tag}-final')) for a in record['command']]
 args=[a.replace('-I'+str(R/'work/dependencies/usr/include'),'-I'+str(fmt)) if a.startswith('-DCMAKE_CXX_FLAGS=') else a for a in args]
 env=os.environ.copy();env.update(record['child_environment_overrides'])
 result=run(args,env=env);result['child_environment_overrides']=record['child_environment_overrides'];results.append(result)
 save('configure_final.json',results);assert result['rc']==0
flags=(R/'work/build-baseline-final/dart/CMakeFiles/dart.dir/flags.make').read_text()
assert '-I'+str(fmt) in flags and '-isystem '+str(R/'work/dependencies/usr/include') in flags
save('build_failure_resolution.json',{'initial_failure':'Octomap std::iterator deprecated declaration under -Werror','cause':'Combined dependency prefix was passed as -I, demoting third-party headers from prior SYSTEM classification','resolution':'Separate fmt/spdlog-only normal include prefix; all other imported headers retain -isystem. Werror retained, source/algorithms unmodified. New final build dirs preserve initial failed objects/logs.','compiler_warning_suppression_added':False,'source_modified':False})
print('Final configs restored prior external header classification; no warning suppression')
