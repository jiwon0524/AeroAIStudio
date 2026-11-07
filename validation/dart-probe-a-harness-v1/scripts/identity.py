"""Pinned file descriptor identity. Pure ELF note parsing, no loader/ldd."""
import hashlib,os,stat,struct

def stamp(s):return (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
def build_id_fd(fd):
    h=os.pread(fd,64,0)
    if len(h)!=64 or h[:6]!=b'\x7fELF\x02\x01':raise ValueError('ELF64LE required')
    if struct.unpack_from('<H',h,18)[0]!=62:raise ValueError('x86-64 required')
    off=struct.unpack_from('<Q',h,32)[0];size,count=struct.unpack_from('<HH',h,54)
    if size!=56 or count>1024:raise ValueError('program header bounds')
    ids=[]
    for i in range(count):
        ph=os.pread(fd,56,off+i*size)
        if len(ph)!=56:raise ValueError('truncated program headers')
        kind,_,pos,_,_,length,_,_=struct.unpack('<IIQQQQQQ',ph)
        if kind!=4:continue
        if length>65536:raise ValueError('note buffer bound')
        data=os.pread(fd,length,pos)
        if len(data)!=length:raise ValueError('truncated note segment')
        at=0
        while at+12<=len(data):
            ns,ds,nt=struct.unpack_from('<III',data,at);at+=12
            if ns>4096 or ds>4096 or at+((ns+3)&~3)+((ds+3)&~3)>len(data):raise ValueError('note bounds')
            name=data[at:at+ns];at+=(ns+3)&~3;desc=data[at:at+ds];at+=(ds+3)&~3
            if name==b'GNU\0' and nt==3:ids.append(desc.hex())
    if len(set(ids))!=1 or not ids[0]:raise ValueError('missing/ambiguous Build-ID')
    return ids[0]

def describe_fd(fd):
    before=os.fstat(fd)
    if not stat.S_ISREG(before.st_mode):raise ValueError('not regular file')
    h=hashlib.sha256();offset=0
    while True:
        chunk=os.pread(fd,1048576,offset)
        if not chunk:break
        h.update(chunk);offset+=len(chunk)
    bid=build_id_fd(fd);after=os.fstat(fd)
    if stamp(before)!=stamp(after):raise ValueError('file mutated during read')
    return {'sha256':h.hexdigest(),'build_id':bid,'device':before.st_dev,'inode':before.st_ino,'size':before.st_size,'mtime_ns':before.st_mtime_ns,'ctime_ns':before.st_ctime_ns}

def check_fd(fd,expected,strict_stat=True):
    actual=describe_fd(fd)
    keys=('sha256','build_id','device','inode') if strict_stat else ('sha256','build_id')
    for key in keys:
        if actual[key]!=expected[key]:raise ValueError(key+' mismatch')
    return actual

def open_checked(entry):
    path=entry['real_path']
    if not os.path.isabs(path) or os.path.realpath(path)!=path:raise ValueError('canonical absolute path required')
    fd=os.open(path,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
    try:check_fd(fd,entry)
    except BaseException:os.close(fd);raise
    return fd
