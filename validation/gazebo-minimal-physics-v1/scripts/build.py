"""Compile/link only; never execute any built artifact or target loader."""
from pathlib import Path
import subprocess,shlex,json,os,argparse
B=Path(__file__).resolve().parents[1]
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--observer-only',action='store_true');args=parser.parse_args()
 flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','gz-sim8'],text=True))
 includes=[]
 for x in flags:
  if x.startswith('-I'):includes+=['-isystem',x[2:]]
  else:includes.append(x)
 base=['/usr/bin/g++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-fstack-protector-strong']+includes
 outputs=[B/'work/gazebo_gate_server',B/'work/libaero_gate_observer.so']
 if any(os.path.lexists(p) for p in (outputs[1:] if args.observer_only else outputs)):raise ValueError('existing build output; no overwrite')
 cmds=[base+[str(B/'src/server.cc'),str(B/'src/adapter.cc'),'-Wl,-z,relro,-z,now','-lgz-sim8','-lsdformat14','-o',str(outputs[0])],
       base+['-shared','-fPIC',str(B/'src/observer.cc'),'-Wl,-z,relro,-z,now,-soname,libaero_gate_observer.so','-lgz-sim8','-lgz-plugin2','-lgz-math7','-o',str(outputs[1])]]
 results=[]
 selected=[(1,cmds[1])] if args.observer_only else list(enumerate(cmds))
 for i,cmd in selected:
  p=subprocess.run(cmd,capture_output=True,text=True)
  (B/f'work/build_{i}.stdout').write_text(p.stdout);(B/f'work/build_{i}.stderr').write_text(p.stderr)
  results.append({'argv':cmd,'returncode':p.returncode})
  if p.returncode:break
 (B/'reports/build_result.json').write_text(json.dumps({'steps':results,'previous_server_success':'reports/build_initial.json' if args.observer_only else None,'executed_artifacts':False},indent=2)+'\n')
 return 0 if len(results)==len(selected) and all(x['returncode']==0 for x in results) else 1
if __name__=='__main__':raise SystemExit(main())
