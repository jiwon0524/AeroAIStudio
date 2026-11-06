from common import *
import time,re
inv=json.loads((R/'reports/symbol_inventory.json').read_text());tool=R/'work/dependencies/usr/bin/abidiff';dep=R/'work/dependencies/usr'
env=os.environ.copy();env['LD_LIBRARY_PATH']=str(dep/'lib/x86_64-linux-gnu')+':'+str(dep/'lib')
records=[]
# No suppressions or hidden symbol filters. Fail instead of silently downgrading to ELF-only.
for part in ('external','ode','ipopt','nlopt','core'):
 for pair in (('baseline','trace'),('reference','trace')):
  left=('packaged_' if part in ('ipopt','nlopt') else 'installed_')+part if pair[0]=='reference' else 'baseline_'+part
  right='trace_'+part;name=left+'_vs_'+right
  args=[tool,'--no-default-suppression','--no-show-locs','--no-corpus-path','--fail-no-debug-info',inv[left]['path'],inv[right]['path']]
  started=time.monotonic();result=run(args,env=env);output=result.pop('stdout');error=result.pop('stderr');f=R/'reports'/('abidiff_'+name+'.txt');f.write_text(output+error)
  result.update(name=name,duration_s=time.monotonic()-started,report=str(f.relative_to(R)),report_sha256=sha(f),error_bit=bool(result['rc']&1),abi_change_bit=bool(result['rc']&4),incompatible_change_bit=bool(result['rc']&8),summary='\n'.join(output.splitlines()[:5]),diagnostic=error[:2000]);records.append(result);save('dwarf_comparison.json',records)
  print(name,'rc',result['rc'],result['summary'],result['diagnostic'][:160],flush=True)
