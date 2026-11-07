import importlib.util,json,sys
from pathlib import Path
B=Path(__file__).resolve().parents[1];ROOT=B.parents[1]
spec=importlib.util.spec_from_file_location('preserve',ROOT/'validation/dart-probe-a-harness-v1/scripts/preserve.py');p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p);p.TASK=B
if __name__=='__main__':
 if sys.argv[1]=='before':(B/'work/preservation_before.json').write_text(json.dumps(p.snapshot()))
 else:
  old=json.loads((B/'work/preservation_before.json').read_text());new=p.snapshot();changes=[x for x,h in old['files'].items() if new['files'].get(x)!=h];added=sorted(set(new['files'])-set(old['files']));v={'baseline_files':len(old['files']),'changed_or_missing':changes,'new_existing_scope_files':added,'main_head_unchanged':old['main_head']==new['main_head'],'main_status_unchanged':old['main_status']==new['main_status']};v['status']='PASS' if not changes and not added and v['main_head_unchanged'] and v['main_status_unchanged'] else 'FAIL';(B/'reports/integrity.json').write_text(json.dumps(v,indent=2)+'\n');print(json.dumps(v))
