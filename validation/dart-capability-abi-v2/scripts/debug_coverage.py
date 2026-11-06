from common import *
import re
inv=json.loads((R/'reports/symbol_inventory.json').read_text());dep=R/'work/dependencies/usr';env=os.environ.copy();env['LD_LIBRARY_PATH']=str(dep/'lib/x86_64-linux-gnu')+':'+str(dep/'lib');records={}
for name in ('installed_core','installed_external','installed_ode','packaged_ipopt','packaged_nlopt'):
 p=Path(inv[name]['path']);out=R/'work'/('abi-'+name+'.xml')
 cmd=run([dep/'bin/abidw','--no-corpus-path','--no-show-locs','--out-file',out,p],env=env)
 text=out.read_text() if out.exists() else ''
 records[name]={'command':cmd['command'],'rc':cmd['rc'],'stderr':cmd['stderr'],'abi_instr_count':len(re.findall(r'<abi-instr[ >]',text)),'function_decl_count':len(re.findall(r'<function-decl[ >]',text)),'embedded_debug_info_present':'.debug_info ' in inv[name]['sections'],'has_debuglink':'.gnu_debuglink' in inv[name]['sections'],'has_debugaltlink':'.gnu_debugaltlink' in inv[name]['sections'],'abixml_sha256':sha(out) if out.exists() else None,'scope':'Observe availability of actual type information; do not infer full type ABI from symbol-only comparison'}
save('debug_coverage.json',records);print({k:{f:v[f] for f in ('rc','abi_instr_count','function_decl_count','embedded_debug_info_present','has_debuglink')} for k,v in records.items()})
