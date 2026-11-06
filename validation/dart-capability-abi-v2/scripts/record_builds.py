from common import *
import re
records=[]
for tag in ('baseline','trace'):
 for phase,folder,log in [('initial',f'work/build-{tag}',f'build_{tag}.log'),('final',f'work/build-{tag}-final',f'build_{tag}_final.log')]:
  text=(R/'reports'/log).read_text();record={'tag':tag,'phase':phase,'build_directory':str(R/folder),'log':str(Path('reports')/log),'completed_targets':re.findall(r'Built target (\S+)',text),'error_lines':[l for l in text.splitlines() if 'error:' in l],'log_sha256':sha(R/'reports'/log)};records.append(record)
save('build_results.json',records);print([(r['tag'],r['phase'],r['completed_targets'],r['error_lines'][:1]) for r in records])
