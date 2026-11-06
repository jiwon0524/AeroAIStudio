from common import *
import shutil,re
prefix=R/'work/dependencies'
shutil.copytree(IMPL/'work/headers',prefix,symlinks=True)
records=[]
for p in sorted((R/'downloads').glob('*.deb')):
 fields=run(['dpkg-deb','-f',p,'Package','Version','Architecture'])
 meta=dict(line.split(': ',1) for line in fields['stdout'].splitlines() if ': ' in line)
 info=run(['apt-cache','show',meta['Package']+'='+meta['Version']])
 expected=re.search(r'^SHA256: (\w+)',info['stdout'],re.M).group(1)
 assert sha(p)==expected,(p,expected)
 extraction=run(['dpkg-deb','-x',p,prefix]);assert extraction['rc']==0
 records.append({'file':p.name,'package':meta,'sha256':sha(p),'apt_metadata_sha256_match':True,'apt_metadata':info['stdout'],'extraction_command':extraction['command'],'source':'Ubuntu noble archive via configured apt package index; download/extract only, no install'})
lib=prefix/'usr/lib/x86_64-linux-gnu'
for name in ('libode.so.8','libode.so.8.0.2'):
 p=lib/name
 if not p.exists():p.symlink_to(Path('/usr/lib/x86_64-linux-gnu')/name)
for name in ('fmt','spdlog'):shutil.copytree(Path('/usr/include')/name,prefix/'usr/include'/name)
relocations=[]
for p in prefix.rglob('*.pc'):
 old=p.read_text();new=old.replace('prefix=/usr\n','prefix='+str(prefix/'usr')+'\n')
 if new!=old:
  before=sha(p);p.write_text(new);relocations.append({'file':str(p.relative_to(prefix)),'before_sha256':before,'after_sha256':sha(p),'reason':'Relocate isolated pkg-config prefix only; package files in system are untouched'})
save('dependencies.json',{'packages':records,'pkgconfig_relocations':relocations,'ODE_runtime':'Reuse unchanged installed libode.so.8.0.2 through isolated symlinks','IPOPT_NLOPT_historical_build_versions':'UNVERIFIED; absent installed runtimes. Version-matched Ubuntu noble dev/runtime pairs selected, not claimed to recover historical buildinfo'})
env=os.environ.copy();env['PKG_CONFIG_PATH']=str(lib/'pkgconfig')+':'+str(prefix/'usr/lib/pkgconfig')
save('dependency_detection_probe.json',{n:run(['pkg-config','--modversion','--cflags','--libs',n],env=env) for n in ('ipopt','nlopt','ode')})
env['LD_LIBRARY_PATH']=str(lib)
save('dependency_loader_checks.json',{p.name:run(['ldd','-r',p],env=env) for p in lib.glob('lib*.so*') if p.is_file() and not p.is_symlink() and any(n in p.name for n in ('ipopt','nlopt','mumps','scotch','abigail'))})
print('Verified/extracted',len(records),'packages; relocated',len(relocations),'pkg-config files')
