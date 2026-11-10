"""Compile catalog+launch only, attest nine reused objects; never execute ELF."""
from pathlib import Path
import json,shlex,subprocess,shutil,socket,datetime
import receipts
R,B=receipts.R,receipts.B
old=R.parent/'gazebo-request-guard-v8'
prior=json.loads((old/'reports/build_receipt.json').read_text())
W=R/"work"/datetime.datetime.now(datetime.timezone.utc).strftime("build-%Y%m%dT%H%M%S%fZ");W.mkdir()
steps=[]
def command(label,argv):
    argv=[str(Path(shutil.which(argv[0])).resolve()),*argv[1:]]
    log=W/(label+'.log')
    with log.open('x') as f:
        p=subprocess.Popen(argv,stdout=f,stderr=subprocess.STDOUT)
        identity=dict(host=socket.gethostname(),pid=p.pid,start='UNKNOWN')
        try:identity['start']=Path('/proc',str(p.pid),'stat').read_text().rsplit(')',1)[1].split()[19]
        except OSError:pass
        rc=p.wait()
    if rc:raise ValueError('build failed: '+str(log))
    steps.append(dict(label=label,argv=argv,process=identity,returncode=rc,log=str(log),log_sha256=receipts.sha(log),compiler_sha256=receipts.sha(argv[0])))
for p,h in {**prior['inputs'],**prior['outputs']}.items():
    if receipts.sha(p)!=h:raise ValueError('published baseline changed: '+p)
for unit in prior['translation_units']:
    if receipts.sha(unit['object'])!=unit['object_sha256']:raise ValueError('old object changed')
# Reproduce latest repaired v8 link, not old work/launch.o.
base=list(next(s for s in prior['steps'] if s['label']=='link')['argv'])
argv=base.copy();argv[argv.index('-o')+1]=str(W/'baseline-relinked');command('baseline-relink',argv)
expected=prior['outputs'][base[base.index('-o')+1]]
assert receipts.sha(W/'baseline-relinked')==expected
units=[];inputs={}
for unit in prior['translation_units']:
    label=unit['label'];item=dict(unit)
    if label in ('catalog','launch'):
        source=R/'inputs'/(label+'.c');obj=W/(label+'.o');dep=W/(label+'.d')
        command(label,['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-fstack-protector-strong','-fPIC','-MD','-MF',str(dep),'-c',str(source),'-o',str(obj)])
        dependencies={p:receipts.sha(p) for p in shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1])}
        item.update(source=str(source),object=str(obj),object_sha256=receipts.sha(obj),input_hashes=dependencies,status='RECOMPILED')
    else:item['status']='REUSED_REPRODUCED_V8'
    inputs.update(item['input_hashes']);units.append(item)
replacements={u['object']:next(n['object'] for n in units if n['label']==u['label']) for u in prior['translation_units']}
argv=[replacements.get(p,p) for p in base];argv[argv.index('-o')+1]=str(W/'candidate');command('link',argv)
elf=subprocess.check_output(['readelf','-h','-d','-l',str(W/'candidate')],text=True)
assert 'libdart' not in elf and 'libgz' not in elf
(W/'readelf.txt').write_text(elf)
outputs={str(W/'candidate'):receipts.sha(W/'candidate'),**{p:h for p,h in prior['outputs'].items() if p!=base[base.index('-o')+1]}}
snapshot=receipts.snapshot()
record=dict(schema=3,status='COMPILED_LINKED_STATIC_ONLY',steps=steps,translation_units=units,recompiled_translation_units=2,reused_translation_units=9,inputs=inputs,outputs=outputs,source_manifest_sha256=snapshot['sha256'],source_hashes=snapshot['files'],external_python_hashes=snapshot['external_python'],reused_baseline=dict(receipt_sha256=receipts.sha(old/'reports/build_receipt.json'),recorded_elf_sha256=expected,reproduced_elf_sha256=receipts.sha(W/'baseline-relinked')),executed=False,limits_changed=False,candidate_limits_changed=True,entry_exit=78)
for name,value in [('source_manifest',snapshot),('build_receipt',record)]:(R/'reports'/(name+'.json')).write_text(json.dumps(value,indent=2)+'\n')
print('2 changed TUs compiled,9 reused; candidate linked; no ELF executed')
