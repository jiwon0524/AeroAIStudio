"""Compile/link only; keep all prior sources, objects, ELFs and receipts intact."""
from common import *
import shlex,subprocess,re,os,time,socket
OLD=ROOT/'validation/gazebo-joint-codegen-fix-v1';OLDROOT=OLD/'work/config-01'
allowed={str(Path(k).resolve()):v['sha256'] for k,v in json.loads((OLD/'work/selected_files.json').read_text()).items()}
for row in json.loads((ROOT/'validation/gazebo-joint-inputs-v1/reports/toolchain_files.json').read_text()):allowed[row['realpath']]=row['sha256']
local={str(f.resolve()):sha(f) for f in (B/'inputs').iterdir() if f.is_file()}
records=[]
def run(label,argv,cwd=B/'work'):
 log=B/'logs'/((('deadline.' if sys.argv[1:]==['--deadline-static'] else '')+label)+'.log');need(not log.exists(),'preserve old build log')
 with log.open('x') as out:
  start=time.time();p=subprocess.Popen(argv,cwd=cwd,stdout=out,stderr=subprocess.STDOUT,env={'PATH':'/usr/bin:/bin','LC_ALL':'C'})
  try:ident=Path('/proc',str(p.pid),'stat').read_text().split(') ',1)[1].split()[19]
  except OSError:ident='UNKNOWN'
  rc=p.wait()
 records.append({'label':label,'returncode':rc,'host':socket.gethostname(),'pid':p.pid,'start_identity':ident,'seconds':round(time.time()-start,3),'argv':argv,'log':str(log.relative_to(ROOT)),'sha256':sha(log)})
 dump(B/'reports/build_steps.json',records);need(rc==0,'build failed '+label)
def audit(dep):
 fields=shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1]);files={}
 for f in fields:
  path=(Path(f) if Path(f).is_absolute() else B/'work'/f).resolve();name=str(path)
  need(not name.startswith('/usr/local/'),'local header')
  if name in local:need(sha(path)==local[name],'changed exact new input')
  elif path.is_relative_to(OLDROOT) or path.is_relative_to(OLD/'inputs'):pass
  else:
   need(not re.search(r'/include/(?:dart|gz/(?:physics7|sim8))(?:/|$)',name),'installed subject header')
   need(allowed.get(name)==sha(path),'unlocked header '+name)
  files[name]=sha(path)
 return files
# Original pinned flags and selected link operands; only source/object/output change.
row=json.loads((OLDROOT/'build/harness/compile_commands.json').read_text())[0];argv=shlex.split(row['command']);argv[argv.index('-c')+1]=str(B/'inputs/harness_ack.cc');argv[argv.index('-o')+1]=str(B/'work/harness_ack.o');argv += ['-MD','-MF',str(B/'work/harness_ack.d')]
need(sha(Path(argv[0]).resolve())==allowed[str(Path(argv[0]).resolve())],'compiler SHA')
need(not re.search(r'-march=native|-mavx|-fno-rtti|-fno-exceptions|_GLIBCXX_USE_CXX11_ABI=0',' '.join(argv)),'ABI option')
run('harness.compile',argv);harness_headers=audit(B/'work/harness_ack.d')
text=subprocess.check_output(['/usr/bin/ninja','-C',str(OLDROOT/'build/harness'),'-t','commands','aero-joint-harness'],text=True)
link=shlex.split(text.splitlines()[-1].split('&&')[1].strip());link=[str(B/'work/harness_ack.o') if t=='CMakeFiles/aero-joint-harness.dir/harness.cc.o' else t for t in link];link[link.index('-o')+1]=str(B/'work/aero-joint-harness-ack')
run('harness.link',link)
run('harmless.compile',['/usr/bin/x86_64-linux-gnu-gcc-13','-std=c17','-O2','-Wall','-Wextra','-Werror','-fPIE','-pie','-Wl,-z,relro,-z,now','-MD','-MF',str(B/'work/harmless.d'),str(B/'inputs/harmless.c'),'-o',str(B/'work/harmless')]);fixture_headers=audit(B/'work/harmless.d')
elfs={}
for f in [B/'work/aero-joint-harness-ack',B/'work/harmless']:
 meta=subprocess.check_output(['/usr/bin/readelf','-h','-d','-l','-n',str(f)],text=True);fd=os.open(f,os.O_RDONLY)
 try:identity_row=identity.describe_fd(fd)
 finally:os.close(fd)
 needed=re.findall(r'Shared library: \[(.*?)\]',meta)
 if f.name=='harmless':need(needed==['libc.so.6'],'harmless must be libc-only')
 elfs[str(f)]={**identity_row,'needed':needed,'metadata':meta}
dump(B/'reports/build.json',{'status':'PASS_COMPILE_LINK_STATIC_ONLY','local_input_hashes':local,'harness_headers':harness_headers,'harmless_headers':fixture_headers,'ELFs':elfs,'subject_execution':False,'fixture_execution':False})
print('PASS ACK harness and harmless fixture build/static; no target executed')
