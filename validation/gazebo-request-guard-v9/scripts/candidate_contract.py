"""Read-only whole-candidate contract reconciliation; NO FD preparation/launch."""
from pathlib import Path
import json,hashlib,os,copy
import configuration as Q,receipts
R,B=receipts.R,receipts.B

def verify(policy,manifest,records,read_sources=True):
    required=[r for r in records if r['required']]
    expected={p for r in required for p in r['aliases']}
    rows=policy['paths']
    Q.need(len(rows)==len(expected)==468 and {r['path'] for r in rows}==expected,'missing/duplicate/unexpected required alias')
    replacements={policy[k]['path']:policy[k] for k in ('native_replacement','allowlist_replacement')}
    groups={};original_groups={}
    for old in required:
        first=next(r for r in rows if r['path']==old['aliases'][0]);key=(first['original']['device'],first['original']['inode'])
        original_groups[key]=copy.deepcopy(old['original'])
        for path in old['aliases']:
            row=next(r for r in rows if r['path']==path)
            Q.need(all(row[k]==first[k] for k in ('source','original','size','executable')),'alias object/FD metadata disagreement')
            original=manifest['mounts'][path]
            if path in replacements:
                change=replacements[path]
                Q.need(row['source']==change['source'] and row['original']['sha256']==change['sha256'],'candidate replacement hash')
            else:Q.need(all(row['original'][k]==original[k] for k in ('device','inode','sha256')),'unapproved source identity/hash')
            Q.need(row['executable'] is old['executable'],'alias executable intent')
        Q.need(key not in groups,'cross-original deduplication')
        groups[key]=dict(original=first['original'],source=first['source'],bytes=first['size'],aliases=old['aliases'],executable=first['executable'],approved_original=old['original'])
    Q.need(len(groups)==303,'required original count')
    needed=Q.admission([g['bytes'] for g in groups.values()])
    if read_sources:
        for g in groups.values():
            fd=os.open(g['source'],os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
            try:
                before=os.fstat(fd);h=hashlib.sha256()
                while True:
                    block=os.read(fd,1048576)
                    if not block:break
                    h.update(block)
                after=os.fstat(fd);o=g['original']
                Q.need((before.st_dev,before.st_ino,before.st_size)==(o['device'],o['inode'],g['bytes']) and
                       (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)==
                       (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns) and h.hexdigest()==o['sha256'],'source same-FD hash/identity changed')
            finally:os.close(fd)
    return list(groups.values()),needed

def main():
    import collector as C
    # Authenticate the original sealed contract using existing verifier.
    c,m,seal=C.channel.S.catalog.load_contract()
    previous=json.loads((R.parent/'gazebo-request-guard-v3/reports/copy_contract.json').read_text())
    import importlib.util
    spec=importlib.util.spec_from_file_location('contract_v4',R.parent/'gazebo-request-guard-v4/scripts/inputs.py');v4=importlib.util.module_from_spec(spec);spec.loader.exec_module(v4)
    records=v4.classify(m,previous);policy=json.loads((R/'reports/policy.json').read_text())
    groups,total=verify(policy,m,records)
    historical=json.loads((R.parent/'gazebo-request-guard-v7/reports/resource_decision.json').read_text())
    large=[g for g in groups if g['bytes']>67108864]
    Q.need(len(large)==5 and sum(len(g['aliases']) for g in large)==16,'large input reconciliation')
    value=dict(schema=1,parent_contract_sha256=seal,parent_v8_commit='35bc722847bc8676fc808b392b5680c6d08b2c29',
        approved_candidate_only=dict(object_cap=Q.OBJECT_CAP,preparation_admission_cap=Q.ADMISSION_CAP,owner_collector_properties=Q.owner_properties()),
        target_resources=copy.deepcopy(m['resources']),target_rlimits=copy.deepcopy(m['rlimits']),
        preserved_contract_fields={k:copy.deepcopy(m[k]) for k in ('ack_protocol','deadlines','stream_limits','one_shot','outputs','fd_sources','payload','required_canonical_mappings')},
        argv_environment_source='inputs/target_env.inc and launch.c TARGET_EXECUTABLE/target_environment; original ordered_bwrap_argv is historical only; native namespace+FD mounts replace bwrap',
        paths=policy['paths'],objects=groups,required_paths=468,required_objects=303,large_objects=large,
        static_source_same_fd_hash_verified=True,actual_prepared_objects_this_phase=0,actual_delivered_paths_this_phase=0,
        calculated=dict(output_pages=total-131072,native_output_plus_buffers=total,admission_headroom=Q.ADMISSION_CAP-total,
            collector_output_plus_1MiB=total-131072+1048576,previous_cold_cache_model=historical['full_preparation_with_cold_source_page_cache'],
            previous_model_with_reserve=historical['full_modeled_preparation_with_reserve'],owner_cap=Q.OWNER_MEMORY_MAX,
            previous_model_headroom=Q.OWNER_MEMORY_MAX-historical['full_modeled_preparation_with_reserve']),
        measured=dict(preparation_peak='UNKNOWN_NOT_RUN',target_usage='UNKNOWN_NOT_RUN',owner_charge_placement='UNKNOWN_NOT_RUN'),
        preparation_rlimits_read_only_observation=Q.inherited_preparer_limits(),
        delivery=dict(object='final RO regular memfd; F_SEAL_WRITE/GROW/SHRINK/SEAL/EXEC; final same-FD SHA/identity/exec intent',
            aliases='one pin per original dev/inode; no cross-origin digest deduplication',mount='FD bind + RDONLY/NOSUID/NODEV + per-object NOEXEC; canonical same FD identity',
            phases=['OWNERV8/O identity only','303 CATALOG_OBJECT/C + CATALOG_COMPLETE/K','held target PLACE/P independent target limits','audit/root handoff/A','listener ACK and single exec guard','GO','pre-EXIT_ACK live mappings','EXIT_ACK','audit COMPLETE+EOF, stdout/stderr EOF, exit, cleanup+integrity','collector pins closed before V']),
        active_entry_exit=78,execution_authorized=False,live_limits_changed=False,stage_b='BLOCKED',risk_acceptance='UNDECIDED',runtime='UNVERIFIED')
    value['sha256']=hashlib.sha256(receipts.canonical(value)).hexdigest()
    (R/'reports/candidate_contract.json').write_text(json.dumps(value,indent=2)+'\n')
    print('468 static paths /303 originals /5 large objects /16 aliases verified; actual preparation+delivery0')
if __name__=='__main__':main()
