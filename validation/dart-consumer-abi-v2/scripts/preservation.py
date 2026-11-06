from common import *
import sys
manifest=R/'work/preservation.json'
if sys.argv[1]=='before':
 files={}
 # Reuse V1's explicit original manifest as an input, but take fresh hashes.
 prior=json.loads((V1/'work/preservation.json').read_text())['files']
 for f in prior:
  if Path(f).is_file():files[f]=sha(f)
 for root in [V1,V]:
  for p in root.rglob('*'):
   if p.is_file() and '__pycache__' not in p.parts:files[str(p)]=sha(p)
 for p in libs().values():files[str(p)]=sha(p)
 files[str(MAIN/'AGENTS.md')]=sha(MAIN/'AGENTS.md');files[str(MAIN/'handoff.md')]=sha(MAIN/'handoff.md')
 data=dict(files=files,main_status=run(['git','-C',MAIN,'status','--porcelain'])['stdout'],main_head=run(['git','-C',MAIN,'rev-parse','HEAD'])['stdout'])
 manifest.write_text(json.dumps(data));print('baseline',len(files))
else:
 d=json.loads(manifest.read_text());changed=[p for p,h in d['files'].items() if not Path(p).is_file() or sha(p)!=h]
 status=run(['git','-C',MAIN,'status','--porcelain'])['stdout']==d['main_status'];head=run(['git','-C',MAIN,'rev-parse','HEAD'])['stdout']==d['main_head']
 o=dict(files_checked=len(d['files']),changed=changed,main_status_preserved=status,main_head_preserved=head,status='PASS' if not changed and status and head else 'FAIL');save('integrity.json',o);print(o)
