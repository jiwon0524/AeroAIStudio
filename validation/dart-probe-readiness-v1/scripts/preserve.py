"""Read-only preservation manifests. Never follows directory symlinks."""
import hashlib,json,os,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
TASK=ROOT/'validation/dart-probe-readiness-v1'
MAIN=Path('/home/jiwon/Projects/AeroAIStudio')
def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()
def snapshot():
    files={}
    for root in (MAIN,ROOT):
        for base,dirs,names in os.walk(root):
            dirs[:]=[d for d in dirs if d not in ('.git','__pycache__') and not (Path(base)/d).is_symlink() and Path(base)/d != TASK]
            for name in names:
                p=Path(base)/name
                if root==ROOT and p==ROOT/'handoff.md': continue
                if p.is_symlink(): files[str(p)]='LINK:'+os.readlink(p)
                elif p.is_file(): files[str(p)]=digest(p)
    return {'files':files,'main_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=MAIN,text=True).strip(),'main_status':subprocess.check_output(['git','status','--porcelain=v1'],cwd=MAIN,text=True)}
if __name__=='__main__':
    import sys
    target=TASK/'work/preservation_before.json'
    if sys.argv[1]=='before': target.write_text(json.dumps(snapshot()))
    else:
        old=json.loads(target.read_text()); new=snapshot()
        changed=[p for p,h in old['files'].items() if new['files'].get(p)!=h]
        result={'baseline_files':len(old['files']),'changed_or_missing':changed,'main_head_unchanged':old['main_head']==new['main_head'],'main_status_unchanged':old['main_status']==new['main_status'],'new_existing_scope_files':sorted(set(new['files'])-set(old['files']))}
        result['status']='PASS' if not changed and result['main_head_unchanged'] and result['main_status_unchanged'] and not result['new_existing_scope_files'] else 'FAIL'
        (TASK/'reports/integrity.json').write_text(json.dumps(result,indent=2)+'\n'); print(json.dumps(result))
