from evidence import *
import sys
MAIN=Path('/home/jiwon/Projects/AeroAIStudio'); EXP=ROOT.parents[1]
p=WORK/'preservation.json'
if sys.argv[1]=='before':
 old=json.loads((EXP/'validation/dart-destructor-cleanup-v4/work/preservation.json').read_text())
 files={f:sha(f) for f in old['files'] if Path(f).is_file()}
 missing=[f for f in old['files'] if not Path(f).is_file()]
 for f in (EXP/'validation/dart-destructor-cleanup-v4').rglob('*'):
  if f.is_file():files[str(f)]=sha(f)
 for f in [Path('/var/lib/dpkg/status'),*Path('/etc/apt/sources.list.d').glob('*'),*Path('/etc/ld.so.conf.d').glob('*')]:
  if f.is_file():files[str(f)]=sha(f)
 p.write_text(json.dumps(dict(files=files,prior_missing=missing,main_status=run(['git','-C',MAIN,'status','--porcelain'])['stdout'],main_head=run(['git','-C',MAIN,'rev-parse','HEAD'])['stdout'])))
 print('preservation baseline',len(files),'prior missing',len(missing))
else:
 d=json.loads(p.read_text());changed=[f for f,h in d['files'].items() if not Path(f).is_file() or sha(f)!=h]
 s=run(['git','-C',MAIN,'status','--porcelain'])['stdout']==d['main_status']; h=run(['git','-C',MAIN,'rev-parse','HEAD'])['stdout']==d['main_head']
 o=dict(files_checked=len(d['files']),changed=changed,prior_missing=d['prior_missing'],main_status_preserved=s,main_head_preserved=h,status='PASS' if not changed and s and h and not d['prior_missing'] else 'FAIL');save('integrity.json',o);print(o)
