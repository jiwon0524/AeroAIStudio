"""Read ELF/source bytes only. Does not import launch/stage/supervisor or run targets."""
import ast,hashlib,json,os,subprocess,sys
from pathlib import Path
B=Path(__file__).resolve().parents[1];ROOT=B.parents[1]
sys.path.insert(0,str(ROOT/'validation/dart-probe-a-harness-v1/scripts'))
from identity import open_checked
m=json.loads((B/'reports/manifest.json').read_text());c=json.loads((B/'reports/runtime_contract.json').read_text())
checks={};detail=[]
checks['source_pins']=all(hashlib.sha256((B/p).read_bytes()).hexdigest()==h for p,h in c['prepared_source_sha256'].items())
checks['manifest_pin']=hashlib.sha256((B/'reports/manifest.json').read_bytes()).hexdigest()==(B/'work/manifest.sha256').read_text().strip()
for profile,entries in m['profiles'].items():
 for entry in entries:
  fd=open_checked(entry);os.close(fd)
  assert not entry['rpath'] and not entry['runpath']
  detail.append({k:entry[k] for k in ('real_path','sha256','build_id','device','inode')})
checks['all_pinned_files']=True
for p in (B/'scripts').glob('*.py'):ast.parse(p.read_text())
checks['python_ast']=True
src=(B/'fixtures/skeleton.cpp').read_text()
checks['gate_before_create']=src.index('read(STDIN_FILENO')<src.index('Skeleton::create')
checks['exactly_one_create']=src.count('Skeleton::create(')==1
checks['reset_before_expired']=src.index('owner.reset()')<src.index('if (!observer.expired())')
checks['scope']=all(x not in src for x in ('World::','createJoint','BodyNode::','CollisionDetector::'))
checks['fresh_one_shot']=not any((B/'work').glob('*attempt*')) and not (B/'reports/runtime').exists()
exe=B/'work/skeleton_fixture'
def read(*args):return subprocess.check_output(args,text=True)
dynamic=read('readelf','-d',str(exe));symbols=read('nm','-DC',str(exe));program=read('readelf','-lW',str(exe))
checks['no_search_path']='(RPATH)' not in dynamic and '(RUNPATH)' not in dynamic
checks['relro_now']='GNU_RELRO' in program and 'BIND_NOW' in dynamic
checks['core_create_import']='U dart::dynamics::Skeleton::create' in symbols
exports=read('nm','-DC',m['profiles']['installed_core_future_only'][0]['real_path'])
checks['core_create_export']=' T dart::dynamics::Skeleton::create(std::__cxx11::basic_string' in exports
# Strict alias graph uses only known providers; no dynamic loader invocation.
providers={name for e in m['profiles']['installed_core_future_only'] for name in e['soname']}
checks['closure']=all(n in providers for e in m['profiles']['installed_core_future_only'] for n in e['needed'])
checks['fixture_needed_in_closure']=all(n in providers for n in m['profiles']['harmless_fixture_only'][0]['needed'])
result={'checks':checks,'status':'PASS' if all(checks.values()) else 'FAIL','execution':'NOT_RUN','libraries':detail,'dynamic':dynamic,'undefined_symbols':symbols,'limitations':['Static checks do not validate runtime dispatch, namespace enforcement, object ABI, destruction or resource sufficiency.','weak_ptr expired proves ownership control-block state, not absence of all leaks.']}
(B/'reports/static_review.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'status':result['status'],'checks':checks}))
raise SystemExit(0 if all(checks.values()) else 1)
