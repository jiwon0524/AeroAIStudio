from common import *
from elf_tables import Elf
import re
selected={};scan={}
for arm,p in libs().items():
 if arm in ['Bullet','Gazebo']:
  full=run(['objdump','-d','-C','--no-show-raw-insn',p]);(R/f'work/{arm}.disassembly').write_text(full['stdout']);text=full['stdout']
  fs=re.split(r'(?=^[0-9a-f]+ <)',text,flags=re.M)
  scan[arm]=dict(indirect_calls=sum(bool(re.search(r'\bcall\s+\*',l)) for l in text.splitlines()),dynamic_cast_sites=[l.strip() for l in text.splitlines() if re.search(r'\bcall.*<__dynamic_cast',l)],memory_displacements='Candidate memory operands only; full object/register provenance not recovered')
  patterns=['BulletCollisionObject::getBulletCollisionObject','BulletCollisionObject::BulletCollisionObject','BulletCollisionObject::updateEngineData','BulletCollisionDetector::createCollisionObject','BulletCollisionDetector::create()','BulletCollisionGroup::BulletCollisionGroup','GetContactsFromLastStep','SimulationFeatures::convertContact']
  selected[arm]={f.splitlines()[0]:f for f in fs if f and any(k in f.splitlines()[0] for k in patterns) and '@plt>' not in f.splitlines()[0] and (arm!='Gazebo' or re.search(r'::(?:GetContactsFromLastStep|convertContact)\(',f.splitlines()[0]))}
 else:
  e=Elf(p);selected[arm]={}
  for n,s in e.syms.items():
   if s['section']=='UND' or s['type']!='FUNC':continue
   if any(k in n for k in ['CollisionObject13getShapeFrame','CollisionObject20getCollisionDetector','CollisionObjectC2','CollisionResult10getContact','CollisionResult14getNumContacts']):
    d=run(['objdump','-d','-C','--no-show-raw-insn','--start-address='+hex(s['address']),'--stop-address='+hex(s['address']+s['size']),p])['stdout'];selected[arm][n]=d
# Compilation creates no executable; comparing fresh code from three header sets.
fixture={a:(R/f'work/{a}/boundary.disassembly').read_text() for a in ['A','B','C']}
def norm(s):
 return '\n'.join(l for l in s.splitlines() if not l.endswith('file format elf64-x86-64'))
save('inline_access.json',dict(installed_disassembly=selected,consumer_scan=scan,fixture_code={a:dict(path=str(R/f'work/{a}/boundary.disassembly'),sha256=sha(R/f'work/{a}/boundary.o')) for a in fixture},fixture_disassembly_equal={a:norm(fixture['A'])==norm(fixture[a]) for a in ['B','C']},evidence_level='Installed getters and Bullet functions provide selected binary offset/call evidence. Gazebo scan candidates are not exhaustive source-level inline provenance.',limits=['Cannot map every optimized memory operand to a DART member without debug','Matching fixture code proves only current compiler/header recipe','No getter, cast, ctor, plugin or collision function was executed']))
print('selected',{a:len(v) for a,v in selected.items()})
