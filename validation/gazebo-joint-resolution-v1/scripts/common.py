from pathlib import Path
import sys,importlib.util,json,hashlib
B=Path(__file__).resolve().parents[1];ROOT=B.parents[1]
def load(name,relative):
 before=list(sys.path)
 spec=importlib.util.spec_from_file_location(name,ROOT/relative);obj=importlib.util.module_from_spec(spec);sys.modules[name]=obj
 try:spec.loader.exec_module(obj)
 finally:sys.path[:]=before
 return obj
identity=load('identity','validation/dart-probe-a-harness-v1/scripts/identity.py')
mapped=load('resolution_mapped','validation/dart-probe-a-harness-v1/scripts/mapped.py')
policy=load('resolution_policy','validation/gazebo-minimal-physics-v1/scripts/gate.py')
limits={'MemoryMax':'536870912','MemorySwapMax':'0','TasksMax':'64','CPUQuota':'100%','CPUQuotaPeriodSec':'100ms','RuntimeMaxSec':'30s','TimeoutStopSec':'2s','KillMode':'control-group','OOMPolicy':'stop','Delegate':'no','Slice':'app.slice'}
readback={'memory.max':'536870912','memory.swap.max':'0','pids.max':'64','cpu.max':'100000 100000'}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def need(ok,reason):
 if not ok:raise ValueError(reason)
def dump(p,value):Path(p).write_text(json.dumps(value,indent=2)+'\n')
