"""Owned service stage. Stdin GO/read and stdout telemetry/write cross bwrap.
Current pinned technical blockers reject before opening payload files/exec.
"""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import *
from plan import read_plan,runtime_ready,argv
import os

def main():
 need(len(sys.argv)==4 and sys.argv[1]=='--owned-joint-stage','fixed stage arguments')
 plan=read_plan();runtime_ready(plan,sys.argv[3]);rel=sys.argv[2]
 need(Path('/proc/self/cgroup').read_text().strip()=='0::'+rel,'stage cgroup')
 target=Path('/sys/fs/cgroup')/rel.lstrip('/')
 for name,value in readback.items():need((target/name).read_text().strip()==value,'stage resources')
 fds={}
 try:
  for row in plan['mounts'].values():
   src=row['source']
   if src in fds:continue
   fd=os.open(src,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW);fds[src]=fd;st=os.fstat(fd)
   need((st.st_dev,st.st_ino)==(row['device'],row['inode']),'post-open mount inode')
   # Hash backing FD, not a second path lookup.
   digest=hashlib.sha256();off=0
   while chunk:=os.pread(fd,1048576,off):digest.update(chunk);off+=len(chunk)
   need(digest.hexdigest()==row['sha256'],'post-open mount SHA');os.set_inheritable(fd,True)
  command=argv(plan,fds);os.execve(command[0],command,{'PATH':'/usr/bin:/bin','LC_ALL':'C'})
 finally:
  for fd in fds.values():os.close(fd)
if __name__=='__main__':
 try:main()
 except Exception as e:print('joint stage refused: '+str(e),file=sys.stderr);raise SystemExit(78)
