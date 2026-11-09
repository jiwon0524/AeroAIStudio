"""Reconcile sealed isolation controls with observable failure coverage."""
from pathlib import Path
import hashlib,json,sys,subprocess
R=Path(__file__).resolve().parents[1];B=R.parents[1]
OLD=B/'validation/gazebo-joint-execution-contract-v1'
sys.path.insert(0,str(OLD/'scripts'))
import contract
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def evidence(path,*terms):
    p=B/path;lines=p.read_text().splitlines()
    sites={t:[i for i,line in enumerate(lines,1) if t in line] for t in terms}
    assert all(sites.values()),(path,sites)
    return dict(path=path,sha256=sha(p),sites=sites)
def main():
    m=contract.read()
    previous=B/'validation/gazebo-joint-external-review-v1'
    prior=json.loads((previous/'reports/checkpoint.json').read_text())
    for row in prior['evidence']:assert sha(B/row['path'])==row['sha256']
    ode=json.loads((previous/'reports/build_receipt.json').read_text())
    assert sha(Path(ode['elf']['path']))==ode['elf']['sha256']
    src=OLD/'scripts/contract.py'
    code=src.read_text()
    for flag in ('--unshare-all','--cap-drop','--ro-bind-fd','--remount-ro','--clearenv','--proc','--dev'):
        assert flag in m['ordered_bwrap_argv']
    assert '--seccomp' not in m['ordered_bwrap_argv']
    assert not any('SystemCallFilter' in k or 'RestrictAddressFamilies' in k for k in m['resources'])
    evidence_rows=[
      evidence('validation/gazebo-joint-execution-contract-v1/scripts/contract.py','--unshare-all','--ro-bind-fd','--tmpfs','--proc','--clearenv','technical resource blocker'),
      evidence('validation/gazebo-joint-isolation-v1/inputs/fd_bridge.c','S_ISFIFO(in.st_mode)','dup2(2,1)','close_range(5','execv(exe'),
      evidence('validation/gazebo-joint-execution-contract-v1/scripts/attestor.py','for kind in','for fd,expected in','self.isolation();','final mapping' if 'final mapping' in (OLD/'scripts/attestor.py').read_text() else 'self.last_mapping=result'),
      evidence('validation/gazebo-joint-execution-contract-v1/scripts/native_gate.py','self.failed = True','late native access/load/fatal','native final precondition'),
      evidence('validation/gazebo-joint-execution-contract-v1/scripts/protocol.py','self.observe()','EXIT_ACK','stdout_eof and stderr_eof and rc==0'),
      evidence('validation/gazebo-joint-resolution-v1/scripts/supervisor.py','stderr=subprocess.PIPE','while selector.get_map() or p.poll() is None:','session.finalize','verdict.get(\'error\')'),
      evidence('validation/gazebo-joint-boundary-v1/inputs/fd_bridge.c','endpoint(2,O_WRONLY,&err)','same_pipe(&out,&err)','close_range(5','execv(exe')]
    controls=[
      dict(control='filesystem visibility',denial='Fresh root tmpfs; individual pinned RO inputs; root remounted RO; no host-root directory bind. Namespace intended before bridge/harness exec, persists for child threads/destructors.',
           not_denied='Approved files may be reopened; reads/stat/access probes allowed; /scratch and /run writable; proc/dev/shm surfaces remain. Missing host paths normally fail lookup, not a recorded violation.',recording='No complete filesystem attempt channel.',runtime='Actual namespace/mounts/FD leakage, proc/device reachability and errors must be measured.'),
      dict(control='network namespace',denial='--unshare-all intends separate network namespace before exec; no intentional host socket passed.',
           not_denied='socket/connect/bind/listen/send/recv are not syscall-filtered. Local sockets/loopback/abstract UNIX within sandbox remain possible; externally created inherited socket retains capability regardless of namespace.',recording='No complete socket attempt channel.',runtime='Namespace and interface/readback, inherited descriptor identities, network failure behavior.'),
      dict(control='dynamic loading',denial='Fresh filesystem omits unapproved host DSOs/config; clearenv removes ambient loader vars. Reviewed Sim seal denies its own late LoadLib entrypoints.',
           not_denied='Direct foreign dlopen/dlmopen of mounted ELF or procfd alias is not globally intercepted; loader/global constructors run before main and destructors after ACK. Mapping snapshots are point observations, not before-access hooks.',recording='Native fatal/unknown packets latch failure only if produced. Successful or failed silent foreign requests are not reported.',runtime='Provider/mapping/lifetime and all-thread loader mediation evidence.'),
      dict(control='inherited descriptors',denial='Existing bridge closes >=5 before harness exec and checks stdin/stdout FIFO. Candidate additionally validates stderr, all directions, distinct channels and null device.',
           not_denied='Old bridge accepts socket/file as stderr and duplicates it to stdout. Normal supervisor configures PIPEs, but this is not a boundary invariant. No closed-world FD audit during native lifetime.',recording='Candidate exits78 for bad entry FDs; current actual manifest selects old bridge. Candidate remains undeployed.',runtime='Actual 0..4 type/mode/identity at handoff, absence of unintended FDs and no later socket creation.'),
      dict(control='post ACK verdict',denial='GO/100/final-live-mapping/EXIT_ACK policy unchanged; collection must drain both streams until exit and perform owned cleanup.',
           not_denied='ACK itself does not prevent destructor syscalls; exit0 plus EOF cannot reveal an unreported denied request. No authenticated external denial log/EOF/provenance is wired.',recording='NativeSession failure latch rejects observed fatal/unexpected request even when exit0 and cleanup succeed; current collector is session factory only, no released full native execution loop.',runtime='Drain order/late evidence plus trusted mediation coverage from loader init through all threads and final process death.')]
    categories={
      'ODE/libccd init, primitive, collision, cleanup': 'Host path visibility restricted, internal attempts not globally mediated/audited.',
      'FCL/global allocators/DSO init and cleanup': 'Same namespace boundary; constructor reachability separately bounded; no global access-attempt record.',
      'crypto/provider/config and cleanup': 'Host configuration/modules absent unless mounted; silent failure/default-provider fallback is not a violation event.',
      'transport/ZeroMQ/background and shutdown': 'Network namespace contains external reach; creation/local sockets and inherited-socket exception remain outside blanket denial.',
      'console/log streams/destructors': 'RO inputs prevent writes through those mounts; writable scratch and approved pipe writes remain possible. No general unexpected-log-path rejection.',
      'all callbacks after EXIT_ACK': 'Namespace restrictions intended to persist; final mapping snapshot precedes destruction; attempt audit still absent.'}
    report=dict(status='BLOCKED_MISSING_COMPLETE_DENIAL_AND_ATTEMPT_RECORDING',prior_manifest_sha256=sha(OLD/'reports/manifest.json'),
      controls=controls,external_paths=[dict(path=k,status='TECHNICAL_BLOCKER',finding=v) for k,v in categories.items()],evidence=evidence_rows,
      reused_evidence={str(p.relative_to(B)):sha(p) for p in [previous/'reports/final_report.md',previous/'reports/tests.json',previous/'reports/build_receipt.json',previous/'reports/candidate_deployment.json']},
      valid_prior_ode_candidate=ode['elf'],deployment='CONDITION_NOT_MET_NO_DEPLOYMENT_NO_RESEAL',
      stage_b='BLOCKED',risk_acceptance='UNDECIDED',actual_runtime='UNVERIFIED',subject_execution=False)
    (R/'reports/boundary.json').write_text(json.dumps(report,indent=2)+'\n')
    print('5 controls / 6 external lifetime categories reviewed; deployment condition NOT MET')
if __name__=='__main__':main()
