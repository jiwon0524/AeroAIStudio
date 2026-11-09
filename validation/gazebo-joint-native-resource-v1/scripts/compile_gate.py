import sys,subprocess,hashlib,json,os,shlex
from pathlib import Path
r=Path(__file__).resolve().parents[1]
a=sys.argv[1:]
if '-c' not in a:raise SystemExit('compile-only launcher')
if any(x in ' '.join(a) for x in ['-march=native','-fno-rtti','-fno-exceptions']):raise SystemExit('ABI flags rejected')
record=r/'logs'/('headers-'+str(os.getpid())+'.d')
a=['-MD' if x=='-MMD' else x for x in a]
if '-MF' in a:p=Path(a[a.index('-MF')+1])
else:p=record;a+=['-MD','-MF',str(p)]
code=subprocess.run(a).returncode
if code:raise SystemExit(code)
record.write_text(p.read_text())
rows={}
for x in shlex.split(p.read_text().replace('\\\n',' ').split(':',1)[1]):
 f=Path(x).resolve()
 if str(f).startswith('/usr/local/') or '/usr/include/gz/sim8/' in str(f):raise SystemExit('installed subject header '+str(f))
 rows[str(f)]=hashlib.sha256(f.read_bytes()).hexdigest()
record.with_suffix('.json').write_text(json.dumps(rows,sort_keys=True)+'\n')
