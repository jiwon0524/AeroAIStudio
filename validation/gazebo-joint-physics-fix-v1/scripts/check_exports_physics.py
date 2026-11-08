from pathlib import Path
import json,re,hashlib
p=Path(__file__).resolve().parents[1];root=p/'work/config-01';build=root/'build/physics';rows=[json.loads(l) for l in (root/'logs/physics.trace.jsonl').read_text().splitlines()];out={}
for target in ['gz-physics7','gz-physics7-sdf','gz-physics7-mesh','gz-physics7-heightmap','gz-physics7-dartsim','gz-physics7-dartsim-plugin']:
 regs=[x for x in rows if x.get('cmd','').lower()=='install' and x.get('args',[])[:2]==['EXPORT',target]];assert len(regs)==1,(target,regs)
 assert 'aero-joint-cmake' in regs[0]['args'] and 'gz-physics7::' in regs[0]['args']
 hits=[f for f in build.rglob(target+'-targets.cmake') if '/CMakeFiles/Export/' in str(f)];assert len(hits)==1,(target,hits)
 text=hits[0].read_text();names=re.findall(r'add_library\(([^\s]+)',text);assert names==['gz-physics7::'+target],(target,names)
 cfg=build/'cmake'/(target+'-config.cmake');assert cfg.is_file()
 out[target]={'registration':regs[0],'namespace':'gz-physics7::','exported_targets':names,'export_file':str(hits[0]),'export_sha256':hashlib.sha256(hits[0].read_bytes()).hexdigest(),'transitive_links':re.findall(r'INTERFACE_LINK_LIBRARIES "(.*?)"',text),'package_config_sha256':hashlib.sha256(cfg.read_bytes()).hexdigest()}
(p/'reports/physics_exports.json').write_text(json.dumps(out,indent=2)+'\n');print('PASS6 sole registrations; namespaces and target names retained')
