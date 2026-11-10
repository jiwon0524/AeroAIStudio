"""Freeze small-only approval candidate. Read files only; never run driver."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import *
import datetime,subprocess

def inventory():
    paths=[p for d in ('inputs','scripts','tests') for p in sorted((R/d).iterdir()) if p.is_file()]
    paths.append(R/'reports/policy.json')
    for n in range(1,10):paths.extend(sorted((R.parent/f'gazebo-request-guard-v{n}'/'scripts').glob('*.py')))
    paths.extend([R.parent/'gazebo-joint-execution-contract-v1/scripts/protocol.py',R.parent/'gazebo-joint-isolation-v1/scripts/protocol.py'])
    return {str(p):sha(p) for p in sorted(set(paths))}

def main():
    build=json_read(R/'reports/build_receipt.json')
    for p,h in {**build['inputs'],**build['outputs']}.items():need(sha(p)==h,'build dependency/artifact changed: '+p)
    policy=json_read(R/'reports/policy.json');groups={}
    for row in policy['paths']:
        o=row['original'];key=o['device'],o['inode'];g=groups.setdefault(key,dict(original=o,aliases=[],size=row['size'],executable=row['executable'],required=True));g['aliases'].append(row['path'])
        st=Path(row['source']).stat();need((st.st_dev,st.st_ino,st.st_size)==(o['device'],o['inode'],row['size']) and sha(row['source'])==o['sha256'],'small source identity/hash')
    need(len(groups)==4 and len(policy['paths'])==5,'small object count')
    previous=R.parent/'gazebo-joint-resolution-v1/reports/harmless_summary.json';history=json_read(previous)
    need(history['status']=='PASS_ISOLATION_PATH_ONLY' and history['physical_steps']==0 and history['sample_count']==100,'previous harmless evidence')
    for name,key in [('result.json','raw_result_sha256'),('stdout.raw','raw_stdout_sha256'),('stderr.raw','raw_stderr_sha256')]:need(sha(previous.parent/'harmless_runtime'/name)==history[key],'prior raw evidence changed')
    v9=R.parent/'gazebo-request-guard-v9';v9tests=json_read(v9/'reports/tests.json')
    need(v9tests['new_checks']==1638 and v9tests['source_manifest_sha256']==json_read(v9/'reports/source_manifest.json')['sha256'],'v9 receipt binding')
    snapshot=dict(files=inventory(),baseline_v9_commit='e37a69229a1a1a77937f0c22335a78a2858f86a0',old_harmless_report_sha256=sha(previous),v9_test_report_sha256=sha(v9/'reports/tests.json'),runtime_executed=False)
    snapshot['sha256']=__import__('hashlib').sha256(canonical(snapshot)).hexdigest()
    (R/'reports/source_manifest.json').write_text(json.dumps(snapshot,indent=2)+'\n')
    build.update(source_manifest_sha256=snapshot['sha256'])
    (R/'reports/build_receipt.json').write_text(json.dumps(build,indent=2)+'\n')
    files=dict(snapshot['files']);files.update(build['outputs']);
    host_tools=['/usr/bin/python3','/usr/bin/systemd-run','/usr/bin/systemctl','/usr/bin/busctl','/usr/bin/git']
    files.update({p:sha(p) for p in host_tools})
    for evidence in [previous,previous.parent/'harmless_runtime/result.json',previous.parent/'harmless_runtime/stdout.raw',previous.parent/'harmless_runtime/stderr.raw',v9/'reports/tests.json',v9/'reports/candidate_contract.json',v9/'reports/source_manifest.json']:
        files[str(evidence)]=sha(evidence)
    files[str(R/'reports/build_receipt.json')]=sha(R/'reports/build_receipt.json');files[str(R/'reports/source_manifest.json')]=sha(R/'reports/source_manifest.json')
    for row in policy['paths']:files[row['source']]=row['original']['sha256']
    owner=next(p for p in build['outputs'] if Path(p).name=='owner');anchor=next(p for p in build['outputs'] if Path(p).name=='unit-anchor')
    description='aero-v10-small-02:'+snapshot['sha256']
    contract=dict(schema=1,status='PROPOSED_REQUIRES_SEPARATE_EXPLICIT_RUNTIME_APPROVAL',profile='SMALL_HARMLESS_ONLY',run='v10-small-02',
        dart_gazebo_loading=False,physical_steps=0,large_objects_prepared=False,maximum_memory_measured=False,
        owner_unit='aero-guard-v10-owner-small-02.service',target_unit='aero-guard-v10-target-small-02.service',description=description,target_description=description+':target',
        marker=str(R/'work/harmless-small-02.once'),output=str(R/'work/runtime-small-02'),owner_binary=owner,anchor=anchor,
        required_policy_objects=4,required_policy_paths=5,control_sealed_executables=2,
        owner_memory_max=5368709120,object_cap=543979760,preparation_admission_cap=2159132672,target_memory_max=536870912,
        target_rlimits=dict(CPU=10,AS=2147483648,FSIZE=1048576,NOFILE=256,CORE=0),target_tasks_max=64,target_runtime_s=30,target_stop_s=2,
        deadlines=dict(host_s=40,collection_s=25,ack_ms=5000),stream_limits=dict(stdout_total=65536,stdout_pending=16384,stderr_total=1048576,stderr_pending=65536),audit_native_cap=1048576,
        policy=policy,records=list(groups.values()),manifest=dict(mounts={x['path']:dict(x['original'],source=x['source']) for x in policy['paths']},required_canonical_mappings=['/probe/fixture','/usr/lib/x86_64-linux-gnu/libc.so.6','/usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2']),
        calculated_small_native_output_pages=sum((g['size']+4095)&~4095 for g in groups.values()),
        small_mapping_policy='kernel maps dev/ino + retained sealed pin + canonical RO FD; map_files preferred; EPERM/EACCES fallback explicit for small profile only',
        source_manifest_sha256=snapshot['sha256'],files=files,original_launcher_exit=78,stage_b='BLOCKED',risk_acceptance='UNDECIDED',runtime='UNVERIFIED')
    contract['manifest'].update(deadlines=contract['deadlines'],stream_limits=contract['stream_limits'])
    contract['diagnostics']={'required':True,'per_file_cap':16384,'native_record_max':192,'native_records_per_process_max':32,'files':['host-startup.jsonl','collector-startup.jsonl','native-parent.stderr'],'mode':'0600','not_independent_audit':True}
    (R/'reports/execution_contract.json').write_text(json.dumps(contract,indent=2)+'\n')
    print('Frozen small candidate; contract SHA256',sha(R/'reports/execution_contract.json'))
if __name__=='__main__':main()
