"""Bounded LSDA call-site/action decoder; never executes throw/catch/cleanup."""
from common import *
from elf_reader import Elf
from eh_reader import Cursor,eh_records

def parse_lsda(data,address,function_start):
 c=Cursor(data,address);enc=c.byte();lpbase=function_start if enc==255 else c.ptr(enc)['value'];type_enc=c.byte();type_table=None
 if type_enc!=255:off=c.leb();type_table=c.base+c.i+off
 site_enc=c.byte();length=c.leb();stop=c.i+length
 if stop>len(data):raise ValueError('LSDA call-site table exceeds buffer')
 sites=[]
 while c.i<stop:
  start=c.ptr(site_enc)['value'];length=c.ptr(site_enc)['value'];lp=c.ptr(site_enc)['value'];action=c.leb()
  if c.i>stop:raise ValueError('LSDA call-site record overrun')
  sites.append(dict(start=lpbase+start,end=lpbase+start+length,landing_pad=lpbase+lp if lp else None,action_offset=action))
 actions_start=stop
 for site in sites:
  records=[];seen=set();pos=actions_start+site['action_offset']-1 if site['action_offset'] else None
  while pos is not None:
   if pos in seen:raise ValueError('cyclic LSDA action chain')
   if not 0<=pos<len(data):raise ValueError('LSDA action outside buffer')
   if len(records)>=32:raise ValueError('LSDA action chain limit')
   seen.add(pos);a=Cursor(data,address);a.i=pos;filter_value=a.leb(True);next_field=a.i;disp=a.leb(True)
   records.append(dict(address=hex(address+pos),filter=filter_value,next_displacement=disp,meaning='CLEANUP' if filter_value==0 else 'TYPE_FILTER' if filter_value>0 else 'EXCEPTION_SPEC_UNKNOWN'))
   pos=next_field+disp if disp else None
  site['actions']=records;site['classification']='NO_LANDING_PAD' if site['landing_pad'] is None else 'CLEANUP_ONLY' if site['action_offset']==0 or all(x['filter']==0 for x in records) else 'ACTION_CHAIN_PRESENT'
 return dict(address=hex(address),LPStart=lpbase,type_encoding=type_enc,type_table=hex(type_table) if type_table else None,callsite_encoding=site_enc,sites=sites,limits='Type filter numbers decoded; typeinfo and complete catch/action semantics not certified')

def cleanup_for(e,fde):
 if not fde or not fde['lsda'] or not fde['lsda']['value']:return dict(status='NO_LSDA_IN_SELECTED_FDE',sites=[],limits='Does not prove no throw/terminate or equivalent unwinding')
 addr=fde['lsda']['value'];sec=next((s for s in e.sections if s[2]&2 and s[3]<=addr<s[3]+s[5]),None)
 if not sec:raise ValueError('LSDA pointer outside allocated sections')
 # Limit parser input to actual section tail; record lengths further bound access.
 data=e.read(addr,sec[3]+sec[5]-addr);out=parse_lsda(data,addr,fde['start']);out['status']='DECODED_STATIC'
 for site in out['sites']:
  if site['landing_pad']:
   start=site['landing_pad'];bounds=[f for f in eh_records(e)[1] if f['start']<=start<f['end']];end=min(start+128,bounds[0]['end']) if bounds else start;site['landing_bound']='FDE' if bounds else 'UNKNOWN';text=run(['objdump','-d','-C','--no-show-raw-insn','--start-address='+hex(start),'--stop-address='+hex(end),e.path])['stdout'];p=R/f'work/{e.path.name}-{start:x}-landing.asm';p.write_text(text);site['landing_disassembly_path']=str(p);site['landing_excerpt']=text
 return out
