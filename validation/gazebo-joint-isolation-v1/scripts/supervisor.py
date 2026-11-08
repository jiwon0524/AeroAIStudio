"""One-shot joint supervisor. Current pinned plan rejects before marker/service.
Only --execute-approved-joint-once reaches this future runtime path.
"""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import *
from plan import read_plan,runtime_ready
from live import smoke,service_argv,owned_stop,cleanup_ok,Attestor
from protocol import Lines,Session
from integrity import capture
import os,selectors,time,subprocess,uuid

def absent(paths):
 for p in paths:
  path=Path(p);need(not os.path.lexists(path),'existing output/one-shot '+str(path))
  # Reject symlink ancestors, even dangling ones, before any filesystem change.
  for parent in path.parents:need(not parent.is_symlink(),'symlink output ancestor '+str(parent))

def exclusive(paths,record):
 for p in paths:
  fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
  with os.fdopen(fd,'w') as f:json.dump(record,f)

def run(risk):
 plan=read_plan();runtime_ready(plan,risk) # Must precede manager queries/marker/service.
 need(subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()=='experiment/dart-internal-trace','branch')
 outputs=[B/p for p in plan['outputs']];markers=[B/p for p in plan['one_shot']];absent(outputs+markers)
 before_integrity=capture(plan);manager=smoke.properties(manager=True);need(manager['rc']==0 and manager['values'].get('SystemState')=='running','manager unavailable')
 managerpath=manager['values']['ControlGroup'];unit='aero-joint-once-'+uuid.uuid4().hex+'.service';rel=managerpath+'/app.slice/'+unit;target=smoke.CG/rel.lstrip('/')
 need(smoke.properties(unit)['values'].get('LoadState')=='not-found' and not target.exists(),'unit collision');controllers=smoke.snapshot(managerpath)
 payload=['/usr/bin/python3','-I','-B',str(B/'scripts/stage.py'),'--owned-joint-stage',rel,risk]
 command=service_argv(unit,payload);exclusive(markers,{'unit':unit,'no_retry':True,'plan_sha256':sha(B/'reports/plan.json')});outputs[0].mkdir(mode=0o700)
 integrity_fd=os.open(outputs[1],os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 p=None;saved=None;identities=[];session=None;verdict={'status':'FAIL','unit':unit,'go_sent':False};att=None;final_mapping=False
 started=time.monotonic();observation_deadline=started+25;host_deadline=started+40
 streams={name:Lines(65536 if name=='stdout' else 1048576,16384 if name=='stdout' else 65536) for name in ('stdout','stderr')};logs={};selector=selectors.DefaultSelector()
 try:
  for name in streams:logs[name]=(outputs[0]/(name+'.raw')).open('xb')
  p=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env={'PATH':'/usr/bin:/bin','LC_ALL':'C','XDG_RUNTIME_DIR':'/run/user/'+str(os.getuid())})
  for name in streams:
   fd=getattr(p,name).fileno();os.set_blocking(fd,False);selector.register(fd,selectors.EVENT_READ,name)
  packets=[];worlds=[]
  while selector.get_map() or p.poll() is None:
   need(time.monotonic()<host_deadline and time.monotonic()<observation_deadline,'collection/exit timeout')
   props=smoke.properties(unit)
   if props['rc']==0 and props['values'].get('ActiveState')=='active':
    state=props['values'];need(state.get('Id')==unit and state.get('ControlGroup')==rel and bool(state.get('InvocationID')),'unit identity')
    if saved is None:saved=state
    else:need(state['InvocationID']==saved['InvocationID'],'unit invocation changed')
    current=[smoke.identity(int(x)) for x in (smoke.read(target/'cgroup.procs') or '').split()]
    for ident in current:
     need(ident and ident['cgroup']=='0::'+rel,'process outside own cgroup')
     if not any(x['pid']==ident['pid'] and x['start']==ident['start'] for x in identities):identities.append(ident)
    if att is None:
     expected=plan['candidate_elfs'][plan['payload'][1]];matches=[]
     for ident in current:
      try:st=os.stat('/proc/'+str(ident['pid'])+'/exe')
      except OSError:continue
      if (st.st_dev,st.st_ino)==(expected['device'],expected['inode']):matches.append(ident)
     need(len(matches)<=1,'multiple harness processes')
     if matches:
      ident=matches[0];g=os.fstat(p.stdin.fileno());o=os.fstat(p.stdout.fileno());att=Attestor(plan,ident['pid'],ident['start'],rel,(g.st_dev,g.st_ino),(o.st_dev,o.st_ino))
      def send(data):
       need(data==b'GO\n' and not verdict['go_sent'],'duplicate/wrong GO');verdict['go_sent']=True;p.stdin.write(data);p.stdin.flush();p.stdin.close()
      session=Session(att.c,att.ready,send)
   for key,_ in selector.select(.02):
    name=key.data;chunk=os.read(key.fd,8192)
    if not chunk:streams[name].finish();selector.unregister(key.fd);continue
    logs[name].write(chunk)
    for line in streams[name].feed(chunk):
     if name=='stdout':packets.append(json.loads(line))
     else:
      text=line.decode('utf-8',errors='strict')
      if text.startswith('AERO_WORLD '):worlds.append(text)
      need(not any(s in text.lower() for s in ('double free','corrupted','bad_alloc','terminate called','addresssanitizer','runtime error:')),'allocator/exception diagnostic')
   if session:
    for line in worlds:session.stderr(line)
    worlds.clear()
    for packet in packets:
     session.packet(packet)
     if packet.get('kind')=='sample':att.mappings();final_mapping=len(session.samples)==100
    packets.clear()
    if not session.sent and len(session.ready)==2 and len(session.worlds)>=2:
     diff=smoke.differences(controllers,smoke.snapshot(managerpath),rel.lstrip('/'));need(all(x['expected'] for x in diff),'unexpected controller change');session.authorize()
    if session.sent and p.poll() is None:att.mappings()
  rc=p.wait(timeout=max(.01,min(2,host_deadline-time.monotonic())));verdict['returncode']=rc
 except Exception as e:verdict['error']=str(e)
 finally:
  selector.close()
  if p and p.stdin and not p.stdin.closed:p.stdin.close()
  if p and p.poll() is None:
   try:p.wait(timeout=2)
   except subprocess.TimeoutExpired:
    now=smoke.properties(unit)['values']
    if saved:
     try:
      stop=owned_stop(saved,now,[(x,smoke.identity(x['pid'])) for x in identities]);smoke.cmd(stop,timeout=2)
     except Exception as e:verdict['owned_stop_refused']=str(e)
    try:p.wait(timeout=2)
    except subprocess.TimeoutExpired:verdict['reap_failed']=True
  deadline=min(host_deadline,time.monotonic()+2)
  final=smoke.properties(unit)['values']
  while time.monotonic()<deadline and (final.get('LoadState')!='not-found' or target.exists()):
   time.sleep(.02);final=smoke.properties(unit)['values']
  remaining=[];cleanup_unknown=False
  for ident in identities:
   try:os.stat('/proc/'+str(ident['pid']))
   except FileNotFoundError:continue
   except OSError:cleanup_unknown=True;continue
   now=smoke.identity(ident['pid'])
   if now is None:cleanup_unknown=True
   elif now['start']==ident['start']:remaining.append(ident)
  after_diff=smoke.differences(controllers,smoke.snapshot(managerpath),'NO_OWN_PATH');clean=not cleanup_unknown and cleanup_ok(final,target.exists(),remaining,after_diff)
  for f in logs.values():f.close()
  try:intact=capture(plan)==before_integrity
  except Exception as e:intact=False;verdict['integrity_error']=str(e)
  verdict.update(cleanup=clean,cleanup_visibility_unknown=cleanup_unknown,original_integrity=intact,remaining=remaining,controller_diff=after_diff,saved_unit=saved,final_unit=final,cgroup_removed=not target.exists(),observed_process_identities=identities,elapsed_seconds=time.monotonic()-started)
  if session:
   verdict.update(pre_go_evidence=att.ready_evidence,world_observations=session.worlds,samples=session.samples,last_mapping=att.last_mapping,stdout_eof=streams['stdout'].eof,stderr_eof=streams['stderr'].eof,stream_bytes={name:stream.count for name,stream in streams.items()})
  if session and not verdict.get('error'):
   try:verdict.update(session.finalize(streams['stdout'].eof,streams['stderr'].eof,p.returncode,clean,intact,final_mapping))
   except Exception as e:verdict['error']=str(e)
  with os.fdopen(integrity_fd,'w') as f:json.dump({'before':before_integrity,'after_matches':intact},f,indent=2)
  with (outputs[0]/'result.json').open('x') as f:json.dump(verdict,f,indent=2)
 return 0 if verdict['status']=='PASS' else 1
if __name__=='__main__':
 try:
  if sys.argv[1:]==['--preflight']:
   plan=read_plan();from plan import validate
   validate(plan);print(json.dumps({'status':'BLOCKED','blockers':plan['blockers'],'risk_acceptance':'UNDECIDED','stage_b':'BLOCKED','side_effects':'none'},indent=2));raise SystemExit(78)
  need(sys.argv[1:] and sys.argv[1]=='--execute-approved-joint-once' and len(sys.argv)==3,'explicit execution flag and risk decision required')
  raise SystemExit(run(sys.argv[2]))
 except Exception as e:print('joint supervisor refused before launch: '+str(e),file=sys.stderr);raise SystemExit(78)
