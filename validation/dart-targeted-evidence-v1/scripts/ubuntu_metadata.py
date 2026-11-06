"""Metadata only, exact official HTTP URLs advertised by official HTTPS redirect.
No packages fetched. Without signature key this is a discovery hint, not ABI proof.
"""
from evidence import *
import lzma
release=WORK/'ddebs-http-release';text=release.read_text()
results=[]
for part in ['universe/binary-amd64/Packages.xz','Release.gpg']:
 url='http://ddebs.ubuntu.com/dists/noble/'+part;p=WORK/('ubuntu-'+Path(part).name)
 q=run(['curl','--proto','=http','--silent','--show-error','--fail','--max-time','30','--max-filesize','6000000','--output',p,url])
 result={'url':url,'rc':q['rc'],'stderr':q['stderr'],'size':p.stat().st_size if p.exists() else None,'sha256':sha(p) if p.exists() else None};results.append(result)
 if q['rc']:continue
 if part.endswith('.xz'):
  m=re.search(r'^ ([0-9a-f]{64})\s+(\d+) '+re.escape(part)+r'$',text,re.M)
  if not m or sha(p)!=m[1] or p.stat().st_size!=int(m[2]):raise ValueError('metadata checksum mismatch')
  rows=paragraphs(lzma.decompress(p.read_bytes()).decode());candidates=[x for x in rows if x.get('Source','').split(' ')[0]=='dart' or x.get('Package','').startswith('libdart')]
  for row in candidates:row['classification']='VERSION_ONLY_MATCH' if row.get('Version','').startswith('6.13.2') else 'SOURCE_UNKNOWN'
  save('ubuntu_debug_candidates.json',{'candidates':candidates,'downloaded_debug_packages':False,'meaning':'Ubuntu package VERSION_ONLY_MATCH; no Build-ID candidate file acquired, no equivalence to OSRF installed build','release_sha256':sha(release),'index_hash_verified_against_release':True,'signature':'see ubuntu_metadata_requests.json; do not infer authenticity from HTTP checksum alone'})
home=WORK/'gpg-empty'
sig=run(['gpgv','--homedir',home,'--keyring','/usr/share/keyrings/ubuntu-archive-keyring.gpg',WORK/'ubuntu-Release.gpg',release])
save('ubuntu_metadata_requests.json',{'requests':results,'release_url':'http://ddebs.ubuntu.com/dists/noble/Release','signature':sig,'trust':'AUTHENTICATED' if sig['rc']==0 else 'SIGNATURE_UNVERIFIED; discovery only, never installed ABI proof'})
print('Ubuntu metadata only',[(r['rc'],r['size']) for r in results],'signature rc',sig['rc'])
