from common import *
import ast,subprocess,re,os,shlex

def main():
 build=json.loads((B/'reports/build.json').read_text());m=json.loads((ROOT/'validation/gazebo-joint-harness-fix-v1/reports/final_manifest.json').read_text())
 oldneeded=[r['soname'] for r in m['ELFs'][m['executable']]['needed']];new=build['ELFs'][str(B/'work/aero-joint-harness-ack')]
 need(new['needed']==oldneeded,'new harness dependencies changed')
 for f,r in m['ELFs'].items():need(sha(f)==r['sha256'],'old ELF changed')
 for profile in ['actual','harmless']:
  p=json.loads((B/'reports'/(profile+'_plan.json')).read_text());need(p['payload'][1] in build['ELFs'],'payload missing build receipt')
  need(sha(p['payload'][1])==build['ELFs'][p['payload'][1]]['sha256'],'payload SHA')
  if profile=='harmless':
   need(build['ELFs'][p['payload'][1]]['needed']==['libc.so.6'],'fixture loads subject')
   syms=subprocess.check_output(['/usr/bin/nm','-u',p['payload'][1]],text=True);need(not re.search(r'dlopen|execv|system@|posix_spawn',syms),'fixture dynamic loading/exec path')
   dump(B/'reports/harmless_safety.json',{'status':'PASS_LIBC_ONLY_STATIC','exe':p['payload'][1],'sha256':sha(p['payload'][1]),'DT_NEEDED':['libc.so.6'],'undefined_symbols':syms,'exec_path':'systemd-run -> pinned Python stage -> bwrap -> original libc-only fd_bridge -> libc-only harmless; no GZ/DART mount','claim':'static safety, not an execution result'})
 files=list((B/'scripts').glob('*.py'))+list((B/'tests').glob('*.py'))+list((B/'inputs').iterdir())+[B/'reports/build.json',B/'reports/resources.json']+[B/'reports'/(profile+'_'+kind+'.json') for profile in ['actual','harmless'] for kind in ['plan','argv']]
 for rel in ['scripts/common.py','scripts/protocol.py','scripts/plan.py','scripts/live.py','scripts/integrity.py']:
  files.append(ROOT/'validation/gazebo-joint-isolation-v1'/rel)
 for rel in ['validation/dart-probe-a-harness-v1/scripts/identity.py','validation/dart-probe-a-harness-v1/scripts/mapped.py','validation/dart-cgroup-smoke-v1/scripts/smoke.py','validation/dart-cgroup-integration-v1/scripts/integration.py','validation/gazebo-minimal-physics-v1/scripts/gate.py']:files.append(ROOT/rel)
 files=[f for f in files if f.name!='source_pin.sha256']
 for f in files:
  if f.suffix=='.py':ast.parse(f.read_text(),filename=str(f))
 record={'files':{str(f.relative_to(ROOT)):sha(f) for f in sorted(set(files))}};dump(B/'reports/source_pin.json',record);(B/'inputs/source_pin.sha256').write_text(sha(B/'reports/source_pin.json')+'\n');print('PASS code/plan/build seal and harmless static safety')
if __name__=='__main__':main()
