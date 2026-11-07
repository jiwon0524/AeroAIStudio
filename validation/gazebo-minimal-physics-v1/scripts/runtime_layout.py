"""Reused systemd argv/cleanup policy. No service or process operation on import."""
from pathlib import Path
import importlib.util
ROOT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('prior_service_layout',ROOT/'validation/dart-cgroup-integration-v1/scripts/integration.py')
prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)
LIMITS={'MemoryMax':'512M','MemorySwapMax':'0','TasksMax':'64','CPUQuota':'100%','CPUQuotaPeriodSec':'100ms','RuntimeMaxSec':'30s','TimeoutStopSec':'2s','KillMode':'control-group','OOMPolicy':'stop','Delegate':'no','Slice':'app.slice'}
def service_argv(unit,payload):
 argv=prior.argv(unit,payload)
 return [argv[0],'--property=UnsetEnvironment=LD_PRELOAD LD_AUDIT LD_LIBRARY_PATH']+[('--property='+x.split('=',1)[1].split('=',1)[0]+'='+LIMITS[x.split('=',1)[1].split('=',1)[0]]) if x.startswith('--property=') else x for x in argv[1:]]
def cleanup_ok(observed):
 # Same invariants as the approved native supervisor; missing data is rejection.
 return (observed.get('unit_load_state')=='not-found' and observed.get('cgroup_removed') is True
  and observed.get('remaining_pid_start_identities')==[] and observed.get('temp_removed') is True
  and observed.get('canary_removed') is True and observed.get('controller_before_after_diff')==[])
def owned_stop_allowed(unit,saved,current):
 return (bool(saved.get('InvocationID')) and saved.get('Id')==unit==current.get('Id')
  and saved['InvocationID']==current.get('InvocationID'))
