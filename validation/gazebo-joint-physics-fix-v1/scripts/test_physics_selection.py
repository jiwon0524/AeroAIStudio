from pathlib import Path
import shutil,tempfile,json,subprocess
p=Path(__file__).resolve().parents[1];build=p/'work/config-01/build/physics';source=(p/'scripts/check_selected_physics.py').read_text();reused=json.loads((p/'work/config-01/manifests/reused_elfs.json').read_text());oldprobe=next(k for k in reused if 'gazebo-joint-header-fix-v1' in k and 'aero-joint-probe' in k);out=[]
for case in ['unapproved_selected_library','changed_reused_hash','missing_contact_feature']:
 with tempfile.TemporaryDirectory(prefix='aero-physics-negative-',dir='/tmp') as directory:
  t=Path(directory);shutil.copytree(build/'.cmake',t/'.cmake');(t/'CMakeFiles').mkdir();shutil.copy2(build/'CMakeFiles/rules.ninja',t/'CMakeFiles/rules.ninja');shutil.copy2(build/'build.ninja',t/'build.ninja');shutil.copy2(build/'CMakeCache.txt',t/'CMakeCache.txt')
  code=source.replace("build=root/'build/physics'",'build=Path('+repr(str(t))+')').replace("(r/'reports/physics_selected_closure.json')",'Path('+repr(str(t/'result.json'))+')').replace("(r/'logs/physics.selected_commands.txt')",'Path('+repr(str(t/'commands.txt'))+')')
  if case=='unapproved_selected_library':
   reply=t/'.cmake/api/v1/reply';index=json.loads(next(reply.glob('index-*.json')).read_text());model=json.loads((reply/index['reply']['codemodel-v2']['jsonFile']).read_text());entry=next(x for x in model['configurations'][0]['targets'] if x['name']=='gz-physics7-dartsim-plugin');f=reply/entry['jsonFile'];v=json.loads(f.read_text());v['link']['commandFragments'].append({'fragment':'/usr/lib/x86_64-linux-gnu/libGLESv2.so','role':'libraries'});f.write_text(json.dumps(v));expected='unlocked file:'
  elif case=='changed_reused_hash':
   code=code.replace('def verify(path):',"reused_elfs["+repr(oldprobe)+"]='0'*64\ndef verify(path):");expected='reused predecessor hash mismatch'
  else:
   f=t/'CMakeCache.txt';f.write_text(f.read_text().replace('DART_HAS_CONTACT_SURFACE_HEADER:INTERNAL=1','DART_HAS_CONTACT_SURFACE_HEADER:INTERNAL='));expected='ContactSurface header check did not pass'
  proc=subprocess.run(['/usr/bin/python3','-S','-c','__file__='+repr(str(p/'scripts/check_selected_physics.py'))+'\n'+code],capture_output=True,text=True);data=json.loads((t/'result.json').read_text());assert proc.returncode==1 and any(expected in x for x in data['errors']),(case,proc.stderr,data)
  out.append({'case':case,'status':'PASS_REJECTED','errors':data['errors']})
(p/'reports/negative_tests.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
