"""Compile only changed native launch TU; statically relink verified parent objects."""
from pathlib import Path
import hashlib,json,subprocess,shlex,os,socket
R=Path(__file__).resolve().parents[1];P=R.parent/'gazebo-request-guard-v5'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
parent=json.loads((P/'reports/build_receipt.json').read_text())
reused=[]
for name in ('catalog','broker','control','entry'):
    obj=P/'work'/f'{name}.o';step=next(s for s in parent['steps'] if s['argv'][-1]==str(obj))
    assert sha(obj)==step['object_sha256']
    assert all(sha(p)==digest for p,digest in step['inputs'].items())
    reused.append(dict(object=str(obj),sha256=sha(obj),all_parent_dependencies_verified=True))
cc=parent['compiler']['path'];assert sha(cc)==parent['compiler']['sha256']
flags=['-std=c11','-O2','-Wall','-Wextra','-Werror','-fstack-protector-strong','-fPIE']
obj=R/'work/launch.o';dep=R/'work/launch.d'
argv=[cc,*flags,'-I'+str(P/'inputs'),'-MD','-MF',str(dep),'-c',str(R/'inputs/launch.c'),'-o',str(obj)]
with (R/'work/compile.log').open('w') as out:
    p=subprocess.Popen(argv,stdout=out,stderr=subprocess.STDOUT)
    identity=dict(host=socket.gethostname(),pid=p.pid,start='UNKNOWN')
    try:identity['start']=Path(f'/proc/{p.pid}/stat').read_text().rsplit(')',1)[1].split()[19]
    except OSError:pass
    assert p.wait()==0,'compile failure: work/compile.log'
headers={p:sha(p) for p in shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1])}
elf=R/'work/candidate'
link=[cc,'-pie','-Wl,-z,relro,-z,now',str(obj),*[x['object'] for x in reused],'-lcrypto','-o',str(elf)]
subprocess.run(link,check=True,capture_output=True)
metadata=subprocess.check_output(['readelf','-h','-d','-l',str(elf)],text=True)
asm=subprocess.check_output(['objdump','-d',str(elf)],text=True)
assert 'libcrypto.so.3' in metadata and 'libc.so.6' in metadata and 'libdart' not in metadata and 'libgz' not in metadata
assert '<main>:' in asm and '<candidate_supervise>:' in asm
(R/'work/readelf.txt').write_text(metadata);(R/'work/disassembly.txt').write_text(asm)
(R/'reports/build_receipt.json').write_text(json.dumps(dict(status='COMPILE_LINK_STATIC_ONLY',compiler=parent['compiler'],compile_argv=argv,
    process=identity,inputs=headers,object_sha256=sha(obj),reused=reused,link_argv=link,elf_sha256=sha(elf),executed=False,entry_exit=78),indent=2)+'\n')
print('1 changed TU compiled; 4 parent objects verified and linked; ELF never executed')
