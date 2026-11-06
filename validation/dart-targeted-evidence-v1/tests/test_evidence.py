import sys,unittest,tempfile,struct,zlib,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from evidence import *
class EvidenceTests(unittest.TestCase):
 def test_build_id(self):self.assertEqual(build_id(' Build ID: aabb00112233\n'),'aabb00112233')
 def test_build_id_reject(self):
  for t in ['', 'Build ID: abc','Build ID: aabb0011\nBuild ID: ccdd0011']:
   with self.assertRaises(ValueError):build_id(t)
 def test_sha_known_vector(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'a';p.write_bytes(b'abc');self.assertEqual(sha(p),'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')
 def test_package_continuation(self):self.assertEqual(paragraphs('Package: dart\nVersion: 1\nDescription: a\n b\n\nPackage: x\n')[0]['Description'],'a\nb')
 def test_empty_package_field(self):self.assertEqual(paragraphs('Package: dart\nChecksums-Sha256:\n abc 1 a\n')[0]['Checksums-Sha256'],'\nabc 1 a')
 def test_bad_package(self):
  for t in ['bad',' continuation','Package: x\nPackage: y','bad field: x']:
   with self.assertRaises(ValueError):paragraphs(t)
 def test_debuglink_and_crc(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'a';p.write_bytes(b'123456789');raw=b'x.debug\0'+struct.pack('<I',0xcbf43926);n,crc=debuglink(raw)
   self.assertEqual(n,'x.debug');self.assertTrue(crc_match(p,crc));p.write_bytes(b'changed');self.assertFalse(crc_match(p,crc))
 def test_debuglink_invalid(self):
  for b in [b'',b'x',b'../x\0\0\0\0'+b'\0'*4,b'x\0',b'..\0\0'+b'\0'*4]:
   with self.assertRaises(ValueError):debuglink(b)
 def test_classify(self):
  self.assertEqual(classify('aa','aa',True),'EXACT_BUILD_ID_DEBUG_FOUND');self.assertEqual(classify('aa','bb',True),'MISMATCHED_BUILD');self.assertEqual(classify('aa','aa',False),'PARTIAL_DEBUG_FOUND');self.assertEqual(classify('aa',None,False),'DEBUG_NOT_FOUND')
 def test_allowlist(self):
  self.assertTrue(official_url('https://packages.osrfoundation.org/a'))
  for u in ['http://packages.osrfoundation.org/a','https://packages.osrfoundation.org.evil/a','https://u:p@packages.osrfoundation.org/a','file:///a','https://debuginfod.ubuntu.com:444/a']:self.assertFalse(official_url(u))
 def test_path_escape(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'x';p.symlink_to('/etc/passwd')
   with self.assertRaises(ValueError):validate_path(p,[t])
 def test_path_file(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'x';p.write_text('a');self.assertEqual(validate_path(p,[t]),p)
   with self.assertRaises(ValueError):validate_path(Path(t),[t])
 def test_sections_invalid(self):
  for d in [b'',b'not elf',b'\x7fELF\x02\x01'+b'\0'*58]:
   with self.assertRaises(ValueError):section_bytes(d,'.gnu_debuglink')
 def test_real_elf_crosscheck(self):
  # Read installed ELF only; never run it.
  p=Path('/usr/lib/x86_64-linux-gnu/libdart.so.6.13.2');d=elf(p)
  self.assertEqual(d['build_id'],build_id(run(['readelf','--notes',p])['stdout']));self.assertEqual(d['debuglink']['filename'],d['build_id'][2:]+'.debug')
  self.assertIsNone(section_bytes(p.read_bytes(),'.does_not_exist'))
if __name__=='__main__':unittest.main()
