"""Compile/link candidate bridge only; never execute it or an isolation fixture."""
from pathlib import Path
import hashlib,json,shlex,subprocess,difflib
R=Path(__file__).resolve().parents[1];B=R.parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
prior=B/'validation/gazebo-joint-isolation-v1'
receipt=json.loads((prior/'reports/bridge_compile.json').read_text())
compiler=Path(receipt['compiler'])
assert sha(compiler)==receipt['compiler_sha256']
src=R/'inputs/fd_bridge.c';out=R/'work/fd_bridge';dep=R/'work/fd_bridge.d'
argv=[str(compiler),'-std=c17','-O2','-fPIE','-pie','-Wall','-Wextra','-Werror','-Wl,-z,relro,-z,now','-MD','-MF',str(dep),str(src),'-o',str(out)]
with (R/'work/compile.log').open('w') as log:
    subprocess.run(argv,stdout=log,stderr=subprocess.STDOUT,check=True)
headers={}
for name in shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1]):
    p=Path(name)
    if p==src:continue
    headers[str(p)]=sha(p)
    if str(p) in receipt['headers']:assert sha(p)==receipt['headers'][str(p)]
elf=subprocess.check_output(['readelf','-h','-d','-l','-n',str(out)],text=True)
asm=subprocess.check_output(['objdump','-d',str(out)],text=True)
for call in ('fcntl@plt','fstat@plt','close_range@plt','setrlimit@plt','execv@plt'):
    assert call in asm,call
assert 'libc.so.6' in elf
st=out.stat()
old=(prior/'inputs/fd_bridge.c').read_text()
patch=''.join(difflib.unified_diff(old.splitlines(True),src.read_text().splitlines(True),fromfile='a/fd_bridge.c',tofile='b/fd_bridge.c',n=0))
(R/'reports/fd_bridge.patch').write_text(patch)
row=dict(status='COMPILED_LINKED_STATIC_ONLY_NOT_DEPLOYED',source_sha256=sha(src),
    compiler_sha256=sha(compiler),argv=argv,headers=headers,
    elf=dict(source=str(out),sha256=sha(out),device=st.st_dev,inode=st.st_ino,metadata=elf),
    subject_execution=False,need_runtime=['bridge refusal before exec for invalid stdio','exact handoff FD set/types/modes/identities','absence of ambient sockets','namespace/readback through exit'],
    unchanged_limits=dict(CPU=10,AS=2147483648,FSIZE=1048576,NOFILE=256,CORE=0))
(R/'work/bridge.asm').write_text(asm)
(R/'reports/build_receipt.json').write_text(json.dumps(row,indent=2)+'\n')
print('bridge compiled/linked/static inspected; NOT EXECUTED / NOT DEPLOYED')
