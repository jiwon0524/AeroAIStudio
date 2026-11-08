"""Seal implementation/plan and audit bridge compilation. No target execution."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import *
import os,shlex,subprocess,ast

def main():
 need(sys.argv[1:]==['--seal-preparation'],'explicit preparation seal required')
 tools=json.loads((ROOT/'validation/gazebo-joint-inputs-v1/reports/toolchain_files.json').read_text())
 allowed={x['realpath']:x['sha256'] for x in tools};allowed.update({str(Path(k).resolve()):v['sha256'] for k,v in json.loads((ROOT/'validation/gazebo-joint-codegen-fix-v1/work/selected_files.json').read_text()).items()})
 compiler=Path('/usr/bin/x86_64-linux-gnu-gcc-13').resolve();need(sha(compiler)==allowed[str(compiler)],'compiler hash changed')
 dep=(B/'work/fd_bridge.d').read_text().replace('\\\n',' ');deps=shlex.split(dep.split(':',1)[1]);headers={}
 for name in deps:
  f=Path(name).resolve()
  if f==B/'inputs/fd_bridge.c':continue
  need(not str(f).startswith('/usr/local/') and allowed.get(str(f))==sha(f),'unlocked shim header '+str(f));headers[str(f)]=sha(f)
 shim=B/'work/fd_bridge';text=subprocess.check_output(['/usr/bin/readelf','-h','-d','-l','-n',str(shim)],text=True)
 need('libc.so.6' in text and '[Requesting program interpreter: /lib64/ld-linux-x86-64.so.2]' in text,'shim ELF metadata')
 need('Library rpath:' not in text and 'Library runpath:' not in text,'shim search path')
 files=list((B/'scripts').glob('*.py'))+list((B/'tests').glob('*.py'))+list((B/'inputs').glob('*.c'))+[B/'inputs/joint-elf.sha256',B/'reports/plan.json',B/'reports/ordered_argv.json']
 # Also seal reused code, including helpers imported by the legacy integration.
 reused=['validation/dart-probe-a-harness-v1/scripts/identity.py','validation/dart-probe-a-harness-v1/scripts/mapped.py','validation/gazebo-minimal-physics-v1/scripts/gate.py','validation/dart-cgroup-smoke-v1/scripts/smoke.py','validation/dart-cgroup-integration-v1/scripts/integration.py']
 files += [ROOT/x for x in reused]
 for f in files:
  if f.suffix=='.py':ast.parse(f.read_text(),filename=str(f))
 record={'status':'SEALED_PREPARATION_ONLY','files':{str(f.relative_to(ROOT)):sha(f) for f in sorted(files)},'bridge_sha256':sha(shim)}
 dump(B/'reports/source_pin.json',record);(B/'inputs/source_pin.sha256').write_text(sha(B/'reports/source_pin.json')+'\n')
 dump(B/'reports/bridge_compile.json',{'status':'PASS_COMPILE_AND_STATIC_ONLY','compiler':str(compiler),'compiler_sha256':sha(compiler),'headers':headers,'ELF_sha256':sha(shim),'ELF_metadata':text,'target_execution':False,'compile_argv':['/usr/bin/x86_64-linux-gnu-gcc-13','-std=c17','-O2','-fPIE','-pie','-Wall','-Wextra','-Werror','-Wl,-z,relro,-z,now','-MD','-MF','validation/gazebo-joint-isolation-v1/work/fd_bridge.d','validation/gazebo-joint-isolation-v1/inputs/fd_bridge.c','-o','validation/gazebo-joint-isolation-v1/work/fd_bridge']})
 print('PASS source seal and bridge compile/static audit',len(headers),'headers')
if __name__=='__main__':main()
