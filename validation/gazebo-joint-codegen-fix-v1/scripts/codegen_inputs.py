"""Exact codegen argv/input policy. No generator or subject execution."""
from pathlib import Path
import json,hashlib,shlex
p=Path(__file__).resolve().parents[1];root=p/'work/config-01';build=root/'build/sim-03';source=root/'src/sim/src/proto';out=build/'gz_msgs_gen'
lock=json.loads((p/'work/selected_files.json').read_text());tools=json.loads((p.parents[1]/'validation/gazebo-joint-inputs-v1/reports/toolchain_files.json').read_text());allowed={str(Path(k).resolve()):v['sha256'] for k,v in lock.items()};allowed.update({x['realpath']:x['sha256'] for x in tools})
origin=json.loads((p/'reports/codegen_origin.json').read_text());protos={str(f.resolve()):hashlib.sha256(f.read_bytes()).hexdigest() for f in source.rglob('*.proto')};assert len(protos)==4
# Compare by filename under the known exact private protocol subdirectory.
assert {Path(k).name:v for k,v in protos.items()}=={Path(k).name:v for k,v in origin['private_proto_files'].items()}
def sha(file):return hashlib.sha256(Path(file).read_bytes()).hexdigest()
def pinned(path):
 real=str(Path(path).resolve());assert Path(real).is_file() and allowed.get(real)==sha(real),'unapproved/changed codegen input '+real
 return real
scripts={str(Path('/usr/bin/gz-msgs10_generate.py').resolve()),str(Path('/usr/bin/gz-msgs10_generate_factory.py').resolve())}
descriptor=root/'prefix/share/gz/protos/gz-msgs10.gz_desc'
def validate(tokens):
 assert tokens[0]=='/usr/bin/python3';pinned(tokens[0]);script=pinned(tokens[1]);assert script in scripts,'unknown codegen script'
 opts={};i=2;lists={'--dependency-proto-descs','--protos'};flags={'--generate-cpp','--generate-python'}
 while i<len(tokens):
  key=tokens[i];assert key.startswith('--') and key not in opts,'invalid/duplicate generator option';i+=1
  if key in flags:opts[key]=True
  elif key in lists:
   values=[]
   while i<len(tokens) and not tokens[i].startswith('--'):values.append(tokens[i]);i+=1
   opts[key]=values
  else:assert i<len(tokens);opts[key]=tokens[i];i+=1
 common={'--output-cpp-path','--proto-path'}
 assert Path(opts['--proto-path']).resolve()==source.resolve();assert Path(opts['--output-cpp-path']).resolve()==out.resolve()
 if script.endswith('gz-msgs10_generate.py'):
  assert set(opts)==common|{'--protoc-exec','--gz-generator-bin','--input-path','--dependency-proto-descs','--generate-cpp','--generate-python','--output-python-path'}
  assert pinned(opts['--protoc-exec'])==str(Path('/usr/bin/protoc').resolve());assert pinned(opts['--gz-generator-bin'])==str(Path('/usr/bin/gz-msgs10_protoc_plugin').resolve())
  assert [str(Path(x).resolve()) for x in opts['--dependency-proto-descs']]==[str(descriptor.resolve())];pinned(descriptor)
  inp=str(Path(opts['--input-path']).resolve());assert inp in protos and sha(inp)==protos[inp]
  assert Path(opts['--output-python-path']).resolve()==out/'python'
 else:
  assert set(opts)==common|{'--proto-package','--protos'};assert opts['--proto-package']=='gz.sim.private_msgs'
  assert set(str(Path(x).resolve()) for x in opts['--protos'])==set(protos)
  for f,h in protos.items():assert sha(f)==h
 return {'script':script,'options':opts}
