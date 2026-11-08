"""Strict GO-to-exit state machine; pure policy plus explicit supervisor callbacks."""
from common import *
import math,re
class Lines:
 def __init__(self,total,buffer):self.total=total;self.buffer=buffer;self.count=0;self.pending=b'';self.eof=False
 def feed(self,data):
  need(not self.eof,'data after EOF');self.count+=len(data);need(self.count<=self.total,'cumulative output exceeded');out=[]
  self.pending+=data
  while b'\n' in self.pending:
   row,self.pending=self.pending.split(b'\n',1);need(len(row)<=self.buffer,'line buffer exceeded');out.append(row)
  need(len(self.pending)<=self.buffer,'pending buffer exceeded');return out
 def finish(self):need(not self.pending,'truncated output at EOF');self.eof=True

def world_line(line):
 if not line.startswith('AERO_WORLD '):return None
 pairs=dict(x.split('=',1) for x in line.split()[1:]);need(set(pairs)=={'entity','world','solver','detector','init','iteration','sim_time','native_frame','native_time'},'world evidence schema')
 need(all(pairs[k]=='0' for k in ('iteration','sim_time','native_frame','native_time')) and pairs['init']=='1','world zero/init changed')
 for k in ('world','solver','detector'):need(int(pairs[k],16)>0,'missing native pointer')
 return pairs

class Session:
 def __init__(self,contract,attest,send_go):
  self.contract=contract;self.attest=attest;self.send_go=send_go;self.ready=[];self.worlds=[];self.engine=None;self.typed=[];self.fingerprints=[];self.sent=False;self.samples=[];self.finished=False
 def stderr(self,line):
  row=world_line(line)
  if row:
   if len(self.worlds)>=2:need(row==self.worlds[0],'native world/solver/detector changed')
   self.worlds.append(row)
 def packet(self,row):
  need(not self.finished,'packet after finalization');need(isinstance(row,dict),'packet object missing');kind=row.get('kind')
  if kind=='engine_entry':
   if self.sent:need(row==self.fingerprints[0][0],'post-GO engine changed')
   self.engine=row;self.typed=[]
  elif kind=='typed':
   if self.sent:need(row in self.fingerprints[0][1],'post-GO provider changed')
   self.typed.append(row)
  elif kind=='ready_state':
   need(not self.sent and len(self.ready)<2 and self.engine is not None,'unexpected/missing ready evidence')
   need(type(row.get('native_frame')) is int and row['native_frame']==0 and type(row.get('native_time')) in (int,float) and row['native_time']==0 and type(row.get('init_count')) is int and row['init_count']==1,'native zero/init')
   self.ready.append(row);self.fingerprints.append((self.engine,self.typed[:]))
  elif kind=='sample':
   need(self.sent,'sample before GO');need(len(self.samples)<100,'101st sample');i=len(self.samples)+1
   need(type(row.get('native_frame')) is int and row['native_frame']==i and type(row.get('native_time')) in (int,float) and math.isfinite(row['native_time']) and abs(row['native_time']-i*.001)<=1e-12 and row.get('init_count')==1,'native post-GO counter/init')
   self.samples.append(row)
   if len(self.samples)==100:policy.validate_run(self.samples)
  else:raise ValueError('unexpected packet '+str(kind))
 def authorize(self):
  need(not self.sent,'duplicate GO');need(len(self.ready)==2 and len(self.worlds)>=2,'two ready/world observations required')
  need(self.ready[0]==self.ready[1] and self.worlds[0]==self.worlds[1] and self.fingerprints[0]==self.fingerprints[1],'pre-GO state/provider/world changed')
  need({x['label'] for x in self.fingerprints[0][1]}=={'dart/ode/getType','gz/ode/getType'},'only active ODE accepted')
  need(all(x['base']==self.worlds[0]['detector'] for x in self.fingerprints[0][1]),'world detector/base mismatch')
  snapshots=[self.attest(raw,self.fingerprints[i]) for i,raw in enumerate(self.ready)]
  gate=policy.Gate(self.contract);token=gate.authorize(snapshots);need(token=='GO\n','GO token')
  self.sent=True;self.send_go(token.encode('ascii'))
 def finalize(self,stdout_eof,stderr_eof,returncode,cleanup,integrity,mapping_final):
  need(self.sent and not self.finished,'missing GO/already finalized');need(stdout_eof and stderr_eof,'EOF missing')
  need(returncode==0,'nonzero exit');policy.validate_run(self.samples)
  need(cleanup is True and integrity is True and mapping_final is True,'cleanup/integrity/final mapping missing')
  self.finished=True;return {'status':'PASS','samples':100,'sim_time_ns':100000000}
