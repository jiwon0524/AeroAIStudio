from common import *
import re
prefix=R/'work/dependencies';configs={};profiles={}
configs['installed']=(IMPL/'work/headers/usr/include/dart/config.hpp').read_text()
for tag in ('baseline','trace'):
 b=R/f'work/build-{tag}-final';configs[tag]=(b/'dart/config.hpp').read_text()
 profiles[tag]={'flags':(b/'dart/CMakeFiles/dart.dir/flags.make').read_text(),'link':(b/'dart/CMakeFiles/dart.dir/link.txt').read_text(),'cache_selected':[l for l in (b/'CMakeCache.txt').read_text().splitlines() if re.match(r'^(CMAKE_(BUILD_TYPE|CXX_COMPILER|CXX_FLAGS|SHARED_LINKER_FLAGS|INSTALL_PREFIX)|HAVE_|IPOPT_|NLOPT_|ODE_|fmt_DIR|spdlog_DIR)',l)]}
 definitions={k:dict(re.findall(r'^#define\s+(\w+)\s+([^\n]+)',v,re.M)) for k,v in configs.items()}
 # Compiler dependency files are authoritative for actual selected headers.
 deps=list((b/'dart/CMakeFiles/dart.dir').rglob('*.o.d'))
 profiles[tag]['actual_dependencies']={'files':len(deps),'local_spdlog8_references':[str(p) for p in deps if '/usr/local/include/spdlog' in p.read_text()],'isolated_fmt9_reference_files':sum('/format-prefix/include/fmt/' in p.read_text() for p in deps)}
macro=run(['g++','-dM','-E','-x','c++','-include','string','/dev/null'])['stdout']
selected=[l for l in macro.splitlines() if re.match(r'^#define (__cplusplus|__GNUC__|__GNUC_MINOR__|_GLIBCXX_USE_CXX11_ABI|__GLIBCXX__) ',l)]
changes={key:{k:definitions[k].get(key) for k in definitions} for key in set().union(*[d.keys() for d in definitions.values()]) if len({d.get(key) for d in definitions.values()})>1}
save('build_profile.json',{'profiles':profiles,'config_differences':changes,'capabilities':{k:{n:v.get(n) for n in ('HAVE_IPOPT','HAVE_NLOPT','HAVE_ODE')} for k,v in definitions.items()},'compiler':run(['g++','--version']),'linker':run(['ld','--version']),'CXX_macros':selected,'installed_debug_sections':run(['readelf','-SW','/usr/lib/x86_64-linux-gnu/libdart.so.6.13.2'])['stdout'],'original_buildinfo_compiler':'UNVERIFIED: installed binary stripped, original buildinfo/compiler flags unavailable'})
print('Capability/config summary', {k:{n:v.get(n) for n in ('HAVE_IPOPT','HAVE_NLOPT','HAVE_ODE')} for k,v in definitions.items()},'config differences',list(changes))
