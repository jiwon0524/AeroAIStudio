"""Prepare immutable input objects only: no exec, dlopen, mmap or target.

Copies are run-scoped FDs, never durable pathname permissions. Receipts do not
authorize reopening an old FD number or recreating an object without hashing.
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
path = R.parent/'gazebo-request-guard-v2/scripts/catalog.py'
spec = importlib.util.spec_from_file_location('v2_catalog', path)
catalog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalog)
BASE_SEALS = fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL
SEAL_EXEC = 0x20
REQUIRED_SEALS = BASE_SEALS | SEAL_EXEC
MFD_EXEC = 0x10
MFD_NOEXEC_SEAL = 0x08
PREP_OBJECT_LIMIT = 64*1024*1024

def need(ok, why):
    if not ok:
        raise ValueError(why)

def digest_fd(fd):
    h = hashlib.sha256()
    offset = 0
    while True:
        b = os.pread(fd, 1048576, offset)
        if not b:
            return h.hexdigest()
        h.update(b)
        offset += len(b)

def identity(fd):
    st = os.fstat(fd)
    return dict(device=st.st_dev, inode=st.st_ino, size=st.st_size)

def elf_interpreter(fd):
    """Read bounded ELF metadata from the sealed FD; never load or map it."""
    h = os.pread(fd,64,0)
    need(len(h)==64 and h[:6]==b'\x7fELF\x02\x01', 'unsupported ELF class/encoding')
    need(struct.unpack_from('<H',h,18)[0]==62, 'unsupported ELF machine')
    offset=struct.unpack_from('<Q',h,32)[0]
    width,count=struct.unpack_from('<HH',h,54)
    size=os.fstat(fd).st_size
    need(width==56 and count<=256 and offset+width*count<=size, 'invalid ELF program headers')
    result=None
    for i in range(count):
        p=os.pread(fd,width,offset+i*width)
        need(len(p)==width, 'truncated ELF program header')
        if struct.unpack_from('<I',p)[0]!=3:continue  # PT_INTERP
        start,length=struct.unpack_from('<Q',p,8)[0],struct.unpack_from('<Q',p,32)[0]
        need(result is None and 1<length<=4096 and start+length<=size, 'invalid ELF interpreter')
        raw=os.pread(fd,length,start)
        need(raw.endswith(b'\0') and b'\0' not in raw[:-1], 'invalid interpreter string')
        result=raw[:-1].decode('ascii')
        need(result.startswith('/'), 'relative ELF interpreter')
    return result

def validate_object(fd, receipt):
    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    need((flags & os.O_ACCMODE) == os.O_RDONLY and not flags & os.O_PATH, 'copy FD mode')
    st = os.fstat(fd)
    need(stat.S_ISREG(st.st_mode), 'copy not regular')
    need(identity(fd) == receipt['object'], 'copy object substitution')
    seals = fcntl.fcntl(fd, fcntl.F_GET_SEALS)
    need(seals & REQUIRED_SEALS == REQUIRED_SEALS, 'missing immutable/mode seals')
    need(bool(st.st_mode & 0o111) == receipt['executable_intent'], 'copy exec mode')
    need(digest_fd(fd) == receipt['sha256'], 'sealed bytes hash mismatch')
    return True

def copy_one(row, check_fd, executable, limit=PREP_OBJECT_LIMIT):
    """Owns returned readonly sealed FD; caller closes it. Verify after seal.
    Unsupported flags/seals/proc FD reopen are blockers, never silent fallback.
    """
    source = os.open(row['source'], os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
    write_fd = read_fd = None
    try:
        size = os.fstat(source).st_size
        need(0 <= size <= limit, 'preparation per-object memory budget')
        check_fd(source, row)
        flags = os.MFD_ALLOW_SEALING | os.MFD_CLOEXEC | (MFD_EXEC if executable else MFD_NOEXEC_SEAL)
        write_fd = os.memfd_create('aero-input-'+row['sha256'][:16], flags)
        # Permission changes affect this new anonymous object only.
        os.fchmod(write_fd, 0o500 if executable else 0o400)
        offset = 0
        while offset < size:
            b = os.pread(source, min(1048576, size-offset), offset)
            need(bool(b), 'source shrank during copy')
            pos = 0
            while pos < len(b):
                n = os.pwrite(write_fd, b[pos:], offset+pos)
                need(n > 0, 'copy short write')
                pos += n
            offset += len(b)
        need(os.pread(source, 1, size) == b'', 'source grew during copy')
        check_fd(source, row)
        fcntl.fcntl(write_fd, fcntl.F_ADD_SEALS, REQUIRED_SEALS)
        read_fd = os.open('/proc/self/fd/'+str(write_fd), os.O_RDONLY|os.O_CLOEXEC)
        need(identity(read_fd) == identity(write_fd), 'copy reopen substituted')
        os.close(write_fd); write_fd = None
        receipt = dict(object=identity(read_fd), sha256=row['sha256'],
                       executable_intent=executable,
                       original={k:row[k] for k in ('device','inode','sha256')},
                       seals=fcntl.fcntl(read_fd,fcntl.F_GET_SEALS),
                       fd_link=os.readlink('/proc/self/fd/'+str(read_fd)),
                       fd_lifetime='CURRENT_PREPARER_ONLY', executed=False, mapped=False)
        # Hash the final immutable bytes, not source/copy buffer before sealing.
        validate_object(read_fd, receipt)
        if executable:
            receipt['elf_interpreter'] = elf_interpreter(read_fd)
        check_fd(source, row)
        result = read_fd; read_fd = None
        return result, receipt
    finally:
        for fd in (source, write_fd, read_fd):
            if fd is not None:
                os.close(fd)

def groups(manifest):
    """Aliases for one original inode share ONE object, including mixed paths.
    Distinct original identities never merge merely because bytes match.
    """
    grouped = {}
    for dest, row in manifest['mounts'].items():
        need(dest.startswith('/') and '..' not in Path(dest).parts, 'unsafe alias')
        key = (row['device'], row['inode'])
        g = grouped.setdefault(key, dict(row=row, aliases=[], executable=False))
        need(row['sha256'] == g['row']['sha256'], 'same inode conflicting hash')
        g['aliases'].append(dest)
        g['executable'] |= dest in manifest['elfs']
    return sorted(grouped.values(), key=lambda g:sorted(g['aliases'])[0])

def check_aliases(group, receipt, table):
    need(set(table) == set(group['aliases']), 'missing/unexpected alias')
    for value in table.values():
        need(value == receipt['object'], 'alias uses different object')
    return True

def prepare():
    c, m, seal = catalog.load_contract()
    records = []
    for g in groups(m):
        # All alias sources must still match the original contract, not only
        # the first source. FD retained only while validating this group.
        item = dict(aliases=sorted(g['aliases']), original_source=g['row']['source'],
                    original={k:g['row'][k] for k in ('device','inode','sha256')},
                    executable_intent=g['executable'], allowed_for_target=False)
        try:
            for dest in g['aliases']:
                c.checked_file(m['mounts'][dest])
            fd, receipt = copy_one(g['row'], c.check_fd, g['executable'])
            try:
                table = {alias:identity(fd) for alias in g['aliases']}
                check_aliases(g, receipt, table)
                item.update(status='SEALED_BYTES_VERIFIED', receipt=receipt,
                            alias_same_object=True)
            finally:
                os.close(fd)
            item['object_retained'] = False
            item['delivery_blockers'] = ['original inode expectations differ',
                'canonical pathname/mapping delivery not verified',
                'live launch/audit integration incomplete']
        except (OSError, ValueError) as e:
            item.update(status='BLOCKED_PREPARATION', reason=str(e), object_retained=False)
        records.append(item)
    return dict(schema=1, parent_contract_sha256=seal, execution_contract=False, deployed=False,
                native_execution=False, executable_mapping_tested=False,
                preparation_object_limit=PREP_OBJECT_LIMIT,
                aliases_total=sum(len(g['aliases']) for g in records),
                objects_total=len(records), sealed_objects=sum(g['status']=='SEALED_BYTES_VERIFIED' for g in records),
                sealed_aliases=sum(len(g['aliases']) for g in records if g['status']=='SEALED_BYTES_VERIFIED'),
                allowed_aliases=0, objects=records)

if __name__ == '__main__':
    result = prepare()
    (R/'reports/copy_contract.json').write_text(json.dumps(result,indent=2)+'\n')
    print('sealed objects',result['sealed_objects'],'/',result['objects_total'],
          '; allowed target aliases 0; no execution/mmap')
