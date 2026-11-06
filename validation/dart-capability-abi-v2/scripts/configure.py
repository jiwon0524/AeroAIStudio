from common import *
import shutil,re
prefix=R/'work/dependencies';lib=prefix/'usr/lib/x86_64-linux-gnu'
env=os.environ.copy();env['PKG_CONFIG_PATH']=str(lib/'pkgconfig')+':'+str(prefix/'usr/lib/pkgconfig')
old=json.loads((OLD/'reports/configure_corrected.json').read_text());results=[]
for tag in ('baseline','trace'):
 src=R/f'work/{tag}-source';build=R/f'work/build-{tag}'
 shutil.copytree(OLD/f'work/{tag}-source',src,symlinks=True)
 before={str(p.relative_to(src)):sha(p) for p in src.rglob('*') if p.is_file()}
 command=next(x['command'] for x in old if x['tag']==tag)
 replaced=[]
 for a in command:
  a=a.replace(str(OLD/f'work/{tag}-source'),str(src)).replace(str(OLD/f'work/build-{tag}'),str(build)).replace(str(OLD/f'work/prefix-{tag}'),str(R/f'work/prefix-{tag}'))
  a=a.replace(str(IMPL/'work/headers/usr'),str(prefix/'usr')).replace(str(OLD/'work/dependency-prefix/include'),str(prefix/'usr/include'))
  replaced.append(a)
 env['LDFLAGS']=next(x['LDFLAGS'] for x in old if x['tag']==tag)
 result=run(replaced,env=env);result['source_files_sha256']=before;result['child_environment_overrides']={k:env[k] for k in ('PKG_CONFIG_PATH','LDFLAGS')};results.append(result)
 save('configure_results.json',results)
 if result['rc']:raise RuntimeError('Configure failed '+tag)
 header=(build/'dart/config.hpp').read_text()
 values={n:re.search(r'^#define '+n+r' (\d+)',header,re.M).group(1) for n in ('HAVE_IPOPT','HAVE_NLOPT','HAVE_ODE')}
 assert all(v=='1' for v in values.values()),values
 print(tag,values)
save('build_protocol.json',{'targets':['dart','dart-optimizer-ipopt','dart-optimizer-nlopt','dart-collision-ode'],'forbidden':['Gazebo','World::step','Stage B','install target','global loader change'],'source_changes':'NONE: copy of previously verified sources; no solver/instrumentation changes','parallel_jobs_per_build':4})
