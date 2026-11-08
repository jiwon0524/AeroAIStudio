from pathlib import Path
import hashlib,json,subprocess,re
root=Path(__file__).resolve().parents[1]; rows=[]
for name in ['libode8t64','libbullet3.24t64','libbullet-dev']:
 base=root/'work/extracted'/name
 mismatches=[]; checked=0; files=[]
 for p in sorted((base/'usr').rglob('*')):
  if p.is_file() and not p.is_symlink():
   host=Path('/')/p.relative_to(base)
   if '/lib/' in str(p) or '/include/' in str(p):
    a=hashlib.sha256(p.read_bytes()).hexdigest()
    b=hashlib.sha256(host.read_bytes()).hexdigest() if host.is_file() else None
    files.append({'relative':str(p.relative_to(base)),'sha256':a,'host_sha256':b})
    checked+=1
    if a!=b:mismatches.append(str(host))
 rows.append({'package':name,'checked':checked,'mismatches':mismatches,'files':files})
(root/'reports/package_bytes.json').write_text(json.dumps(rows,indent=2)+'\n')
elfs=['/usr/lib/x86_64-linux-gnu/libode.so.8','/usr/lib/x86_64-linux-gnu/libBulletCollision.so.3.24','/usr/lib/x86_64-linux-gnu/libLinearMath.so.3.24']
elfrows=[]
for name in elfs:
 p=Path(name).resolve()
 elfrows.append({'path':name,'realpath':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'static_dynamic_notes_versions':subprocess.check_output(['readelf','-d','-n','-V',str(p)],text=True),'precision_symbols':subprocess.check_output(['nm','-D','-C',str(p)],text=True) if 'BulletCollision' in name else ''})
(root/'work/external_elf_raw.json').write_text(json.dumps(elfrows,indent=2)+'\n')
for row in elfrows:
 raw=row.pop('static_dynamic_notes_versions')
 row['needed']=re.findall(r'Shared library: \[(.*?)\]',raw)
 row['soname']=re.findall(r'Library soname: \[(.*?)\]',raw)
 row['build_id']=re.findall(r'Build ID: ([a-f0-9]+)',raw)
 row['symbol_versions']=sorted(set(re.findall(r'(?:GLIBCXX|GLIBC|CXXABI)_[0-9.]+',raw)))
 row['precision_symbols']=[x for x in row['precision_symbols'].splitlines() if 'btStaticPlaneShape::btStaticPlaneShape' in x]
(root/'reports/external_elf.json').write_text(json.dumps(elfrows,indent=2)+'\n')
print([(x['package'],x['checked'],len(x['mismatches'])) for x in rows])
print(elfrows[1]['precision_symbols'])
