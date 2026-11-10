"""Bounded framing/demultiplexing for PRIVATE owner channel; not authentication.
OS peer/FD ownership is required outside this parser and currently not wired.
Never feed target stdout/stderr here. Two sequence spaces are explicitly tagged.
"""
import json

def unique(pairs):
    row={}
    for k,v in pairs:
        if k in row:raise ValueError('duplicate audit JSON key')
        row[k]=v
    return row

def nonfinite(value):raise ValueError('nonfinite audit JSON value')

class AuditChannel:
    MAX_LINE=4096
    MAX_TOTAL=1048576
    KINDS={
        'lifecycle':{'private_channel','preexec_stop','ptrace_armed','filter_listener_bound','exec_stop',
            'task_born','request','denial','input_prepared','replied_denied','input_delivered',
            'transport_failure','task_dead','all_dead'},
        'gate':{'start','denial','all_dead','complete'}}
    def __init__(self,binding,consume,fail):
        self.binding=dict(binding);self.consume=consume;self.fail=fail
        self.seq={'lifecycle':0,'gate':0};self.buffer=b'';self.total=0
        self.closed=self.broken=False;self.dead=self.complete=False
    def need(self,yes,reason):
        if not yes:raise ValueError(reason)
    def feed(self,chunk):
        try:
            self.need(not self.closed and not self.broken,'channel already closed/broken')
            self.need(type(chunk) is bytes,'channel byte framing')
            self.total+=len(chunk);self.need(self.total<=self.MAX_TOTAL,'audit overflow')
            self.buffer+=chunk
            while b'\n' in self.buffer:
                line,self.buffer=self.buffer.split(b'\n',1)
                self.need(len(line)<=self.MAX_LINE,'audit line overflow')
                row=json.loads(line,object_pairs_hook=unique,parse_constant=nonfinite)
                self.need(type(row) is dict and set(row)=={'stream','seq','kind','binding','payload'},'audit schema')
                stream=row['stream'];self.need(stream in self.seq,'unknown audit stream')
                self.need(type(row['seq']) is int and row['seq']==self.seq[stream]+1,'audit loss/replay')
                self.need(json.dumps(row['binding'],sort_keys=True,allow_nan=False)==
                          json.dumps(self.binding,sort_keys=True,allow_nan=False),'audit run/policy/source binding')
                self.need(row['kind'] in self.KINDS[stream],'unknown/loss audit record')
                self.need(not self.complete,'record after final audit completion')
                if stream=='lifecycle' and row['kind']=='all_dead':self.dead=True
                if stream=='gate' and row['kind']=='complete':
                    self.need(self.dead,'audit complete before death');self.complete=True
                self.consume(row);self.seq[stream]+=1
            self.need(len(self.buffer)<=self.MAX_LINE,'partial audit line overflow')
        except Exception as e:
            self.broken=True;self.fail(str(e));raise
    def eof(self):
        try:
            self.need(not self.closed and not self.broken and not self.buffer and self.complete,
                      'early/duplicate/truncated audit EOF')
            self.closed=True
        except Exception as e:
            self.broken=True;self.fail(str(e));raise
