"""Fixed Bubblewrap fixture verifier. No generic command/runtime-probe interface."""
import hashlib,json,os,signal,socket,subprocess,tempfile,time
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];R=BASE/'reports';W=BASE/'work'
def write(name,x):(R/name).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def ns():return {k:os.readlink('/proc/self/ns/'+k) for k in ('user','mnt','net','pid')}
def identity(pid):
    try:
        x=Path(f'/proc/{pid}/stat').read_text().split(') ',1)[1].split();return {'pid':pid,'state':x[0],'ppid':int(x[1]),'start':x[19]}
    except (OSError,IndexError,ValueError):return None

def descendants(pid):
    rows=[x for p in Path('/proc').iterdir() if p.name.isdigit() and (x:=identity(int(p.name)))]
    found={pid}
    for _ in range(10):
        new={x['pid'] for x in rows if x['ppid'] in found};old=len(found);found|=new
        if len(found)==old:break
    return [x for x in rows if x['pid'] in found]

def command(folder,canary,resolv,case,port):
    return ['/usr/bin/prlimit','--cpu=2:2','--as=268435456:268435456','--fsize=65536:65536','--nofile=64:64','--core=0:0','--','/usr/bin/bwrap','--unshare-all','--die-with-parent','--new-session','--ro-bind','/','/','--tmpfs','/tmp','--proc','/proc','--dev','/dev','--ro-bind',str(BASE/'tests'),'/mnt','--ro-bind',str(canary),'/media','--ro-bind',str(canary),'/opt','--ro-bind',str(resolv),'/etc/resolv.conf','--bind',str(folder),'/run','--chdir','/run','--clearenv','--setenv','PATH','/usr/bin:/bin','--setenv','HOME','/run','--setenv','TMPDIR','/run','--setenv','LC_ALL','C','/usr/bin/python3','-I','-B','/mnt/fixture.py',case,json.dumps(ns()),str(port)]

def run(case,canary,resolv,port,broken=False):
    started=time.monotonic(); survivors=[]; observed=[]
    with tempfile.TemporaryDirectory(dir=W,prefix='run-') as directory:
        folder=Path(directory);cmd=command(folder,canary,resolv,case,port)
        if broken:cmd[cmd.index('/usr/bin/bwrap')+1:cmd.index('/usr/bin/bwrap')+1]=['--invalid-isolation-option']
        with open(folder/'stdout','wb') as out,open(folder/'stderr','wb') as err:
            p=subprocess.Popen(cmd,stdout=out,stderr=err,env={'PATH':'/usr/bin:/bin','LC_ALL':'C'},start_new_session=True)
            timed=False
            try:
                if case=='descendants' and not broken:time.sleep(.25);observed=descendants(p.pid)
                rc=p.wait(timeout=.7 if case in ('timeout','descendants') else 6)
            except subprocess.TimeoutExpired:
                timed=True;observed=descendants(p.pid);os.killpg(p.pid,signal.SIGKILL);rc=p.wait(timeout=2)
            for _ in range(20):
                survivors=[x for x in observed if (y:=identity(x['pid'])) and y['start']==x['start'] and y['state']!='Z']
                if not survivors:break
                time.sleep(.05)
        stdout=(folder/'stdout').read_text();stderr=(folder/'stderr').read_text()
        ready='"gate": "READY"' in stdout;entered=(folder/'started').exists()
        record={'test_id':case if not broken else 'fail_closed','purpose':case if not broken else 'reject invalid sandbox before fixture entry','fixture':'tests/fixture.py','isolation':'bwrap user/mount/net/pid/ipc/uts/cgroup namespaces; root ro; output rw; private tmpfs/dev/proc','expected':'fixture gate success and bounded outcome' if not broken else 'nonzero + no fixture entry','returncode':rc,'signal':-rc if rc<0 else None,'timeout':timed,'gate_ready':ready,'fixture_entered':entered,'seconds':round(time.monotonic()-started,3),'stdout':stdout,'error':stderr,'observed_processes':observed,'live_survivors':survivors,'evidence':'reports/fixture_results.json','max_output_file_bytes':max(x.stat().st_size for x in folder.iterdir() if x.is_file())}
    record['temporary_cleanup']=not folder.exists();return record

def main():
    results=[]; host_ns=ns()
    with tempfile.TemporaryDirectory(dir=W,prefix='canaries-') as d:
        c=Path(d);(c/'value').write_text('preserve-me');resolv=c/'resolv.conf';resolv.write_text('nameserver 127.0.0.1\noptions timeout:1 attempts:1\n')
        original=hashlib.sha256((c/'value').read_bytes()).hexdigest()
        with socket.socket() as tcp,socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as udp:
            tcp.bind(('127.0.0.1',0));port=tcp.getsockname()[1];tcp.listen(1);tcp.settimeout(.1);udp.bind(('127.0.0.1',port));udp.settimeout(.1)
            gate=run('normal',c,resolv,port);gate['status']='PASS' if gate['returncode']==0 and gate['gate_ready'] and gate['fixture_entered'] else 'FAIL';results.append(gate)
            if gate['status']=='PASS':
                for case in ('filesystem','network','exit','signal','timeout','cpu','memory','file','descendants','normal'):
                    r=run(case,c,resolv,port);expected={'exit':7,'signal':143,'memory':23,'file':24}
                    ok=r['gate_ready'] and r['fixture_entered'] and not r['live_survivors'] and r['temporary_cleanup']
                    if case in ('timeout','descendants'):ok &= r['timeout']
                    elif case=='cpu':ok &= r['returncode'] in (137,-9) and not r['timeout']
                    else:ok &= r['returncode']==expected.get(case,0)
                    if case=='descendants':ok &= len(r['observed_processes'])>=3
                    r['status']='PASS' if ok else 'FAIL';results.append(r)
                    if r['status']=='FAIL':break
                r=run('normal',c,resolv,port,True);r['status']='PASS' if r['returncode']!=0 and not r['fixture_entered'] and not r['gate_ready'] else 'FAIL';results.append(r)
            else:
                for case in ('filesystem','network','exit','signal','timeout','cpu','memory','file','descendants','restart','fail_closed'):results.append({'test_id':case,'status':'SKIP','reason':'mandatory sandbox gate failed','evidence':'reports/fixture_results.json'})
            arrivals=[]
            try:conn,_=tcp.accept();conn.close();arrivals.append('TCP')
            except socket.timeout:pass
            try:udp.recvfrom(1024);arrivals.append('UDP')
            except socket.timeout:pass
        preserved=hashlib.sha256((c/'value').read_bytes()).hexdigest()==original
    write('fixture_results.json',{'host_namespaces':host_ns,'tests':results,'PASS':sum(x['status']=='PASS' for x in results),'FAIL':sum(x['status']=='FAIL' for x in results),'SKIP':sum(x['status']=='SKIP' for x in results),'canary_preserved':preserved,'host_listener_received':arrivals,'canary_temporary_cleanup':not c.exists(),'actual_DART_Gazebo_execution':False,'system_files_write_tested':False,'system_preservation_basis':'root read-only asserted by successful gate only; no destructive write attempt to real project/system'})
    print(json.dumps({'tests':[(x['test_id'],x['status'],x.get('returncode')) for x in results],'canary_preserved':preserved,'received':arrivals}))
if __name__=='__main__':
    main()
    result=json.loads((R/'fixture_results.json').read_text())
    raise SystemExit(bool(result['FAIL'] or result['host_listener_received'] or not result['canary_preserved']))
