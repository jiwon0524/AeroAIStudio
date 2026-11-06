from evidence import *
import gzip,tarfile
BASE='https://packages.osrfoundation.org/gazebo/ubuntu-stable/'
def get(url,name,limit=8388608):
 if not official_url(url):raise ValueError('unapproved source')
 p=WORK/name
 q=run(['curl','--proto','=https','--silent','--show-error','--fail','--max-time','30','--max-filesize',str(limit),'--output',p,url])
 if q['rc']:raise RuntimeError(q)
 return p
release=get(BASE+'dists/noble/InRelease','InRelease')
home=WORK/'gpg-empty';home.mkdir(exist_ok=True,mode=0o700)
sig=run(['gpgv','--homedir',home,'--keyring','/usr/share/keyrings/pkgs-osrf-archive-keyring.gpg',release]);save('repository_signature.json',sig)
if sig['rc']:raise ValueError('repository signature verification failed')
r=release.read_text()
for filename,local in [('main/binary-amd64/Packages','official-01.body'),('main/source/Sources.gz','official-02.body')]:
 m=re.search(r'^ ([0-9a-f]{64})\s+(\d+) '+re.escape(filename)+r'$',r,re.M)
 if not m or sha(WORK/local)!=m[1] or (WORK/local).stat().st_size!=int(m[2]):raise ValueError('index hash/size mismatch')
packages=paragraphs((WORK/'official-01.body').read_text());sources=paragraphs(gzip.decompress((WORK/'official-02.body').read_bytes()).decode())
package=next(x for x in packages if x.get('Package')=='libdart-core+collisions+odelcpsolver6.13' and x.get('Version')=='6.13.2+ds1-1~osrf2~noble' and x.get('Architecture')=='amd64')
src=next(x for x in sources if x.get('Package')=='dart' and x.get('Version')==package['Version'])
save('official_metadata.json',{'package':package,'source':src,'dart_debug_packages':[x for x in packages if 'dart' in x.get('Package','') and re.search('dbg|debug',x.get('Package',''))],'index_signature_verified':True,'index_hashes_verified':True})
p=get(BASE+package['Filename'],'runtime-reference.deb',int(package['Size']))
if p.stat().st_size!=int(package['Size']) or sha(p)!=package['SHA256']:raise ValueError('package checksum mismatch')
extract=WORK/'runtime-reference';extract.mkdir(exist_ok=True)
q=run(['dpkg-deb','--extract',p,extract]);assert q['rc']==0,q
inventory=json.loads((ROOT/'reports/binary_inventory.json').read_text())['binaries'];matches=[]
for row in inventory[:3]:
 ref=extract/Path(row['real_path']).relative_to('/');info=elf(ref)
 matches.append(dict(role=row['role'],installed_path=row['real_path'],reference=info,sha256_match=row['sha256']==info['sha256'],build_id_match=row['build_id']==info['build_id'],package_sha256=package['SHA256']))
save('official_binary_matches.json',matches)
# Only small signed-source-index-listed packaging files; no rebuild or original source archive download.
items=[]
for line in src['Checksums-Sha256'].splitlines():
 parts=line.split()
 if len(parts)!=3:continue
 digest,size,name=parts
 if not name.endswith(('.dsc','.debian.tar.xz')):continue
 p=get(BASE+src['Directory']+'/'+name,name,int(size))
 if p.stat().st_size!=int(size) or sha(p)!=digest:raise ValueError('source checksum mismatch')
 item=dict(file=name,size=int(size),sha256=digest)
 if name.endswith('.debian.tar.xz'):
  with tarfile.open(p) as tf:
   members=[m for m in tf.getmembers() if m.name in ['debian/rules','debian/control','debian/changelog']]
   for member in members:
    if not member.isfile() or member.size>1048576:raise ValueError('invalid source member')
    (WORK/('packaging-'+Path(member.name).name)).write_bytes(tf.extractfile(member).read())
 items.append(item)
save('source_acquisition.json',{'files':items,'original_source_archive':'metadata only, not downloaded; no rebuild','packaging_only':True})
print('signed indices verified; exact installed runtime package matched',[(x['role'],x['sha256_match']) for x in matches])
