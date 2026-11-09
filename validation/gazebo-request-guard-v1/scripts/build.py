"""Compile/link one supervisor candidate; inspect ELF without loading/executing it."""
from pathlib import Path
import hashlib,json,shlex,shutil,subprocess
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
compiler=Path(shutil.which('cc')).resolve()
src=R/'inputs/guard.c';out=R/'work/guard';dep=R/'work/guard.d'
argv=[str(compiler),'-std=c11','-O2','-Wall','-Wextra','-Werror','-fstack-protector-strong','-fPIE','-pie','-Wl,-z,relro,-z,now','-MD','-MF',str(dep),str(src),'-o',str(out)]
with (R/'work/compile.log').open('w') as log:
    p=subprocess.Popen(argv,stdout=log,stderr=subprocess.STDOUT)
    identity={'host':__import__('socket').gethostname(),'pid':p.pid,'start':'UNKNOWN'}
    try:identity['start']=Path('/proc/'+str(p.pid)+'/stat').read_text().rsplit(')',1)[1].split()[19]
    except OSError:pass
    rc=p.wait()
    if rc:raise RuntimeError('compile failed; preserved work/compile.log')
headers={}
for name in shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1]):
    path=Path(name)
    if path!=src:headers[str(path)]=sha(path)
elf=subprocess.check_output(['readelf','-h','-d','-l','-n',str(out)],text=True)
asm=subprocess.check_output(['objdump','-d',str(out)],text=True)
for term in ('ptrace@plt','waitpid@plt','fdatasync@plt','write@plt','guard_monitor','guard_allowed'):
    assert term in asm,term
assert elf.count('Shared library: [libc.so.6]')==1
assert 'libdart' not in elf and 'libgz' not in elf
(R/'work/readelf.txt').write_text(elf);(R/'work/disassembly.txt').write_text(asm)
report=dict(status='COMPILED_LINKED_STATIC_ONLY',argv=argv,compiler=dict(path=str(compiler),sha256=sha(compiler)),
            compiler_process=identity,source=dict(path=str(src),sha256=sha(src)),headers=headers,
            elf=dict(path=str(out),sha256=sha(out),metadata=elf),subject_execution=False,shared_library_loading=False,
            integration='NOT_WIRED_NOT_DEPLOYED',entrypoint_exit=78)
(R/'reports/build_receipt.json').write_text(json.dumps(report,indent=2)+'\n')
print('one supervisor compiled/linked; ELF inspected; NOT EXECUTED')
