"""Static/compile-only tests. Never load a target or execute a destructor."""
import sys,json,re
from pathlib import Path
import pytest
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'scripts'))
from cleanup import parse_lsda
from elf_reader import Elf
from common import libs

def load(n):return json.loads((R/'reports'/n).read_text())
def test_slot18_actual_AP_offset_and_FDE_boundary():
 d=load('slot18_analysis.json')
 for a in ['A','B','C']:
  r=d['arms'][a];assert r['slot_index']==18 and r['table_byte_offset']==r['primary_AP']==144 and r['function_bytes']==997
  assert r['cleanup']['status']=='NO_LSDA_IN_SELECTED_FDE'
 assert all(v['normalized_body_equal'] for v in d['comparison'].values())
def test_stripped_identity_is_inferred_not_named_fact():
 d=load('slot18_analysis.json');assert d['status']=='INFERRED' and not d['arms']['A']['symbol_aliases']
 for a in ['B','C']:assert any(x['name']=='_ZN4dart8dynamics9ShapeNodeD1Ev' for x in d['arms'][a]['symbol_aliases'])
def test_real_D0_and_adjusted_D0_call_slot18():
 d=load('slot18_analysis.json')
 for a in ['A','B','C']:assert d['arms'][a]['D0_directly_calls_entry'] and d['arms'][a]['Node_adjusted_D0_directly_calls_entry']
 g=load('destructor_call_graph.json');text=Path(g['core_records']['A_70']['disassembly_path']).read_text();assert re.search(r'lea\s+-0x90\(%rdi\),%rbx',text) and re.search(r'mov\s+%rbx,%rdi',text)
 assert 'No generic Node D0 -> Node D1 assumption' in g['Node_D0_D1_interpretation']
def test_observed_base_cleanup_order_is_preserved():
 d=load('slot18_analysis.json')
 for a in ['A','B','C']:
  e=Elf(libs()[a]);aliases=[' '.join(x['name'] for x in e.aliases(int(c['target'],16))) for c in d['arms'][a]['call_edges']]
  indices=[next(i for i,n in enumerate(aliases) if k in n) for k in ['10FixedFrameD2','5FrameD2','6EntityD2','7SubjectD1']]
  assert indices==sorted(indices)
def test_sized_delete_matches_compile_constants():
 d=load('ownership_contract.json')
 for a in ['A','B','C']:
  for row in d['ShapeNode_sized_delete'][a].values():assert row['has_sized_delete'] and 1664 in row['delete_sizes']
 for tail,size in [('21BulletCollisionObjectE',48),('20BulletCollisionGroupE',368)]:
  r=next(r for r in d['Bullet_sized_delete'] if r['table'].endswith(tail));assert r['has_sized_delete'] and size in r['sized_delete_args']
def test_deletion_fixtures_only_compiled():
 d=load('ownership_contract.json')['compile_only']
 for r in d.values():assert r['compile']['rc']==0 and r['execution']=='NOT_RUN' and r['sizes']==[1664,16,48,368]
def test_factory_LSDA_maps_constructor_and_new_cleanup():
 d=load('exception_cleanup.json')['Bullet_factory'];assert len(d['sites'])==4
 assert sum(r['classification']=='CLEANUP_ONLY' for r in d['sites'])==3
 ctor=next(r for r in d['sites'] if r['start']==0x2024d)
 assert ctor['landing_pad']==0x20353 and ctor['landing_bound']=='FDE'
 cold=ctor['cold_followup'];assert cold['entry']=='0x12c1c'
 assert 'operator delete(void*, unsigned long)' in cold['disassembly'] and '_Unwind_Resume@plt' in cold['disassembly'] and '$0x30,%esi' in cold['disassembly']
def test_no_LSDA_is_not_no_exception_claim():
 for r in load('exception_cleanup.json')['core'].values():assert r['status']=='NO_LSDA_IN_SELECTED_FDE' and 'Does not prove' in r['limits']
def test_LSDA_cleanup_action_and_explicit_LPStart():
 d=parse_lsda(bytes([255,255,1,4,0,1,1,1,0,0]),0x1000,0x2000)
 assert d['sites'][0]['classification']=='CLEANUP_ONLY' and d['sites'][0]['actions'][0]['filter']==0
 # Explicit LPStart absolute udata4 overrides function start for callsite offsets.
 d=parse_lsda(bytes([3,0,0x30,0,0,255,1,4,2,1,4,0]),0x1000,0x2000)
 assert d['sites'][0]['start']==0x3002 and d['sites'][0]['landing_pad']==0x3004
def test_truncated_and_cyclic_LSDA_are_rejected():
 with pytest.raises(ValueError,match='exceeds buffer'):parse_lsda(bytes([255,255,1,10]),0,0)
 with pytest.raises(ValueError,match='cyclic'):parse_lsda(bytes([255,255,1,4,0,1,1,1,0,127]),0,0)
def test_nonzero_filter_is_not_mislabeled_cleanup_only():
 d=parse_lsda(bytes([255,255,1,4,0,1,1,1,1,0]),0,0)
 assert d['sites'][0]['classification']=='ACTION_CHAIN_PRESENT'
def test_bounded_stop_does_not_auto_start_another_static_stage():
 d=load('analysis_stop.json');assert any(r['item']=='Exception/lifetime neutrality' and r['stop']=='C' for r in d['items'])
 assert 'no automatic further static phase' in d['next_evidence']
