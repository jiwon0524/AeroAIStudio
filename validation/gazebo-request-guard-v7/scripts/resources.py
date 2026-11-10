"""Read-only byte ledger and unapplied resource decision. No setting changes."""
from pathlib import Path
import hashlib,importlib.util,json,os,resource,datetime
R=Path(__file__).resolve().parents[1];P=R.parent/'gazebo-request-guard-v6'
s=importlib.util.spec_from_file_location('v6_reconcile_reused',P/'scripts/reconcile.py');A=importlib.util.module_from_spec(s);s.loader.exec_module(A)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def ledger():
    # Authenticate existing results, do not rerun its555 checks/reconciliation.
    artifacts=json.loads((P/'reports/artifacts.json').read_text())
    for name in ('reports/reconciliation.json','reports/tests.json','scripts/reconcile.py'):
        p=P/name;assert sha(p)==artifacts[str(p.relative_to(R.parents[1]))]
    prior=json.loads((P/'reports/reconciliation.json').read_text())
    assert json.loads((P/'reports/tests.json').read_text())['count']==555
    c,m,receipts,seal=A.v5.old.load_verified()
    rows=A.v5.old.classify(m,receipts)
    page=os.sysconf('SC_PAGE_SIZE');roundup=lambda n:(n+page-1)//page*page
    required=[r for r in rows if r['required']]
    sizes={};objects=[]
    for row in required:
        o=row['original'];key=(o['device'],o['inode'])
        assert key not in sizes
        source=m['mounts'][row['aliases'][0]]['source'];st=os.stat(source)
        assert (st.st_dev,st.st_ino)==key
        sizes[key]=st.st_size
        objects.append(dict(original=o,aliases=row['aliases'],source=source,bytes=st.st_size,
                            pages=roundup(st.st_size),historical_prepared=row['prepared']))
    full=sum(r['pages'] for r in objects);large=[r for r in objects if not r['historical_prepared']]
    large_pages=sum(r['pages'] for r in large);large_bytes=sum(r['bytes'] for r in large)
    # Final digest is nested under catalog_prepare's live64KiB chunk, counted ONCE.
    buffers=131072;reserve=268435456
    assert full==prior['resources']['full_required_page_bytes']==2159001600
    assert full-large_pages==353501184 and len(large)==5
    validation_cache={}
    for section in ('mounts','code','evidence','host_tools'):
        for row in m[section].values():
            st=os.stat(row['source']);validation_cache[st.st_dev,st.st_ino]=roundup(st.st_size)
    source_cache=sum(validation_cache.values())
    cold_model=full+source_cache+buffers
    cg={}
    membership=Path('/proc/self/cgroup').read_text().strip()
    location=membership.split('::',1)[1]
    at=Path('/sys/fs/cgroup')/location.lstrip('/')
    while str(at).startswith('/sys/fs/cgroup'):
        try:cg[str(at.relative_to('/sys/fs/cgroup'))]=dict(memory_max=(at/'memory.max').read_text().strip())
        except OSError:cg[str(at.relative_to('/sys/fs/cgroup'))]=dict(memory_max='UNKNOWN_NOT_VISIBLE')
        if at==Path('/sys/fs/cgroup'):break
        at=at.parent
    options=[]
    for obj in large:
        source=obj['source'];fd=os.open(source,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
        try:
            row=m['mounts'][obj['aliases'][0]]
            try:before=A.v5.old.snapshots.catalog.immutable(fd);error=None
            except OSError as e:before=False;error=e.errno
            c.check_fd(fd,row)
            try:after=A.v5.old.snapshots.catalog.immutable(fd)
            except OSError:after=False
            obj['read_only_observation']=dict(sha256_verified=True,source_identity_verified=True,
                fsverity_before=before,fsverity_after=after,flags_ioctl_errno=error,
                st_blocks_bytes=os.fstat(fd).st_blocks*512)
        finally:os.close(fd)
    inherited={k:list(resource.getrlimit(getattr(resource,'RLIMIT_'+k))) for k in ('AS','FSIZE','NOFILE')}
    options=[dict(storage='original disk file',decision='REJECT_NO_KERNEL_IMMUTABILITY',reason='same-FD hash/identity verified; fs-verity not established; readonly mounts/FDs cannot prevent outside writer'),
        dict(storage='sparse memfd',decision='REJECT_CURRENT_CAP_AND_FSIZE',reason='holes preserve zeros only; logical file size remains >64MiB, seal/exec same requirements; no content-changing stripping'),
        dict(storage='compressed storage or debug stripping',decision='REJECT_BYTE_CONTRACT',reason='loader must receive original bytes; reconstruction has retained-output cost; stripping changes SHA256'),
        dict(storage='disk copy with chmod/RO bind',decision='REJECT_NO_IMMUTABILITY',reason='outside writer/writable alias not excluded; fs-verity setup or immutable storage would require unsupported new preparation and authorization'),
        dict(storage='retained sealed object reuse',decision='REJECT_NO_LIVE_OBJECT',reason='v3 receipts object_retained=false and5 oversized objects never sealed; FD numbers cannot recreate authority')]
    # Exact policy proposal; bounds/reserves are decision inputs, not measured maxima.
    proposal=[
      dict(setting='catalog per-object byte ceiling (all prepare/verify checks)',scope='preparer/native catalog',current=67108864,proposed=max(r['bytes'] for r in large),reason='largest mandatory logical file; same value must guard prepare and final verify'),
      dict(setting='catalog_prepare admission ceiling',scope='preparer/native catalog',current=536870912,proposed=full+buffers,reason='303 distinct output objects page-rounded once + one nested copy/hash buffer pair; excludes overhead by design'),
      dict(setting='owner MemoryMax / memory.max',scope='NEW dedicated preparer+native owner+Python collector cgroup outside target cleanup domain',current='UNDEFINED_NO_OWNER_UNIT; target536870912 unchanged; see read-only cgroup observations',proposed=5368709120,reason=f'worst modeled output+source page caches {full} output + validated-input cache {source_cache} + buffers {buffers} + explicit reserve {reserve} = {cold_model+reserve}; remaining {5368709120-(cold_model+reserve)}; reserve NOT measured peak guarantee'),
    ]
    return dict(schema=1,parent_contract_sha256=seal,reused_prior_checks=555,reconciliation_reused=True,
      objects=objects,large_objects=large,large_exact_bytes=large_bytes,large_page_bytes=large_pages,
      large_known_preparation_bytes=large_pages+buffers,
      prepared298_page_bytes=full-large_pages,full303_page_bytes=full,
      full_output_and_buffers=full+buffers,all_validated_source_page_bytes=source_cache,full_preparation_with_cold_source_page_cache=cold_model,
      full_modeled_preparation_with_reserve=cold_model+reserve,
      service_phase=dict(owner_retained_output_pages=full,owner_output_plus_one_hash_buffer=full+65536,owner_cold_cache_plus_hash_buffer=full+source_cache+65536,modeled_owner_plus_target_at_target_cap=full+source_cache+65536+reserve+536870912,source_cache_residual_upper_model=source_cache,
        known_shared_buffer_bytes=65536,target_MemoryMax=536870912,target_AS=2147483648,
        owner_and_target_domain_budget_model=5368709120+536870912,
        target_private_RSS='UNKNOWN_NOT_MEASURED',target_page_table_kernel_cost='UNKNOWN_NOT_MEASURED',
        explanation='shared memfd pages not charged anew per alias/mapping; charge placement must be observed; private COW/anonymous/thread stacks/page tables additional'),
      omitted_costs=['source cache includes all429 input objects plus validator code/evidence/tools once by dev/inode, not just required303',
        'source page-cache charges may belong to creator domain or preexisting domain; modeled worst both copies',
        'native EVP/allocator/stacks/linked libraries/FD+inode/VMA/slab/pidfd/seccomp/ptrace/socket buffers',
        'collector Python heap/source modules/framing and persisted audit/stdout/stderr evidence page cache',
        'filesystem readahead/metadata/journal, transient sockets and page-table charges; reserves not measurement'],
      double_count_avoided=['64KiB copy+64KiB digest counted once for serial preparation, not5 or303 times',
        'aliases not extra objects; source duplicate paths of same dev/inode not additional copies',
        'RO reopen/dup/mount/mapping do not copy memfd bytes; no entire-file heap or second output from final hash',
        'prepared298 included once in full303; identical digest across3 DART original inodes still3 copies'],
      observations=dict(observed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),cgroup_membership=membership,cgroup_limits=cg,inherited_preparer_rlimits=inherited,usage_peaks_measured=False,source_bytes_read_only_verified=True),
      alternatives=options,proposed_settings=proposal,
      non_changes=dict(target_rlimits=m['rlimits'],target_resources=m['resources'],owner_FSIZE_required_at_least=max(r['bytes'] for r in large),owner_NOFILE_required_floor=316,owner_NOFILE_observed=inherited['NOFILE'],owner_AS=inherited['AS'],
        owner_FSIZE=inherited['FSIZE'],reason='observed owner inherited FSIZE/AS unlimited and NOFILE1048576; no increase needed here. Target child limits remain exact. Any constrained future owner must re-admit; no inheriting target limits before preparation.'),
      applied=False,decision='USER_DECISION_REQUIRED_THREE_SETTINGS_AND_OWNER_PLACEMENT',runtime='UNVERIFIED')
if __name__=='__main__':
    x=ledger();(R/'reports/resource_decision.json').write_text(json.dumps(x,indent=2)+'\n')
    print('five bytes/pages',x['large_exact_bytes'],x['large_page_bytes']);print('full known/cold model',x['full_output_and_buffers'],x['full_preparation_with_cold_source_page_cache'])
