"""Fail-closed preparation launcher. No service/marker/native invocation exists."""
import argparse,json,sys
from pathlib import Path
B=Path(__file__).resolve().parents[1]
def require_executable_contract(contract):
 if contract['status']!='EXECUTION_READY' or contract['blockers']:
  raise ValueError('NOT_EXECUTION_READY: '+ '; '.join(contract['blockers']))
 if not all(contract['capabilities'].values()):raise ValueError('unverified capabilities')
 if contract['risk_acceptance']!='EXPLICITLY_RECORDED':raise ValueError('residual risks not accepted')
 # There is deliberately no process launcher behind this preparation artifact.
 raise ValueError('runtime supervisor integration not implemented')
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--execute-approved-gazebo-once',action='store_true');args=parser.parse_args()
 c=json.loads((B/'reports/runtime_contract.json').read_text())
 if not args.execute_approved_gazebo_once:print(json.dumps(c,indent=2));return 0
 from preflight import check_inputs
 check_inputs()
 require_executable_contract(c)
if __name__=='__main__':
 try:raise SystemExit(main())
 except ValueError as e:print(str(e),file=sys.stderr);raise SystemExit(78)
