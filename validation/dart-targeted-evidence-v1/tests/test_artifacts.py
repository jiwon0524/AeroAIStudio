"""Compile/read-only fixtures. Never execute or load fixture or DART ELF."""
import sys,unittest,tempfile,subprocess,json,struct
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from evidence import *
class ArtifactTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(dir=WORK);cls.path=Path(cls.temp.name)
  for name,value in [('one',1),('two',2)]:
   src=cls.path/(name+'.cc');src.write_text('extern "C" int sample(){return '+str(value)+';}\n')
   q=run(['g++','-shared','-fPIC','-g','-Wl,--build-id=sha1',src,'-o',cls.path/(name+'.so')]);assert q['rc']==0,q
  cls.binary=cls.path/'one.so';cls.debug=cls.path/'one.debug'
  for args in [['objcopy','--only-keep-debug',cls.binary,cls.debug],['objcopy','--strip-debug','--add-gnu-debuglink='+str(cls.debug),cls.binary]]:
   q=run(args);assert q['rc']==0,q
 @classmethod
 def tearDownClass(cls):cls.temp.cleanup()
 def test_real_debug_match(self):
  a,b=elf(self.binary),elf(self.debug)
  self.assertEqual(classify(a['build_id'],b['build_id'],b['has_debug_info']),'EXACT_BUILD_ID_DEBUG_FOUND');self.assertFalse(a['has_debug_info']);self.assertTrue(crc_match(self.debug,a['debuglink']['crc32']))
 def test_wrong_build_rejected(self):
  a,b=elf(self.binary),elf(self.path/'two.so');self.assertNotEqual(a['build_id'],b['build_id']);self.assertEqual(classify(a['build_id'],b['build_id'],b['has_debug_info']),'MISMATCHED_BUILD')
 def test_corrupt_real_debug_crc(self):
  p=self.path/'corrupt.debug';p.write_bytes(self.debug.read_bytes()+b'corrupt');self.assertFalse(crc_match(p,elf(self.binary)['debuglink']['crc32']))
 def test_malformed_real_section_table(self):
  d=bytearray(self.binary.read_bytes());struct.pack_into('<Q',d,40,len(d)+4096)
  with self.assertRaises(ValueError):section_bytes(d,'.gnu_debuglink')
 def test_inventory_and_v4_hashes(self):
  inventory=json.loads((ROOT/'reports/binary_inventory.json').read_text())['binaries']
  self.assertEqual(len(inventory),6);self.assertEqual(len({x['real_path'] for x in inventory}),6)
  for row in inventory:
   self.assertEqual(sha(row['real_path']),row['sha256']);self.assertEqual(elf(row['real_path'])['build_id'],row['build_id'])
   if row['v4_comparison']['recorded']:self.assertTrue(row['v4_comparison']['hash_match']);self.assertTrue(row['v4_comparison']['build_id_match'])
 def test_signed_original_package_match(self):
  signature=json.loads((ROOT/'reports/repository_signature.json').read_text());self.assertEqual(signature['rc'],0)
  matches=json.loads((ROOT/'reports/official_binary_matches.json').read_text());self.assertEqual(len(matches),3)
  for row in matches:self.assertTrue(row['sha256_match']);self.assertTrue(row['build_id_match']);self.assertEqual(sha(row['reference']['real_path']),sha(row['installed_path']))
 def test_ubuntu_metadata_mismatch(self):
  sig=json.loads((ROOT/'reports/ubuntu_debug_signature.json').read_text());self.assertEqual(sig['ddebs_release_signature']['rc'],0);self.assertFalse(sig['system_install'])
  rows=json.loads((ROOT/'reports/ubuntu_debug_candidates.json').read_text())['candidates'];inv=json.loads((ROOT/'reports/binary_inventory.json').read_text())['binaries']
  for package,role in [('libdart6.13-dbgsym','installed_core'),('libdart-collision-bullet6.13-dbgsym','installed_bullet')]:
   candidate=next(r for r in rows if r['Package']==package);target=next(r for r in inv if r['role']==role)
   self.assertNotIn(target['build_id'],candidate['Build-Ids'].split());self.assertNotEqual(candidate['Version'],target['package']['Version'])
 def test_evidence_safety_and_classification(self):
  rows=json.loads((ROOT/'reports/build_id_matches.json').read_text())
  for row in rows[:4]:self.assertEqual(row['classification'],'DEBUG_NOT_FOUND');self.assertFalse(row['acquired'])
  plan=json.loads((ROOT/'reports/probe_plan.json').read_text());self.assertTrue(plan['all_probes_not_run']);self.assertEqual([x['probe'] for x in plan['probes']],list('ABCD'))
  for p in plan['probes']:self.assertEqual(p['execution_status'],'NOT_RUN_DESIGN_ONLY');self.assertTrue(p['status'].startswith('BLOCKED'))
if __name__=='__main__':unittest.main()
