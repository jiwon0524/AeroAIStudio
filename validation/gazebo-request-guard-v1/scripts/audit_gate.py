"""Offline adapter: accepts only a future authenticated supervisor transport.
No launcher, ptrace operation, target process or service is created here.
Identity/authentication and OS lifetime evidence MUST come from that adapter;
Python dictionaries alone do not authenticate a sender. No adapter is released.
"""
import json

def exact(a, b):
    return json.dumps(a,sort_keys=True,allow_nan=False)==json.dumps(b,sort_keys=True,allow_nan=False)

class AuditGate:
    def __init__(self, session, binding, persist):
        self.session, self.binding, self.persist = session, dict(binding), persist
        self.seq = 0
        self.started = self.dead = self.complete = self.closed = False
        self.failed = self.go = self.broken = False
        self.denied = 0

    def need(self, ok, reason):
        if not ok:
            self.failed = True
            raise ValueError(reason)

    def event(self, row, *, authenticated=False):
        self.need(not self.broken, 'audit transport failure latched')
        try:
            self.need(authenticated is True, 'untrusted audit channel')
            self.need(not self.closed and not self.complete, 'late audit record')
            self.need(set(row)=={'seq','kind','binding','payload'}, 'audit fields')
            self.need(type(row['seq']) is int and row['seq']==self.seq+1, 'audit sequence loss/replay')
            self.need(row['binding']==self.binding, 'run/policy/source identity mismatch')
            kind, data = row['kind'], row['payload']
            self.need(kind in {'start','denial','all_dead','complete'}, 'unknown/loss/overflow record')
            if kind=='start':
                self.need(not self.started and self.seq==0, 'duplicate/missing start')
                self.need(exact(data,{'pre_loader':True,'fd_attested':True,'policy_applied':True,
                                 'journal_private':True,'lifetime_tracking':True}), 'incomplete application evidence')
                self.started=True
            else:
                self.need(self.started, 'missing start')
                if kind=='denial':
                    self.need(not self.dead, 'denial after final task death')
                    self.denied+=1
                elif kind=='all_dead':
                    self.need(not self.dead and exact(data,{'live_tasks':0,'wait_echild':True}), 'missing descendant death evidence')
                    self.dead=True
                elif kind=='complete':
                    self.need(self.dead and exact(data,{'denied':self.denied,'lost':0,'pending':0}), 'incomplete final audit')
                    self.complete=True
            # Persist synchronously before accepting GO or any terminal receipt.
            self.need(self.persist(row) is True, 'journal write/sync/overflow failure')
            self.seq+=1
            if self.denied:
                self.failed=True  # Verdict fails; independent audit must keep draining.
        except Exception:
            self.failed=self.broken=True
            raise

    def eof(self):
        self.need(not self.broken and self.complete and not self.closed, 'early/duplicate audit disconnect')
        self.closed=True

    def authorize(self):
        self.need(not self.failed and self.started and not self.closed and not self.go, 'GO lacks audit application evidence')
        try:
            result=self.session.authorize()
            self.go=True
            return result
        except Exception:
            self.failed=True
            raise

    def packet(self, row):
        self.need(not self.failed and self.started and not self.dead, 'native packet outside monitored lifetime')
        try: return self.session.packet(row)
        except Exception:
            self.failed=True
            raise

    def stderr(self, line):
        self.need(not self.failed and self.started and not self.dead, 'stderr outside monitored lifetime')
        try: return self.session.stderr(line)
        except Exception:
            self.failed=True
            raise

    def finalize(self, *args):
        self.need(not self.failed and self.go and self.complete and self.closed and self.dead,
                  'missing independent final audit evidence')
        try: return self.session.finalize(*args)
        except Exception:
            self.failed=True
            raise
