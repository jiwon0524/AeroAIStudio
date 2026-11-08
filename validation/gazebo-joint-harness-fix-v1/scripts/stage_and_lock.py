"""Offline header audit, separate binary/world deployment and ELF manifest.
No loader, ldd, target run or marker access.
"""
from pathlib import Path
import json,hashlib,subprocess,shutil,re,runpy
b=Path.cwd();p=b/'validation/gazebo-joint-harness-fix-v1';r=b/'validation/gazebo-joint-codegen-fix-v1';root=r/'work/config-01';build=root/'build/harness';prefix=p/'work/prefix'
def sha(f):return hashlib.sha256(Path(f).read_bytes()).hexdigest()
assert all(x['returncode']==0 for x in json.loads((p/'reports/steps.json').read_text()));assert len(json.loads((p/'reports/steps.json').read_text()))==2
m=runpy.run_path(str(r/'scripts/check_selection_harness.py'));gate=m['Gate']()
text=subprocess.check_output(['/usr/bin/ninja','-C',str(build),'-t','deps'],text=True);(p/'logs/harness.actual_deps.txt').write_text(text)
headers=sorted({str((Path(s.strip()) if Path(s.strip()).is_absolute() else build/s.strip()).resolve()) for s in text.splitlines() if s.startswith('    ')})
assert len([s for s in text.splitlines() if s and not s.startswith(' ')])==1
for name in headers:gate.verify(name)
assert not gate.errors,gate.errors
(p/'reports/actual_headers.json').write_text(json.dumps({'status':'PASS','object_records':1,'unique_dependencies':len(headers),'local_headers':[],'files':{h:sha(h) for h in headers},'dep_metadata_sha256':hashlib.sha256(text.encode()).hexdigest()},indent=2)+'\n')
exe=build/'aero-joint-harness';engine=root/'prefix/lib/gz-physics-7/engine-plugins/libgz-physics7-dartsim-plugin.so.7.8.0';system=root/'prefix/lib/gz-sim-8/plugins/libgz-sim8-physics-system.so.8.15.0'
fixture=(r/'inputs/fixture.sdf.in').read_text();embedded=(r/'inputs/fixture.hh').read_text().split('R"AERO(',1)[1].split(')AERO"',1)[0];assert embedded==fixture
world=fixture.replace('@SYSTEM@',str(system)).replace('@ENGINE@',str(engine));assert '@SYSTEM@' not in world and '@ENGINE@' not in world
# Existing binary has a compiled stack-prefix binding. Preserve it; separate
# deployment holds binary/world, while the immutable stack stays in its prefix.
if prefix.exists():
 assert sha(exe)==sha(prefix/'bin/aero-joint-harness')
 assert (prefix/'share/aero/world.sdf').read_text()==world
 assert sha(r/'inputs/fixture.sdf.in')==sha(prefix/'share/aero/world.sdf.in')
else:
 (prefix/'bin').mkdir(parents=True);(prefix/'share/aero').mkdir(parents=True)
 shutil.copy2(exe,prefix/'bin/aero-joint-harness');(prefix/'share/aero/world.sdf').write_text(world);shutil.copy2(r/'inputs/fixture.sdf.in',prefix/'share/aero/world.sdf.in')
assert sha(exe)==sha(prefix/'bin/aero-joint-harness')
receipt=json.loads((root/'manifests/staged.json').read_text());reused=json.loads((root/'manifests/reused_elfs.json').read_text());reuse_runpaths=json.loads((root/'manifests/reused_runpaths.json').read_text())
allowed={str(Path(k).resolve()):v['sha256'] for k,v in json.loads((r/'work/selected_files.json').read_text()).items()}
for x in json.loads((b/'validation/gazebo-joint-inputs-v1/reports/tool_elf_closure.json').read_text())['files']:allowed[x['path']]=x['sha256']
expected_search=[str(root/'prefix/lib'),str((r/'work/deps').resolve()/'usr/lib/x86_64-linux-gnu')]
seeds={'executable':prefix/'bin/aero-joint-harness','physics_system':system,'dartsim_engine':engine};queue=list(seeds.values());seen={}
while queue:
 f=queue.pop().resolve();name=str(f)
 if name in seen:continue
 digest=sha(f);row=receipt.get(name);reuse=reused.get(name);owned=f==seeds['executable'] or row is not None or reuse is not None
 if row:assert digest==row['sha256']==sha(row['source']),name
 elif reuse:assert digest==reuse,name
 elif f!=seeds['executable']:
  assert not re.match(r'lib(?:dart|gz-(?:sim8|physics7))',f.name),'installed subject ELF '+name
  assert allowed.get(name)==digest,'unlocked ELF '+name
 metadata=subprocess.check_output(['readelf','-d','-n','-h',name],text=True)
 rpath=re.findall(r'Library rpath: \[(.*?)\]',metadata);runpath=re.findall(r'Library runpath: \[(.*?)\]',metadata)
 if owned:
  assert not rpath,name
  expected=reuse_runpaths[name] if reuse else [':'.join(expected_search)]
  assert runpath==expected,(name,runpath,expected)
 needed=re.findall(r'Shared library: \[(.*?)\]',metadata);edges=[]
 search=[Path(x.replace('${ORIGIN}',str(f.parent)).replace('$ORIGIN',str(f.parent))) for value in rpath+runpath for x in value.split(':') if x]
 for soname in needed:
  candidates=[d/soname for d in search+[root/'prefix/lib',(r/'work/deps').resolve()/'usr/lib/x86_64-linux-gnu',Path('/usr/lib/x86_64-linux-gnu'),Path('/lib/x86_64-linux-gnu'),Path('/usr/lib')] if (d/soname).is_file()];assert candidates,(name,soname)
  target=candidates[0].resolve();edges.append({'soname':soname,'path':str(target)});queue.append(target)
 seen[name]={'sha256':digest,'size':f.stat().st_size,'build_id':re.findall(r'Build ID: ([a-f0-9]+)',metadata),'soname':re.findall(r'Library soname: \[(.*?)\]',metadata),'type':re.findall(r'Type:\s+(.*)',metadata),'rpath':rpath,'runpath':runpath,'needed':edges}
record={'status':'PASS_STATIC_BUILD_AND_DEPLOYMENT','executable':str(seeds['executable']),'source_build':str(exe),'build_prefix_identical':True,'sha256':sha(exe),'world':{'path':str(prefix/'share/aero/world.sdf'),'sha256':sha(prefix/'share/aero/world.sdf'),'template_sha256':sha(r/'inputs/fixture.sdf.in'),'embedded_template_identical':True,'use':'review artifact; harness constructs the same world from embedded template and plugin argv'},'plugins':{k:str(v) for k,v in seeds.items() if k!='executable'},'compiled_stack_prefix':str(root/'prefix'),'standalone_relocatable':False,'ELFs':seen,'scope':'static DT_NEEDED resolution with fixed search/receipt hashes; actual loader maps and dynamic plugins NOT_RUNTIME_VERIFIED'}
(p/'reports/final_manifest.json').write_text(json.dumps(record,indent=2)+'\n');print('PASS deployed byte-identical harness, world and',len(seen),'ELF closure files;',len(headers),'actual headers');print('harness SHA',record['sha256']);print('Build ID',seen[str(seeds['executable'])]['build_id'])
