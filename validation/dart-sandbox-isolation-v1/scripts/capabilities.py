import json,os,platform,shutil,subprocess,time
from pathlib import Path
B=Path(__file__).resolve().parents[1]
def read(p):
 try:return Path(p).read_text().strip()
 except OSError:return 'UNKNOWN'
def run(args):
 t=time.monotonic()
 try:
  p=subprocess.run(args,capture_output=True,text=True,timeout=5);return {'rc':p.returncode,'stdout':p.stdout,'stderr':p.stderr,'seconds':round(time.monotonic()-t,3)}
 except (OSError,subprocess.TimeoutExpired) as e:return {'status':'UNAVAILABLE','error':str(e)}
x={'uid':os.getuid(),'kernel':platform.release(),'tools':{n:shutil.which(n) for n in ('bwrap','unshare','prlimit','timeout','aa-status')},'userns_restriction':read('/proc/sys/kernel/apparmor_restrict_unprivileged_userns'),'userns_clone':read('/proc/sys/kernel/unprivileged_userns_clone'),'max_user_namespaces':read('/proc/sys/user/max_user_namespaces'),'apparmor_enabled':read('/sys/module/apparmor/parameters/enabled'),'apparmor_current':read('/proc/self/attr/current'),'selected_proc_status':[s for s in read('/proc/self/status').splitlines() if s.startswith(('NoNewPrivs:','Seccomp:','CapEff:'))],'namespace_probes':{'bwrap':run(['/usr/bin/bwrap','--unshare-user','--unshare-pid','--unshare-net','--die-with-parent','--ro-bind','/','/','--proc','/proc','--dev','/dev','/usr/bin/true']),'unshare':run(['/usr/bin/unshare','--user','--map-root-user','--mount','--net','--pid','--fork','/usr/bin/true'])},'prlimit':run(['/usr/bin/prlimit','--cpu=2:2','--core=0:0','--','/usr/bin/true']),'seccomp':'host state only; no new syscall filter installed/tested; inherited filter not counted as project isolation','apparmor':'existing enforcement only; no policy/settings changes','scope':'same-user host via approved execution escalation; ordinary tool sandbox namespace denied; not sudo/root','system_changes':False}
(B/'reports/sandbox_capabilities.json').write_text(json.dumps(x,indent=2)+'\n');print(json.dumps(x))
