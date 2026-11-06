from analyze import *
import sys
p=R/'work/preservation.json'
if sys.argv[1]=='before':
 files={}
 roots=[Path('/home/jiwon/Projects/AeroAIStudio'),V]
 for root in roots:
  for folder in (['src','tools','tests','validation','worlds','config'] if root==roots[0] else ['reports','tests','work/baseline-source','work/trace-source']):
   for f in (root/folder).rglob('*'):
    if f.is_file() and '__pycache__' not in f.parts:files[str(f)]=sha(f)
 for f in [Path('/var/lib/dpkg/status'),roots[0]/'AGENTS.md',roots[0]/'handoff.md']:
  files[str(f)]=sha(f)
 for arm in json.loads((R/'reports/provider_inventory.json').read_text()).values():
  for x in arm:files[x['path']]=sha(x['path'])
 p.write_text(json.dumps({'files':files,'main_status':run(['git','-C',roots[0],'status','--porcelain'])['stdout']},indent=2))
 print('baseline',len(files))
else:
 b=json.loads(p.read_text());changed=[f for f,h in b['files'].items() if not Path(f).is_file() or sha(f)!=h]
 same=run(['git','-C','/home/jiwon/Projects/AeroAIStudio','status','--porcelain'])['stdout']==b['main_status']
 save('integrity.json',dict(files_checked=len(b['files']),changed=changed,main_status_preserved=same,status='PASS' if not changed and same else 'FAIL',scope='New before/after hashes; no comparison to stale V2 baseline'))
 print('integrity',len(changed),same)
