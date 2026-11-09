from pathlib import Path
import subprocess,json,shutil
r=Path(__file__).resolve().parents[1];old=r.parents[1]/'validation/gazebo-joint-codegen-fix-v1'
for p in (old/'inputs').glob('*.cmake'):
 if p.name!='toolchain.cmake':shutil.copy2(p,r/'inputs'/p.name)
a=json.loads((r/'reports/sim_configure_argv.json').read_text())
with (r/'logs/sim.configure.final.log').open('w') as f:code=subprocess.run(a,stdout=f,stderr=subprocess.STDOUT).returncode
print('configure',code);raise SystemExit(code)
