"""Unconditional refusal, before any manager/service/marker or native call."""
def preflight():
    return dict(exit_code=78, status='BLOCKED_COPY_IDENTITY_AND_LAUNCH_INTEGRATION',
                service_started=False, marker_created=False, go_sent=False,
                stage_b='BLOCKED', risk_acceptance='UNDECIDED', actual_runtime='UNVERIFIED')

if __name__ == '__main__':
    raise SystemExit(78)
