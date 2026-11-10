"""Recompile only launch TU and relink, preserving original work/ outputs.
Attest reused objects by reproducing the recorded original supervisor ELF first.
No C binary, bridge, owner bootstrap, namespace or service is executed.
"""
from pathlib import Path
import datetime,hashlib,json,subprocess,socket,os,shlex,shutil
import receipts
R=receipts.R;B=receipts.B
prior_dir=R/'work/fd-owner-before-repair'
prior=json.loads((prior_dir/'reports/build_receipt.json').read_text())
run_dir=R/'work/fd-owner-repair'/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
run_dir.mkdir(parents=True,exist_ok=False)
steps=[]
def command(label,argv):
    compiler=str(Path(shutil.which(argv[0])).resolve());argv=[compiler,*argv[1:]]
    log=run_dir/(label+'.log')
    with log.open('w') as stream:
        p=subprocess.Popen(argv,stdout=stream,stderr=subprocess.STDOUT)
        process=dict(host=socket.gethostname(),pid=p.pid,start='UNKNOWN')
        try:process['start']=Path('/proc',str(p.pid),'stat').read_text().rsplit(')',1)[1].split()[19]
        except OSError:pass
        rc=p.wait()
    if rc:raise RuntimeError('compile/link failure retained at '+str(log))
    step=dict(label=label,argv=argv,process=process,returncode=rc,log=str(log.relative_to(B)),log_sha256=receipts.sha(log),compiler_sha256=receipts.sha(compiler))
    steps.append(step);return step
# Original inputs must still match except the intentionally edited launch.c.
for path,digest in prior['inputs'].items():
    if Path(path)==R/'inputs/launch.c':continue
    if receipts.sha(path)!=digest:raise ValueError('unexpected prior native dependency change: '+path)
for path,digest in prior['outputs'].items():
    if receipts.sha(path)!=digest:raise ValueError('original ELF changed: '+path)
base_link=next(s for s in prior['steps'] if s['label']=='link')['argv']
baseline=list(base_link);baseline[baseline.index('-o')+1]=str(run_dir/'baseline-relinked')
command('baseline-relink',baseline)
expected=prior['outputs'][str(R/'work/candidate')]
if receipts.sha(run_dir/'baseline-relinked')!=expected:raise ValueError('reused objects do not reproduce original recorded ELF')
launch=next(s for s in prior['steps'] if s['label']=='launch')['argv']
argv=list(launch);argv[argv.index('-o')+1]=str(run_dir/'launch.o');argv[argv.index('-MF')+1]=str(run_dir/'launch.d')
compile_step=command('launch',argv)
new_link=[str(run_dir/'launch.o') if p==str(R/'work/launch.o') else p for p in base_link]
new_link[new_link.index('-o')+1]=str(run_dir/'candidate')
command('link',new_link)
units=[];dependencies={}
for item in prior['steps']:
    if '-c' not in item['argv']:continue
    label=item['label'];obj=Path(item['argv'][item['argv'].index('-o')+1])
    dep=Path(item['argv'][item['argv'].index('-MF')+1])
    if label=='launch':obj=run_dir/'launch.o';dep=run_dir/'launch.d'
    data={p:receipts.sha(p) for p in shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1])}
    dependencies.update(data)
    units.append(dict(label=label,source=item['argv'][item['argv'].index('-c')+1],object=str(obj),object_sha256=receipts.sha(obj),
        input_hashes=data,status='RECOMPILED' if label=='launch' else 'REUSED_REPRODUCED_BASELINE'))
outputs={str(run_dir/'candidate'):receipts.sha(run_dir/'candidate'),str(R/'work/libaero-resource.so'):receipts.sha(R/'work/libaero-resource.so'),str(R/'work/unit-anchor'):receipts.sha(R/'work/unit-anchor')}
elf=subprocess.check_output(['readelf','-h','-d','-l',str(run_dir/'candidate')],text=True)
if 'libdart' in elf or 'libgz' in elf:raise ValueError('unexpected subject dependency')
(run_dir/'readelf.txt').write_text(elf)
source_manifest=receipts.snapshot()
record=dict(schema=2,status='COMPILED_LINKED_STATIC_ONLY',steps=steps,translation_units=units,
    recompiled_translation_units=1,reused_translation_units=10,inputs=dependencies,outputs=outputs,
    source_manifest_path='validation/gazebo-request-guard-v8/reports/source_manifest.json',source_manifest_sha256=source_manifest['sha256'],
    source_hashes=source_manifest['files'],external_python_hashes=source_manifest['external_python'],
    reused_baseline=dict(receipt_sha256=receipts.sha(prior_dir/'reports/build_receipt.json'),recorded_elf_sha256=expected,reproduced_elf_sha256=receipts.sha(run_dir/'baseline-relinked')),
    executed=False,limits_changed=False,entry_exit=78,baseline_outputs_preserved=True)
for name,value in [('source_manifest',source_manifest),('build_receipt',record)]:
    text=json.dumps(value,indent=2)+'\n';(R/'reports'/f'{name}.json').write_text(text);(run_dir/f'{name}.json').write_text(text)
print('1 changed TU compiled;10 TU objects reused with reproduced baseline ELF;3 outputs hash-bound; no native execution')
