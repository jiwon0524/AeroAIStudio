"""Finite official-source requests only. No installation, target execution, or global config."""
from evidence import *
import concurrent.futures
BASE='https://packages.osrfoundation.org/gazebo/ubuntu-stable/'
urls=[BASE+'dists/noble/Release',BASE+'dists/noble/main/binary-amd64/Packages',BASE+'dists/noble/main/source/Sources.gz',BASE+'pool/main/d/dart/',BASE+'dists/noble/main/debug/binary-amd64/Packages',BASE+'dists/noble/main/debug/binary-amd64/Packages.gz',BASE+'dists/noble/main/debug/Release']
inv=json.loads((ROOT/'reports/binary_inventory.json').read_text())['binaries']
for row in inv[:4]:urls.append('https://debuginfod.ubuntu.com/buildid/'+row['build_id']+'/debuginfo')
# A finite directory query establishes advertised artifacts; guessed URLs alone cannot prove absence.
urls += ['https://ddebs.ubuntu.com/dists/noble/Release']
def request(pair):
 i,url=pair
 if not official_url(url):raise ValueError('unapproved source')
 path=WORK/f'official-{i:02d}.body';headers=WORK/f'official-{i:02d}.headers'
 args=['curl','--proto','=https','--proto-redir','=https','--silent','--show-error','--connect-timeout','10','--max-time','30','--max-filesize','8388608','--dump-header',str(headers),'--output',str(path),'--write-out','%{http_code}\n%{url_effective}\n%{size_download}',url]
 q=run(args);lines=q['stdout'].splitlines()
 result=dict(url=url,rc=q['rc'],http_status=lines[0] if lines else None,effective_url=lines[1] if len(lines)>1 else None,stderr=q['stderr'],body=str(path.relative_to(ROOT)),sha256=sha(path) if path.exists() else None,size=path.stat().st_size if path.exists() else None,limit_bytes=8388608)
 result['redirect_policy']='No redirects followed; non-200 is not evidence of global absence'
 return result
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:rows=list(pool.map(request,enumerate(urls)))
save('official_requests.json',rows)
for r in rows:print(r['http_status'],r['rc'],r['size'],r['url'])
