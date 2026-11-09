from pathlib import Path
import sys,importlib.util,json,hashlib
B=Path(__file__).resolve().parents[1];ROOT=B.parents[1]
# Local helper modules are executed from verified source bytes, never .pyc.
from contract import checked_file,check_fd,read
import os,types
_CODE=globals().get('_SEALED_CODE')
if _CODE is None:_CODE=read()['code']
LOADED={}
def load(name,relative):
 p=str(ROOT/relative)
 if p not in _CODE:raise ValueError('unsealed helper import '+p)
 row=_CODE[p];fd=os.open(p,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
 try:
  check_fd(fd,row);data=os.pread(fd,os.fstat(fd).st_size,0)
  if hashlib.sha256(data).hexdigest()!=row['sha256']:raise ValueError('source bytes changed')
 finally:os.close(fd)
 obj=types.ModuleType(name);obj.__file__=p;obj.__sealed_sha256__=row['sha256'];sys.modules[name]=obj
 before=list(sys.path)
 try:exec(compile(data,p,'exec'),obj.__dict__)
 finally:sys.path[:]=before
 LOADED[p]=row['sha256'];return obj
identity=load('identity','validation/dart-probe-a-harness-v1/scripts/identity.py')
mapped=load('resolution_mapped','validation/dart-probe-a-harness-v1/scripts/mapped.py')
policy=load('resolution_policy','validation/gazebo-minimal-physics-v1/scripts/gate.py')
limits={'MemoryMax':'536870912','MemorySwapMax':'0','TasksMax':'64','CPUQuota':'100%','CPUQuotaPeriodSec':'100ms','RuntimeMaxSec':'30s','TimeoutStopSec':'2s','KillMode':'control-group','OOMPolicy':'stop','Delegate':'no','Slice':'app.slice'}
readback={'memory.max':'536870912','memory.swap.max':'0','pids.max':'64','cpu.max':'100000 100000'}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def need(ok,reason):
 if not ok:raise ValueError(reason)
def dump(p,value):Path(p).write_text(json.dumps(value,indent=2)+'\n')
