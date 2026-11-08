from pathlib import Path
import json,re,hashlib
p=Path(__file__).resolve().parents[1];root=p/'work/config-01';rows=[json.loads(l) for l in (root/'logs/dart.trace.jsonl').read_text().splitlines()];out={}
for c in ['dart','external-odelcpsolver','collision-ode','collision-bullet','utils','utils-urdf']:
 name='dart_component_'+c;target='dart' if c=='dart' else 'dart-'+c
 regs=[x for x in rows if x.get('cmd')=='install' and x.get('args',[])[:2]==['EXPORT',name]]
 members=[x for x in rows if x.get('cmd')=='install' and 'EXPORT' in x.get('args',[]) and name in x['args'] and x['args'][0]=='TARGETS']
 assert len(regs)==len(members)==1,(c,regs,members)
 assert 'aero-joint-cmake' in regs[0]['args'];assert target in members[0]['args']
 files=list((root/'build/dart').rglob('dart_'+c+'Targets.cmake'));assert len(files)==1,(c,files)
 text=files[0].read_text();targets=re.findall(r'add_library\(([^\s]+)',text);assert targets==[target],(c,targets)
 comp=root/'build/dart/share/dart/cmake'/('dart_'+c+'Component.cmake')
 out[c]={'registration':regs[0],'membership':members[0],'target':target,'namespace':'','export_path':str(files[0]),'export_sha256':hashlib.sha256(files[0].read_bytes()).hexdigest(),'component':comp.read_text(),'transitive_properties':re.findall(r'INTERFACE_LINK_LIBRARIES "(.*?)"',text)}
(p/'reports/export_validation.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:{'target':v['target'],'transitive':v['transitive_properties']} for k,v in out.items()},indent=2))
