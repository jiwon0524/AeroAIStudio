"""Compile/link candidate components only. Never executes output ELF."""
from pathlib import Path
import hashlib
import json
import os
import shlex
import shutil
import socket
import subprocess

R = Path(__file__).resolve().parents[1]
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
compiler = Path(shutil.which('cc')).resolve()
common = ['-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-fstack-protector-strong', '-fPIE']
steps = []
for name in ('broker', 'tree', 'entry'):
    source = R/'inputs'/f'{name}.c'
    obj = R/'work'/f'{name}.o'
    dep = R/'work'/f'{name}.d'
    argv = [str(compiler), *common, '-MD', '-MF', str(dep), '-c', str(source), '-o', str(obj)]
    with (R/'work'/f'{name}.log').open('w') as log:
        p = subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT)
        identity = dict(host=socket.gethostname(), pid=p.pid, start='UNKNOWN')
        try:
            identity['start'] = Path(f'/proc/{p.pid}/stat').read_text().rsplit(')', 1)[1].split()[19]
        except OSError:
            pass
        if p.wait():
            raise RuntimeError(f'compile failed: work/{name}.log')
    headers = {}
    for value in shlex.split(dep.read_text().replace('\\\n', ' ').split(':', 1)[1]):
        headers[value] = sha(value)
    steps.append(dict(argv=argv, process=identity, inputs=headers, object_sha256=sha(obj)))
out = R/'work/candidate'
argv = [str(compiler), '-pie', '-Wl,-z,relro,-z,now',
        *[str(R/'work'/f'{n}.o') for n in ('broker', 'tree', 'entry')], '-o', str(out)]
subprocess.run(argv, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
elf = subprocess.check_output(['readelf', '-h', '-d', '-l', '-n', str(out)], text=True)
asm = subprocess.check_output(['objdump', '-d', str(out)], text=True)
assert elf.count('Shared library: [libc.so.6]') == 1
assert 'libdart' not in elf and 'libgz' not in elf
for symbol in ('candidate_install_filter', 'candidate_broker_request', 'candidate_tree_monitor',
               'process_vm_readv@plt', 'ioctl@plt', 'ptrace@plt', 'fdatasync@plt'):
    assert symbol in asm, symbol
(R/'work/readelf.txt').write_text(elf)
(R/'work/disassembly.txt').write_text(asm)
report = dict(status='COMPILED_LINKED_STATIC_ONLY', compiler=dict(path=str(compiler), sha256=sha(compiler)),
              steps=steps, link_argv=argv, elf_sha256=sha(out), elf_metadata=elf,
              executed=False, shared_library_loading=False, entrypoint_exit=78,
              reused_source='validation/gazebo-request-guard-v1/inputs/guard.c', deployed=False)
(R/'reports/build_receipt.json').write_text(json.dumps(report, indent=2)+'\n')
print('3 candidate TUs compiled and linked; ELF NOT EXECUTED')
