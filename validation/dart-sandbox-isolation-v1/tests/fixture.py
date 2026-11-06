"""Harmless fixture, runs only after namespace and mount checks."""
import errno,json,os,resource,signal,socket,subprocess,sys,time
from pathlib import Path
resource.setrlimit(resource.RLIMIT_NPROC,(512,512))
case=sys.argv[1]; host=json.loads(sys.argv[2]);port=int(sys.argv[3])
ns={k:os.readlink('/proc/self/ns/'+k) for k in ('user','mnt','net','pid')}
if not all(ns[k]!=host[k] for k in ns): sys.exit(90)
if not os.statvfs('/media').f_flag & os.ST_RDONLY: sys.exit(91)
if not os.statvfs('/').f_flag & os.ST_RDONLY: sys.exit(92)
if os.statvfs('/run').f_flag & os.ST_RDONLY: sys.exit(93)
print(json.dumps({'gate':'READY','namespaces':ns,'limits':{k:resource.getrlimit(getattr(resource,k)) for k in ('RLIMIT_CPU','RLIMIT_AS','RLIMIT_FSIZE','RLIMIT_NOFILE','RLIMIT_NPROC','RLIMIT_CORE')},'maps_clean':not any(x in Path('/proc/self/maps').read_text().lower() for x in ('libdart','libgazebo','libgz-'))}),flush=True)
Path('/run/started').write_text(case)
if case=='normal': sys.exit(0)
if case=='filesystem':
    result={}
    Path('/run/allowed').write_text('allowed')
    for name in ('/media/value','/opt/value'):
        try:
            with open(name,'w') as f:f.write('unexpected')
            result[name]='UNEXPECTED_WRITE'
        except OSError as e:result[name]=e.errno
    print(json.dumps(result),flush=True)
    sys.exit(0 if all(v==errno.EROFS for v in result.values()) else 94)
if case=='network':
    result={}; routes=Path('/proc/net/route').read_text();result['routes']=routes
    if any(line.split()[1]=='00000000' for line in routes.splitlines()[1:]):sys.exit(95)
    for label,kind,addr in [('host_tcp',socket.SOCK_STREAM,('127.0.0.1',port)),('host_udp',socket.SOCK_DGRAM,('127.0.0.1',port)),('external_tcp',socket.SOCK_STREAM,('192.0.2.1',9)),('external_udp',socket.SOCK_DGRAM,('192.0.2.1',9))]:
        with socket.socket(socket.AF_INET,kind) as s:
            s.settimeout(.3)
            try:
                if kind==socket.SOCK_STREAM:s.connect(addr)
                else:s.sendto(b'fixture',addr)
                result[label]='LOCAL_DATAGRAM_QUEUED' if label=='host_udp' else 'UNEXPECTED_SUCCESS'
            except OSError as e:result[label]={'errno':e.errno,'message':str(e)}
    try:socket.getaddrinfo('sandbox-fixture.invalid',9);result['dns']='UNEXPECTED_SUCCESS'
    except socket.gaierror as e:result['dns']={'errno':e.errno,'message':str(e)}
    result['loopback_policy']='private loopback enabled by bwrap; local UDP send success is not host delivery';result['loopback_flags']=Path('/sys/class/net/lo/flags').read_text().strip();print(json.dumps(result),flush=True)
    sys.exit(0 if all(isinstance(result[k],dict) for k in ('host_tcp','external_tcp','external_udp','dns')) else 96)
if case=='exit':sys.exit(7)
if case=='signal':os.kill(os.getpid(),signal.SIGTERM)
if case=='timeout':time.sleep(30)
if case=='cpu':
    while True:pass
if case=='memory':
    try:bytearray(512*1024*1024)
    except MemoryError:sys.exit(23)
if case=='file':
    try:
        with open('/run/large','wb') as f:f.write(b'x'*131072)
    except OSError:sys.exit(24)
if case=='descendants':
    p=subprocess.Popen(['/usr/bin/python3','-I','-B','-c','import time; time.sleep(30)'])
    print(json.dumps({'child_namespace_pid':p.pid}),flush=True);time.sleep(30)
