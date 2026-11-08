from pathlib import Path
import json,hashlib,re,subprocess
b=Path.cwd();p=b/'validation/gazebo-joint-codegen-fix-v1';old=b/'validation/gazebo-joint-physics-fix-v1';desc=Path('/usr/share/gz/protos/gz-msgs10.gz_desc')
def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()
def fields(data):
 i=0
 def varint(i):
  value=0;shift=0
  while True:
   x=data[i];i+=1;value|=(x&127)<<shift
   if x<128:return value,i
   shift+=7;assert shift<70
 while i<len(data):
  key,i=varint(i);number=key>>3;wire=key&7
  if wire==2:
   length,i=varint(i);value=data[i:i+length];assert len(value)==length;i+=length;yield number,value
  elif wire==0:_,i=varint(i)
  elif wire in [1,5]:i+=8 if wire==1 else 4
  else:raise ValueError('unsupported descriptor wire type')
files={}
for number,value in fields(desc.read_bytes()):
 if number!=1:continue
 f=list(fields(value));name=next(v.decode() for n,v in f if n==1);assert name not in files;files[name]={'package':next((v.decode() for n,v in f if n==2),''),'imports':[v.decode() for n,v in f if n==3]}
source=old/'work/config-01/src/sim-02/src/proto';private={str(f.relative_to(source)):f for f in source.rglob('*.proto')};imports={n:re.findall(r'^import\s+"([^"]+)"',f.read_text(),re.M) for n,f in private.items()};queue=[x for values in imports.values() for x in values];closure={}
while queue:
 name=queue.pop()
 if name in closure:continue
 if name in private:closure[name]={'kind':'selected source proto','sha256':sha(private[name])};queue+=imports[name]
 else:assert name in files, name;closure[name]={'kind':'embedded descriptor','imports':files[name]['imports']};queue+=files[name]['imports']
lock=json.loads((old/'work/selected_files.json').read_text());controlled=[]
paths=[desc,Path('/usr/lib/x86_64-linux-gnu/libgz-msgs10.so.10.4.0'),Path('/usr/include/gz/msgs10/gz/msgs/config.hh'),Path('/usr/bin/gz-msgs10_generate.py'),Path('/usr/bin/gz-msgs10_generate_factory.py'),Path('/usr/bin/gz-msgs10_protoc_plugin')]
for f in paths:
 owner=subprocess.check_output(['dpkg-query','-S',str(f)],text=True).strip().split(': /',1)[0];meta=subprocess.check_output(['dpkg-query','-W','-f=${binary:Package}\t${Version}\t${Architecture}\t${source:Package}\t${source:Version}',owner],text=True);assert '\t10.4.0-1~noble\tamd64\tgz-msgs10\t10.4.0-1~noble' in meta
 md5file=Path(subprocess.check_output(['dpkg-query','--control-path',owner,'md5sums'],text=True).strip());expected=dict((line.split(None,1)[1],line.split(None,1)[0]) for line in md5file.read_text().splitlines());assert hashlib.md5(f.read_bytes()).hexdigest()==expected[str(f).lstrip('/')]
 if f!=desc:assert lock.get(str(f.resolve()),lock.get(str(f),{})).get('sha256')==sha(f)
 controlled.append({'path':str(f),'sha256':sha(f),'package':meta,'matches_installed_package_md5_record':True,'existing_lock':f!=desc})
report={'status':'PASS_PACKAGE_AND_INPUT_SCOPE','descriptor_source':str(desc),'descriptor_sha256':sha(desc),'descriptor_file_count':len(files),'recursive_imports':closure,'private_proto_files':{str(f):sha(f) for f in private.values()},'correspondence':controlled,'repo_metadata':subprocess.check_output(['apt-cache','policy','libgz-msgs10','libgz-msgs10-dev'],text=True),'provenance_limit':'repository candidates and installed package ownership/control hashes verified; historical installation transaction/archive not reauthenticated','additional_codegen_inputs':'four private source proto files; one embedded-dependency descriptor; four generated pb_index files subsequently read by factory; templates embedded in locked scripts/plugin','scripts_imports':'argparse/os/pathlib/subprocess/sys only; standard interpreter runtime, no third-party Python module dependency'}
(p/'reports/codegen_origin.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'status':report['status'],'descriptor_files':len(files),'import_closure':list(closure),'private_proto_count':len(private)},indent=2))
