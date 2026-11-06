import importlib.util,json,unittest
from pathlib import Path
B=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('smoke_review',B/'scripts/smoke.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def row(**kw):
 d={k:None for k in m.KEYS};d.update(kw);return d
class Review(unittest.TestCase):
 def test_expected_activation(self):
  a={'app.slice':row(**{'cgroup.controllers':'memory pids','cgroup.subtree_control':'memory pids'})};b={'app.slice':row(**{'cgroup.controllers':'cpu memory pids','cgroup.subtree_control':'cpu memory pids','cpu.max':'max 100000'})}
  self.assertTrue(all(d['expected'] for d in m.differences(a,b,'own.service')))
 def test_quota_mutation_unexpected(self):
  a={'existing.service':row(**{'cpu.max':'max 100000'})};b={'existing.service':row(**{'cpu.max':'25000 100000'})};self.assertFalse(m.differences(a,b,'own.service')[0]['expected'])
 def test_removal_unexpected(self):
  a={'x':row(**{'cgroup.controllers':'cpu memory pids'})};b={'x':row(**{'cgroup.controllers':'memory pids'})};self.assertFalse(m.differences(a,b,'own.service')[0]['expected'])
 def test_other_topology_change(self):
  self.assertFalse(m.differences({'x':row()},{'y':row()},'own.service')[0]['expected'])
 def test_only_own_path_excluded(self):
  d=m.differences({}, {'own.service':row(),'own.service/child':row(),'own.service-other':row()},'own.service');self.assertEqual([x['path'] for x in d],['own.service-other'])
 def test_approved_plan(self):
  p=json.loads((B.parents[1]/'validation/dart-cgroup-readiness-v1/reports/approval_plan.json').read_text());self.assertEqual(p['creation_argv'][-2:],['/usr/bin/sleep','5']);self.assertEqual((p['limits']['MemoryMax'],p['limits']['TasksMax'],p['limits']['CPUQuota']),('64M','8','25%'))
if __name__=='__main__':unittest.main()
