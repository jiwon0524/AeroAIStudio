"""Frozen Core-only allowlist and harmless fixture profile, never loads libraries."""
import hashlib,importlib.util,json,os,subprocess
from pathlib import Path
from identity import describe_fd,open_checked
B=Path(__file__).resolve().parents[1];ROOT=B.parents[1];R=B/'reports';W=B/'work';OLD=ROOT/'validation/dart-probe-a-static-audit-v1'
def put(n,x):(R/n).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def load_manifest():
    raw=(R/'library_allowlist.json').read_bytes();pin=(W/'manifest.sha256').read_text().strip()
    if hashlib.sha256(raw).hexdigest()!=pin:raise ValueError('manifest pin mismatch')
    return json.loads(raw)

def validate(manifest,profile):
    entries=manifest['profiles'][profile];fds=[]
    if not entries:raise ValueError('empty profile')
    if {e['real_path'] for e in entries}!=set(manifest['required_paths'][profile]):raise ValueError('required library missing or unexpected profile member')
    if len({x['sandbox_path'] for x in entries})!=len(entries):raise ValueError('duplicate sandbox path')
    try:
        for entry in entries:
            if entry['rpath'] or entry['runpath']:raise ValueError('search path disallowed')
            fd=open_checked(entry);fds.append(fd)
        return fds
    except BaseException:
        for fd in fds:os.close(fd)
        raise

def generate():
    spec=importlib.util.spec_from_file_location('static_audit',OLD/'scripts/audit.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    old=json.loads((OLD/'reports/dependency_audit.json').read_text());core=[]
    for real,metadata in old['nodes'].items():
        row=dict(metadata);fd=os.open(real,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
        try:current=describe_fd(fd)
        finally:os.close(fd)
        if current['sha256']!=row['sha256'] or current['build_id']!=row['build_id']:raise ValueError('historical identity mismatch')
        row.update(current,library_name=Path(real).name,absolute_path=real,symlink_final_path=real,sandbox_path=real,required=True,role='installed_core_DT_NEEDED',runtime_binding='UNVERIFIED')
        core.append(row)
    binary=W/'native_fixture';row=m.elf(binary);fd=os.open(binary,os.O_RDONLY|os.O_CLOEXEC)
    try:row.update(describe_fd(fd))
    finally:os.close(fd)
    row.update(library_name='native_fixture',absolute_path=str(binary),symlink_final_path=str(binary),sandbox_path='/fixture/native_fixture',required=True,role='harmless_fixture')
    libc=next(x for x in core if x['library_name']=='libc.so.6');loader=next(x for x in core if x['library_name']=='ld-linux-x86-64.so.2')
    manifest={'schema':'probe_a_allowlist_v1','profiles':{'installed_core_future_only':core,'harmless_fixture_only':[row,libc,loader]},'current_execution_profile':'harmless_fixture_only','DART_libraries_mounted_or_loaded_now':False,'excluded':['local Baseline/Trace Core and External','ODE/Bullet optional plugins','Gazebo'],'historical_risks':'B/C expected External lib/ paths missing; actual elsewhere; trailing empty RUNPATH; no repair or automatic substitute','source_audit_sha256':hashlib.sha256((OLD/'reports/dependency_audit.json').read_bytes()).hexdigest()}
    manifest['required_paths']={k:[e['real_path'] for e in v] for k,v in manifest['profiles'].items()}
    target=R/'library_allowlist.json'
    if target.exists() or (W/'manifest.sha256').exists():raise ValueError('fresh allowlist required')
    put('library_allowlist.json',manifest);(W/'manifest.sha256').write_text(hashlib.sha256(target.read_bytes()).hexdigest()+'\n')
    results={}
    for name in manifest['profiles']:
        fds=validate(manifest,name)
        for fd in fds:os.close(fd)
        results[name]={'status':'PASS','entries':len(fds),'meaning':'file identity only, no runtime binding claim'}
    put('allowlist_validation.json',results)
if __name__=='__main__':generate()
