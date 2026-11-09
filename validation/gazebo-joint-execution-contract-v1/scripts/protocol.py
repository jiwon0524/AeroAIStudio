"""Shared two-token exit barrier for real and harmless collection paths."""
from common import *
base=load('prior_joint_protocol','validation/gazebo-joint-isolation-v1/scripts/protocol.py')
Lines=base.Lines
class AckWindow:
 def __init__(self,write,observe,start,pid):self.write=write;self.observe=observe;self.start=start;self.pid=pid;self.go=False;self.ack=False;self.waiting=False;self.snapshot=None
 def send_go(self,check):
  need(not self.go,'duplicate GO');check();self.go=True;self.write(b'GO\n')
 def final_wait(self,row,count):
  need(self.go and not self.ack and not self.waiting and count==100,'unexpected final barrier')
  need(row=={'kind':'final_wait','iteration':100,'sim_time_ns':100000000},'bad final boundary');self.waiting=True
 def send_ack(self):
  need(self.go and self.waiting and not self.ack,'missing final barrier/duplicate ACK')
  observed=self.observe();need(observed.get('status')=='PASS_FILE_IDENTITY' and observed.get('start')==self.start and observed.get('pid')==self.pid,'final mapping/PID/start mismatch')
  self.snapshot=observed;self.ack=True;self.write(b'EXIT_ACK\n')
 def finish(self,stdout_eof,stderr_eof,rc):need(self.go and self.ack and self.snapshot and stdout_eof and stderr_eof and rc==0,'ACK/EOF/exit evidence missing')
class AckSession(base.Session):
 def __init__(self,contract,attest,window):
  self.window=window
  super().__init__(contract,attest,lambda data:window.send_go(lambda:need(data==b'GO\n','GO token')))
 def packet(self,row):
  if row.get('kind')=='final_wait':self.window.final_wait(row,len(self.samples));return
  need(not self.window.waiting or row.get('kind') not in ('sample','ready_state'),'data after final sample');super().packet(row)
 def finalize(self,out_eof,err_eof,rc,cleanup,integrity,mapping_final):
  self.window.finish(out_eof,err_eof,rc)
  return super().finalize(out_eof,err_eof,rc,cleanup,integrity,mapping_final)
class HarmlessSession:
 def __init__(self,window,initial):self.window=window;self.initial=initial;self.ready=[];self.samples=[]
 def stderr(self,line):pass
 def packet(self,row):
  kind=row.get('kind')
  if kind=='fixture_ready':
   need(not self.window.go and len(self.ready)<2 and row=={'kind':'fixture_ready','iteration':0,'sim_time_ns':0},'fixture ready');self.ready.append(row)
  elif kind=='fixture_sample':
   need(self.window.go and not self.window.waiting and len(self.samples)<100,'unexpected fixture sample')
   i=len(self.samples)+1;need(row=={'kind':'fixture_sample','iteration':i,'sim_time_ns':i*1000000},'fixture sequence');self.samples.append(row)
  elif kind=='final_wait':self.window.final_wait(row,len(self.samples))
  else:raise ValueError('unexpected fixture packet')
 def authorize(self):need(len(self.ready)==2 and self.ready[0]==self.ready[1],'fixture ready evidence');self.window.send_go(self.initial)
 def finalize(self,out_eof,err_eof,rc,cleanup,integrity,mapping_final):
  self.window.finish(out_eof,err_eof,rc);need(len(self.samples)==100 and cleanup is True and integrity is True and mapping_final is True,'fixture completion evidence')
  return {'status':'PASS_ISOLATION_PATH_ONLY','samples':100,'physical_steps':0}
