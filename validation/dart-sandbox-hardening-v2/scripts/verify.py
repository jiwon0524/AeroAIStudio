"""Host orchestrator, subreaps only its own test descendants."""
import ctypes,json,os,signal,socket,subprocess,tempfile,time
from pathlib import Path
B=Path(__file__).resolve().parents[1];R=B/'reports';W=B/'work'
def ident(pid):
 try:
  s=Path(f'/proc/{pid}/stat').read_text().split(') ',1)[1].split();return {'pid':pid,'state':s[0],'ppid':int(s[1]),'start':s[19],'rss_bytes':int(s[21])*os.sysconf('SC_PAGE_SIZE'),'cpu_ticks':int(s[11])+int(s[12])}
 except (OSError,ValueError,IndexError):return None
def tree(pid):
 rows=[v for p in Path('/proc').iterdir() if p.name.isdigit() and (v:=ident(int(p.name)))];ids={pid}
 for _ in range(8):ids|={v['pid'] for v in rows if v['ppid'] in ids}
 return [v for v in rows if v['pid'] in ids]
def reap():
 while True:
  try:
   if os.waitpid(-1,os.WNOHANG)[0]==0:break
  except ChildProcessError:break

def run(mode,cfg):
 start=time.monotonic();observed=[]
 with tempfile.TemporaryDirectory(dir=W,prefix='case-') as d:
  folder=Path(d)
  with open(folder/'stdout','wb') as out,open(folder/'stderr','wb') as err:
   p=subprocess.Popen(['/usr/bin/python3','-I','-B',str(B/'scripts/supervisor.py'),mode,d,json.dumps(cfg)],stdout=out,stderr=err,env={'PATH':'/usr/bin:/bin'},start_new_session=True)
   if mode in ('abnormal','sigkill'):
    for _ in range(100):
     if 'CASE_ENTERED' in (folder/'stdout').read_text() and len(tree(p.pid))>=6:break
     time.sleep(.02)
    observed=tree(p.pid);os.kill(p.pid,signal.SIGKILL if mode=='sigkill' else signal.SIGUSR1)
   try:rc=p.wait(timeout=9)
   except subprocess.TimeoutExpired:
    observed=tree(p.pid);os.kill(p.pid,signal.SIGKILL);rc=p.wait(timeout=2)
   for _ in range(50):
    reap();remaining=[v for v in observed if (now:=ident(v['pid'])) and now['start']==v['start']]
    if not remaining:break
    time.sleep(.02)
  stdout=(folder/'stdout').read_text();stderr=(folder/'stderr').read_text();entered='CASE_ENTERED' in stdout
  if mode in ('namespace_fail','mount_fail','network_fail','resource_fail','supervisor_init','temp_prepare'):ok=rc!=0 and not entered
  elif mode in ('abnormal','sigkill'):ok=entered and len(observed)>=6 and not remaining and rc==(17 if mode=='abnormal' else -9)
  elif mode=='timeout':ok=rc==124 and entered
  else:ok=rc==0 and entered
  r={'test_id':mode,'status':'PASS' if ok else 'FAIL','returncode':rc,'entered':entered,'stdout':stdout,'error':stderr,'seconds':round(time.monotonic()-start,3),'observed_tree':observed,'remaining_identities':remaining if observed else [],'evidence':'reports/fixture_results.json','purpose':mode,'fixture':'tests/fixture.py + scripts/supervisor.py','isolation':'fresh root allowlist; private bounded tmpfs; user/mount/PID/net namespaces'}
 r['temporary_cleanup']=not folder.exists();return r

def main():
 if ctypes.CDLL(None,use_errno=True).prctl(36,1,0,0,0)!=0:raise RuntimeError('subreaper unavailable: fail closed')
 results=[]
 with tempfile.TemporaryDirectory(dir=W,prefix='sockets-') as d:
  unix_path=str(Path(d)/'host.sock');abstract='aero-v2-'+str(os.getpid())
  with socket.socket(socket.AF_INET6) as ipv6,socket.socket(socket.AF_UNIX) as unix,socket.socket(socket.AF_UNIX) as absock:
   ipv6.bind(('::1',0));ipv6.listen();unix.bind(unix_path);unix.listen();absock.bind('\0'+abstract);absock.listen()
   # Positive host controls: sockets exist and accept, before isolation hides them.
   controls=[]
   for server,address,family in ((unix,unix_path,socket.AF_UNIX),(absock,'\0'+abstract,socket.AF_UNIX),(ipv6,ipv6.getsockname(),socket.AF_INET6)):
    with socket.socket(family) as c:c.connect(address);conn,_=server.accept();c.sendall(b'control');controls.append(conn.recv(7)==b'control');conn.close()
   cfg={'port6':ipv6.getsockname()[1],'unix_path':unix_path,'abstract':abstract}
   for mode in ('normal','tmp_capacity','output_capacity','sockets','timeout','abnormal','sigkill','normal','namespace_fail','mount_fail','network_fail','resource_fail','supervisor_init','temp_prepare'):
    r=run(mode,cfg)
    if mode=='normal' and results:r['test_id']='restart'
    results.append(r)
    if r['status']=='FAIL':break
   deliveries=[]
   for name,server in (('ipv6',ipv6),('unix',unix),('abstract',absock)):
    server.settimeout(.1)
    try:conn,_=server.accept();conn.close();deliveries.append(name)
    except socket.timeout:pass
 x={'tests':results,'PASS':sum(r['status']=='PASS' for r in results),'FAIL':sum(r['status']=='FAIL' for r in results),'SKIP':0,'host_socket_controls':controls,'host_received_after_isolation':deliveries,'subreaper_applied':True,'actual_runtime_executed':False}
 (R/'fixture_results.json').write_text(json.dumps(x,indent=2)+'\n');print(json.dumps({'tests':[(r['test_id'],r['status'],r['returncode']) for r in results],'host_controls':controls,'deliveries':deliveries}));return bool(x['FAIL'] or deliveries or not all(controls))
if __name__=='__main__':raise SystemExit(main())
