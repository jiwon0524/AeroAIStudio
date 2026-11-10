"""Trusted startup evidence, distinct from independent native execution audit.
Missing/failed diagnostics can only reject a run; never replace audit authority.
"""
from common import *
import stat,re
CAP=16384
FLAGS=os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC

def private_log(path,append=False):
    return os.fdopen(os.open(path,FLAGS|(os.O_APPEND if append else 0),0o600),'wb',buffering=0)

class Progress:
    def __init__(self,path,run,digest):
        self.file=private_log(path,True);self.run=run;self.digest=digest;self.count=0;self.bytes=0
    def record(self,stage,**fields):
        row=dict(seq=self.count+1,run=self.run,contract_sha256=self.digest,stage=stage,**fields)
        data=canonical(row);need(self.bytes+len(data)<=CAP,'startup diagnostics cap')
        need(self.file.write(data)==len(data),'startup diagnostics short write')
        os.fdatasync(self.file.fileno());self.count+=1;self.bytes+=len(data);return True
    def close(self):self.file.close()

def validate_progress(path,run,digest,required):
    p=Path(path);st=p.stat();need(stat.S_IMODE(st.st_mode)==0o600 and 0<st.st_size<=CAP,'startup diagnostics mode/size')
    rows=[json.loads(x) for x in p.read_bytes().splitlines()]
    need(all(x['seq']==i+1 and x['run']==run and x['contract_sha256']==digest for i,x in enumerate(rows)),'startup diagnostics binding/sequence')
    stages=[x['stage'] for x in rows]
    need(all(stages.count(x)==1 for x in required) and not any(x.endswith('-failed') for x in stages),'startup diagnostics incomplete/failed')
    positions=[stages.index(x) for x in required]
    need(positions==sorted(positions),'startup diagnostics stage order')
    return True

def validate_native(path,parent,complete=True):
    p=Path(path);st=p.stat();need(stat.S_IMODE(st.st_mode)==0o600 and 0<st.st_size<=CAP,'native diagnostics mode/size')
    stages={};seq={}
    for line in p.read_bytes().splitlines():
        m=re.fullmatch(rb'V10DIAG (\d+) (\d+) ([a-z-]+) (-?\d+) (\d+)',line)
        need(m is not None and len(line)<192,'native diagnostics framing')
        pid,n,stage,rc,err=m.groups();pid,n,rc=int(pid),int(n),int(rc);stage=stage.decode()
        need(pid in (parent,1) and seq.get(pid,n-1)+1==n and 0<n<=32 and rc==0,'native diagnostics process/sequence/failure')
        seq[pid]=n;stages.setdefault(pid,[]).append(stage)
    for pid,required in ((parent,['entry','restore-control-cloexec','fd-bridge','domain','control-fds','initial-fds','catalog-prepare','userns','owner-send','owner-ack-resume','wait-status','parent-exit']), (1,['worker-fork','worker-ready','worker-resumed','mount-proc','mount-tmp','mount-catalog','candidate-run-begin','candidate-run-end'])):
        if not complete:required=[x for x in required if x not in ('wait-status','parent-exit','candidate-run-end')]
        seen=stages.get(pid,[]);need(all(x in seen for x in required),'native diagnostics required stages missing')
        need([seen.index(x) for x in required]==sorted(seen.index(x) for x in required),'native diagnostics stage order')
    return True
