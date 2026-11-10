"""Collector mapping proof for sealed anonymous inodes behind canonical binds.
Maps pathname text (including deleted memfd labels) is never permission. Check
actual map_files FD, canonical proc-root FD and retained catalog receipt instead.
"""
from pathlib import Path
import os,copy,stat,fcntl

def need(ok,why):
    if not ok:raise ValueError(why)
def parse(text):
    rows=[]
    for line in text.splitlines():
        f=line.split(None,5);need(len(f)>=5,'maps row')
        a,b=map(lambda s:int(s,16),f[0].split('-'));major,minor=map(lambda s:int(s,16),f[3].split(':'))
        rows.append(dict(range=f[0],lo=a,hi=b,permissions=f[1],offset=int(f[2],16),device=os.makedev(major,minor),inode=int(f[4])))
    return rows
class Proc:
    def __init__(self,validate,pins=None):self.validate,self.pins=validate,pins
    def same(self,fd,receipt):
        st=os.fstat(fd);mode=fcntl.fcntl(fd,fcntl.F_GETFL);seals=fcntl.fcntl(fd,fcntl.F_GET_SEALS)
        need(stat.S_ISREG(st.st_mode) and (mode&os.O_ACCMODE)==os.O_RDONLY and not mode&os.O_PATH and
            seals&0x2f==0x2f and (st.st_dev,st.st_ino,st.st_size)==tuple(receipt['object'][k] for k in ('device','inode','size')) and
            bool(st.st_mode&0o111)==receipt['executable_intent'],'sealed mapping FD substitution')
    def start(self,pid):return Path('/proc',str(pid),'stat').read_text().rsplit(')',1)[1].split()[19]
    def maps(self,pid):return Path('/proc',str(pid),'maps').read_text()
    def check(self,path,receipt):
        fd=os.open(path,os.O_RDONLY|os.O_CLOEXEC) # Kernel proc-root/map_files links; PID/start checked both sides.
        try:
            if self.pins is None:self.validate(fd,receipt)
            else:
                # Bytes were SHA256-verified after immutable seals before fork.
                # Revalidate retained and observed descriptions of that SAME
                # still-open object, avoiding rehash per segment/alias at ACK.
                pin=next(p for p in self.pins.values() if p['receipt']==receipt)
                self.same(pin['fd'],receipt);self.same(fd,receipt)
        finally:os.close(fd)

def verify(pid,start,plan,pins,ops):
    need(ops.start(pid)==start,'mapping PID/start changed')
    text=ops.maps(pid);maps=parse(text)
    by_object={(p['receipt']['object']['device'],p['receipt']['object']['inode']):p['receipt'] for p in pins.values()}
    observed=set();records=[]
    for row in maps:
        if row['inode']==0:continue
        key=row['device'],row['inode']
        need(key in by_object,'unknown file mapping')
        receipt=by_object[key]
        need(not ('w' in row['permissions'] and 'x' in row['permissions']),'W+X mapping')
        need('x' not in row['permissions'] or receipt['executable_intent'],'NX object executed')
        ops.check(f'/proc/{pid}/map_files/'+row['range'],receipt)
        canonical=[p for p,v in plan['mounts'].items() if (v['device'],v['inode'])==key]
        need(canonical,'mapping lacks canonical binding')
        for path in canonical:ops.check(f'/proc/{pid}/root'+path,receipt)
        observed.add(key)
        records.append(dict(row,path=canonical[0]))
    for path in plan['required_canonical_mappings']:
        obj=plan['mounts'][path];need((obj['device'],obj['inode']) in observed,'required mapping absent '+path)
    need(ops.start(pid)==start and ops.maps(pid)==text,'mapping changed during collection')
    return dict(status='PASS_FILE_IDENTITY',pid=pid,start=start,records=records)
