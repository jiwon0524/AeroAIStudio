"""Build two changed TUs and one callback-only unit mock. Never run owner ELF.
No namespace/manager/marker operations occur in this compiler-only script.
"""
from pathlib import Path
import json,hashlib,shlex,subprocess,shutil,datetime,socket
R=Path(__file__).resolve().parents[1]
OLD=R.parent/'gazebo-request-guard-v10-small02'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def need(ok,why):
    if not ok:raise ValueError(why)
prior=json.loads((OLD/'reports/build_receipt.json').read_text())
W=R/'work'/datetime.datetime.now(datetime.timezone.utc).strftime('build-%Y%m%dT%H%M%S%fZ')
W.mkdir();steps=[];units=[]
def run(label,args):
    exe=str(Path(shutil.which(args[0])).resolve());argv=[exe,*args[1:]]
    log=W/(label+'.log')
    with log.open('x') as f:
        p=subprocess.Popen(argv,stdout=f,stderr=subprocess.STDOUT)
        identity=dict(host=socket.gethostname(),pid=p.pid,start='UNKNOWN')
        try:identity['start']=Path('/proc',str(p.pid),'stat').read_text().rsplit(')',1)[1].split()[19]
        except OSError:pass
        rc=p.wait()
    steps.append(dict(label=label,argv=argv,rc=rc,process=identity,
                      log=str(log),log_sha256=sha(log),compiler_sha256=sha(exe)))
    need(rc==0,'compile/link error: '+str(log))
flags=['-std=c11','-O2','-Wall','-Wextra','-Werror','-fstack-protector-strong','-fPIC']
for name in ('launch','entry'):
    obj=W/(name+'.o');dep=W/(name+'.d')
    run(name,['cc',*flags,'-I',str(OLD/'inputs'),'-MD','-MF',str(dep),'-c',str(R/'inputs'/(name+'.c')),'-o',str(obj)])
    inputs={p:sha(p) for p in shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1])}
    units.append(dict(label=name,source=str(R/'inputs'/(name+'.c')),object=str(obj),
                      object_sha256=sha(obj),input_hashes=inputs,status='COMPILED'))
for name in ('probe','catalog','metadata','control','broker','bound','loader','namespace'):
    u=next(u for u in prior['translation_units'] if u['label']==name)
    need(sha(u['object'])==u['object_sha256'],'reused object changed')
    for p,h in u['input_hashes'].items():need(sha(p)==h,'reused dependency changed')
    units.append(dict(u,status='REUSED_HASH_VERIFIED'))
objects={u['label']:u['object'] for u in units}
run('owner-link',['cc','-pie','-Wl,-z,relro,-z,now',*[objects[n] for n in
    ('catalog','launch','metadata','control','entry','broker','bound','loader','namespace')],'-lcrypto','-o',str(W/'owner-blocked')])
run('map-io-mock',['cc',*flags,'-I',str(R/'inputs'),str(R/'tests/map_io_mock.c'),'-o',str(W/'map-io-mock')])
outputs={str(p):sha(p) for p in (W/'owner-blocked',W/'map-io-mock')}
for p in outputs:
    value=subprocess.check_output(['/usr/bin/readelf','-h','-d','-l','-Ws',p],text=True)
    need(not any('Shared library: ['+x in value for x in ('libdart','libgz','libsdformat')),'forbidden ELF dependency')
    (W/(Path(p).name+'.readelf.txt')).write_text(value)
disassembly=subprocess.check_output(['/usr/bin/objdump','-d','--disassemble=main',str(W/'owner-blocked')],text=True)
(W/'entry-disassembly.txt').write_text(disassembly)
receipt=dict(status='COMPILED_LINKED_OWNER_NOT_EXECUTED',steps=steps,translation_units=units,
             recompiled_owner_tus=2,reused_objects=8,mock_binary=str(W/'map-io-mock'),
             mock_source_sha256=sha(R/'tests/map_io_mock.c'),outputs=outputs,
             baseline_build_sha256=sha(OLD/'reports/build_receipt.json'),
             entry_disassembly=str(W/'entry-disassembly.txt'),entry_disassembly_sha256=sha(W/'entry-disassembly.txt'),
             owner_execution_count=0,services_started=0,markers_consumed=0,limits_changed=False)
(R/'reports/build_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print('Built blocked entry+launch2 TUs; reused8 objects. Callback mock built separately; owner not run.')
