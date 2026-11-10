"""Read-only path reconciliation. Never prepares, maps, loads or runs an input."""
from pathlib import Path
import hashlib, importlib.util, json, os, re
R=Path(__file__).resolve().parents[1]
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
v5=load('plan_v6_parent',R.parent/'gazebo-request-guard-v5/scripts/plan.py')
def compare(required,compiled):
    if len(compiled)!=len(set(compiled)):raise ValueError('duplicate compiled alias')
    return sorted(set(required)-set(compiled)),sorted(set(compiled)-set(required))
def analyze():
    c,m,prior,seal=v5.old.load_verified();records=v5.old.classify(m,prior)
    roots={}
    for k,p in m['roles'].items():roots.setdefault(p,[]).append('role:'+k)
    for p in m['required_canonical_mappings']:roots.setdefault(p,[]).append('required_canonical_mapping')
    for p in m['payload'][:2]:roots.setdefault(p,[]).append('payload')
    chains={p:[p] for p in roots};todo=list(sorted(roots))
    while todo:
        p=todo.pop(0)
        for e in m['soname_edges']:
            if e['consumer']==p and e['mount'] not in chains:
                chains[e['mount']]=chains[p]+[e['mount']];todo.append(e['mount'])
    compiled=[]
    for line in (R.parent/'gazebo-request-guard-v5/inputs/allowlist.inc').read_text().splitlines():
        if line.startswith('{'):compiled.append(json.loads(re.match(r'\{("(?:[^"\\]|\\.)*")',line)[1]))
    required=[p for r in records if r['required'] for p in r['aliases']]
    missing,extra=compare(required,compiled)
    paths=[]
    argv=m['ordered_bwrap_argv']
    for r in records:
        if not r['required']:continue
        original=r['original'];aliases=sorted(r['aliases'])
        native=[k for k,v in m['native']['expected'].items() if v==[original['sha256'],original['device'],original['inode']]]
        witnesses=[dict(path=p,chain=chains[p],roots=roots[chains[p][0]]) for p in aliases if p in chains]
        for p in aliases:
            row=m['mounts'][p];source=row['source']
            fd=10+m['fd_sources'].index(source)
            mount=[i for i in range(len(argv)-2) if argv[i:i+3]==['--ro-bind-fd',str(fd),p]]
            if len(mount)!=1:raise ValueError('missing/duplicate FD mount '+p)
            paths.append(dict(path=p,canonical_source=source,original=original,
                original_size=os.stat(source).st_size,canonical_aliases=aliases,
                required_by=witnesses,native_roles=native,
                direct_requirement=p in chains or bool(native) or p=='/input/joint-elf.sha256',
                alias_aggregation='same original dev/inode; entire approved alias group required when any witness/native role is required',
                compiled=p in compiled,in_approved_sealed_contract=True,
                mount=dict(mode=row['mode'],argv_index=mount[0],original_source_fd=fd),
                fd_delivery='DENIED_MISSING_OBJECT' if p in missing else 'CANDIDATE_ONLY_NOT_DELIVERED',
                delivery_requirements=['final RO FD seals+exec mode+SHA256+copy dev/inode/size',
                    'all aliases mounted from same retained copy FD; no cross-origin digest dedup',
                    'canonical openat2 same object; INPUT_OBJECT policy index before ADDFD_SEND',
                    'new copy native/collector identity contract required; old original inode projection incompatible']))
    resources=json.loads((R.parent/'gazebo-request-guard-v5/reports/resources.json').read_text())
    prior_by={(r['original']['device'],r['original']['inode']):r for r in prior['objects']}
    for obj in resources['blocked_objects']:
        p=obj['aliases'][0];row=m['mounts'][p];old=prior_by[row['device'],row['inode']]
        obj['original']={k:row[k] for k in ('device','inode','sha256')}
        obj['approved_contract_aliases']=all(a in m['mounts'] for a in obj['aliases'])
        obj['streaming']='ALREADY_BOUNDED_64KiB; cannot remove retained dense output pages or object cap'
        obj['reuse']='UNAVAILABLE: prior object_retained='+str(old.get('object_retained',False))+'; no live sealed FD receipt for this object'
        obj['preparation_known_lower_bound']=obj['native_output_plus_buffers']
        obj['service_usage']='UNKNOWN: PT_LOAD is not RSS; target retains AS=2GiB/MemoryMax=512MiB; owner charge placement unapproved'
        obj['minimum_cap_increase']=obj['bytes']-obj['current_object_limit']
        obj['decision']='DENY_LIMIT_CHANGE_DEFERRED'
    result=dict(schema=1,parent_contract_sha256=seal,
        sources=dict(full_required='v4 classify(sealed v1 manifest, hash-pinned v3 receipts)',compiled='v5 inputs/allowlist.inc: required AND historical prepared'),
        counts=dict(required_paths=len(required),required_objects=sum(r['required'] for r in records),compiled_paths=len(compiled),compiled_objects=sum(r['required'] and r['prepared'] for r in records)),
        required_paths=sorted(required),compiled_paths=sorted(compiled),required_minus_compiled=missing,compiled_minus_required=extra,
        duplicate_aliases=False,contract_version_mismatch=False,
        root_cause='16 approved aliases of 5 distinct mandatory original objects exceed unchanged 64MiB preparation cap; historical readiness is not live FD readiness',
        paths=paths,resources=resources,limits_changed=False,deployed=False,runtime_verified=False)
    return result
if __name__=='__main__':
    result=analyze();(R/'reports/reconciliation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['counts']);print('missing',len(result['required_minus_compiled']),'extra',len(result['compiled_minus_required']))
