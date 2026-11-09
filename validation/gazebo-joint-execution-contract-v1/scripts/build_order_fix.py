"""Compile two affected Sim translation units, relink only. Never execute outputs."""
from pathlib import Path
import json,shlex,subprocess,shutil,hashlib,difflib
R=Path(__file__).resolve().parents[1];B=R.parents[1];N=B/'validation/gazebo-joint-native-resource-v1';old=N/'work/build/sim';src=R/'work/src/sim';prefix=R/'work/prefix/lib'
prefix.mkdir(parents=True,exist_ok=True)
assert not src.exists(),'preserve existing source copy'
shutil.copytree(N/'work/src/sim',src,symlinks=True)
patch=[]
for rel in ['src/systems/physics/Physics.cc','src/SimulationRunner.cc']:
 p=src/rel;a=p.read_text()
 if rel.endswith('Physics.cc'):
  line='  aero_joint::State("ready_state",_info,this->jointBody,_ecm,this->jointWorld->getSimFrames(),this->jointWorld->getTime(),this->jointInitCount);\n';assert a.count(line)==1;b=a.replace(line,'')
 else:
  line='    bootstrap->JointState("ready_state",this->currentInfo,this->entityCompMgr);';assert a.count(line)==1;b=a.replace(line,'    if (!bootstrap->JointValidate(this->currentInfo)) return false;\n'+line+'\n    if (!bootstrap->JointValidate(this->currentInfo)) return false;\n'+line)
 p.write_text(b);patch+=difflib.unified_diff(a.splitlines(True),b.splitlines(True),fromfile=rel,tofile=rel,n=0)
(R/'inputs/ready_order.patch').write_text(''.join(patch))
commands=[];objects={}
for rel in ['src/SimulationRunner.cc','src/systems/physics/Physics.cc']:
 row=next(x for x in json.loads((old/'compile_commands.json').read_text()) if x['file']==str(N/'work/src/sim'/rel));a=shlex.split(row['command']);obj=a[a.index('-o')+1];newobj=R/'work'/(Path(rel).stem+'.o');objects[obj]=str(newobj)
 a[a.index('-c')+1]=str(src/rel);a[a.index('-o')+1]=str(newobj);a+=['-MD','-MF',str(newobj.with_suffix('.d'))];commands.append((Path(rel).stem+'.compile',a))
for target in ['gz-sim8','gz-sim8-physics-system']:
 text=subprocess.check_output(['/usr/bin/ninja','-C',str(old),'-t','commands',target],text=True)
 line=next(l for l in text.splitlines() if ' -o lib/lib'+target+'.so.' in l and ' -shared ' in l)
 parts=[x.strip() for x in line.split('&&')];a=shlex.split(next(x for x in parts if ' -shared ' in x))
 a=[objects.get(x,x) for x in a];out=prefix/('lib'+target+'.so.8.15.0');a[a.index('-o')+1]=str(out)
 a=[str(prefix/'libgz-sim8.so.8.15.0') if x=='lib/libgz-sim8.so.8.15.0' else ('-Wl,-rpath,'+str(prefix)+':'+x.split(',',2)[2]) if x.startswith('-Wl,-rpath,') else x for x in a]
 commands.append((target+'.link',a))
# Compile first, link core, then plugin (the collected order already satisfies this).
records=[]
for label,a in commands:
 log=R/'logs'/(label+'.log')
 with log.open('x') as f:rc=subprocess.run(a,cwd=old,stdout=f,stderr=subprocess.STDOUT,env={'PATH':'/usr/bin:/bin','LC_ALL':'C'}).returncode
 records.append(dict(label=label,argv=a,cwd=str(old),returncode=rc,log=str(log.relative_to(B)),log_sha256=hashlib.sha256(log.read_bytes()).hexdigest()));(R/'reports/build_steps.json').write_text(json.dumps(records,indent=2)+'\n');print(label,rc,flush=True)
 if rc:raise SystemExit(rc)
for name in ['libgz-sim8','libgz-sim8-physics-system']:
 for suffix in ['.so','.so.8']:(prefix/(name+suffix)).symlink_to(name+'.so.8.15.0')
print('PASS compile/link only; no binary executed')
