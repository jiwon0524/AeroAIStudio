import json,unittest
from pathlib import Path
B=Path(__file__).resolve().parents[1]; R=B/'reports'
class Review(unittest.TestCase):
    def test_json(self):
        for p in R.glob('*.json'): self.assertIsInstance(json.loads(p.read_text()),dict)
    def test_no_promotion(self):
        v=json.loads((R/'readiness_verdict.json').read_text()); self.assertEqual(set(v['probes'].values()),{'BLOCKED'}); self.assertFalse(v['actual_runtime_execution_authorized']); self.assertEqual(v['Stage_B'],'BLOCKED');self.assertEqual(v['runtime'],'NOT_RUNTIME_VERIFIED')
    def test_contracts(self):
        p=json.loads((R/'probe_risk_matrix.json').read_text())['probes'];self.assertEqual([x['probe'] for x in p],list('ABCD'))
        for x in p:
            for k in ('blockers','isolation','stop','success_criteria','failure_handling','post_execution_integrity','exact_targets_manifest','planned_limits','evidence'): self.assertTrue(x[k])
    def test_identification(self):
        rows=json.loads((R/'elf_review.json').read_text())['libraries']; self.assertEqual(sum(x['exists'] for x in rows),9)
        for x in rows:
            if x['exists']: self.assertTrue(x['previous_identity_match']);self.assertEqual(len(x['sha256']),64)
    def test_fixture_results(self):
        r=json.loads((R/'fixture_test_results.json').read_text());self.assertEqual((r['PASS'],r['FAIL'],r['SKIP']),(14,0,0))
    def test_limitations_visible(self):
        r=json.loads((R/'isolation_review.json').read_text());self.assertIn('NOT_VALIDATED',r['filesystem_sandbox']);self.assertIn('NOT_VALIDATED',r['network_sandbox'])
if __name__=='__main__': unittest.main()
