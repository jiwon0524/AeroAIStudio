from common import *
from elf_reader import *
import re
VT='_ZTVN4dart8dynamics9ShapeNodeE'
d=json.loads((R/'reports/shapenode_slots.json').read_text());es={a:Elf(libs()[a]) for a in ['A','B','C']};debug={}
for a in ['B','C']:
 addresses=sorted({r['arms'][a]['address'] for r in d['slots']});p=run(['addr2line','-f','-C','-e',libs()[a],*map(hex,addresses)]);lines=p['stdout'].splitlines();assert p['rc']==0 and len(lines)==2*len(addresses);debug[a]={addr:dict(function=lines[2*i],source=lines[2*i+1]) for i,addr in enumerate(addresses)}
for r in d['slots']:
 for a,v in r['arms'].items():
  e=es[a];at=e.sym(VT)['address']+r['abi_byte_offset'];v.update(entry_virtual_address=hex(at),raw_entry_bytes=e.read(at,8).hex(),entry_relocation=e.reloc.get(at),target_binding=sorted({x['binding'] for x in v['aliases']}) or 'UNKNOWN',target_visibility=sorted({x['visibility'] for x in v['aliases']}) or 'UNKNOWN')
  if a in debug:v['DWARF_addr2line']=debug[a][v['address']]
 r['A_B_call_ABI']='COMPATIBLE_WITH_LIMITATIONS: current instruction/offset/call pattern evidence, exact installed type signature unavailable' if r['identity_status']=='INFERRED' else 'UNKNOWN'
 r['B_C_identity']='IDENTIFIED_SAME_LOCAL_SYMBOL';r['B_C_implementation']='NORMALIZED_CODE_MATCH' if r['B_C_normalized_code_equal'] else 'IMPLEMENTATION_OR_OPTIMIZATION_DIFFERENT; not ABI mismatch by itself'
d['binding_legend']={0:'LOCAL',1:'GLOBAL',2:'WEAK'};d['visibility_legend']={0:'DEFAULT',1:'INTERNAL',2:'HIDDEN',3:'PROTECTED'};d['evidence_sources']=[str(V2/'reports/vtable_rtti.json'),str(V2/'reports/boundary_fixture.json')];save('shapenode_slots.json',d)
# Reconcile old prepublish state without changing it or calling it a helper MATCH.
text=(R.parents[1]/'handoff.md').read_text();st=json.loads(re.search(r'```context-handoff-state\n(.*?)\n```',text,re.S).group(1));head=run(['git','rev-parse','HEAD'])['stdout'].strip();parent=run(['git','rev-parse','HEAD^'])['stdout'].strip()
save('handoff_reconciliation.json',dict(initial_helper='REVIEW_REQUIRED only GIT_CHANGED/head',recorded_head=st['git']['head'],observed_head=head,parent=parent,parent_matches_record=parent==st['git']['head'],evidence=[dict(path=x['path'],matches=sha(R.parents[1]/x['path'])==x['sha256']) for x in st['evidence']],publication_files=run(['git','show','--pretty=format:','--name-only',head])['stdout'].splitlines(),scope='V2 checkpoint before V3 handoff replacement'))
print('DWARF sources', {a:sum(not x['source'].startswith('??') for x in rows.values()) for a,rows in debug.items()})
