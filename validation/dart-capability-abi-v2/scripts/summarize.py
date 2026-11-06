from common import *
import re,xml.etree.ElementTree as ET,tempfile
inv=json.loads((R/'reports/symbol_inventory.json').read_text());summary={}
for name,v in inv.items():
 d=v['dynamic'];summary[name]={'path':v['path'],'sha256':v['sha256'],'SONAME':re.findall(r'\(SONAME\).*?\[(.*?)\]',d),'NEEDED':re.findall(r'\(NEEDED\).*?\[(.*?)\]',d),'RPATH_RUNPATH':re.findall(r'\((?:RUNPATH|RPATH)\).*?\[(.*?)\]',d),'FLAGS':[x.strip() for x in d.splitlines() if '(FLAGS' in x],'undefined_symbol_versions':sorted({s['version'] for s in v['symbols'].values() if s['section']=='UND'})}
save('elf_summary.json',summary)
vts={k:{n:s['size'] for n,s in inv[k]['symbols'].items() if n.startswith('_ZTVN4dart') and s['section']!='UND'} for k in ('installed_core','baseline_core','trace_core')}
vts['size_differences']={n:{k:vts[k].get(n) for k in ('installed_core','baseline_core','trace_core')} for n in set().union(*(vts[k].keys() for k in ('installed_core','baseline_core','trace_core'))) if len({vts[k].get(n) for k in ('installed_core','baseline_core','trace_core')})>1}
save('vtable_sizes.json',vts)
tests={}
for name in ('regression','native_tests','native_tests_initial'):
 suites=list(ET.parse(R/f'reports/{name}.xml').iter('testsuite'));tests[name]={k:sum(int(s.get(k,0)) for s in suites) for k in ('tests','failures','errors','skipped')}
tests['final_total_distinct']=tests['regression']['tests']+tests['native_tests']['tests'];tests['initial_metadata_audit_failure']='Incorrect OFF getType expectation in newly added audit test; actual Active guard inspected, test corrected to assert OFF identical and ON extra metadata calls. Original instrumentation and criteria unchanged; initial XML/log retained.'
save('test_summary.json',tests)
# Preserve the actual four-arm call audit result outside ephemeral pytest temp output.
rows={}
audit_dir=Path(tempfile.mkdtemp(prefix='metadata-audit-',dir=R/'work'))
for tag,enabled in [('original','off'),('baseline','off'),('trace','off'),('trace','on')]:
 path=audit_dir/(tag+enabled+'.json')
 q=run([R/f'work/{tag}_metadata','primary_true',enabled,path]);assert q['rc']==0;rows[tag+'_'+enabled]={'rc':q['rc'],'stdout':q['stdout'],'stderr':q['stderr']}
save('metadata_call_observation.json',rows)
print('Tests',tests);print('DART vtable size differences',len(vts['size_differences']))
