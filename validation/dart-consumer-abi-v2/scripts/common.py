from pathlib import Path
import subprocess,hashlib,json,os
R=Path(__file__).resolve().parents[1]
V=R.parent/'dart-capability-abi-v2'
V1=R.parent/'dart-consumer-abi-v1'
MAIN=Path('/home/jiwon/Projects/AeroAIStudio')
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def run(args,env=None,cwd=None,timeout=120):
 p=subprocess.run(list(map(str,args)),env=env,cwd=cwd,capture_output=True,text=True,timeout=timeout)
 return dict(command=list(map(str,args)),rc=p.returncode,stdout=p.stdout,stderr=p.stderr)
def save(n,o):
 p=R/'reports'/n;p.write_text(json.dumps(o,indent=2,ensure_ascii=False)+'\n')
def libs():return {'A':Path('/usr/lib/x86_64-linux-gnu/libdart.so.6.13.2'),'B':V/'work/build-baseline-final/lib/libdart.so.6.13.2','C':V/'work/build-trace-final/lib/libdart.so.6.13.2','Bullet':Path('/usr/lib/x86_64-linux-gnu/libdart-collision-bullet.so.6.13.2'),'Gazebo':Path('/usr/lib/x86_64-linux-gnu/gz-physics-7/engine-plugins/libgz-physics7-dartsim-plugin.so.7.8.0')}
