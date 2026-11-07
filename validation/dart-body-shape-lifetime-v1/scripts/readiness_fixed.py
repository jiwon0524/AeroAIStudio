"""Core-only static mount contract and fail-closed post-open decision. No launch API."""
import copy, json, os, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'validation/dart-probe-a-harness-v1/scripts'))
from allowlist import load_manifest, validate
from mapped import verify, start_id

def aliases(entries):
    providers={}
    for entry in entries:
        for name in entry['soname']:
            if '/' in name or name in providers: raise ValueError('ambiguous/unsafe SONAME')
            providers[name]=entry
    mounts={e['sandbox_path']:e for e in entries}
    # Include the root library SONAME required by the directly linked fixture.
    for name,provider in providers.items():
        target='/usr/lib/x86_64-linux-gnu/'+name
        if target in mounts and mounts[target]['real_path']!=provider['real_path']:
            raise ValueError('alias collision')
        mounts[target]=provider
    edges=[]
    for entry in entries:
        for name in entry['needed']:
            if name not in providers: raise ValueError('unresolved NEEDED '+name)
            provider=providers[name]
            target='/usr/lib/x86_64-linux-gnu/'+name
            if target in mounts and mounts[target]['real_path']!=provider['real_path']:
                raise ValueError('alias collision')
            mounts[target]=provider
            edges.append({'consumer':entry['real_path'],'needed':name,'target':target,'provider':provider['real_path']})
    return mounts,edges

def mount_arguments(entries,fds):
    if len(entries)!=len(fds): raise ValueError('FD count')
    mounts,_=aliases(entries); by_path={e['real_path']:fd for e,fd in zip(entries,fds)}
    args=[]
    for target,entry in sorted(mounts.items()):
        args+=['--ro-bind-fd',str(by_path[entry['real_path']]),target]
    return args

def mapped_entries(entries,allowed_paths):
    mounts,_=aliases(entries); result=[]
    for path in allowed_paths:
        if path not in mounts: raise ValueError('unknown mapping alias')
        row=copy.deepcopy(mounts[path]);row['sandbox_path']=path;row['required']=False;result.append(row)
    return result

def post_open(pid,expected_start,entries,baseline,send,checker=verify):
    """Caller owns a paused post-open child; reject sends no close permission.

    Baseline is the pre-open harness mapping profile. Require every Core inode,
    allow only pinned canonical/alias paths, and verify stable live identity.
    Constructors have already run before this gate. Never authorizes launch.
    """
    if start_id(pid)!=expected_start: raise ValueError('PID identity changed')
    mounts,_=aliases(entries)
    candidates=mapped_entries(entries,mounts)
    additional=[]
    for row in baseline:
        if row['sandbox_path'] in mounts:
            expected=mounts[row['sandbox_path']]
            if any(row[k]!=expected[k] for k in ('device','inode','sha256','build_id')):
                raise ValueError('baseline conflicts with Core')
            next(e for e in candidates if e['sandbox_path']==row['sandbox_path'])['required']=True
        else: additional.append(row)
    result=checker(pid,candidates+additional)
    if result['status']!='PASS_FILE_IDENTITY': return {'status':'REJECTED','evidence':result}
    seen={(r['device'],r['inode']) for r in result['records']}
    if not {(e['device'],e['inode']) for e in entries}<=seen:
        return {'status':'REJECTED','reason':'Core closure missing','evidence':result}
    if start_id(pid)!=expected_start: raise ValueError('PID identity changed')
    # Explicitly retain weaker file-identity classification even when close is allowed.
    send('CLOSE\n')
    return {'status':'PASS_FILE_IDENTITY','evidence':result,'resident_pages_verified':False}
