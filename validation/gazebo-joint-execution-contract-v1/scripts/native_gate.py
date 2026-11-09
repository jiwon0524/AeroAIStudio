"""Native event adapter for the existing ACK session; contains no launch code."""
from collections import Counter

class NativeSession:
    def __init__(self, expected, schema_closure, ack_session):
        self.expected = expected
        self.closure = set(schema_closure)
        self.session = ack_session
        self.seq = 0
        self.counts = Counter()
        self.complete = self.failed = self.go = False

    def __getattr__(self, name):
        return getattr(self.session, name)

    def require(self, ok, reason):
        if not ok:
            self.failed = True
            raise ValueError(reason)

    def packet(self, row):
        self.require(not self.failed, 'native resource failure latched')
        try:
            if row.get('kind') != 'native_resource':
                if row.get('kind') in ('ready_state', 'fixture_ready'):
                    self.require(self.complete, 'native closure missing before ready')
                return self.session.packet(row)
            self.require(not self.complete and not self.go, 'late native access/load/fatal')
            self.require(set(row) == {'kind','seq','role','sha256','device','inode','ok'}, 'native fields')
            self.require(type(row['seq']) is int and row['seq'] == self.seq+1, 'native sequence gap')
            self.require(type(row['device']) is int and type(row['inode']) is int, 'noninteger FD identity')
            self.require(row['ok'] is True, 'native open/parse/load/late request failed')
            self.seq += 1
            role = row['role']
            if role in self.expected:
                self.require((row['sha256'],row['device'],row['inode']) == tuple(self.expected[role]), 'selected FD/provider/world identity mismatch')
            else:
                self.require(role in {'schema_init','schema_include','schema_root','conversion','server_config_parse','world_parse','world_graph','physics_loaded','dartsim_loaded','complete'}, 'unknown native role')
                self.require((row['sha256'], row['device'], row['inode']) == ('',0,0), 'outcome fields')
            self.counts[role] += 1
            if role == 'complete':
                self.require(self.closure <= self.counts.keys(), 'required recursive schema observation missing')
                for required in ('world_bytes','schema_root','server_config','server_config_parse','world_parse','world_graph','physics','physics_provider','physics_loaded','dartsim','dartsim_provider','dartsim_loaded','conversion/1_10.convert','conversion'):
                    self.require(self.counts[required] == 1, 'missing/duplicate required outcome '+required)
                reads = sum(v for k,v in self.counts.items() if k.startswith('schema/'))
                self.require(self.counts['schema_init'] >= 1 and self.counts['schema_include'] >= 1, 'incomplete schema result closure')
                self.complete = True
        except Exception:
            self.failed = True
            raise

    def authorize(self):
        self.require(not self.failed and self.complete and not self.go, 'native GO precondition')
        self.go = True
        try:
            return self.session.authorize()
        except Exception:
            self.failed = True
            raise

    def stderr(self, line):
        self.require(not self.failed, 'native failure latched')
        try:
            return self.session.stderr(line)
        except Exception:
            self.failed = True
            raise

    def finalize(self, *args):
        self.require(self.go and self.complete and not self.failed, 'native final precondition')
        try:
            return self.session.finalize(*args)
        except Exception:
            self.failed = True
            raise
