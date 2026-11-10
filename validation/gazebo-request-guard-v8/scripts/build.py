"""Changed C/C++ components only; compile/link/read ELF, never load outputs."""
from pathlib import Path
import hashlib,json,shlex,subprocess,socket,os,sys,re
R=Path(__file__).resolve().parents[1];B=R.parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
steps=[]
def run(label,argv):
    log=R/'work'/(label+'.log')
    with log.open('w') as f:
        p=subprocess.Popen(argv,stdout=f,stderr=subprocess.STDOUT)
        identity=dict(host=socket.gethostname(),pid=p.pid,start='UNKNOWN')
        try:identity['start']=Path('/proc',str(p.pid),'stat').read_text().rsplit(')',1)[1].split()[19]
        except OSError:pass
        rc=p.wait()
    if rc:raise RuntimeError(str(log))
    steps.append(dict(label=label,argv=argv,process=identity,returncode=rc))
flags=['-O2','-Wall','-Wextra','-Werror','-fstack-protector-strong','-fPIC']
for name in ('bound','loader','namespace','unit_anchor'):
    run(name,['cc','-std=c11',*flags,'-MD','-MF',str(R/'work'/f'{name}.d'),'-c',str(R/'inputs'/f'{name}.c'),'-o',str(R/'work'/f'{name}.o')])
run('anchor-link',['cc','-pie','-Wl,-z,relro,-z,now',str(R/'work/unit_anchor.o'),'-o',str(R/'work/unit-anchor')])
run('native',['c++','-std=c++17',*flags,'-Wno-misleading-indentation','-MD','-MF',str(R/'work/native_resource.d'),'-c',str(R/'inputs/native_resource.cc'),'-o',str(R/'work/native_resource.o')])
lib=R/'work/libaero-resource.so'
run('native-link',['c++','-shared','-Wl,-z,relro,-z,now,-soname,libaero-resource.so',str(R/'work/native_resource.o'),str(R/'work/bound.o'),'-lcrypto','-ldl','-pthread','-o',str(lib)])
# Full compile-time468 paths; retained-FD factory keeps existing64MiB/512MiB caps.
sys.path.insert(0,str(B/'validation/gazebo-request-guard-v7/scripts'));import resources as prior
c,m,receipt,seal=prior.A.v5.old.load_verified();records=prior.A.v5.old.classify(m,receipt)
allowlist=R/'work/joint-elf.sha256'
original_native=m['mounts'][m['roles']['native']]['sha256']
allowlist.write_text(m['allowlist_text'].replace(original_native+' '+m['roles']['native'],sha(lib)+' '+m['roles']['native']))
lines=[];policy=[]
for row in records:
    if not row['required']:continue
    o=dict(row['original']);source=m['mounts'][row['aliases'][0]]['source']
    if m['roles']['native'] in row['aliases']:
        st=lib.stat();o.update(device=st.st_dev,inode=st.st_ino,sha256=sha(lib));source=str(lib)
    if '/input/joint-elf.sha256' in row['aliases']:
        st=allowlist.stat();o.update(device=st.st_dev,inode=st.st_ino,sha256=sha(allowlist));source=str(allowlist)
    for path in sorted(row['aliases']):
        lines.append('{'+','.join([json.dumps(path),str(o['device'])+'ULL',str(o['inode'])+'ULL',json.dumps(o['sha256']),str(int(row['executable'])),json.dumps(source)])+'},')
        policy.append(dict(path=path,source=source,original=o,size=Path(source).stat().st_size,executable=row['executable']))
