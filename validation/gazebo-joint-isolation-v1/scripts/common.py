"""Pinned local module reuse. Importing this module starts no service or target."""
from pathlib import Path
import importlib.util,sys,json,hashlib
B=Path(__file__).resolve().parents[1]; ROOT=B.parents[1]
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,ROOT/path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
identity=load('joint_identity','validation/dart-probe-a-harness-v1/scripts/identity.py')
sys.modules['identity']=identity
mapped=load('joint_mapped','validation/dart-probe-a-harness-v1/scripts/mapped.py')
policy=load('joint_policy','validation/gazebo-minimal-physics-v1/scripts/gate.py')
limits={'MemoryMax':'536870912','MemorySwapMax':'0','TasksMax':'64','CPUQuota':'100%','CPUQuotaPeriodSec':'100ms','RuntimeMaxSec':'30s','TimeoutStopSec':'2s','KillMode':'control-group','OOMPolicy':'stop','Delegate':'no','Slice':'app.slice'}
readback={'memory.max':'536870912','memory.swap.max':'0','pids.max':'64','cpu.max':'100000 100000'}
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def need(ok,reason):
 if not ok:raise ValueError(reason)
def dump(path,data):Path(path).write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n')
