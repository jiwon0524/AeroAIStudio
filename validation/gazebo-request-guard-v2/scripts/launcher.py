"""No candidate deployment; no manager, marker, service, target or loader."""
def preflight():
    return dict(exit_code=78, stage_b='BLOCKED', risk_acceptance='UNDECIDED',
                actual_runtime='UNVERIFIED', normal_inputs='BLOCKED_IMMUTABLE_ORIGINALS',
                preloader='BLOCKED_TRUSTED_LAUNCH_HANDOFF', threads='CANDIDATE_NOT_ENABLED',
                trusted_audit='BLOCKED_LIVE_COLLECTOR_AND_OWNERSHIP', go_sent=False,
                service_started=False, marker_created=False)

if __name__ == '__main__':
    raise SystemExit(78)
