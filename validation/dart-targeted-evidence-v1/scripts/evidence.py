"""Read-only ELF/package validation; never loads or executes target ELF."""
from pathlib import Path
import hashlib, json, re, struct, subprocess, zlib
ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'work'
def run(args):
 p=subprocess.run(list(map(str,args)),capture_output=True,text=True,timeout=40,env={'PATH':'/usr/bin:/bin','LC_ALL':'C'})
 return {'rc':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
def sha(path):
 with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(name,data):
 (ROOT/'reports'/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
def paragraphs(text):
 result=[]
 for block in re.split(r'\n\s*\n',text.strip()):
  row={}; key=None
  for line in block.splitlines():
   if line.startswith((' ','\t')):
    if key is None:raise ValueError('orphan continuation')
    row[key]+='\n'+line[1:]
   else:
    if ':' not in line:raise ValueError('invalid control field')
    key,value=line.split(':',1);value=value.lstrip(' ')
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9-]*',key) or key in row:raise ValueError('duplicate/invalid field')
    row[key]=value
  if row:result.append(row)
 return result
def build_id(text):
 ids=re.findall(r'Build ID:\s*([0-9a-fA-F]+)\b',text)
 if len(set(ids))!=1 or len(ids[0])%2 or len(ids[0])<8:raise ValueError('missing/ambiguous build ID')
 return ids[0].lower()
def section_bytes(data,wanted):
 if len(data)<64 or data[:6]!=b'\x7fELF\x02\x01':raise ValueError('only ELF64 little endian supported')
 offset=struct.unpack_from('<Q',data,40)[0]; size,count,names=struct.unpack_from('<HHH',data,58)
 if size!=64 or count==0 or names>=count or offset+size*count>len(data):raise ValueError('invalid section table')
 headers=[struct.unpack_from('<IIQQQQIIQQ',data,offset+i*size) for i in range(count)]
 nh=headers[names];strings=data[nh[4]:nh[4]+nh[5]]
 for h in headers:
  if h[0]>=len(strings):raise ValueError('invalid name index')
  end=strings.find(b'\0',h[0])
  if end<0:raise ValueError('unterminated section name')
  if strings[h[0]:end].decode('ascii')==wanted:
   if h[4]+h[5]>len(data):raise ValueError('section outside file')
   return data[h[4]:h[4]+h[5]]
 return None
def debuglink(data):
 end=data.find(b'\0')
 if end<=0:raise ValueError('invalid debuglink filename')
 name=data[:end].decode('utf-8'); offset=(end+4)&~3
 if Path(name).name!=name or name in ('.','..') or '\\' in name or offset+4!=len(data):raise ValueError('unsafe/truncated debuglink')
 return name,struct.unpack_from('<I',data,offset)[0]
def crc_match(path,crc):return zlib.crc32(Path(path).read_bytes())&0xffffffff==crc
def validate_path(path,roots):
 p=Path(path).resolve(strict=True)
 if not p.is_file() or not any(p.is_relative_to(Path(r).resolve()) for r in roots):raise ValueError('path outside allowed roots')
 return p
def official_url(url):
 from urllib.parse import urlsplit
 u=urlsplit(url)
 return u.scheme=='https' and u.hostname in {'packages.osrfoundation.org','debuginfod.ubuntu.com','ddebs.ubuntu.com','archive.ubuntu.com'} and not u.username and not u.password and u.port in (None,443)
def classify(target_id,candidate_id,has_dwarf):
 if not candidate_id:return 'DEBUG_NOT_FOUND'
 if candidate_id!=target_id:return 'MISMATCHED_BUILD'
 return 'EXACT_BUILD_ID_DEBUG_FOUND' if has_dwarf else 'PARTIAL_DEBUG_FOUND'
def elf(path):
 p=validate_path(path,['/usr/lib','/tmp/AeroAIStudio-dart-internal-trace'])
 notes=run(['readelf','-n',p]);dynamic=run(['readelf','-d',p]);sections=run(['readelf','-SW',p])
 if any(x['rc'] for x in [notes,dynamic,sections]):raise ValueError('readelf rejected file')
 def tags(tag):return re.findall(r'\('+tag+r'\).*?\[(.*?)\]',dynamic['stdout'])
 sec=sections['stdout'];dl=section_bytes(p.read_bytes(),'.gnu_debuglink')
 return dict(real_path=str(p),sha256=sha(p),build_id=build_id(notes['stdout']),soname=tags('SONAME'),needed=tags('NEEDED'),rpath=tags('RPATH'),runpath=tags('RUNPATH'),has_debug_info=bool(re.search(r'\s\.debug_info\s',sec)),has_symtab=bool(re.search(r'\s\.symtab\s',sec)),debuglink=dict(zip(['filename','crc32'],debuglink(dl))) if dl is not None else None)
