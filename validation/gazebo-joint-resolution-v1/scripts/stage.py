import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import *
from plan import read_plan,ready,argv
import os

def main():
 need(len(sys.argv)==4 and sys.argv[1]=='--owned-stage','stage arguments')
 p=read_plan(sys.argv[3]);ready(p);rel=sys.argv[2]
 need(Path('/proc/self/cgroup').read_text().strip()=='0::'+rel,'stage cgroup mismatch')
 for k,v in readback.items():need((Path('/sys/fs/cgroup')/rel.lstrip('/')/k).read_text().strip()==v,'stage resource mismatch')
 fds={}
 try:
  for r in p['mounts'].values():
   src=r['source']
   if src in fds:continue
   fd=os.open(src,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW);fds[src]=fd;st=os.fstat(fd)
   need((st.st_dev,st.st_ino)==(r['device'],r['inode']),'post-open identity')
   h=hashlib.sha256();off=0
   while chunk:=os.pread(fd,1048576,off):h.update(chunk);off+=len(chunk)
   need(h.hexdigest()==r['sha256'],'post-open SHA');os.set_inheritable(fd,True)
  a=argv(p,fds);os.execve(a[0],a,{'PATH':'/usr/bin:/bin','LC_ALL':'C'})
 finally:
  for fd in fds.values():os.close(fd)
if __name__=='__main__':
 try:main()
 except Exception as e:print('stage refused: '+str(e),file=sys.stderr);raise SystemExit(78)
