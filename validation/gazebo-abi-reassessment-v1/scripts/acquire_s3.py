from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import urllib.request,urllib.parse,hashlib,json,xml.etree.ElementTree as E
root=Path(__file__).resolve().parents[1]; host='https://osrf-distributions.s3.us-east-1.amazonaws.com/'
rows=[]; keys=[]
for prefix in ['gz-physics/releases/gz-physics7_7.8.0','gz-physics/releases/libgz-physics7']:
    marker=''; page=0
    while True:
        url=host+'?'+urllib.parse.urlencode(dict(prefix=prefix,marker=marker,**{'max-keys':1000}))
        data=urllib.request.urlopen(url,timeout=40).read(); name=f's3-{len(rows)}.xml'; (root/'work/downloads'/name).write_bytes(data)
        rows.append(dict(url=url,file='work/downloads/'+name,sha256=hashlib.sha256(data).hexdigest(),bytes=len(data)))
        tree=E.fromstring(data); ns={'s':'http://s3.amazonaws.com/doc/2006-03-01/'}
        found=[v.text for v in tree.findall('.//s:Key',ns)]; keys+=found
        if tree.find('s:IsTruncated',ns).text!='true': break
        marker=found[-1]; page+=1
        assert page<10
chosen=[k for k in keys if '7.8.0-1~noble' in k and (k.endswith(('.dsc','.tar.xz','.buildinfo','.changes')) or ('amd64' in k and any(v in k for v in ['-dbg_','-dartsim_','-core-dev_','-dartsim-dev_','/libgz-physics7_'])))]
def fetch(k):
    url=host+k; data=urllib.request.urlopen(url,timeout=60).read(); name=k.split('/')[-1]; (root/'work/downloads'/name).write_bytes(data)
    return dict(url=url,file='work/downloads/'+name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
with ThreadPoolExecutor(max_workers=4) as pool: rows+=list(pool.map(fetch,chosen))
(root/'reports/s3_acquisition.json').write_text(json.dumps(dict(keys=keys,downloads=rows),indent=2)+'\n')
for r in rows: print(r['file'],r['bytes'])
