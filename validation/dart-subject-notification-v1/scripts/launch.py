"""Default prints contract only. Actual flag requires separate runtime authorization."""
import argparse,hashlib,json,os,subprocess,sys
from common import B,R,W,load_manifest,validate,check_prepared,check_fresh
import preservation
from resolution import preflight

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--execute-approved-notification-once',action='store_true');args=parser.parse_args()
 contract=json.loads((R/'runtime_contract.json').read_text())
 if not args.execute_approved_notification_once:
  print(json.dumps(contract,ensure_ascii=False,indent=2));return 0
 check_fresh();check_prepared()
 m=load_manifest();fds=[]
 try:
  for profile in m['profiles']:fds+=validate(m,profile)
 finally:
  for fd in fds:os.close(fd)
 preflight(m)  # Static ELF + exact mount-plan check BEFORE any one-shot.
 from notification_supervisor import prepare_service
 prepare_service()  # Read-only manager/unit collision check before collection marker.
 marker=W/'runtime_collection_attempt.json'
 with marker.open('x') as f:json.dump({'no_retry':True,'mode':'subject notification once; explicit future authorization required'},f)
 before=preservation.p.snapshot()
 with (W/'runtime_integrity_before.json').open('x') as f:json.dump(before,f)
 result=subprocess.run([sys.executable,'-B',str(B/'scripts/notification_supervisor.py'),'--execute-approved-notification-once'],cwd=B.parents[1])
 after=preservation.p.snapshot();changed=[p for p,h in before['files'].items() if after['files'].get(p)!=h];added=sorted(set(after['files'])-set(before['files']))
 integrity={'changed_or_missing':changed,'new_existing_scope_files':added,'main_head_unchanged':before['main_head']==after['main_head'],'main_status_unchanged':before['main_status']==after['main_status']}
 integrity['status']='PASS' if not changed and not added and integrity['main_head_unchanged'] and integrity['main_status_unchanged'] else 'FAIL'
 (R/'runtime_integrity.json').write_text(json.dumps(integrity,indent=2)+'\n')
 return result.returncode if integrity['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
