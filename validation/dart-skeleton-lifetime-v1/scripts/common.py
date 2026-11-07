import hashlib,importlib.util,json,os,sys
from pathlib import Path
B=Path(__file__).resolve().parents[1];ROOT=B.parents[1];R=B/'reports';W=B/'work'
sys.path.insert(0,str(ROOT/'validation/dart-probe-a-harness-v1/scripts'))
sys.path.insert(0,str(ROOT/'validation/dart-probe-a-runtime-readiness-v1/scripts'))
import readiness
from identity import describe_fd
from allowlist import load_manifest as old_manifest, validate
from mapped import verify

def put(n,v):(R/n).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def load_manifest():
 raw=(R/'manifest.json').read_bytes()
 if hashlib.sha256(raw).hexdigest()!=(W/'manifest.sha256').read_text().strip():raise ValueError('manifest pin')
 m=json.loads(raw);reference=old_manifest()
 if m['profiles']['installed_core_future_only']!=reference['profiles']['installed_core_future_only']:raise ValueError('Core allowlist changed')
 return m

def gate(pid,manifest,send,require_core=False,reject_fixture=False):
 core=manifest['profiles']['installed_core_future_only'];baseline=manifest['profiles']['harmless_fixture_only']
 if require_core:
  from mapped import start_id
  return readiness.post_open(pid,start_id(pid),core,baseline,lambda _:send('GO\n'))
 # Fixture profile only; Core files are exposed for aliases but must not be mapped.
 expected=json.loads(json.dumps(baseline))
 if reject_fixture:expected[0]['sha256']='0'*64
 result=verify(pid,expected)
 if result['status']=='PASS_FILE_IDENTITY':send('GO\n')
 return result

def generate():
 m=old_manifest();m['profiles']['harmless_fixture_only']=json.loads(json.dumps(m['profiles']['harmless_fixture_only']))
 fixture=m['profiles']['harmless_fixture_only'][0];binary=W/'native_loader'
 fd=os.open(binary,os.O_RDONLY|os.O_CLOEXEC)
 try:fixture.update(describe_fd(fd))
 finally:os.close(fd)
 for key in ('real_path','requested_path','absolute_path','symlink_final_path'):fixture[key]=str(binary)
 m['required_paths']['harmless_fixture_only']=[e['real_path'] for e in m['profiles']['harmless_fixture_only']]
 put('manifest.json',m);(W/'manifest.sha256').write_text(hashlib.sha256((R/'manifest.json').read_bytes()).hexdigest()+'\n')
if __name__=='__main__':generate()
