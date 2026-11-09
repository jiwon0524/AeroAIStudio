"""Session construction only; no service, target, marker or process operation."""
from contract import validate,need
from protocol import AckSession,AckWindow,Lines
from native_gate import NativeSession
from attestor import Attestor,owned_stop,cleanup_ok

def session(manifest, attestor, write):
    validate(manifest)
    need(type(attestor) is Attestor and attestor.plan is manifest,'stale/mixed attestor object')
    window=AckWindow(write,attestor.mappings,attestor.start,attestor.pid)
    native=manifest['native']
    return NativeSession(native['expected'],native['schema_closure'],AckSession(manifest['attestation'],attestor.ready,window)),window
