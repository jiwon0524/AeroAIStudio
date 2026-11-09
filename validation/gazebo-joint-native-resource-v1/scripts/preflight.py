"""Refusal only: neither a service nor marker can be created here."""
import json
if __name__ == '__main__':
    print(json.dumps({'status':'BLOCKED','exit_code':78,
      'blockers':['NEW_NATIVE_CHAIN_NOT_SEALED_IN_ACTUAL_SUPERVISOR',
                  'LAZY_DART_ODE_AUXILIARY_ACCESS_CLOSURE_UNRESOLVED'],
      'manager_queried':False,'service_started':False,'marker_created':False,'go_sent':False,
      'stage_b':'BLOCKED','risk_acceptance':'UNDECIDED','actual_runtime':'UNVERIFIED'},indent=2))
    raise SystemExit(78)
