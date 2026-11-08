"""Negative metadata tests in disposable copies; never compile or execute targets."""
from pathlib import Path
import shutil,tempfile,json,subprocess,hashlib
p=Path(__file__).resolve().parents[1];build=p/'work/config-01/build/dart';source=(p/'scripts/check_selected_dart.py').read_text();out=[]
for case in ['unlocked_selected_library','unresolved_tinyxml2_configuration']:
 with tempfile.TemporaryDirectory(prefix='aero-selection-negative-',dir='/tmp') as folder:
  temp=Path(folder);shutil.copytree(build/'.cmake',temp/'.cmake');shutil.copytree(build/'joint-targets',temp/'joint-targets');(temp/'CMakeFiles').mkdir();shutil.copy2(build/'CMakeFiles/rules.ninja',temp/'CMakeFiles/rules.ninja');shutil.copy2(build/'build.ninja',temp/'build.ninja')
  reply=temp/'.cmake/api/v1/reply';index=json.loads(next(reply.glob('index-*.json')).read_text());model=json.loads((reply/index['reply']['codemodel-v2']['jsonFile']).read_text());targets=model['configurations'][0]['targets'];entry=next(x for x in targets if x['name']=='dart-utils');file=reply/entry['jsonFile'];target=json.loads(file.read_text())
  if case=='unlocked_selected_library':target['link']['commandFragments'].append({'fragment':'/usr/lib/x86_64-linux-gnu/libGLESv2.so','role':'libraries'})
  else:
   for group in target['compileGroups']:group['defines']=[x for x in group.get('defines',[]) if x['define']!='TINYXML2_IMPORT']
  file.write_text(json.dumps(target))
  code=source.replace("build=root/'build/dart'",'build=Path('+repr(str(temp))+')').replace("(r/'reports/dart_selected_closure.json')",'Path('+repr(str(temp/'result.json'))+')').replace("(r/'logs/dart.selected_commands.txt')",'Path('+repr(str(temp/'commands.txt'))+')')
  launcher='__file__='+repr(str(p/'scripts/check_selected_dart.py'))+'\n'+code
  result=subprocess.run(['/usr/bin/python3','-S','-c',launcher],capture_output=True,text=True)
  record=json.loads((temp/'result.json').read_text());assert result.returncode==1
  expected='unlocked file:' if case.startswith('unlocked') else 'tinyxml2 effective definition mismatch'
  assert any(expected in x for x in record['errors']),record
  out.append({'case':case,'status':'PASS_REJECTED','errors':record['errors']})
(p/'reports/negative_tests.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
