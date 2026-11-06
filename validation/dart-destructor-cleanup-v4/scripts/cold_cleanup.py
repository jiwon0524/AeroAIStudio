"""Follow one direct landing-pad jump into its bounded cold FDE, then stop."""
from common import *
from elf_reader import Elf
from eh_reader import eh_records
import re
p=R/'reports/exception_cleanup.json';d=json.loads(p.read_text());e=Elf(libs()['Bullet']);fs=eh_records(e)[1];cache={}
for site in d['Bullet_factory']['sites']:
 if not site['landing_pad']:continue
 m=re.search(r'\bjmp\s+([0-9a-f]+)',site.get('landing_excerpt',''))
 if not m:site['cold_followup']='NO_DIRECT_JUMP';continue
 target=int(m[1],16);f=next((f for f in fs if f['start']<=target<f['end']),None)
 if not f:site['cold_followup']='NO_FDE_BOUNDARY';continue
 if f['start'] not in cache:
  text=run(['objdump','-d','-C','--no-show-raw-insn','--start-address='+hex(f['start']),'--stop-address='+hex(f['end']),e.path])['stdout'];out=R/f'work/Bullet-cold-{f["start"]:x}.asm';out.write_text(text);cache[f['start']]=dict(start=hex(f['start']),end=hex(f['end']),path=str(out),disassembly=text)
 site['cold_followup']=dict(entry=hex(target),**cache[f['start']],limits='One cold FDE only; local shared release/deleter dynamic behavior remains UNKNOWN')
d['personality_facilities']={}
for arm in ['A','B','C','Bullet']:
 lib=Elf(libs()[arm]);cies,_=eh_records(lib);rows=[]
 for cie in cies.values():
  ptr=cie['personality'];record=dict(augmentation=cie['augmentation'],personality=ptr)
  if ptr and ptr['indirect']:
   try:record['indirect_target']=lib.pointer(ptr['value'])
   except ValueError:record['indirect_target']='UNKNOWN'
  rows.append(record)
 d['personality_facilities'][arm]=rows
d['followup_stop']='C after one cold FDE per LP target; no recursive chase of arbitrary indirect cleanup';save('exception_cleanup.json',d);print('cold FDEs',len(cache))
