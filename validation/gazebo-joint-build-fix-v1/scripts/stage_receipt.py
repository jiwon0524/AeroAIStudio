"""Future static provenance check after selected component staging. No ELF run."""
from pathlib import Path
import hashlib,json,sys,re
r=Path(__file__).resolve().parents[1];root=r/'work/config-01';component=sys.argv[1]
build=root/'build'/component;prefix=root/'prefix'
receipt=root/'manifests/staged.json';known=json.loads(receipt.read_text()) if receipt.exists() else {}
names={'probe':['aero-joint-probe'],'dart':['dart','dart-external-odelcpsolver','dart-collision-ode','dart-collision-bullet','dart-utils','dart-utils-urdf'],'physics':['gz-physics7','gz-physics7-dartsim-plugin'],'sim':['gz-sim8','gz-sim8-physics-system']}[component]
artifacts={}
for p in build.rglob('*.so*'):
 if p.is_file() and any(re.fullmatch('lib'+re.escape(n)+r'\.so(?:\..*)?',p.name) for n in names):
  real=p.resolve()
  if real.name in artifacts and artifacts[real.name]!=real:raise ValueError('ambiguous built artifact')
  artifacts[real.name]=real
changed=0
for p in prefix.rglob('*.so*'):
 if not p.is_file():continue
 source=artifacts.get(p.resolve().name)
 sha=hashlib.sha256(p.read_bytes()).hexdigest()
 if source is not None:
  if sha!=hashlib.sha256(source.read_bytes()).hexdigest():raise ValueError('staged bytes differ '+str(p))
  known[str(p.resolve())]={'sha256':sha,'source':str(source),'component':component};changed+=1
 elif known.get(str(p.resolve()),{}).get('sha256')!=sha:raise ValueError('unknown staged ELF '+str(p))
if changed==0 and component!='harness':raise ValueError('no selected artifacts staged')
receipt.write_text(json.dumps(known,indent=2)+'\n')
print('PASS staged provenance',component,changed)
