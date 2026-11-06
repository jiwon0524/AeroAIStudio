from common import *
import shutil,re
for p in (OLD/'tests').glob('*'):
 if p.is_file() and p.suffix in ('.py','.cpp'):shutil.copyfile(p,R/'tests'/p.name)
shutil.copyfile(OLD/'trace_schema.py',R/'trace_schema.py')
script=(OLD/'scripts/compile_fixtures.py').read_text().replace('from inventory import R,OLD,run,save','from common import R,OLD,run,save').replace("headers=OLD/'work/headers/usr/include'","headers=R/'work/dependencies/usr/include'")
(R/'scripts/compile_fixtures.py').write_text(script)
audit={}
for p in (R/'tests').glob('*.cpp'):
 code=re.sub(r'//[^\n]*|/\*.*?\*/','',p.read_text(),flags=re.S)
 bad=re.findall(r'(?:\.|->)\s*step\s*\(|\b(?:system|popen|execve|execl)\s*\(',code)
 audit[p.name]={'sha256':sha(p),'forbidden_calls':bad};assert not bad
# Imported regression modules and guard were read; all runtime operations are mocked/fenced.
for name in ('tests/test_gazebo_action24_one_tick_control.py','tests/test_action24_collision_pair_integration.py','tools/host4_offline_test_guard.py'):
 p=ORIGINAL/name;audit[name]={'sha256':sha(p),'scope':'Read before tests. Runtime launch/transport and non-allowlisted subprocesses denied by explicit pytest plugin.'}
save('test_safety_review.json',audit)
print('Native source safety reviewed',len(audit))
