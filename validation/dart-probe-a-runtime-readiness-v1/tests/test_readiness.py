import copy, json, os, subprocess, sys, unittest
from pathlib import Path
from unittest.mock import patch
B=Path(__file__).resolve().parents[1];sys.path.insert(0,str(B/'scripts'))
import readiness as r
E=r.load_manifest()['profiles']['installed_core_future_only']
class Contract(unittest.TestCase):
    def test_closure(self):
        mounts,edges=r.aliases(E);self.assertEqual(len(E),16);self.assertEqual(len(edges),58)
        self.assertTrue(all(x['provider'] in {e['real_path'] for e in E} for x in edges))
    def test_missing(self):
        with self.assertRaises(ValueError):r.aliases(E[:-1])
    def test_duplicate(self):
        with self.assertRaises(ValueError):r.aliases(E+[E[0]])
    def test_fd_count(self):
        with self.assertRaises(ValueError):r.mount_arguments(E,[])
    def test_alias_identity(self):
        mounts,_=r.aliases(E)
        for row in r.mapped_entries(E,mounts):self.assertEqual(row['sha256'],mounts[row['sandbox_path']]['sha256'])
    def gate(self,report):
        sent=[]
        with patch.object(r,'start_id',return_value='123'):
            result=r.post_open(1,'123',E,[],sent.append,lambda *a:report)
        return result,sent
    def test_reject_no_permission(self):
        self.assertEqual(self.gate({'status':'FAIL'})[1],[])
    def test_missing_core(self):
        result,sent=self.gate({'status':'PASS_FILE_IDENTITY','records':[]});self.assertEqual(result['status'],'REJECTED');self.assertEqual(sent,[])
    def test_accept_file_identity_only(self):
        result,sent=self.gate({'status':'PASS_FILE_IDENTITY','records':E});self.assertEqual(sent,['CLOSE\n']);self.assertFalse(result['resident_pages_verified'])
    def test_pid_reuse(self):
        with patch.object(r,'start_id',return_value='456'):
            with self.assertRaises(ValueError):r.post_open(1,'123',E,[],lambda _:self.fail('permission sent'))
    def test_shared_baseline(self):
        sent=[]
        with patch.object(r,'start_id',return_value='123'):
            result=r.post_open(1,'123',E,[E[-1]],sent.append,lambda *a:{'status':'PASS_FILE_IDENTITY','records':E})
        self.assertEqual(sent,['CLOSE\n'])
    def test_conflicting_baseline(self):
        bad=copy.deepcopy(E[-1]);bad['inode']+=1
        with patch.object(r,'start_id',return_value='123'):
            with self.assertRaises(ValueError):r.post_open(1,'123',E,[bad],lambda _:self.fail('permission'))
    def test_protocol(self):
        p=subprocess.run([str(B/'work/post_open')],input='CLOSE\n',text=True,capture_output=True);self.assertEqual(p.returncode,0);self.assertIn('CLOSE_SIMULATED',p.stdout)
    def test_protocol_reject(self):
        p=subprocess.run([str(B/'work/post_open')],input='GO\n',text=True,capture_output=True);self.assertEqual(p.returncode,78);self.assertNotIn('CLOSE_SIMULATED',p.stdout)
    def test_protocol_eof(self):
        p=subprocess.run([str(B/'work/post_open')],input='',text=True,capture_output=True);self.assertEqual(p.returncode,78)
    def test_protocol_timeout(self):
        p=subprocess.Popen([str(B/'work/post_open')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
        try:self.assertEqual(p.wait(timeout=3),78)
        finally:p.stdin.close();p.stdout.close()
if __name__=='__main__':unittest.main()
