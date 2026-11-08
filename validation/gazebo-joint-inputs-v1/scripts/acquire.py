import hashlib,json,subprocess,urllib.request,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
rows=json.loads((root/'reports/packages.json').read_text()) if (root/'reports/packages.json').exists() else []
for name in (sys.argv[1:] or ['libode-dev','libode8t64','libbullet-dev','libbullet3.24t64']):
 raw=subprocess.check_output(['apt-cache','show',name],text=True)
 fields={line.split(': ',1)[0]:line.split(': ',1)[1] for line in raw.splitlines() if ': ' in line and not line.startswith(' ')}
 url='https://archive.ubuntu.com/ubuntu/'+fields['Filename']
 p=root/'work/downloads'/Path(fields['Filename']).name
 data=urllib.request.urlopen(url,timeout=45).read()
 sha=hashlib.sha256(data).hexdigest()
 if sha!=fields['SHA256']: raise RuntimeError('hash mismatch '+name)
 p.write_bytes(data)
 dst=root/'work/extracted'/name; dst.mkdir(exist_ok=True)
 subprocess.run(['dpkg-deb','--extract',str(p),str(dst)],check=True)
 rows=[row for row in rows if row['package']!=name]
 rows.append({'package':name,'version':fields['Version'],'architecture':fields['Architecture'],'source':fields.get('Source'),'depends':fields.get('Depends'),'url':url,'sha256':sha,'index_sha256':fields['SHA256'],'archive':str(p.relative_to(Path.cwd())),'extracted':str(dst.relative_to(Path.cwd()))})
 (root/'reports/packages.json').write_text(json.dumps(rows,indent=2)+'\n')
 print(name,sha,flush=True)
