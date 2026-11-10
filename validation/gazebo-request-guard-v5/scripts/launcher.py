"""No release: refusal before any service/marker, native function or target."""
def preflight():
    return dict(exit_code=78,status='BLOCKED_FULL_CATALOG_IDENTITY_AND_NORMAL_LOADER_POLICY',
                service_started=False,marker_created=False,go_sent=False,
                stage_b='BLOCKED',risk_acceptance='UNDECIDED',actual_runtime='UNVERIFIED')
if __name__=='__main__':raise SystemExit(78)
