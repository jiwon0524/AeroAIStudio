"""Compile only two changed trusted-owner TUs; hash-reuse all other objects.
Never execute native outputs, driver, service or marker operations.
"""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import *
import subprocess,shutil,shlex,datetime,socket
OLD=R.parent/'gazebo-request-guard-v10'
prior=json_read(OLD/'reports/build_receipt.json')
W=R/'work'/datetime.datetime.now(datetime.timezone.utc).strftime('build-%Y%m%dT%H%M%S%fZ');W.mkdir()
steps=[];units=[]
def run(label,args):
    exe=str(Path(shutil.which(args[0])).resolve());argv=[exe,*args[1:]];p=W/(label+'.log')
    with p.open('x') as f:
        proc=subprocess.Popen(argv,stdout=f,stderr=subprocess.STDOUT)
        task=dict(host=socket.gethostname(),pid=proc.pid,start='UNKNOWN')
        try:task['start']=Path('/proc',str(proc.pid),'stat').read_text().rsplit(')',1)[1].split()[19]
        except OSError:pass
        rc=proc.wait()
    steps.append(dict(label=label,argv=argv,process=task,rc=rc,log=str(p),log_sha256=sha(p),compiler_sha256=sha(exe)))
    need(rc==0,'compile/link failed: '+str(p))
flags=['-std=c11','-O2','-Wall','-Wextra','-Werror','-fstack-protector-strong','-fPIC']
for name in ('launch','owner_main'):
    obj=W/(name+'.o');dep=W/(name+'.d')
    run(name,['cc',*flags,'-MD','-MF',str(dep),'-c',str(R/'inputs'/(name+'.c')),'-o',str(obj)])
    inputs={p:sha(p) for p in shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1])}
    units.append(dict(label=name,source=str(R/'inputs'/(name+'.c')),object=str(obj),object_sha256=sha(obj),input_hashes=inputs,status='COMPILED'))
for name in ('probe','catalog','metadata','control','broker','bound','loader','namespace'):
    u=next(x for x in prior['translation_units'] if x['label']==name)
    need(sha(u['object'])==u['object_sha256'],'reused object hash changed')
    for p,h in u['input_hashes'].items():need(sha(p)==h,'reused dependency changed')
    need((R/'inputs'/(name+'.c')).read_bytes()==Path(u['source']).read_bytes(),'reused local source differs')
    units.append(dict(u,status='REUSED_HASH_VERIFIED'))
objects={u['label']:u['object'] for u in units}
run('owner-link',['cc','-pie','-Wl,-z,relro,-z,now',*[objects[n] for n in ('catalog','launch','metadata','control','owner_main','broker','bound','loader','namespace')],'-lcrypto','-o',str(W/'owner')])
outputs={str(W/'owner'):sha(W/'owner')}
for name in ('probe','unit-anchor'):
    p=next(p for p in prior['outputs'] if Path(p).name==name);need(sha(p)==prior['outputs'][p],'reused ELF hash changed');outputs[p]=sha(p)
for p in outputs:
    out=subprocess.check_output(['/usr/bin/readelf','-h','-d','-l','-Ws',p],text=True)
    need(not any('Shared library: ['+x in out for x in ('libdart','libgz','libsdformat')),'forbidden ELF dependency')
    (W/(Path(p).name+'.readelf.txt')).write_text(out)
receipt=dict(status='COMPILED_LINKED_NOT_EXECUTED',steps=steps,translation_units=units,recompiled=2,reused=8,reused_anchor=True,inputs={p:h for u in units for p,h in u['input_hashes'].items()},outputs=outputs,baseline_receipt_sha256=sha(OLD/'reports/build_receipt.json'),actual_native_executions=0,actual_services_started=0,limits_changed=False)
(R/'reports/build_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print('Compiled2 owner TUs; reused8 objects and probe/anchor; native execution0')
