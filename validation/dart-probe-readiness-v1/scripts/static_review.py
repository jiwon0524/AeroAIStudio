"""Read ELF bytes with readelf only; never ldd or loader trace."""
import json,re,subprocess
from pathlib import Path
from preserve import digest,ROOT,TASK
source=ROOT/'validation/dart-targeted-evidence-v1/reports'
rows={}
arms=json.loads((source/'probe_library_arms.json').read_text())
for item in json.loads((source/'binary_inventory.json').read_text())['binaries']+[x for a in arms.values() for x in a['libraries']]:
    path=item.get('real_path',item.get('path')); p=Path(path)
    if path in rows: continue
    if not p.is_file(): rows[path]={'path':path,'exists':False}; continue
    outputs={flag:subprocess.check_output(['/usr/bin/readelf',flag,str(p)],text=True,stderr=subprocess.STDOUT) for flag in ('-dW','-nW','-SW')}
    d=outputs['-dW']; build=re.search(r'Build ID:\s*(\S+)',outputs['-nW'])
    row={'path':path,'exists':True,'sha256':digest(p),'build_id':build.group(1) if build else None,'soname':re.findall(r'\(SONAME\).*?\[(.*?)\]',d),'needed':re.findall(r'\(NEEDED\).*?\[(.*?)\]',d),'rpath':re.findall(r'\(RPATH\).*?\[(.*?)\]',d),'runpath':re.findall(r'\(RUNPATH\).*?\[(.*?)\]',d),'init_fini_tags':[l.strip() for l in d.splitlines() if any(t in l for t in ('(INIT)','(FINI)','(INIT_ARRAY','(FINI_ARRAY'))]}
    row['previous_identity_match']=row['sha256']==item.get('sha256') and row['build_id']==item.get('build_id')
    row['empty_loader_component']=any('' in v.split(':') for v in row['rpath']+row['runpath'])
    rows[path]=row
result={'tool':'/usr/bin/readelf -dW/-nW/-SW only','libraries':list(rows.values()),'closure_frozen':False,'constructor_semantics_reviewed':False,'symbol_resolution_executed':False,'collision_review':'same Core SONAME across arms: separate processes required; retained installed Bullet binds Core by SONAME; symbol providers/interposition/transitive closure remain unverified','load_order_plan':'one fresh process per arm; freeze External and transitive providers first, then Core, then selected collision module; Gazebo plugin metadata only, never load','shutdown_plan':'no assumed safe dlclose: approve reverse handle order only after init/fini/TLS/global/thread ownership audit; process exit also executes cleanup'}
(TASK/'reports/elf_review.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'existing':sum(r['exists'] for r in rows.values()),'missing':sum(not r['exists'] for r in rows.values()),'all_existing_identity_match':all(r.get('previous_identity_match',True) for r in rows.values())}))
