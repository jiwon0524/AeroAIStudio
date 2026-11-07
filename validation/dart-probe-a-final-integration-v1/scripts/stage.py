import os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import *
spec=importlib.util.spec_from_file_location('proven_stage',ROOT/'validation/dart-probe-a-harness-v1/scripts/stage.py');old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
def main():
 if len(sys.argv)!=10 or sys.argv[1]!='--owned-service-stage':raise ValueError('fixed args')
 rel=sys.argv[2]
 if Path('/proc/self/cgroup').read_text().strip()!='0::'+rel:raise ValueError('cgroup membership')
 target=Path('/sys/fs/cgroup')/rel.lstrip('/');old.resources(target)
 if any(os.environ.get(k) for k in ('LD_PRELOAD','LD_AUDIT','LD_LIBRARY_PATH')):raise ValueError('loader environment')
 m=load_manifest();core=m['profiles']['installed_core_future_only'];base=m['profiles']['harmless_fixture_only'];fds=[]
 try:
  corefds=validate(m,'installed_core_future_only');fds+=corefds
  basefds=validate(m,'harmless_fixture_only');fds+=basefds
  canary=os.open(W/'canary',os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW);fds.append(canary)
  limits=os.open(target,os.O_PATH|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW);fds.append(limits)
  # Reuse proven sandbox layout; canonical libc/loader mount once via baseline.
  cmd=old.bwrap(base,basefds,canary,limits,sys.argv[3:]);alias=readiness.mount_arguments(core,corefds)
  # Insert Core/aliases before baseline FD bindings; equivalent mounts overlap only
  # for libc/loader and use the same validated inode.
  pos=cmd.index('--ro-bind-fd');cmd[pos:pos]=alias
  for fd in fds:os.set_inheritable(fd,True)
  os.execve(cmd[0],cmd,{'PATH':'/usr/bin:/bin','LC_ALL':'C'})
 finally:
  for fd in fds:os.close(fd)
if __name__=='__main__':main()
