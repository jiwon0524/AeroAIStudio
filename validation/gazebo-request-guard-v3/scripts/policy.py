"""Offline policy/launch review. Decisions are plans, never kernel authority.
Unknown requests and absent live evidence stay denied. No process operations.
"""
import json
import os
from pathlib import Path

R = Path(__file__).resolve().parents[1]

def request_plan(kind, *, path=None, row=None, copy_verified=False,
                 canonical_delivery=False, flags=0):
    # Copy verification alone does not establish namespace/path or native
    # identity compatibility. This prevents 594 blanket approvals.
    if kind in {'open', 'openat'}:
        if not row or not path or not path.startswith('/') or row.get('logical_path') != path:
            return 'DENY_UNKNOWN_PATH'
        if flags & ~(os.O_CLOEXEC|os.O_NONBLOCK|os.O_NOFOLLOW):
            return 'DENY_ACCESS_MODE'
        if not copy_verified:
            return 'DENY_UNVERIFIED_COPY'
        if not canonical_delivery:
            return 'BLOCKED_PATH_AND_IDENTITY_DELIVERY'
        return 'PLAN_ATOMIC_READONLY_FD_DELIVERY'
    if kind in {'fstat', 'newfstatat', 'statx', 'access', 'faccessat2', 'readlink'}:
        return 'BLOCKED_METADATA_EMULATION'  # no inspected pointer is continued
    if kind in {'read', 'pread64', 'lseek', 'close'}:
        return 'BLOCKED_TARGET_FD_LEDGER_AND_EMULATION'
    if kind in {'mmap_file_exec', 'mmap_file_data', 'mprotect_exec'}:
        return 'BLOCKED_MAPPING_OBJECT_AND_PATH_PROOF'
    if kind in {'clone', 'clone3', 'fork', 'vfork', 'futex', 'rseq', 'set_robust_list'}:
        return 'BLOCKED_THREAD_POLICY_AND_TRACKING_PROOF'
    if kind in {'execve', 'execveat'}:
        return 'BLOCKED_ONE_SHOT_PREEXEC_HANDOFF'
    return 'DENY_UNKNOWN_REQUEST'

REQUIRED = ('copies_retained', 'namespace_fd_attestation', 'private_journal_before_exec',
            'filter_before_exec', 'external_listener_bound', 'listener_not_in_target',
            'ptrace_options_before_exec', 'one_shot_exec_identity', 'all_task_tracking',
            'live_authenticated_collector')

def deployment_ready(evidence):
    # No production evidence factory exists. This function is a completeness
    # checker for static review/mocks, NOT an authentication boolean producer.
    missing = [k for k in REQUIRED if evidence.get(k) is not True]
    if missing:
        raise ValueError('missing integration: '+','.join(missing))
    raise ValueError('actual execution unauthorized; runtime evidence unavailable')

def compatibility(manifest, copies):
    by_path = {p:g for g in copies['objects'] for p in g['aliases']}
    rows = []
    for path, old in sorted(manifest['mounts'].items()):
        group = by_path[path]
        new = group.get('receipt', {}).get('object')
        rows.append(dict(path=path, byte_copy=group['status'],
                         old_identity=[old['device'], old['inode']], copy_identity=new,
                         aliases=group['aliases'], executable=path in manifest['elfs'],
                         old_contract_accepts=False,
                         reasons=['original contract mounted inode differs']+
                            (['direct memfd name/deleted mapping rejected by original mapped.py']
                             if path in manifest['elfs'] else [])))
    # No changes to original projections/compiled headers are written. List
    # precisely what a separately reviewed copy contract would have to bind.
    interpreters=[]
    for group in copies['objects']:
        interp=group.get('receipt',{}).get('elf_interpreter')
        if interp:
            # Only the explicitly sealed namespace symlinks, never host
            # realpath or a guessed ambient loader search path.
            resolved=interp
            if resolved.startswith('/lib64/'):resolved='/usr/lib64/'+resolved[len('/lib64/'):]
            if resolved=='/usr/lib64/ld-linux-x86-64.so.2':resolved='/usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2'
            if resolved.startswith('/lib/'):resolved='/usr/lib/'+resolved[len('/lib/'):]
            interpreters.append(dict(consumer_aliases=group['aliases'],PT_INTERP=interp,
                sealed_namespace_resolution=resolved,listed_in_parent=resolved in manifest['mounts']))
    return dict(status='NOT_DEPLOYABLE', inputs=rows,interpreters=interpreters,
                soname_edges_total=len(manifest['soname_edges']),
                soname_edges_all_pinned=all(e['mount'] in by_path and
                    manifest['mounts'][e['mount']]['source']==e['provider'] for e in manifest['soname_edges']),
                identity_consumers=['mounts', 'elfs', 'native.expected', 'plugin_expectations.hh',
                    'attestation.allowed_mappings', 'engine/detector/provider identities',
                    'FD mount attestor', 'maps/map_files/proc-root checks'],
                content_consumers=['sha256 allowlist (same bytes)', 'ELF Build ID (same bytes)',
                                   'SONAME edges and logical paths (must remain same)'],
                bootstrap_order=['private journal and collector ownership',
                    'copies pinned and final bytes verified', 'namespace/FD invariant established',
                    'preexec EXITKILL/TRACE* established', 'filter and external listener bound',
                    'target listener removed and initial exec one-shot bound',
                    'exec stop before loader', 'all-task collection through ECHILD and final EOF'],
                earliest_certain_blocker='initial exec denied by installed v2/v3 filter',
                first_actual_loader_syscall='UNKNOWN_NO_EXECUTION',
                normal_requests={k:request_plan(k) for k in ['execveat','openat','newfstatat','statx',
                    'access','read','pread64','mmap_file_exec','mprotect_exec','clone','clone3','futex']},
                unknown_path_policy='DENY (including unsealed loader cache/probes)',
                runtime_only=['canonical bind mount name for sealed anonymous inode',
                    'executable mmap/exec and LSM/noexec in target namespace',
                    'actual loader requests and optional negative lookups',
                    'ADDFD cancellation, task inheritance, supervisor disconnect and EOF drain'])

if __name__ == '__main__':
    from snapshots import catalog
    c, manifest, seal = catalog.load_contract()
    copies = json.loads((R/'reports/copy_contract.json').read_text())
    result = compatibility(manifest, copies)
    result['parent_contract_sha256'] = seal
    (R/'reports/policy_review.json').write_text(json.dumps(result,indent=2)+'\n')
