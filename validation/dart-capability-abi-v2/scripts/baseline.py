from common import *
import ast
files={}
for root in (IMPL,OLD):
 for p in root.rglob('*'):
  if p.is_file():files[str(p)]=sha(p)
for d in ('src','tools','tests'):
 for p in (ORIGINAL/d).rglob('*'):
  if p.is_file() and '__pycache__' not in p.parts:files[str(p)]=sha(p)
oldbase=json.loads((IMPL/'baseline.json').read_text());previous={}
for group in ('evidence','source','system_libraries'):
 previous[group]=[]
 for p,h in oldbase[group].items():
  actual=Path(p) if Path(p).is_absolute() else ORIGINAL/p
  files[str(actual)]=sha(actual)
  if files[str(actual)]!=h:previous[group].append(p)
closure=json.loads((OLD/'reports/installed_closure_hashes_before.json').read_text())
for p in closure:files[p]=sha(p)
for p in (ORIGINAL/'AGENTS.md',ORIGINAL/'handoff.md',Path('/var/lib/dpkg/status')):files[str(p)]=sha(p)
raw=run(['git','status','--porcelain=v1','-z'],cwd=ORIGINAL)['stdout']
audit=[]
# Read every existing modified/untracked file; do not stage or relocate any of them.
for entry in raw.split('\0'):
 if not entry:continue
 name=entry[3:];p=ORIGINAL/name
 if not p.is_file():continue
 row={'path':name,'status':entry[:2],'sha256':sha(p),'bytes':p.stat().st_size,'ownership':'PREEXISTING_NOT_INCLUDED'}
 if p.suffix=='.py':
  tree=ast.parse(p.read_text());row['top_level_declarations']=[n.name for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef))]
 if entry[:2]!='??':row['diff']=run(['git','diff','--',name],cwd=ORIGINAL)['stdout']
 audit.append(row)
save('baseline_manifest.json',{'files':files,'original_git_status':raw,'original_head':run(['git','rev-parse','HEAD'],cwd=ORIGINAL)['stdout'].strip(),'prior_implementation_hash_comparison':previous,'installed_closure_comparison':{p:files[p]==h for p,h in closure.items()}})
save('preexisting_work_audit.json',audit)
save('initial_git.json',{'original':run(['git','status'],cwd=ORIGINAL),'worktree':run(['git','status'],cwd=R.parents[1]),'worktrees':run(['git','worktree','list'],cwd=ORIGINAL),'decision':'Separate experiment worktree. Original main/dirty files remain unchanged; no original uncommitted file is included in commits.'})
print('Preserved baseline files',len(files),'preexisting audited',len(audit),'previous differences',previous)
