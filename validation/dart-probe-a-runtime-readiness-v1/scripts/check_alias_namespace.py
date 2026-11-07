"""Expose pinned Core files read-only, execute only no-loader protocol fixture."""
import json, os, subprocess
from pathlib import Path
from readiness import ROOT, load_manifest, validate, mount_arguments
B=ROOT/'validation/dart-probe-a-runtime-readiness-v1'
def main():
    m=load_manifest();entries=m['profiles']['installed_core_future_only'];fds=validate(m,'installed_core_future_only')
    binary=os.open(B/'work/post_open',os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
    args=['/usr/bin/bwrap','--unshare-all','--die-with-parent','--new-session','--cap-drop','ALL','--tmpfs','/','--dir','/usr/lib/x86_64-linux-gnu','--symlink','usr/lib','/lib','--dir','/usr/lib64','--symlink','usr/lib64','/lib64','--symlink','../lib/x86_64-linux-gnu/ld-linux-x86-64.so.2','/usr/lib64/ld-linux-x86-64.so.2']
    args+=mount_arguments(entries,fds)
    args+=['--ro-bind-fd',str(binary),'/fixture','--remount-ro','/','--clearenv','/fixture']
    try:
        p=subprocess.run(args,pass_fds=tuple(fds+[binary]),input='CLOSE\n',text=True,capture_output=True,timeout=10)
        result={'status':'PASS' if p.returncode==0 and p.stdout=='POST_OPEN_SIMULATED\nCLOSE_SIMULATED\n' else 'FAIL','exit_code':p.returncode,'stdout':p.stdout,'stderr':p.stderr,'DART_loaded':False,'Core_files_mounted':p.returncode==0,'scope':'successful exit demonstrates FD alias arguments accepted and libc loader aliases exercised; DART alias resolution not dynamically exercised','supervisor':'not used in this focused mount check; previous integration reused'}
        (B/'reports/alias_namespace.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result));return p.returncode
    finally:
        for fd in fds+[binary]:os.close(fd)
if __name__=='__main__':raise SystemExit(main())
