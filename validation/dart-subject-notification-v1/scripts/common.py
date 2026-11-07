import hashlib,importlib.util,json,os,sys
from pathlib import Path
B=Path(__file__).resolve().parents[1];ROOT=B.parents[1];R=B/'reports';W=B/'work'
sys.path.insert(0,str(ROOT/'validation/dart-probe-a-harness-v1/scripts'))
sys.path.insert(0,str(ROOT/'validation/dart-probe-a-runtime-readiness-v1/scripts'))
import readiness_fixed as readiness
from identity import describe_fd
from allowlist import load_manifest as old_manifest, validate
from mapped import verify
# Shared helper imports must not shadow this task's launch/supervisor modules.
sys.path.insert(0,str(B/'scripts'))

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


def check_prepared():
 contract=json.loads((R/'runtime_contract.json').read_text())
 for relative,digest in contract['prepared_source_sha256'].items():
  if hashlib.sha256((B/relative).read_bytes()).hexdigest()!=digest:
   raise ValueError('prepared source changed '+relative)
 if any(os.environ.get(k) for k in ('LD_PRELOAD','LD_AUDIT','LD_LIBRARY_PATH')):
  raise ValueError('loader environment rejected')
 import subprocess
 if subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()!='experiment/dart-internal-trace':
  raise ValueError('unexpected branch')
 subprocess.run(['git','merge-base','--is-ancestor',contract['base_commit'],'HEAD'],cwd=ROOT,check=True,stdout=subprocess.DEVNULL)

def check_fresh():
 paths=[R/'runtime',R/'runtime_integrity.json']+[W/n for n in
  ('runtime_collection_attempt.json','runtime_attempt.json','runtime_integrity_before.json','stdout','stderr','canary')]
 if any(os.path.lexists(p) for p in paths):raise ValueError('existing lifetime output or consumed one-shot')