(R/'inputs/allowlist.inc').write_text('\n'.join(lines)+'\n')
counts=(B/'validation/gazebo-request-guard-v5/inputs/policy_counts.h').read_text().replace('COMPILED_PATHS 452','COMPILED_PATHS 468')
directories=sorted({str(parent) for row in policy for parent in Path(row['path']).parents if str(parent)!='.'}|{'/usr/lib64','/dev','/dev/shm','/proc','/input/resources','/cwd','/scratch','/run'})
negative={'/etc/ld.so.cache','/etc/ld.so.preload'}
search={'/usr/lib/x86_64-linux-gnu','/usr/lib'}
names=set()
for path,row in m['elfs'].items():
    if path not in {p['path'] for p in policy}:continue
    names.update(row['needed'])
    for field in row['runpath']:
        for directory in field.split(':'):
            expanded=directory.replace('${ORIGIN}',str(Path(path).parent)).replace('$ORIGIN',str(Path(path).parent))
            if not expanded.startswith('/') or '$' in expanded or '..' in Path(expanded).parts:raise ValueError('unsupported loader search token')
            search.add(expanded)
for directory in search:
    for name in names:
        negative.add(str(Path(directory)/name))
        for level in ('x86-64-v2','x86-64-v3','x86-64-v4'):
            negative.add(str(Path(directory)/'glibc-hwcaps'/level/name))
    for level in ('x86-64-v2','x86-64-v3','x86-64-v4'):negative.add(str(Path(directory)/'glibc-hwcaps'/level))
negative=sorted(negative-{row['path'] for row in policy}-set(directories))
links={'/lib':'usr/lib','/lib64':'usr/lib64','/usr/lib64/ld-linux-x86-64.so.2':'../lib/x86_64-linux-gnu/ld-linux-x86-64.so.2'}
for name,values in [('directories',directories),('negative',negative)]:
    (R/'inputs'/(name+'.inc')).write_text('\n'.join(json.dumps(v)+',' for v in values)+'\n')
(R/'inputs/links.inc').write_text('\n'.join('{'+json.dumps(k)+','+json.dumps(v)+'},' for k,v in links.items())+'\n')
counts+='#define DIRECTORY_COUNT '+str(len(directories))+'\n#define NEGATIVE_COUNT '+str(len(negative))+'\n#define LINK_COUNT '+str(len(links))+'\n'
(R/'inputs/policy_counts.h').write_text(counts)
for name in ('metadata','catalog','broker','control','launch','entry'):
    run(name,['cc','-std=c11',*flags,'-MD','-MF',str(R/'work'/f'{name}.d'),'-c',str(R/'inputs'/f'{name}.c'),'-o',str(R/'work'/f'{name}.o')])
elf=R/'work/candidate'
run('link',['cc','-pie','-Wl,-z,relro,-z,now',*[str(R/'work'/f'{n}.o') for n in ('catalog','broker','control','launch','entry','bound','loader','metadata','namespace')],'-lcrypto','-o',str(elf)])
inputs={}
for dep in (R/'work').glob('*.d'):
    for p in shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1]):inputs[p]=sha(p)
for out in (elf,lib,R/'work/unit-anchor'):
    metadata=subprocess.check_output(['readelf','-h','-d','-l','-Ws',str(out)],text=True)
    assert 'libdart' not in metadata and 'libgz' not in metadata
    (R/'work'/(out.name+'.elf.txt')).write_text(metadata)
(R/'reports/policy.json').write_text(json.dumps(dict(paths=policy,full_required_paths=468,native_replacement=dict(path=m['roles']['native'],source=str(lib),sha256=sha(lib),parent_sha256=m['mounts'][m['roles']['native']]['sha256']),directories=directories,negative=negative,links=links,allowlist_replacement=dict(path='/input/joint-elf.sha256',source=str(allowlist),sha256=sha(allowlist)),native_build_id=re.search(r'Build ID: ([a-f0-9]+)',subprocess.check_output(['readelf','-n',str(lib)],text=True))[1],deployed=False,parent_contract_sha256=seal),indent=2)+'\n')
(R/'reports/build_receipt.json').write_text(json.dumps(dict(status='COMPILED_LINKED_STATIC_ONLY',steps=steps,inputs=inputs,outputs={str(p):sha(p) for p in (elf,lib,R/'work/unit-anchor')},executed=False,limits_changed=False,entry_exit=78),indent=2)+'\n')
print('11 TUs compiled, supervisor and native consumer linked; outputs NOT EXECUTED')
