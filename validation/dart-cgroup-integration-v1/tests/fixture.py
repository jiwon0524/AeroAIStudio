"""Bounded three-process fixture; all descendants repeat the entry gate."""
import errno,json,os,resource,socket,subprocess,sys,time
from pathlib import Path

def gate(cfg):
    ns={k:os.readlink('/proc/self/ns/'+k) for k in ('user','mnt','pid','net')}
    if cfg['sandbox']:
        if resource.getrlimit(resource.RLIMIT_AS)!=(268435456,268435456):raise RuntimeError('address space gate')
        if any(ns[k]==cfg['host_ns'][k] for k in ns):raise RuntimeError('namespace gate')
        for p in ('/','/dev','/project','/fixture'):
            if not os.statvfs(p).f_flag & os.ST_RDONLY:raise RuntimeError('readonly gate '+p)
        for p,cap in (('/tmp',4194304),('/run',4194304),('/dev/shm',1048576)):
            s=os.statvfs(p)
            if s.f_blocks*s.f_frsize!=cap:raise RuntimeError('tmpfs capacity gate '+p)
        for key,value in (('memory.max','67108864'),('memory.swap.max','0'),('pids.max','8'),('cpu.max','25000 100000')):
            if Path('/limits',key).read_text().strip()!=value:raise RuntimeError('limit gate '+key)
        if Path(cfg['host_canary']).exists() or Path(cfg['unix_path']).exists():raise RuntimeError('host exposure gate')
    else:
        rel=Path('/proc/self/cgroup').read_text().strip()
        if rel!='0::'+cfg['cgroup']:raise RuntimeError('host cgroup gate')
        limits=Path('/sys/fs/cgroup')/cfg['cgroup'].lstrip('/')
        for key,value in (('memory.max','67108864'),('memory.swap.max','0'),('pids.max','8'),('cpu.max','25000 100000')):
            if (limits/key).read_text().strip()!=value:raise RuntimeError('host limit gate '+key)
    if any(x in Path('/proc/self/maps').read_text().lower() for x in ('libdart','libgz-','libgazebo')):raise RuntimeError('forbidden library gate')
    return ns

def isolation(cfg):
    out={}
    for p in ('/project/'+cfg['project_canary_name'],'/fixture/fixture.py'):
        try:
            fd=os.open(p,os.O_WRONLY);os.close(fd);out[p]='UNEXPECTED_WRITABLE'
        except OSError as e:out[p]=e.errno
    for p in ('/tmp/probe','/run/probe'):
        Path(p).write_text('owned');Path(p).unlink()
    out['private_writes']=True
    for label,family,addr in (('ipv4_external',socket.AF_INET,('192.0.2.1',9)),('ipv6_external',socket.AF_INET6,('2001:db8::1',9)),('ipv6_host',socket.AF_INET6,('::1',cfg['port6'])),('unix_host',socket.AF_UNIX,cfg['unix_path']),('abstract_host',socket.AF_UNIX,'\0'+cfg['abstract'])):
        with socket.socket(family,socket.SOCK_STREAM) as s:
            s.settimeout(.2)
            try:s.connect(addr);out[label]='UNEXPECTED_CONNECTED'
            except OSError as e:out[label]=e.errno
    if out['/project/'+cfg['project_canary_name']]!=errno.EROFS or out['/fixture/fixture.py']!=errno.EROFS:raise RuntimeError('write isolation')
    if out['ipv4_external']!=errno.ENETUNREACH or out['ipv6_external']!=errno.ENETUNREACH:raise RuntimeError('external network isolation')
    if out['ipv6_host'] not in (errno.ECONNREFUSED,errno.ENETUNREACH) or out['unix_host']!=errno.ENOENT or out['abstract_host'] not in (errno.ECONNREFUSED,errno.ENOENT):raise RuntimeError('host socket isolation')
    return out

def main():
    role=int(sys.argv[1]);cfg=json.loads(sys.argv[2]);ns=gate(cfg)
    row={'role':('parent','child','grandchild')[role],'pid':os.getpid(),'ppid':os.getppid(),'cgroup':Path('/proc/self/cgroup').read_text().strip(),'ns':ns,'rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'gate':'PASS'}
    if role==0 and cfg['sandbox']:row['isolation']=isolation(cfg)
    print(json.dumps(row),flush=True)
    if role<2:
        child=subprocess.Popen(['/usr/bin/python3','-I','-B',__file__,str(role+1),json.dumps(cfg)])
        try:code=child.wait(timeout=6)
        except subprocess.TimeoutExpired:child.terminate();child.wait(timeout=2);raise
        if code:raise RuntimeError('descendant failed '+str(code))
    else:time.sleep(2)
if __name__=='__main__':main()
