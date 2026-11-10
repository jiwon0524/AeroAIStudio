"""Pure candidate mount/identity/owner contract; no mount, FD open, or launch.
Live callers must provide a verifier that checks the final SAME FD. Synthetic
receipts in tests never authorize launch. Original sealed contract is unchanged.
"""
from copy import deepcopy
import hashlib,json
REQUIRED_SEALS=0x2f

def need(ok,why):
    if not ok:raise ValueError(why)

def project(manifest,records,pins,verify):
    required=[r for r in records if r['required']]
    expected={(r['original']['device'],r['original']['inode']) for r in required}
    need(set(pins)==expected,'missing/unexpected required original object')
    objects={};identities=set();fds=set();mounts={}
    for row in required:
        original=row['original'];key=(original['device'],original['inode']);pin=pins[key]
        need(set(pin)=={'fd','receipt'},'pin fields')
        fd=pin['fd'];receipt=pin['receipt'];obj=receipt['object']
        need(type(fd) is int and fd>=5 and fd not in fds,'invalid/shared owner FD')
        need(receipt['original']==original and receipt['sha256']==original['sha256'],'copy/source hash identity')
        need(receipt['executable_intent'] is row['executable'],'exec intent')
        need(type(obj['device']) is int and type(obj['inode']) is int and type(obj['size']) is int
             and obj['device']>0 and obj['inode']>0 and obj['size']>=0,'copy identity schema')
        identity=(obj['device'],obj['inode']);need(identity not in identities,'cross-origin deduplication')
        need(receipt['seals']&REQUIRED_SEALS==REQUIRED_SEALS,'data/mode seals missing')
        need(verify(fd,receipt) is True,'live final sealed FD verification failed')
        identities.add(identity);fds.add(fd);objects[key]=deepcopy(obj)
        for path in row['aliases']:
            need(path not in mounts and path in manifest['mounts'],'duplicate/unknown alias')
            old=manifest['mounts'][path]
            need(all(old[k]==original[k] for k in ('device','inode','sha256')),'original alias binding')
            mounts[path]=dict(path=path,source_fd=fd,sha256=original['sha256'],**obj,executable=row['executable'])
    native={}
    for role,value in manifest['native']['expected'].items():
        if role=='world_bytes':native[role]=list(value);continue
        key=(value[1],value[2]);need(key in objects,'native identity outside required set')
        obj=objects[key];native[role]=[value[0],obj['device'],obj['inode']]
    elf={p:dict(manifest['elfs'][p],device=v['device'],inode=v['inode']) for p,v in mounts.items() if p in manifest['elfs']}
    required_mappings=manifest['required_canonical_mappings']
    need(set(required_mappings)<=set(elf),'required canonical mappings omitted')
    # fd-mount fragments only. A list of strings is not execution authorization.
    argv=[]
    for p in sorted(mounts):argv+=['--ro-bind-fd',str(mounts[p]['source_fd']),p]
    policy=dict(schema=1,mounts=mounts,native_expected=native,elfs=elf,
        required_canonical_mappings=list(required_mappings),mount_fragments=argv,
        owner=dict(placement='outside target cgroup and cleanup domain',single_wait_owner=True,
            child_release='only after target cgroup identity+limits readback, initial stop, listener ACK, exec-stop, collector A',
            final='native owner waits V while collector observes target-only exit+cleanup; owner cleanup follows V/failure'),
        native_runtime_identity_consumer='NOT_IMPLEMENTED; old compiled native identities remain original; reject deployment',
        executable_mapping_policy='NOT_IMPLEMENTED; file-backed mmap remains denied',
        execution_authorized=False,release_exit=78)
    policy['sha256']=hashlib.sha256((json.dumps(policy,sort_keys=True,separators=(',',':'))+'\n').encode()).hexdigest()
    return policy

def placement(owner,target,collector):
    """Fail closed on absent actual identity/limit/domain observations."""
    for role in (owner,target,collector):
        need(type(role.get('pid')) is int and role['pid']>0 and bool(role.get('start')) and role.get('cgroup','').startswith('/'),'process identity/placement missing')
    need(len({r['pid'] for r in (owner,target,collector)})==3,'overlapping process ownership')
    target_group=target['cgroup'].rstrip('/')
    for role in (owner,collector):
        need(role['cgroup']!=target_group and not role['cgroup'].startswith(target_group+'/'),'owner/collector within target cleanup domain')
    need(target.get('memory_max')==536870912 and target.get('nofile')==256 and target.get('fsize')==1048576
         and target.get('address_space')==2147483648,'target limits mismatch')
    need(owner.get('charge_domain')==owner['cgroup'],'preparer charge domain unproved')
    return True
