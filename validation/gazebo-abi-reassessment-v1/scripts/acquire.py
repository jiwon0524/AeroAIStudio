"""Download evidence only; never execute acquired content."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib,json,urllib.request,urllib.error
ROOT=Path(__file__).resolve().parents[1]
base='https://packages.osrfoundation.org/gazebo/'
urls=[]
for repo in ['ubuntu','ubuntu-stable','ubuntu-prerelease']:
    pool=base+repo+'/pool/main/g/gz-physics7/'
    for name in ['gz-physics7_7.8.0-1~noble.dsc','gz-physics7_7.8.0-1~noble.tar.xz','gz-physics7_7.8.0-1~noble_amd64.buildinfo','gz-physics7_7.8.0-1~noble_amd64.changes','libgz-physics7-dbg_7.8.0-1~noble_amd64.deb']:
        urls.append((repo+'-'+name,pool+name))
urls += [('release.tar.bz2','https://classic.gazebosim.org/distributions/gz-physics/releases/gz-physics-7.8.0.tar.bz2'),('buildfarm-config.json','https://api.github.com/repos/gazebo-tooling/release-tools/contents/jenkins-scripts')]
for ident in ['c53e1a304ceb0f0dac85ff0e4872d0ffc50a28ac','4e60105d86d50ee9e394f6c461411e3cba5eeec1']:
    urls.append((ident+'.debug','https://debuginfod.ubuntu.com/buildid/'+ident+'/debuginfo'))
def get(item):
    name,url=item
    row=dict(url=url,file='work/downloads/'+name)
    try:
        with urllib.request.urlopen(url,timeout=35) as response:
            data=response.read(); row['status']=response.status
        path=ROOT/row['file']; path.write_bytes(data)
        row.update(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
    except Exception as e:
        row['error']=str(e)
    return row
with ThreadPoolExecutor(max_workers=5) as pool:
    rows=list(pool.map(get,urls))
(ROOT/'reports/acquisition.json').write_text(json.dumps(rows,indent=2)+'\n')
for row in rows: print(row['file'],row.get('status',row.get('error')),row.get('bytes',''))
