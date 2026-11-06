"""Owned harmless fixture. All cases are behind mandatory namespace/mount gates."""
import errno,json,os,resource,socket,subprocess,sys,time
from pathlib import Path
case=sys.argv[1];host=json.loads(sys.argv[2]); cfg=json.loads(sys.argv[3])
resource.setrlimit(resource.RLIMIT_NPROC,(512,512))
ns={k:os.readlink('/proc/self/ns/'+k) for k in ('user','mnt','pid','net')}
if any(ns[k]==host[k] for k in ns):sys.exit(90)
if resource.getrlimit(resource.RLIMIT_AS)!=(268435456,268435456):sys.exit(91)
if not os.statvfs('/').f_flag & os.ST_RDONLY:sys.exit(92)
if os.statvfs('/tmp').f_blocks*os.statvfs('/tmp').f_frsize>4194304:sys.exit(93)
print(json.dumps({'ready':True,'ns':ns,'pid':os.getpid(),'limits':{k:resource.getrlimit(getattr(resource,k)) for k in ('RLIMIT_CPU','RLIMIT_AS','RLIMIT_FSIZE','RLIMIT_NOFILE','RLIMIT_NPROC','RLIMIT_CORE')},'maps_clean':not any(s in Path('/proc/self/maps').read_text().lower() for s in ('libdart','libgz-','libgazebo'))}),flush=True)
print('CASE_ENTERED',flush=True)
if case=='normal':sys.exit(0)
if case=='tree':
 p=subprocess.Popen(['/usr/bin/python3','-I','-B','-c','import subprocess,time; subprocess.Popen(["/usr/bin/python3","-I","-B","-c","import time;time.sleep(30)"]);time.sleep(30)'])
 print(json.dumps({'child':p.pid}),flush=True);time.sleep(30)
if case in ('tmp_capacity','output_capacity'):
 directory='/tmp' if case=='tmp_capacity' else '/run';total=0;error=None
 try:
  for i in range(80):
   with open(directory+'/'+str(i),'wb') as f:f.write(b'x'*65536)
   total+=65536
 except OSError as e:error=e.errno
 v=os.statvfs(directory);print(json.dumps({'bytes_written':total,'errno':error,'capacity':v.f_blocks*v.f_frsize}),flush=True)
 sys.exit(0 if error==errno.ENOSPC and total<=4194304 and v.f_blocks*v.f_frsize==4194304 else 94)
if case=='sockets':
 result={};port=cfg['port6']
 with socket.socket(socket.AF_INET6,socket.SOCK_STREAM) as listener:
  listener.bind(('::1',0));listener.listen();client=socket.socket(socket.AF_INET6,socket.SOCK_STREAM);client.connect(listener.getsockname());conn,_=listener.accept();client.sendall(b'local');result['ipv6_local']=conn.recv(5).decode();conn.close();client.close()
 for label,kind,addr in [('ipv6_host',socket.SOCK_STREAM,('::1',port)),('ipv6_external_tcp',socket.SOCK_STREAM,('2001:db8::1',9)),('ipv6_external_udp',socket.SOCK_DGRAM,('2001:db8::1',9))]:
  with socket.socket(socket.AF_INET6,kind) as s:
   s.settimeout(.3)
   try:
    if kind==socket.SOCK_STREAM:s.connect(addr)
    else:s.sendto(b'fixture',addr)
    result[label]='UNEXPECTED_SUCCESS'
   except OSError as e:result[label]=e.errno
 result['host_path_visible']=Path(cfg['unix_path']).exists()
 with socket.socket(socket.AF_UNIX) as s:
  try:s.connect(cfg['unix_path']);result['unix_host']='UNEXPECTED_SUCCESS'
  except OSError as e:result['unix_host']=e.errno
 with socket.socket(socket.AF_UNIX) as s:
  try:s.connect('\0'+cfg['abstract']);result['abstract_host']='UNEXPECTED_SUCCESS'
  except OSError as e:result['abstract_host']=e.errno
 with socket.socket(socket.AF_UNIX) as listener:
  listener.bind('/tmp/internal.sock');listener.listen();client=socket.socket(socket.AF_UNIX);client.connect('/tmp/internal.sock');conn,_=listener.accept();client.sendall(b'local');result['unix_local']=conn.recv(5).decode();conn.close();client.close()
 print(json.dumps(result),flush=True)
 sys.exit(0 if result['ipv6_local']=='local' and result['unix_local']=='local' and not result['host_path_visible'] and result['unix_host']==errno.ENOENT and result['abstract_host'] in (errno.ECONNREFUSED,errno.ENOENT) and result['ipv6_external_tcp']==errno.ENETUNREACH and result['ipv6_external_udp']==errno.ENETUNREACH and isinstance(result['ipv6_host'],int) else 95)
