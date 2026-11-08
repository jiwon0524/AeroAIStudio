"""Read-only original-input snapshot; writes are confined to new runtime outputs."""
from common import *
import subprocess,os

def capture(plan):
 original=json.loads((ROOT/'validation/gazebo-joint-harness-fix-v1/reports/preflight.json').read_text());main=Path('/home/jiwon/Projects/AeroAIStudio')
 head=subprocess.check_output(['git','-C',str(main),'rev-parse','HEAD'],text=True).strip();status=subprocess.check_output(['git','-C',str(main),'status','--porcelain=v1','-z']).hex()
 need(head==original['main']['head'] and status==original['main']['status_hex'],'main HEAD/status changed')
 hashes={}
 for r in original['main']['dirty_regular_files']:
  p=main/r['path'];hashes[str(p)]=sha(p);need(hashes[str(p)]==r['sha256'],'main dirty hash changed')
 for p,h in original['fixed_inputs'].items():hashes[p]=sha(p);need(hashes[p]==h,'original fixed input changed')
 for row in plan['mounts'].values():hashes[row['source']]=sha(row['source']);need(hashes[row['source']]==row['sha256'],'planned input changed')
 receipt=json.loads((ROOT/'validation/gazebo-joint-codegen-fix-v1/work/config-01/manifests/staged.json').read_text())
 for p,row in receipt.items():need(sha(p)==sha(row['source'])==row['sha256'],'receipt changed')
 link=ROOT/'libgz-physics-dartsim-plugin.so';st=link.lstat();need(link.is_symlink() and not link.exists(),'root symlink changed')
 return {'main_head':head,'main_status':status,'hashes':hashes,'symlink':{'target':os.readlink(link),'inode':st.st_ino,'mtime_ns':st.st_mtime_ns},'receipt':receipt}
