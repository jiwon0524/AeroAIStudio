from pathlib import Path
import subprocess,json,hashlib,os
R=Path(__file__).resolve().parents[1]
ORIGINAL=Path('/home/jiwon/Projects/AeroAIStudio')
OLD=ORIGINAL/'validation/v071-host/gazebo-action24-dart-build-abi-parity-v1'
IMPL=ORIGINAL/'validation/v071-host/gazebo-action24-dart-internal-trace-v1-implementation'
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def save(name,data):
 p=R/'reports'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n')
def run(cmd,cwd=None,env=None):
 p=subprocess.run(list(map(str,cmd)),cwd=cwd,env=env,capture_output=True,text=True)
 return {'command':list(map(str,cmd)),'cwd':str(cwd) if cwd else None,'rc':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
