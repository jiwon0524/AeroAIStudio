"""Compile/link public-header audit only. Never loads the resulting shared ELF."""
from pathlib import Path
import subprocess,shlex,json,os
B=Path(__file__).resolve().parents[1]
def main():
 out=B/'work/libpublic_api_audit.so'
 if os.path.lexists(out):raise ValueError('refuse overwrite')
 flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','gz-sim8'],text=True));includes=[]
 for x in flags:
  includes.extend(['-isystem',x[2:]] if x.startswith('-I') else [x])
 cmd=['/usr/bin/g++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-shared','-fPIC']+includes+[str(B/'src/public_api_audit.cc'),'-Wl,-z,relro,-z,now','-lgz-sim8','-o',str(out)]
 p=subprocess.run(cmd,capture_output=True,text=True)
 (B/'work/build.stdout').write_text(p.stdout);(B/'work/build.stderr').write_text(p.stderr)
 (B/'reports/build_result.json').write_text(json.dumps({'argv':cmd,'returncode':p.returncode,'artifact_executed_or_loaded':False,'scope':'public-header static assertions and link only'},indent=2)+'\n')
 return p.returncode
if __name__=='__main__':raise SystemExit(main())
