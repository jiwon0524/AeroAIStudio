"""Offline static parser/contract tests; no load, construction, destruction or physics."""
import sys,json,struct,subprocess,re
from pathlib import Path
import pytest
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'scripts'))
from elf_reader import Elf,variant,frames
from exception_tables import Cursor,eh_records
from common import libs,V2

def load(n):return json.loads((R/'reports'/n).read_text())
def test_reproduce_exact_V2_67_and_current_pointer_words():
 d=load('shapenode_slots.json');old=json.loads((V2/'reports/vtable_rtti.json').read_text())
 assert d['V2_unknown_indices']==old['core_comparison']['B'][d['vtable']]['unknown_slots']
 assert len(d['slots'])==67
 for arm in ['A','B','C']:
  e=Elf(libs()[arm]);t=e.table(d['vtable'])
  for r in d['slots']:assert t[r['slot_index']]['address']==r['arms'][arm]['address']
def test_installed_identity_never_promoted_from_inference():
 d=load('shapenode_slots.json');assert sum(d['counts'].values())==67
 for r in d['slots']:
  assert r['arms']['B']['identity_status']==r['arms']['C']['identity_status']=='IDENTIFIED'
  assert r['arms']['B']['identity']==r['arms']['C']['identity']
  assert r['identity_status'] in ['INFERRED','UNRESOLVED']
  if r['identity_status']=='INFERRED':assert r['A_B_normalized_code_equal'] or r['checked_local_call_comparison']['equal']
def test_address_points_are_not_function_ordinals():
 d=load('shapenode_slots.json');assert len(d['address_points'])==21
 for r in d['slots']:
  assert r['abi_byte_offset']==r['slot_index']*8
  assert r['address_point_byte_offset']+r['offset_from_address_point']==r['abi_byte_offset']
 assert next(r for r in d['slots'] if r['slot_index']==70)['offset_from_address_point']==8
def test_destructor_variant_and_thunk_classification():
 for n,v in [('_ZN1AD0Ev','D0'),('_ZN1AD1Ev','D1'),('_ZN1AD2Ev','D2'),('_ZN1AC1Ev','C1'),('_ZN1AC2Ev','C2')]:assert variant(n)==v
 d=load('rtti_thunks.json');assert d['counts']=={'nonvirtual':12,'virtual':30}
 assert all(t['candidate'].startswith(('_ZTh','_ZTv')) for t in d['thunks'])
def test_rtti_base_descriptors_and_type_names_match():
 d=load('rtti_thunks.json');assert d['rtti']['A']==d['rtti']['B']==d['rtti']['C'];assert d['type_name']['A']==d['type_name']['B']==d['type_name']['C']
def test_actual_consumer_callsite_and_core_deleting_dispatch():
 d=load('consumer_virtual_calls.json');assert d['selected_sites'][0]['absolute_table_index']==107 and not d['selected_sites'][0]['in_V2_67']
 assert any('jmp    *0x8(%rax)' in r['disassembly'] for r in d['core_NodeDestructor'])
 assert next(r for r in load('shapenode_slots.json')['slots'] if r['slot_index']==70)['consumer_usage']=='INDIRECTLY_REACHABLE'
def test_EH_decoder_matches_independent_readelf_FDE_boundaries():
 e=Elf(libs()['A']);cs,fs=eh_records(e);other,_=frames(e.path)
 assert {f['start']:f['end'] for f in fs}=={start:f['end'] for start,f in other.items()}
 assert any(c['personality'] for c in cs.values())
 for r in load('exception_abi.json')['libraries']['A']['selected_LSDA_sections']:assert r['section']=='.gcc_except_table'
def test_lifetime_fixture_is_compile_only_and_equivalent():
 d=load('destructor_contract.json')['compile_only']
 for x in d.values():assert x['compile']['rc']==0 and x['execution']=='NOT_RUN' and x['sizes']==[1664,16,48]
 norm=lambda t:'\n'.join(l for l in t.splitlines() if not l.endswith('file format elf64-x86-64'))
 assert norm(d['A']['disassembly'])==norm(d['B']['disassembly'])==norm(d['C']['disassembly'])
def test_ownership_graph_keeps_cross_module_deallocation_visible():
 d=load('ownership_boundary.json');assert d['runtime']=='NOT_RUNTIME_VERIFIED'
 assert any('D0' in r['operation'] and r['from_module']=='core deleter' for r in d['edges'])
 assert d['required_lifetimes']
@pytest.fixture
def probe(tmp_path):
 p=tmp_path/'p.cpp';p.write_text('struct Probe { virtual int a(); virtual int b(); virtual ~Probe(); }; int Probe::a(){return 1;} int Probe::b(){return 2;} Probe::~Probe(){} extern "C" const unsigned long marker=0x12345678;')
 so=tmp_path/'p.so';obj=tmp_path/'p.o'
 for args in [['g++','-fPIC','-shared',str(p),'-o',str(so)],['g++','-c',str(p),'-o',str(obj)]]:subprocess.run(args,check=True,capture_output=True)
 return so,obj
def test_ET_REL_requires_section_offset_and_constant_is_correct(probe):
 e=Elf(probe[1]);assert struct.unpack('<Q',e.read_symbol('marker'))[0]==0x12345678
 with pytest.raises(ValueError,match='ET_REL'):e.read(0,8)
def test_relocation_slot_swap_is_detected(probe):
 e=Elf(probe[0]);n='_ZTV5Probe';before=e.table(n);a=e.sym(n)['address']+16;b=a+8;e.reloc[a],e.reloc[b]=e.reloc[b],e.reloc[a]
 after=e.table(n);assert before!=after and before[2]==after[3]
def test_unknown_relocation_is_rejected(probe):
 e=Elf(probe[0]);a=e.sym('_ZTV5Probe')['address']+16;e.reloc[a]['type']=999
 with pytest.raises(ValueError,match='unsupported pointer relocation'):e.pointer(a)
def test_out_of_range_virtual_address_is_rejected(probe):
 with pytest.raises(ValueError,match='unmapped'):Elf(probe[0]).read(1<<62,8)
def test_corrupt_section_offset_is_rejected(probe,tmp_path):
 d=bytearray(probe[0].read_bytes());struct.pack_into('<Q',d,40,1<<62);p=tmp_path/'bad';p.write_bytes(d)
 with pytest.raises(ValueError,match='section table'):Elf(p)
def test_corrupt_RELA_symbol_index_is_rejected(probe,tmp_path):
 e=Elf(probe[0]);sec=next(s for s in e.sections if s[1]==4 and s[5]);d=bytearray(e.data);struct.pack_into('<Q',d,sec[4]+8,(0xffffffff<<32)|1);p=tmp_path/'bad-rel';p.write_bytes(d)
 with pytest.raises(ValueError,match='relocation symbol index'):Elf(p)
def test_EH_signed_encoding_and_truncation():
 c=Cursor(b'\xfc\xff\xff\xff',0x1000);assert c.ptr(0x1b)['value']==0xffc
 assert Cursor(b'\x78').leb(True)==-8
 with pytest.raises(ValueError,match='truncated EH'):Cursor(b'\x80').leb()
 with pytest.raises(ValueError,match='unsupported EH'):Cursor(b'\0'*8).ptr(0x50)
