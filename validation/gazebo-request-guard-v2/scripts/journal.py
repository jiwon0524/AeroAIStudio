"""Native journal -> existing AuditGate offline integration.

read_private consumes a descriptor retained solely by trusted supervisor and
collector, not target stdout/stderr. OS launch proof is deliberately mandatory
and unavailable in production. Passing mock evidence is NOT authentication.
"""
import importlib.util
from pathlib import Path
import os
import stat

R = Path(__file__).resolve().parents[1]
path = R.parent / 'gazebo-request-guard-v1/scripts/audit_gate.py'
spec = importlib.util.spec_from_file_location('reused_guard_audit', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
AuditGate = module.AuditGate

class JournalAdapter:
    MAX_BYTES = 1048576
    MAX_LINE = 192

    def __init__(self, gate, root, proof):
        self.gate, self.root, self.proof = gate, root, proof
        self.seq = self.denied = self.total = 0
        self.live = set()
        self.pending = {}
        self.started = self.dead = self.complete = self.closed = False
        self.failed = False

    def need(self, yes, reason):
        if not yes:
            self.failed = self.gate.failed = True
            raise ValueError(reason)

    def emit(self, kind, payload):
        self.gate.event(dict(seq=self.gate.seq+1, kind=kind,
                             binding=dict(self.gate.binding), payload=payload),
                        authenticated=True)

    def feed(self, raw):
        try:
            self.need(not self.failed and not self.closed and not self.complete, 'journal already terminal')
            self.total += len(raw)
            self.need(self.total <= self.MAX_BYTES and len(raw) <= self.MAX_LINE, 'journal overflow')
            self.need(raw.endswith(b'\n') and raw.count(b'\n') == 1, 'partial/multiple journal row')
            fields = raw.decode('ascii').split()
            self.need(len(fields) == 5, 'journal schema')
            seq, kind, pid, nr, denied = fields
            seq, pid, nr, denied = map(int, (seq, pid, nr, denied))
            self.need(seq == self.seq+1 and pid > 0, 'sequence/task identity')
            expected = self.denied + (kind == 'DENY')
            self.need(denied == expected, 'denial counter mismatch')
            self.need(self.started or kind == 'EXEC_STOP', 'missing exec boundary')
            if kind == 'EXEC_STOP':
                self.need(not self.started and seq == 1 and pid == self.root, 'exec start mismatch')
                required = {'pre_loader', 'fd_attested', 'policy_applied', 'journal_private', 'lifetime_tracking'}
                # Adapter receives these from a future verified launch owner.
                # EXEC_STOP by itself establishes none of the other claims.
                self.need(set(self.proof) == required and all(v is True for v in self.proof.values()),
                          'trusted launch integration missing')
                self.emit('start', dict(self.proof))
                self.live.add(pid)
                self.started = True
            elif kind == 'TASK_BORN':
                self.need(nr in self.live and pid not in self.live and len(self.live) < 64,
                          'unbound/duplicate/excess task')
                self.live.add(pid)
            elif kind == 'REQUEST':
                self.need(pid in self.live and pid not in self.pending, 'unbound/overlapping request')
                self.pending[pid] = (nr, kind)
            elif kind in {'DENY', 'INPUT_PREPARED', 'INPUT_DELIVERED', 'REPLIED_DENY', 'CANCELLED'}:
                self.need(pid in self.live and pid in self.pending and self.pending[pid][0] == nr,
                          'request completion mismatch')
                previous = self.pending[pid][1]
                allowed = {'DENY': {'REQUEST'}, 'INPUT_PREPARED': {'REQUEST'},
                           'INPUT_DELIVERED': {'INPUT_PREPARED'}, 'REPLIED_DENY': {'DENY'},
                           'CANCELLED': {'REQUEST', 'DENY', 'INPUT_PREPARED'}}
                self.need(previous in allowed[kind], 'request transition mismatch')
                if kind in {'DENY', 'CANCELLED'}:
                    self.emit('denial', {'nr': nr, 'task': pid, 'reason': kind})
                if kind in {'INPUT_DELIVERED', 'REPLIED_DENY', 'CANCELLED'}:
                    del self.pending[pid]
                else:
                    self.pending[pid] = (nr, kind)
            elif kind == 'EXIT_STOP':
                self.need(pid in self.live, 'unbound exit stop')
            elif kind == 'TASK_DEAD':
                self.need(pid in self.live, 'duplicate/unbound death')
                # raw wait status zero is the only accepted successful exit.
                if nr != 0 or pid in self.pending:
                    self.emit('denial', {'task': pid, 'reason': 'abnormal/pending death'})
                self.pending.pop(pid, None)
                self.live.remove(pid)
            elif kind == 'ALL_DEAD':
                self.need(pid == self.root and not self.dead and not self.live and not self.pending,
                          'missing all-task death')
                self.emit('all_dead', {'live_tasks': 0, 'wait_echild': True})
                self.dead = True
            elif kind == 'COMPLETE':
                self.need(pid == self.root and self.dead and not self.live and not self.pending,
                          'completion before terminal collection')
                self.emit('complete', {'denied': self.gate.denied, 'pending': 0, 'lost': 0})
                self.complete = True
            else:
                self.need(False, 'unknown/loss/overflow native record')
            self.seq, self.denied = seq, denied
        except Exception:
            self.failed = self.gate.failed = True
            raise

    def eof(self):
        self.need(not self.failed and self.complete and not self.closed, 'early/duplicate native EOF')
        self.gate.eof()
        self.closed = True

    def read_private(self, fd):
        # Post-death regular journal ingestion only. Live collector/drain and
        # private FD ownership attestation remain unavailable. Do NOT poll an
        # active regular file and call its temporary end authenticated EOF.
        self.need(self.proof.get('journal_private') is True, 'unproven channel owner')
        st = os.fstat(fd)
        self.need(stat.S_ISREG(st.st_mode) and st.st_uid == os.geteuid() and
                  st.st_nlink == 1 and st.st_mode & 0o077 == 0, 'unsafe journal FD')
        offset = 0
        while True:
            chunk = os.pread(fd, self.MAX_LINE+1, offset)
            if not chunk:
                break
            end = chunk.find(b'\n')
            self.need(end >= 0 and end+1 <= self.MAX_LINE, 'truncated/oversized journal')
            self.feed(chunk[:end+1])
            offset += end+1
        self.eof()
