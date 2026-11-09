"""Unconditional refusal; no manager/service/marker or native operation."""
def preflight():
    return dict(exit_code=78, status='BLOCKED_INTEGRATION_AND_PERMITTED_RESOURCE_POLICY',
                manager_queried=False, service_started=False, marker_created=False,
                go_sent=False, stage_b='BLOCKED', risk_acceptance='UNDECIDED', actual_runtime='UNVERIFIED')
if __name__=='__main__':
    raise SystemExit(78)
