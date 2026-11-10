"""Approved candidate resource configuration. Pure validation, no setters."""
from pathlib import Path
import os,resource
OBJECT_CAP=543979760
ADMISSION_CAP=2159132672
OWNER_MEMORY_MAX=5368709120
TARGET_MEMORY_MAX=536870912

def need(ok,why):
    if not ok:raise ValueError(why)

def owner_properties():
    # Only this preparation-domain property is approved here. Never merge into
    # target_properties or replace the independently validated target domain.
    return {'MemoryMax':OWNER_MEMORY_MAX}

def admission(sizes,budget=ADMISSION_CAP,object_cap=OBJECT_CAP):
    need(type(budget) is int and 131072<=budget<=ADMISSION_CAP,'unapproved admission ceiling')
    need(type(object_cap) is int and object_cap==OBJECT_CAP,'unapproved object ceiling')
    need(all(type(s) is int and 0<=s<=object_cap for s in sizes),'per-object byte ceiling')
    total=131072+sum((s+4095)&~4095 for s in sizes)
    need(total<=budget,'required objects exceed admission')
    return total

def domain(parent,collector,target_group,read,observe):
    """Read actual placement before native preparation/initial owner ACK.
    Injected read/observe in tests; no process placement or property mutation.
    """
    p,c=observe(parent),observe(collector)
    group=p['cgroup']
    need(group.startswith('/') and group!='/' and '..' not in Path(group).parts and '//' not in group,'dedicated preparation domain')
    need(c['cgroup']==group and parent!=collector,'owner/collector must share bounded preparation domain')
    need(target_group.startswith('/') and target_group!='/' and group!=target_group and
         not group.startswith(target_group.rstrip('/')+'/') and not target_group.startswith(group.rstrip('/')+'/'),'target must be separate sibling domain')
    need(read(group,'memory.max').strip()==str(OWNER_MEMORY_MAX),'preparation MemoryMax readback')
    for pid,identity in ((parent,p),(collector,c)):
        again=observe(pid)
        need(all(again[k]==identity[k] for k in ('pid','start','cgroup')),'preparation identity/domain changed')
    need(read(group,'memory.max').strip()==str(OWNER_MEMORY_MAX),'preparation bound changed')
    return group

def read_cgroup(group,name):
    return (Path('/sys/fs/cgroup')/group.lstrip('/')/name).read_text()

def inherited_preparer_limits():
    """Read-only observations, not an assurance of future memory peaks."""
    return {name:list(resource.getrlimit(getattr(resource,'RLIMIT_'+name))) for name in ('AS','FSIZE','NOFILE')}
