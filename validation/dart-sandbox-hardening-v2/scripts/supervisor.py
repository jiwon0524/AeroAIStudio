"""Fixed fixture supervisor; no arbitrary executable accepted."""
import json,os,signal,subprocess,sys
from pathlib import Path
B=Path(__file__).resolve().parents[1]
mode,folder=sys.argv[1:3];cfg=json.loads(sys.argv[3]);folder=Path(folder)
if mode=='supervisor_init':sys.exit(71)
if mode=='temp_prepare':
 try:(folder/'stdout'/'nested').mkdir(parents=True)
 except OSError:sys.exit(72)
 sys.exit(73)
host={k:os.readlink('/proc/self/ns/'+k) for k in ('user','mnt','pid','net')}
case=mode if mode in ('normal','tmp_capacity','output_capacity','sockets') else 'tree'
cmd=['/usr/bin/prlimit','--cpu=2:2','--as=268435456:268435456','--fsize=65536:65536','--nofile=64:64','--core=0:0','--','/usr/bin/bwrap','--unshare-all','--die-with-parent','--new-session','--size','16777216','--tmpfs','/','--ro-bind','/usr','/usr','--symlink','usr/bin','/bin','--symlink','usr/lib','/lib','--symlink','usr/lib64','/lib64','--proc','/proc','--dev','/dev','--size','1048576','--tmpfs','/dev/shm','--remount-ro','/dev','--ro-bind',str(B/'tests'),'/mnt','--size','4194304','--tmpfs','/tmp','--size','4194304','--tmpfs','/run','--remount-ro','/','--chdir','/run','--clearenv','--setenv','PATH','/usr/bin:/bin','--setenv','LC_ALL','C','/usr/bin/python3','-I','-B','/mnt/fixture.py',case,json.dumps(host),json.dumps(cfg)]
if mode=='namespace_fail':cmd.insert(cmd.index('--unshare-all')+1,'--invalid-namespace-option')
if mode=='mount_fail':cmd[cmd.index(str(B/'tests'))]='/nonexistent-owned-test-source'
if mode=='network_fail':cmd.insert(cmd.index('--unshare-all')+1,'--share-net')
if mode=='resource_fail':cmd[cmd.index('--as=268435456:268435456')]='--as=134217728:134217728'
signal.signal(signal.SIGUSR1,lambda *_:os._exit(17))
p=subprocess.Popen(cmd)
(folder/'bwrap_pid').write_text(str(p.pid))
if mode=='timeout':
 try:rc=p.wait(timeout=.5)
 except subprocess.TimeoutExpired:p.kill();p.wait(timeout=2);sys.exit(124)
else:rc=p.wait(timeout=8)
sys.exit(rc if rc>=0 else 128-rc)
