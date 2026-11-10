"""Read-only sealed input preparation. Never creates a service or target.

Only original contract inodes with kernel enforced immutable data qualify.
A RO descriptor/mount, hash snapshot, chmod, or copied memfd is insufficient.
"""
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import struct

R = Path(__file__).resolve().parents[1]
OLD = R.parent / 'gazebo-joint-execution-contract-v1'
FS_IOC_GETFLAGS = 0x80086601  # Linux x86-64 unsigned long ioctl ABI
FS_VERITY_FL = 0x00100000

def load_contract():
    # Authenticate validator before import, just as sealed launcher bootstrap.
    m = json.loads((OLD / 'reports/manifest.json').read_text())
    raw = (json.dumps(m, sort_keys=True, separators=(',', ':')) + '\n').encode()
    seal = (OLD / 'inputs/manifest.sha256').read_text().strip()
    if hashlib.sha256(raw).hexdigest() != seal:
        raise ValueError('manifest seal mismatch')
    path = OLD / 'scripts/contract.py'
    if hashlib.sha256(path.read_bytes()).hexdigest() != m['code'][str(path)]['sha256']:
        raise ValueError('untrusted contract validator')
    spec = importlib.util.spec_from_file_location('guard_v2_contract', path)
    c = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(c)
    c.validate(m)
    return c, m, seal

def immutable(fd):
    flags = bytearray(8)
    fcntl.ioctl(fd, FS_IOC_GETFLAGS, flags, True)
    return bool(struct.unpack('L', flags)[0] & FS_VERITY_FL)

def pin(row, check_fd, opener=os.open, closer=os.close, verity=immutable):
    """Return owned FD only after SAME-FD identity/hash/immutability checks.
    Caller must close it. No target name is reopened following validation.
    """
    fd = opener(row['source'], os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        mode = fcntl.fcntl(fd, fcntl.F_GETFL)
        if (mode & os.O_ACCMODE) != os.O_RDONLY or mode & os.O_PATH:
            raise ValueError('non-readable/unsafe input FD')
        if not stat.S_ISREG(os.fstat(fd).st_mode) or not verity(fd):
            raise ValueError('original inode lacks proven immutable data')
        # Verity must be established BEFORE hashing, then checked again. No
        # enable-verity operation is performed; system changes are forbidden.
        check_fd(fd, row)
        if not verity(fd):
            raise ValueError('immutable proof changed')
        return fd
    except BaseException:
        closer(fd)
        raise

def inspect():
    c, m, seal = load_contract()
    sources = {}
    for row in m['mounts'].values():
        if row['source'] in sources:
            continue
        try:
            fd = pin(row, c.check_fd)
            os.close(fd)
            result = {'status': 'PINNABLE_IMMUTABLE_ORIGINAL'}
        except (OSError, ValueError) as e:
            result = {'status': 'DENIED', 'reason': str(e)}
        sources[row['source']] = result
    rows = []
    for dest, row in sorted(m['mounts'].items()):
        rows.append(dict(path=dest, source=row['source'], sha256=row['sha256'],
                         device=row['device'], inode=row['inode'], access='O_RDONLY',
                         elf=dest in m['elfs'], **sources[row['source']]))
    return dict(contract_sha256=seal, inputs=rows, unique_sources=len(sources),
                pinnable=sum(r['status'] != 'DENIED' for r in rows),
                denied=sum(r['status'] == 'DENIED' for r in rows),
                subject_execution=False, deployed=False)

if __name__ == '__main__':
    (R / 'reports/input_mapping.json').write_text(json.dumps(inspect(), indent=2) + '\n')
