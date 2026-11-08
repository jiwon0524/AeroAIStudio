from pathlib import Path
import runpy,json,copy
b=Path.cwd();r=b/'validation/gazebo-joint-codegen-fix-v1';p=b/'validation/gazebo-joint-harness-fix-v1';m=runpy.run_path(str(r/'scripts/check_selection_harness.py'));g=m['Gate']();result=g.run();assert result['status']=='PASS_STATIC_SELECTED_CLOSURE',result['errors'];(p/'reports/selection.json').write_text(json.dumps(result,indent=2)+'\n')
info=result['generated'];tests=[]
def reject(name,action):
 g.errors.clear();action();assert g.errors,name;tests.append({'case':name,'status':'PASS_REJECTED','errors':sorted(set(g.errors))})
reject('required_path_missing',lambda:g.verify(r/'inputs/missing-required-input.hh'))
reject('outside_allowlist',lambda:g.verify('/etc/hostname'))
reject('installed_Sim',lambda:g.verify('/usr/lib/x86_64-linux-gnu/libgz-sim8.so.8'))
reject('local_headers',lambda:g.verify('/usr/local/include'))
reject('root_dangling_symlink',lambda:g.verify(b/'libgz-physics-dartsim-plugin.so'))
reject('unresolved_link_library',lambda:g.link_tokens(['-laero_unapproved_missing']))
reject('unresolved_target_expression',lambda:g.link_tokens(['$<TARGET_FILE:unknown>']))
reject('relative_uninterpreted_link_input',lambda:g.link_tokens(['unresolved/library.so']))
reject('response_file',lambda:g.link_tokens(['@unknown.rsp']))
missing=copy.deepcopy(info);missing.pop('link');reject('missing_link_metadata',lambda:g.model(missing))
extra=copy.deepcopy(info);extra['dependencies']=[{'id':'unplanned'}];reject('unexpected_generated_target',lambda:g.model(extra))
(p/'reports/negative_tests.json').write_text(json.dumps({'positive':'PASS_STATIC_SELECTED_CLOSURE','negative_tests':tests,'execution':'Python gate and ninja metadata only; no subject execution'},indent=2)+'\n')
print('PASS approved selection;',len(tests),'negative rejection cases')
