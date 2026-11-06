from common import *
import re,ast
root=R.parents[1]
# Explicit allowlist: never add an entire ignored folder or any pre-existing main edit.
report_names=['abi_layout.json','abi_summary.json','build_failure_resolution.json','build_profile.json','build_protocol.json','build_results.json','capability_sources.json','configure_commands.json','consumer_references.json','debug_coverage.json','dependencies.json','dependency_detection_probe.json','dependency_loader_checks.json','dwarf_comparison.json','elf_summary.json','fixture_compile.json','initial_git.json','installed_debug_paths.json','instrumentation_delta.json','integrity.json','loader_checks.json','metadata_call_observation.json','neutrality_static_review.json','original_debug_buildinfo_probe.json','reference_modules.json','patch_roundtrip.json','symbol_differences.json','test_safety_review.json','test_summary.json','vtable_sizes.json','final_report.md','verdict.json']
files=[root/'AGENTS.md',R/'.gitignore',R/'README.md',R/'trace_schema.py',R/'instrumentation/dart_internal_trace_v1.patch']
files+=sorted((R/'scripts').glob('*.py'))+sorted(p for p in (R/'tests').iterdir() if p.is_file() and p.suffix in ('.py','.cpp'))
files+=[R/'reports'/name for name in report_names]
missing=[str(p) for p in files if not p.is_file()]
if missing:raise RuntimeError('Do not publish incomplete investigation: '+str(missing))
for p in files:
 assert not p.is_symlink() and p.stat().st_size<2_000_000,(p,p.stat().st_size)
 assert 'work' not in p.relative_to(R).parts if p!=root/'AGENTS.md' else True
 if p.suffix=='.py':ast.parse(p.read_text())
 text=p.read_text();assert not re.search(r'(?:gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY)',text),p
branch=run(['git','branch','--show-current'],cwd=root)['stdout'].strip();assert branch=='experiment/dart-internal-trace'
plan={'branch':branch,'base_commit':'46134c6bf5670ed61ba252f394ccdddb7ff2cf6b','files':sorted(str(p.relative_to(root)) for p in files),'file_count':len(files),'total_bytes':sum(p.stat().st_size for p in files),'local_only':['handoff.md','work/','downloads/','raw logs/XML/full manifests/symbol_inventory/preexisting diff audit','reports/git_publication.json'],'tests':json.loads((R/'reports/test_summary.json').read_text())}
save('publication_plan.json',plan);print('Reviewed explicit publication list:',plan['file_count'],'files,',plan['total_bytes'],'bytes');print('\n'.join(plan['files']))
