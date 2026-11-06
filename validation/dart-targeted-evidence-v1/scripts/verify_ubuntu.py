from evidence import *
# Use installed Ubuntu archive trust anchor to authenticate existing APT index before fetching a keyring package.
base=Path('/var/lib/apt/lists');rel=base/'kr.archive.ubuntu.com_ubuntu_dists_noble_InRelease';pkgs=base/'kr.archive.ubuntu.com_ubuntu_dists_noble_main_binary-amd64_Packages';home=WORK/'gpg-empty'
sig=run(['gpgv','--homedir',home,'--keyring','/usr/share/keyrings/ubuntu-archive-keyring.gpg',rel]);assert sig['rc']==0,sig
m=re.search(r'^ ([0-9a-f]{64})\s+(\d+) main/binary-amd64/Packages$',rel.read_text(),re.M);assert m and sha(pkgs)==m[1] and pkgs.stat().st_size==int(m[2])
row=next(x for x in paragraphs(pkgs.read_text()) if x.get('Package')=='ubuntu-dbgsym-keyring')
p=WORK/'ubuntu-dbgsym-keyring.deb';url='https://archive.ubuntu.com/ubuntu/'+row['Filename'];assert official_url(url)
q=run(['curl','--proto','=https','--silent','--show-error','--fail','--max-time','30','--max-filesize',row['Size'],'--output',p,url]);assert q['rc']==0,q
assert sha(p)==row['SHA256'] and p.stat().st_size==int(row['Size'])
d=WORK/'ubuntu-keyring-extracted';d.mkdir(exist_ok=True);assert run(['dpkg-deb','--extract',p,d])['rc']==0
keys=list(d.glob('usr/share/keyrings/*'))
sigargs=['gpgv','--homedir',home]
for key in keys:sigargs+=['--keyring',key]
sigargs += [WORK/'ubuntu-Release.gpg',WORK/'ddebs-http-release'];verified=run(sigargs);assert verified['rc']==0,verified
save('ubuntu_debug_signature.json',dict(ubuntu_apt_release_signature=sig,ubuntu_apt_index_sha256=sha(pkgs),keyring_package=row,keyring_package_url=url,keyring_package_sha256=sha(p),ddebs_release_signature=verified,keys=[{'path':str(k.relative_to(ROOT)),'sha256':sha(k)} for k in keys],system_install=False))
print('Ubuntu debug Release signature verified via authenticated isolated keyring package')
