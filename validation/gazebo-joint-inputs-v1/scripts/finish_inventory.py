from pathlib import Path
import hashlib,json,subprocess
r=Path(__file__).resolve().parents[1]
packages=json.loads((r/'reports/packages.json').read_text()); deps=r/'work/deps';deps.mkdir(exist_ok=True)
for row in packages:
 subprocess.run(['dpkg-deb','--extract',row['archive'],str(deps)],check=True)
# Extracted packages remain immutable. Relocated pkgconfig copies are separate.
pcdir=r/'inputs/pkgconfig';pcdir.mkdir(exist_ok=True)
for p in (deps/'usr/lib/x86_64-linux-gnu/pkgconfig').glob('*.pc'):
 text=p.read_text().replace('prefix=/usr','prefix='+str(deps/'usr'))
 (pcdir/p.name).write_text(text)
file_rows=[]
for p in sorted(deps.rglob('*')):
 if p.is_symlink():file_rows.append({'path':str(p.relative_to(r)),'symlink':str(p.readlink())})
 elif p.is_file():file_rows.append({'path':str(p.relative_to(r)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
(r/'reports/dependency_files.json').write_text(json.dumps(file_rows,indent=2)+'\n')
configs=sorted(str(p.relative_to(deps)) for p in deps.rglob('*cmake'))
(r/'reports/dependency_configs.json').write_text(json.dumps(configs,indent=2)+'\n')
print('isolated dependency files',len(file_rows))
print('\n'.join(x for x in configs if 'config' in x.lower() and 'version' not in x.lower()))
