"""Owned transient-service stage: validate pinned fds, then exec original sandbox tools."""
import json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from allowlist import B,load_manifest,validate

def require(ok,message):
    if not ok:raise ValueError(message)
def resources(target):
    expected={'memory.max':'67108864','memory.swap.max':'0','pids.max':'8','cpu.max':'25000 100000'}
    for name,value in expected.items():require((target/name).read_text().strip()==value,'live resource mismatch '+name)

def bwrap(entries,fds,canary,limits,args):
    a=['/usr/bin/prlimit','--cpu=2:2','--as=268435456:268435456','--fsize=65536:65536','--nofile=64:64','--core=0:0','--','/usr/bin/bwrap','--unshare-all','--die-with-parent','--new-session','--cap-drop','ALL','--size','16777216','--tmpfs','/','--dir','/usr','--dir','/usr/lib','--dir','/usr/lib/x86_64-linux-gnu','--dir','/usr/lib64','--symlink','usr/lib','/lib','--symlink','usr/lib64','/lib64','--symlink','../lib/x86_64-linux-gnu/ld-linux-x86-64.so.2','/usr/lib64/ld-linux-x86-64.so.2','--proc','/proc','--dev','/dev','--size','1048576','--tmpfs','/dev/shm','--remount-ro','/dev']
    for row,fd in zip(entries,fds):a+=['--ro-bind-fd',str(fd),row['sandbox_path']]
    a+=['--ro-bind-fd',str(canary),'/input/canary','--ro-bind-fd',str(limits),'/limits','--dir','/cwd','--size','4194304','--tmpfs','/tmp','--size','4194304','--tmpfs','/run','--remount-ro','/','--chdir','/cwd','--clearenv','--setenv','LC_ALL','C','/fixture/native_fixture','--harness']+args
    return a

def main():
    require(len(sys.argv)==10 and sys.argv[1]=='--owned-service-stage','fixed stage args required')
    # stage args: own cgroup, host mnt/net/user/pid, IPv6 port, UNIX path, abstract name.
    rel=sys.argv[2];require(Path('/proc/self/cgroup').read_text().strip()=='0::'+rel,'service cgroup mismatch')
    target=Path('/sys/fs/cgroup')/rel.lstrip('/');resources(target)
    require(not any(os.environ.get(k) for k in ('LD_PRELOAD','LD_AUDIT','LD_LIBRARY_PATH')),'loader environment not allowed')
    manifest=load_manifest();entries=manifest['profiles']['harmless_fixture_only'];fds=validate(manifest,'harmless_fixture_only')
    canary=os.open(B/'work/canary',os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW);limits=os.open(target,os.O_PATH|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW)
    for fd in fds+[canary,limits]:os.set_inheritable(fd,True)
    args=sys.argv[3:];command=bwrap(entries,fds,canary,limits,args)
    os.execve(command[0],command,{'PATH':'/usr/bin:/bin','LC_ALL':'C'})
if __name__=='__main__':
    try:main()
    except Exception as e:
        print(json.dumps({'phase':'service_stage','status':'REJECTED','error':str(e),'body_entered':False}),flush=True);raise SystemExit(78)
