"""Audit extra ON metadata virtual calls separately from actual solve/apply order."""
from pathlib import Path
import subprocess,json
R=Path(__file__).resolve().parents[1]
def test_metadata_queries_are_gated_and_not_mislabeled_as_runtime_neutral(tmp_path):
 rows={}
 for tag,enabled in [('original','off'),('baseline','off'),('trace','off'),('trace','on')]:
  run=subprocess.run([str(R/f'work/{tag}_metadata'),'primary_true',enabled,str(tmp_path/(tag+enabled+'.json'))],capture_output=True,text=True,check=True)
  lines=run.stdout.splitlines();rows[tag+'_'+enabled]={'impulses':lines[0],'calls':lines[1].split()}
 base=rows['baseline_off'];assert rows['original_off']==base
 assert rows['trace_off']==base
 for k in ('trace_on',):
  assert rows[k]['impulses']==base['impulses']
  assert [v for v in rows[k]['calls'] if not v.startswith('metadata:')]==[v for v in base['calls'] if not v.startswith('metadata:')]
  assert sum(v.startswith('metadata:') for v in rows[k]['calls']) > sum(v.startswith('metadata:') for v in base['calls'])
 # The asserted extra call is an observed limitation, not a neutrality PASS.
 (tmp_path/'metadata_call_observation.json').write_text(json.dumps(rows,indent=2))
