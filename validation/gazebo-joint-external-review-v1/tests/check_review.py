"""Reuse 31 sealed static/mock cases, add shutdown/fallback negative cases.

No native execution. Original test source remains unchanged; redirect only its
report output and temporary directory to this phase before evaluating it.
"""
from pathlib import Path
import hashlib, json, os, subprocess

R = Path(__file__).resolve().parents[1]
B = R.parents[1]
OLD = B/'validation/gazebo-joint-execution-contract-v1'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main_state():
    root = Path('/home/jiwon/Projects/AeroAIStudio')
    status = subprocess.check_output(['git','status','--porcelain','-z'],cwd=root)
    files = {}
    for entry in status.split(b'\0'):
        if not entry: continue
        p = root/os.fsdecode(entry[3:])
        if p.is_symlink(): files[str(p)] = ['symlink',os.readlink(p)]
        elif p.is_file(): files[str(p)] = sha(p)
    return dict(head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root).decode().strip(),status=status.hex(),files=files)

source = OLD/'tests/test_contract.py'
old_report = OLD/'reports/tests.json'
before = {str(p):sha(p) for p in (source,old_report,OLD/'reports/manifest.json',OLD/'inputs/manifest.sha256',OLD/'reports/contract_result.md')}
main_before = main_state()
link = B/'libgz-physics-dartsim-plugin.so'
link_before = (link.lstat().st_ino,os.readlink(link))
text = source.read_text()
assert text.count("(R/'reports/tests.json').write_text(") == 1
text = text.replace("(R/'reports/tests.json').write_text(","Path("+repr(str(R/'reports/reused_tests.json'))+").write_text(")
text = text.replace("tempfile.TemporaryDirectory(dir=R/'work')", "tempfile.TemporaryDirectory(dir=Path("+repr(str(R/'work'))+"))")
scope = {'__file__':str(source),'__name__':'sealed_mock_reuse'}
exec(compile(text,str(source),'exec'),scope)
assert len(scope['cases']) == 31
checks=[]
def reject(name, fn):
    try: fn()
    except (ValueError,OSError,KeyError): checks.append(dict(case=name,status='PASS_REJECTED'))
    else: raise AssertionError(name)

def final_wait():
    s,w,out = scope['initialized']()
    for i in range(1,101):
        t=i*.001
        state={k:0 for k in ['x','y','z','vx','vy','vz','roll','pitch','yaw']}
        state.update(z=1-4.905*t*t,vz=-9.81*t)
        s.packet(dict(kind='sample',iteration=i,sim_time_ns=i*1000000,dt_ns=1000000,paused=False,native_frame=i,native_time=t,init_count=1,state_source='measured_live_components',state=state))
    s.packet(dict(kind='final_wait',iteration=100,sim_time_ns=100000000))
    w.send_ack()
    assert out == [b'GO\n',b'EXIT_ACK\n']
    return s

for name, packet in [
    ('shutdown_native_fatal',dict(kind='native_resource',seq=999,role='fatal',sha256='',device=0,inode=0,ok=False)),
    ('shutdown_file_fallback',dict(kind='aux_resource_request',path='/unexpected/config')),
    ('shutdown_network_request',dict(kind='aux_resource_request',operation='connect',address='unexpected')),
    ('shutdown_dynamic_load',dict(kind='aux_resource_request',operation='dlopen',path='/unexpected/provider.so'))]:
    s=final_wait()
    reject(name,lambda:s.packet(packet))
    reject(name+'_cannot_pass_with_ACK_EOF_exit_cleanup',lambda:s.finalize(True,True,0,True,True,True))

for missing in ('server_config','server_config_parse','physics_provider','dartsim_provider','world_graph'):
    s,w,out=scope['setup']()
    def incomplete():
        for p in scope['packets']():
            if p['role'] != missing:
                p=dict(p,seq=s.seq+1)
                s.packet(p)
    reject('missing_'+missing+'_before_ready',incomplete)
    reject('missing_'+missing+'_GO_denied',s.authorize)
    assert out==[]

for failure in ('ODE_init','ODE_thread_data','ODE_world'):
    s,w,out=scope['setup']()
    reject(failure+'_fatal_before_ready',lambda:s.packet(dict(kind='native_resource',seq=1,role='fatal',sha256='',device=0,inode=0,ok=False)))
    reject(failure+'_GO_denied',s.authorize)
    assert out==[]

import copy
candidate=json.loads((R/'reports/build_receipt.json').read_text())['elf']
q=copy.deepcopy(scope['m'])
q['mounts'][q['roles']['dart_ode']].update(source=candidate['path'],real_path=candidate['path'],sha256=candidate['sha256'],device=candidate['device'],inode=candidate['inode'])
reject('candidate_partial_mount_replacement_rejected',lambda:scope['C'].validate(q,scope['C'].digest(q),files=False))

assert main_before == main_state()
assert before == {p:sha(Path(p)) for p in before}
assert link_before == (link.lstat().st_ino,os.readlink(link))
# The bound manifest is checked again after tests: all mount/code/host inputs.
scope['C'].validate(scope['m'])
result=dict(status='PASS_STATIC_MOCK_ONLY',reused_cases=31,new_negative_cases=len(checks),checks=checks,
            original_reports_unchanged=before,main_preserved=True,dangling_symlink_preserved=True,
            sealed_inputs_revalidated=True,subject_execution=False,
            coverage_limit='Injected packets test collector policy only, not external native before-access interception.')
(R/'reports/tests.json').write_text(json.dumps(result,indent=2)+'\n')
print('PASS: 31 reused +',len(checks),'new negative static/mock cases; native access remains unverified')
