from common import *
from urllib.parse import quote
version='6.13.2+ds1-1~osrf2~noble'
names=[f'libdart-core+collisions+odelcpsolver6.13-dbgsym_{version}_amd64.ddeb',f'libdart-core+collisions+odelcpsolver6.13-dbgsym_{version}_amd64.deb',f'dart_{version}_amd64.buildinfo']
records=[]
for name in names:
 url='https://packages.osrfoundation.org/gazebo/ubuntu-stable/pool/main/d/dart/'+quote(name,safe='._-~+')
 p=run(['curl','--head','--location','--silent','--show-error','--max-time','20','--output','/dev/null','--write-out','%{http_code}',url]);p['url']=url;records.append(p)
 print(name,p['rc'],p['stdout'],flush=True)
save('original_debug_buildinfo_probe.json',records)
