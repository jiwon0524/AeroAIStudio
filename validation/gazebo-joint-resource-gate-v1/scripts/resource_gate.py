"""Fail-closed resource outcome contract. No native producer exists yet.

These packets are a specification tested with synthetic inputs, not observations
from Gazebo. A complete ledger alone cannot release the actual launch blocker.
"""
import copy


class ResourceError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ResourceError(message)


class ResourceLedger:
    """Exact final selections, not a list of failed search candidates."""

    def __init__(self, expected):
        self.expected = copy.deepcopy(expected)
        self.seen = set()
        self.closed = False
        self.failed = False

    def packet(self, row):
        try:
            require(not self.closed and not self.failed, 'closed/failed resource ledger')
            require(set(row) == {'kind', 'role', 'selected', 'outcome', 'fallback',
                                 'errors', 'closure_complete'}, 'resource packet fields')
            require(row['kind'] == 'resource_result', 'resource packet kind')
            role = row['role']
            require(role in self.expected and role not in self.seen,
                    'unexpected/duplicate resource role')
            require(row['selected'] == self.expected[role], 'unapproved final selection')
            require(row['outcome'] == 'success' and row['fallback'] is False,
                    'load failure or fallback')
            require(type(row['errors']) is int and row['errors'] == 0,
                    'parse/load errors')
            require(row['closure_complete'] is True, 'unobserved required include/closure')
            self.seen.add(role)
        except (ResourceError, TypeError, KeyError):
            self.failed = True
            raise

    def complete(self):
        require(not self.failed and not self.closed, 'closed/failed resource ledger')
        if self.seen != set(self.expected):
            self.failed = True
            raise ResourceError('missing required resource observations')
        self.closed = True


class ResourceSession:
    """Mock-tested adapter to the existing ACK session; not wired to a launcher.

    No control bytes are sent here. Only the existing native/identity/physics
    session can authorize GO, and only after a fully observed resource ledger.
    Native instrumentation and its binary provenance remain separate blockers.
    """

    def __init__(self, expected, ack_session):
        self.ledger = ResourceLedger(expected)
        self.session = ack_session
        self.ready_started = False
        self.authorized = False
        self.failed = False

    def packet(self, row):
        require(not self.failed, 'failed resource session')
        try:
            self._packet(row)
        except Exception:
            self.failed = True
            raise

    def _packet(self, row):
        if row.get('kind') == 'resource_result':
            require(not self.ready_started, 'late resource outcome')
            self.ledger.packet(row)
            return
        if not self.ready_started:
            self.ledger.complete()
            self.ready_started = True
        self.session.packet(row)

    def authorize(self):
        require(not self.failed and self.ready_started and self.ledger.closed and not self.authorized,
                'missing resource preamble or duplicate GO')
        self.authorized = True
        return self.session.authorize()

    def stderr(self, line):
        require(not self.failed, 'failed resource session')
        try:
            return self.session.stderr(line)
        except Exception:
            self.failed = True
            raise

    def finalize(self, *args):
        require(self.authorized and not self.failed, 'GO missing or failed resource session')
        try:
            return self.session.finalize(*args)
        except Exception:
            self.failed = True
            raise
