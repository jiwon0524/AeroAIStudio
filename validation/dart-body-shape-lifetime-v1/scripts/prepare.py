"""Fresh compile-artifact manifest preparation only; readelf/FD reads, never a loader."""
import hashlib,json,os,re,subprocess,sys
from pathlib import Path
from common import B,ROOT,R,W
from identity import describe_fd

def main():
 for p in (R/'manifest.json',W/'manifest.sha256'):
  if os.path.lexists(p):raise ValueError('refuse repinning existing manifest')
 m=json.loads((ROOT/'validation/dart-skeleton-lifetime-v2/reports/manifest.json').read_text())
 e=m['profiles']['harmless_fixture_only'][0];binary=(W/'body_shape_fixture').resolve()
 fd=os.open(binary,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
 try:e.update(describe_fd(fd))
 finally:os.close(fd)
 for k in ('real_path','requested_path','absolute_path','symlink_final_path'):e[k]=str(binary)
 dynamic=subprocess.check_output(['/usr/bin/readelf','-dW',str(binary)],text=True)
 for tag,key in [('NEEDED','needed'),('SONAME','soname'),('RPATH','rpath'),('RUNPATH','runpath')]:
  e[key]=re.findall(r'\('+tag+r'\).*?\[(.*?)\]',dynamic)
 e.update(sandbox_path='/fixture/native_fixture',role='body-shape normal ownership; NOT_RUNTIME_VERIFIED',library_name='body_shape_fixture')
 # Remove inherited stale executable metadata. Runtime identity keys are fresh.
 for k in ('stat','special_sections','flags','lifetime_imports','ifunc_count','gnu_unique_count','debuglink','has_debug_info','has_symtab'):e.pop(k,None)
 m['required_paths']['harmless_fixture_only']=[x['real_path'] for x in m['profiles']['harmless_fixture_only']]
 raw=(json.dumps(m,indent=2)+'\n').encode();(R/'manifest.json').write_bytes(raw)
 (W/'manifest.sha256').write_text(hashlib.sha256(raw).hexdigest()+'\n')
 print(json.dumps({'identity':{k:e[k] for k in ('real_path','sha256','build_id','size')},'needed':e['needed'],'target_executed':False}))
if __name__=='__main__':main()
