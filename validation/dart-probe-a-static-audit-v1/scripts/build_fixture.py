"""Build only. The loader-enabled object is never linked or executed here."""
import hashlib,json,subprocess
from pathlib import Path
B=Path(__file__).resolve().parents[1];W=B/'work';R=B/'reports'
def build():
 source=B/'fixtures/probe_a.c';commands=[['/usr/bin/cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-fstack-protector-strong','-Wl,-z,relro,-z,now',str(source),'-o',str(W/'fixture_offline')],['/usr/bin/cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-DPROBE_A_LOADER_ENABLED=1','-c',str(source),'-o',str(W/'loader_review_only.o')]]
 results=[]
 for command in commands:
  p=subprocess.run(command,capture_output=True,text=True,timeout=60);results.append({'command':command,'rc':p.returncode,'stdout':p.stdout,'stderr':p.stderr})
  if p.returncode:break
 (R/'fixture_build.json').write_text(json.dumps(results,indent=2)+'\n')
 if any(r['rc'] for r in results):raise SystemExit(1)
 meta={}
 for name in ('fixture_offline','loader_review_only.o'):
  p=W/name;meta[name]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size,'executed':False}
 (R/'fixture_artifacts.json').write_text(json.dumps(meta,indent=2)+'\n')
if __name__=='__main__':build()
