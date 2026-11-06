"""Consumer compatibility acceptance checks; never load or execute a plugin."""
import json
from pathlib import Path
import pytest
R=Path(__file__).resolve().parents[1]
def load(n):return json.loads((R/'reports'/n).read_text())
def test_inventory_has_actual_elf_consumers():
 for e in load('consumer_inventory.json'):
  assert e['build_id'] and e['sha256'] and e['dart_symbols']
  assert any('libdart' in n for n in e['NEEDED'])
@pytest.mark.parametrize('arm',['B','C'])
def test_all_referenced_symbols_have_effective_provider(arm):
 for r in load('consumer_symbols.json'):assert r['effective_providers'][arm],r['mangled']
@pytest.mark.parametrize('arm',['A','B','C'])
def test_relocations_and_core_selection(arm):
 rows=[x for x in load('loader_results.json') if x['arm']==arm];assert rows
 for x in rows:
  assert x['rc']==0 and not x['issues'] and x['core_external_selected']
  assert 'libdart.so.6.13' in x['dart_closure']
@pytest.mark.parametrize('arm',['B','C'])
def test_retained_auxiliary_imports(arm):
 for e in load('auxiliary_consumers.json'):assert not e['missing'][arm]
def test_public_layout_observations_agree():
 d=load('abi_comparison.json')['layout'];assert all(x['rc']==0 for x in d.values())
 assert len({x['stdout'] for x in d.values()})==1
@pytest.mark.parametrize('arm',['B','C'])
def test_existing_vtable_rtti_metadata_preserved(arm):
 for x in load('abi_comparison.json')['vtable_rtti']:
  # Optional installed Bullet module remains original, not a rebuilt provider.
  if x['metadata'][arm]['size'] is not None:assert x['metadata']['A']==x['metadata'][arm],x['name']
def test_no_unsupported_runtime_claim():
 x=load('instrumentation_review.json');assert x['runtime']=='NOT_RUNTIME_VERIFIED' and x['unknown']
