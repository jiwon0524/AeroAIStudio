"""Read-only checks. No systemd query, process creation, target load or marker."""
from pathlib import Path
import json,os,hashlib,subprocess
B=Path(__file__).resolve().parents[1]
def check_inputs():
 c=json.loads((B/'reports/runtime_contract.json').read_text())
 for relative in c['outputs']+c['one_shot']:
  if os.path.lexists(B/relative):raise ValueError('existing runtime output/one-shot '+relative)
 for relative,digest in c['source_sha256'].items():
  if hashlib.sha256((B/relative).read_bytes()).hexdigest()!=digest:raise ValueError('source/input changed '+relative)
 keys=('LD_PRELOAD','LD_AUDIT','LD_LIBRARY_PATH','GZ_SIM_SYSTEM_PLUGIN_PATH','GZ_SIM_PHYSICS_ENGINE_PATH','GZ_SIM_SERVER_CONFIG_PATH','GZ_SIM_RESOURCE_PATH')
 if any(os.environ.get(k) for k in keys):raise ValueError('inherited loader/Gazebo search environment')
 root=B.parents[1]
 if subprocess.check_output(['git','branch','--show-current'],cwd=root,text=True).strip()!='experiment/dart-internal-trace':raise ValueError('branch mismatch')
 subprocess.run(['git','merge-base','--is-ancestor',c['base_commit'],'HEAD'],cwd=root,check=True,stdout=subprocess.DEVNULL)
 import inputs
 inputs.preflight_static()
 return c
