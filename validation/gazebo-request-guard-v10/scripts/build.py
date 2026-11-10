"""Build only harmless probe/owner and small-policy affected objects. No execution."""
from common import *
import subprocess,shlex,shutil,socket,datetime,re
V9=R.parent/'gazebo-request-guard-v9';prior=json_read(V9/'reports/build_receipt.json')
W=R/'work'/datetime.datetime.now(datetime.timezone.utc).strftime('build-%Y%m%dT%H%M%S%fZ');W.mkdir()
steps=[]
def run(label,argv):
    exe=str(Path(shutil.which(argv[0])).resolve());argv=[exe,*argv[1:]];log=W/(label+'.log')
    with log.open('x') as f:
        proc=subprocess.Popen(argv,stdout=f,stderr=subprocess.STDOUT)
        identity=dict(host=socket.gethostname(),pid=proc.pid,start='UNKNOWN')
        try:identity['start']=Path('/proc',str(proc.pid),'stat').read_text().rsplit(')',1)[1].split()[19]
        except OSError:pass
        rc=proc.wait()
    need(rc==0,'compiler/link error: '+str(log))
    steps.append(dict(label=label,argv=argv,process=identity,rc=rc,log=str(log),log_sha256=sha(log),compiler_sha256=sha(exe)))
flags=['-std=c11','-O2','-Wall','-Wextra','-Werror','-fstack-protector-strong','-fPIC']
def compile_unit(name):
    obj=W/(name+'.o');dep=W/(name+'.d')
    run(name,['cc',*flags,'-MD','-MF',str(dep),'-c',str(R/'inputs'/(name+'.c')),'-o',str(obj)])
    inputs={p:sha(p) for p in shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1])}
    return dict(label=name,source=str(R/'inputs'/(name+'.c')),object=str(obj),object_sha256=sha(obj),input_hashes=inputs,status='COMPILED')
probe=compile_unit('probe');run('probe-link',['cc','-pie','-Wl,-z,relro,-z,now',probe['object'],'-pthread','-o',str(W/'probe')])
# Exactly four small originals and five aliases. No Gazebo/DART backing admitted.
paths=[('/probe/fixture',W/'probe',True),('/input/fixed.txt',R/'inputs/fixed.txt',False),('/input/fixed-alias.txt',R/'inputs/fixed.txt',False)]
oldpolicy=json_read(V9/'reports/policy.json')
for name in ('/usr/lib/x86_64-linux-gnu/libc.so.6','/usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2'):
    row=next(x for x in oldpolicy['paths'] if x['path']==name);need(sha(row['source'])==row['original']['sha256'],'libc/loader baseline changed');paths.append((name,Path(row['source']),True))
policy=[];lines=[]
for name,source,execute in paths:
    st=source.stat();o=dict(device=st.st_dev,inode=st.st_ino,sha256=sha(source))
    policy.append(dict(path=name,source=str(source),original=o,size=st.st_size,executable=execute))
    lines.append('{'+','.join([json.dumps(name),str(o['device'])+'ULL',str(o['inode'])+'ULL',json.dumps(o['sha256']),str(int(execute)),json.dumps(str(source))])+'},')
(R/'inputs/allowlist.inc').write_text('\n'.join(lines)+'\n')
dirs=sorted({str(q) for name,_,_ in paths for q in Path(name).parents}|{'/usr/lib64','/cwd','/dev','/dev/shm','/proc','/input/resources','/scratch','/run'})
neg=['/etc/ld.so.cache','/etc/ld.so.preload']
for base in ('/usr/lib/x86_64-linux-gnu','/usr/lib'):
    for sub in ('','glibc-hwcaps/x86-64-v2/','glibc-hwcaps/x86-64-v3/','glibc-hwcaps/x86-64-v4/'):
        name=base+'/'+sub+'libc.so.6'
        if name not in {p for p,_,_ in paths}:neg.append(name)
neg=sorted(set(neg));links={'/lib':'usr/lib','/lib64':'usr/lib64','/usr/lib64/ld-linux-x86-64.so.2':'../lib/x86_64-linux-gnu/ld-linux-x86-64.so.2'}
for name,values in [('directories',dirs),('negative',neg)]:(R/'inputs'/(name+'.inc')).write_text('\n'.join(json.dumps(x)+',' for x in values)+'\n')
(R/'inputs/links.inc').write_text('\n'.join('{'+json.dumps(k)+','+json.dumps(v)+'},' for k,v in links.items())+'\n')
(R/'inputs/policy_counts.h').write_text('#define COMPILED_PATHS 5\n#define FULL_REQUIRED_PATHS 5\n#define TARGET_EXECUTABLE "/probe/fixture"\n#define TARGET_INPUT "/input/fixed.txt"\n#define TARGET_ALIAS "/input/fixed-alias.txt"\n'+''.join('#define '+k+' '+str(len(v))+'\n' for k,v in [('DIRECTORY_COUNT',dirs),('NEGATIVE_COUNT',neg),('LINK_COUNT',links)]))
(R/'inputs/target_env.inc').write_text('"LC_ALL=C",\n"TMPDIR=/scratch",\n"HOME=/scratch",\n')
(R/'reports/policy.json').write_text(json.dumps(dict(paths=policy,full_required_paths=5,required_objects=4,directories=dirs,negative=neg,links=links,large_objects_included=False),indent=2)+'\n')
# Reused objects must match recorded v9 dependency/object hashes and local sources.
units=[probe]
for name in ('catalog','launch','metadata','control','owner_main'):units.append(compile_unit(name))
for label in ('broker','bound','loader','namespace'):
    unit=next(x for x in prior['translation_units'] if x['label']==label)
    need(sha(unit['object'])==unit['object_sha256'],'reused object changed')
    for p,h in unit['input_hashes'].items():need(sha(p)==h,'reused dependency changed')
    need((R/'inputs'/(label+'.c')).read_bytes()==(V9/'inputs'/(label+'.c')).read_bytes(),'reused source changed')
    units.append(dict(unit,status='REUSED_HASH_VERIFIED_V9'))
objects={x['label']:x['object'] for x in units}
run('owner-link',['cc','-pie','-Wl,-z,relro,-z,now',*[objects[n] for n in ('catalog','launch','metadata','control','owner_main','broker','bound','loader','namespace')],'-lcrypto','-o',str(W/'owner')])
anchor=next(p for p in prior['outputs'] if Path(p).name=='unit-anchor');need(sha(anchor)==prior['outputs'][anchor],'anchor changed')
for out in (W/'probe',W/'owner',Path(anchor)):
    text=subprocess.check_output(['readelf','-h','-d','-l','-Ws',str(out)],text=True)
    need(not re.search(r'NEEDED.*(?:libdart|libgz|libsdformat)',text),'forbidden runtime dependency')
    (W/(out.name+'.readelf.txt')).write_text(text)
need(re.findall(r'\(NEEDED\).*\[(.*?)\]',(W/'probe.readelf.txt').read_text())==['libc.so.6'],'probe must be libc only')
receipt=dict(status='COMPILED_LINKED_NOT_EXECUTED',steps=steps,translation_units=units,recompiled=6,reused=4,reused_anchor=True,
    inputs={p:h for x in units for p,h in x['input_hashes'].items()},outputs={str(p):sha(p) for p in (W/'probe',W/'owner',Path(anchor))},
    baseline_receipt_sha256=sha(V9/'reports/build_receipt.json'),actual_native_executions=0,actual_services_started=0,limits_changed=False)
(R/'reports/build_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print('Compiled6 TUs (probe+owner entry+4 small-policy TUs), reused4 v9 objects+anchor; no native execution')
