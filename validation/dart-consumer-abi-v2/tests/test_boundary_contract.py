"""Static/compile-only ABI checks. No DART/plugin object construction or execution."""
import json,sys,subprocess
from pathlib import Path
import pytest
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'scripts'))
from elf_tables import Elf

def load(n):return json.loads((R/'reports'/n).read_text())
@pytest.mark.parametrize('arm',['A','B','C'])
def test_boundary_compiles_without_running_objects(arm):
 r=load('boundary_fixture.json')[arm]
 assert r['compile']['rc']==r['clang_layout_rc']==0
 assert r['object_execution'].startswith('NOT_RUN')
 assert all(r['classes'].values()) and all(r['member_layouts'].values())
def test_header_base_member_layout_and_constants():
 f=load('boundary_fixture.json');v=load('bullet_core_contract.json')['compile_only_constants']
 for arm in ['B','C']:
  assert f['A']['classes']==f[arm]['classes']
  assert f['A']['member_layouts']==f[arm]['member_layouts']
  assert f['A']['header_vtables']==f[arm]['header_vtables']
  assert v['A']==v[arm]
 assert v['A']['boundary_sizes'][:2]==[24,8]
 assert v['A']['contact_offsets']==[0,24,48,72,80,88,96,100,104]
def test_installed_simple_getters_match_actual_candidate_machine_code():
 d=load('bullet_core_contract.json')['installed_simple_getters'];assert len(d['A'])>=3
 for n,v in d['A'].items():
  for arm in ['B','C']:assert v['code_sha256']==d[arm][n]['code_sha256']
@pytest.mark.parametrize('arm',['B','C'])
def test_resolved_core_virtual_slots_and_rtti(arm):
 d=load('vtable_rtti.json')['core_comparison'][arm];assert d
 for n,v in d.items():
  assert v['status']!='MISMATCH' and v['entry_count_equal'] and not v['known_slot_differences'],n
  if 'ShapeNode' not in n:assert v['status']=='MATCH',n
 assert d['_ZTVN4dart8dynamics9ShapeNodeE']['status']=='UNKNOWN_LOCAL_TARGETS'
 names=load('vtable_rtti.json')['type_names']
 assert names['A']==names[arm]
def test_bullet_rtti_records_primary_core_bases():
 d=load('vtable_rtti.json')['tables']['Bullet']
 pairs=[('21BulletCollisionObject','15CollisionObject'),('20BulletCollisionGroup','14CollisionGroup'),('23BulletCollisionDetector','17CollisionDetector')]
 for child,parent in pairs:
  entries=d['_ZTIN4dart9collision'+child+'E']['entries']
  assert any(x.get('name')=='_ZTIN4dart9collision'+parent+'E' for x in entries)
def test_compiled_inline_virtual_cast_paths_match():
 d=load('inline_access.json');assert all(d['fixture_disassembly_equal'].values())
 text=(R/'work/A/boundary.disassembly').read_text()
 assert 'call   *0x18(%rax)' in text and '0x58(%rdi)' in text and '__dynamic_cast' in text
 assert '0x110(%rdi)' in text
 assert len(d['installed_disassembly']['Gazebo'])>=1
def test_loader_and_consumed_symbol_contract():
 d=load('loader_results.json');assert d['status']=='PASS'
 assert len(d['checks'])==12
 for row in d['consumer_symbols']:assert not row['missing'] and not row['metadata_differences']
def test_instrumentation_does_not_edit_existing_declarations():
 d=load('instrumentation_abi.json');assert d['existing_hpp_checked']>=400 and not d['changed_existing_hpp']
 assert d['runtime']=='NOT_RUNTIME_VERIFIED'
def test_elf_rejects_unsupported_encoding(tmp_path):
 p=tmp_path/'bad';p.write_bytes(b'not ELF')
 with pytest.raises(ValueError):Elf(p)
def test_table_parser_detects_real_relocation_slot_swap(tmp_path):
 # Compile/link a tiny independent ABI fixture. Never load or execute it.
 p=tmp_path/'slots.cpp';p.write_text('struct Base { virtual int one(); virtual int two(); virtual ~Base(); }; int Base::one(){return 1;} int Base::two(){return 2;} Base::~Base(){}')
 so=tmp_path/'slots.so';subprocess.run(['g++','-fPIC','-shared',str(p),'-o',str(so)],check=True,capture_output=True)
 e=Elf(so);n='_ZTV4Base';before=e.table(n);start=e.syms[n]['address']
 a,b=start+16,start+24;assert a in e.reloc and b in e.reloc
 e.reloc[a],e.reloc[b]=e.reloc[b],e.reloc[a]
 after=e.table(n);assert before!=after
 assert before[2]==after[3] and before[3]==after[2]
