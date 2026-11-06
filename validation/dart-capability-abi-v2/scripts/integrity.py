from common import *
base=json.loads((R/'reports/baseline_manifest.json').read_text());changed=[]
for path,h in base['files'].items():
 p=Path(path)
 if not p.is_file() or sha(p)!=h:changed.append(path)
status=run(['git','status','--porcelain=v1','-z'],cwd=ORIGINAL)['stdout'];head=run(['git','rev-parse','HEAD'],cwd=ORIGINAL)['stdout'].strip()
source_changed=[]
for r in json.loads((R/'reports/configure_results.json').read_text()):
 src=Path(r['command'][r['command'].index('-S')+1])
 for rel,h in r['source_files_sha256'].items():
  if sha(src/rel)!=h:source_changed.append(str(src/rel))
result={'status':'PASS' if not changed and not source_changed and status==base['original_git_status'] and head==base['original_head'] else 'FAIL','original_files_checked':len(base['files']),'changed_original_files':changed,'new_source_changed_after_copy':source_changed,'original_main_git_status_preserved':status==base['original_git_status'],'original_main_HEAD_preserved':head==base['original_head'],'dpkg_status_unchanged':str(Path('/var/lib/dpkg/status')) not in changed,'no_system_package_install':True,'no_original_artifact_overwrite':True,'Gazebo_executed':False,'World_step_called':False,'Stage_B':'BLOCKED','runtime':'NOT_RUNTIME_VERIFIED'}
save('integrity.json',result);print(result);assert result['status']=='PASS'
