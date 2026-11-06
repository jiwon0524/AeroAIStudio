from common import *
import sys
p=R/'work/preservation.json'
if sys.argv[1]=='before':
 prior=json.loads((V3/'work/preservation.json').read_text());files={f:sha(f) for f in prior['files'] if Path(f).is_file()}
 for f in V3.rglob('*'):
  if f.is_file() and '__pycache__' not in f.parts:files[str(f)]=sha(f)
 p.write_text(json.dumps(dict(files=files,main_status=run(['git','-C',MAIN,'status','--porcelain'])['stdout'],main_head=run(['git','-C',MAIN,'rev-parse','HEAD'])['stdout'])));print('baseline',len(files))
else:
 d=json.loads(p.read_text());changed=[f for f,h in d['files'].items() if not Path(f).is_file() or sha(f)!=h];s=run(['git','-C',MAIN,'status','--porcelain'])['stdout']==d['main_status'];h=run(['git','-C',MAIN,'rev-parse','HEAD'])['stdout']==d['main_head'];o=dict(files_checked=len(d['files']),changed=changed,main_status_preserved=s,main_head_preserved=h,status='PASS' if not changed and s and h else 'FAIL');save('integrity.json',o);print(o)
