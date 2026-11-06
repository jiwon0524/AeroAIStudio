import importlib.util,json,re,subprocess,unittest
from pathlib import Path
B=Path(__file__).resolve().parents[1];R=B/'reports'
spec=importlib.util.spec_from_file_location('audit',B/'scripts/audit.py');a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
def read(n):return json.loads((R/(n+'.json')).read_text())
class StaticAuditTests(unittest.TestCase):
 def test_prior_identity(self):
  rows=read('elf_identity')['inventory'];checked=[x for x in rows if 'historical_sha_match' in x]
  self.assertEqual(len(checked),10)
  self.assertTrue(all(x['historical_sha_match'] and x['historical_build_id_match'] for x in checked))
 def test_inventory_metadata(self):
  for row in read('elf_identity')['inventory']:
   if row['exists']:
    for key in ('sha256','build_id','architecture','needed','soname','rpath','runpath','real_path','is_symlink'):self.assertIn(key,row)
    self.assertEqual(row['elf_class'],'ELF64');self.assertEqual(row['architecture'],'Advanced Micro Devices X86-64')
 def test_core_closure_candidates(self):
  x=read('dependency_audit');self.assertEqual(x['node_count'],16);self.assertEqual(len(x['edges']),58)
  self.assertFalse(x['missing']);self.assertFalse(x['ambiguous']);self.assertEqual(x['runtime_resolution'],'UNVERIFIED')
 def test_optional_bullet_ode(self):
  x=read('optional_collision_dependencies');self.assertTrue(any('libBulletCollision' in p for p in x['nodes']));self.assertTrue(any('libode.so' in p for p in x['nodes']))
  self.assertTrue(all(e['candidates'] for e in x['edges']))
 def test_missing_old_external_stays_missing(self):
  rows=read('elf_identity')['inventory'];self.assertEqual(sum(not x['exists'] for x in rows),2)
  found=[r for r in rows if r.get('role','').startswith('located_')];self.assertEqual(len(found),2);self.assertTrue(all(x['exists'] for x in found))
 def test_empty_paths(self):
  x=a.search_parts(['/a:/b:'])[0]['components'];self.assertTrue(x[-1]['empty_cwd']);self.assertEqual(len(x),3)
 def test_origin_relative(self):
  x=a.search_parts(['$ORIGIN/../lib:relative:/usr/lib'])[0]['components'];self.assertTrue(x[0]['origin']);self.assertTrue(x[1]['relative']);self.assertFalse(x[2]['relative'])
 def test_absent_path_not_empty_element(self):self.assertEqual(a.search_parts([]),[])
 def test_core_has_no_runpath(self):
  d=read('dependency_audit');self.assertTrue(all(not v['runpath'] and not v['rpath'] for v in d['nodes'].values()))
 def test_local_runpath_empty(self):
  rows=read('runpath_audit')['libraries'];self.assertTrue(all(any(c['empty_cwd'] for p in r['runpath'] for c in p['components']) for r in rows if r.get('arm') in ('B','C') and 'libdart.so.' in r['path']))
 def test_actual_init_arrays(self):
  d=read('dependency_audit');core=d['nodes'][d['root']];self.assertEqual(core['special_sections']['.init_array']['size_bytes'],16);self.assertEqual(core['special_sections']['.fini_array']['size_bytes'],8)
  self.assertEqual(core['special_sections']['.init_array']['file_pointer_values'],['0x1787d0','0x176840'])
 def test_versioned_undefined_names(self):
  d=read('dependency_audit');imports=d['nodes'][d['root']]['lifetime_imports'];self.assertTrue(any('__cxa_atexit' in s for s in imports));self.assertFalse(any(s.startswith('(') for s in imports))
 def test_tls_ifunc_unknown_semantics(self):
  rows=read('initialization_risks')['libraries'];self.assertTrue(any(r['ifunc_count'] for r in rows));self.assertTrue(any('.tbss' in r['sections'] for r in rows));self.assertTrue(all(r['callback_semantics']=='UNVERIFIED' for r in rows))
 def test_cache_parser_filters_arch(self):
  x=a.cache_map(' libx.so (libc6,x86-64) => /lib/libx.so\n libx.so (libc6) => /other/libx.so');self.assertEqual(x,{'libx.so':['/lib/libx.so']})
 def test_missing_candidate(self):self.assertEqual(a.candidates('libNONEXISTENT_AERO_PROBE_A.so',{}),[])
 def test_invalid_elf_rejected(self):
  with self.assertRaises(ValueError):a.sections(B/'fixtures/probe_a.c')
 def test_static_plan_not_execution(self):
  d=read('probe_a_execution_plan');self.assertFalse(d['runtime_command_available']);self.assertFalse(d['runtime_evidence_created']);self.assertIn('Stage B',d['forbidden']);self.assertFalse(d['timeout_design']['automatic_retry'])
 def test_source_no_unsafe_tool(self):
  s=(B/'scripts/audit.py').read_text();self.assertNotIn('ctypes',s);self.assertNotIn("['ldd'",s);self.assertNotIn('CDLL(',s)
if __name__=='__main__':unittest.main()
