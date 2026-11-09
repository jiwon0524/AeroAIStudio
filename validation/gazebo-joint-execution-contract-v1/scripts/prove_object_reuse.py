"""Relink unchanged predecessor objects and compare pinned ELF bytes; never load."""
from pathlib import Path
import subprocess,shlex,hashlib,json
R=Path(__file__).resolve().parents[1];B=R.parents[1];N=B/'validation/gazebo-joint-native-resource-v1';build=N/'work/build/sim';out=R/'work/relink-proof';out.mkdir(exist_ok=False)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
expected=json.loads((N/'reports/deployment_receipt.json').read_text())['ELFs']
records=[]
for target in ['gz-sim8','gz-sim8-physics-system']:
 lines=subprocess.check_output(['/usr/bin/ninja','-C',str(build),'-t','commands',target],text=True).splitlines();line=next(l for l in lines if ' -o lib/lib'+target+'.so.' in l and ' -shared ' in l)
 argv=shlex.split(next(x.strip() for x in line.split('&&') if ' -shared ' in x));original=build/argv[argv.index('-o')+1];copy=out/original.name
 objects={str((build/x).resolve()):sha((build/x).resolve()) for x in argv if x.endswith('.o')}
 argv[argv.index('-o')+1]=str(copy)
 with (R/'logs'/(target+'.reuse-proof.log')).open('x') as f:rc=subprocess.run(argv,cwd=build,stdout=f,stderr=subprocess.STDOUT,env={'PATH':'/usr/bin:/bin','LC_ALL':'C'}).returncode
 row=dict(target=target,returncode=rc,original=str(original),proof=str(copy),original_sha256=sha(original),proof_sha256=sha(copy) if copy.exists() else None,objects=objects)
 row['expected_sha256']=expected[str(N/'work/prefix/lib'/original.name)]['sha256']
 records.append(row);assert rc==0 and row['original_sha256']==row['proof_sha256']==row['expected_sha256'],row
 print('PASS original object relink byte identity',target,len(objects),'objects',flush=True)
(R/'reports/object_reuse.json').write_text(json.dumps(dict(status='PASS_BYTE_IDENTICAL_RELINK_NO_EXECUTION',records=records),indent=2)+'\n')
