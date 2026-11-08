"""Post-fixture static resource closure extension; no service or target invocation."""
from common import *
import os,subprocess,re,xml.etree.ElementTree as ET

def main():
 config=Path('/usr/include/gz/sdformat14/sdf/config.hh');text=config.read_text();need('#define SDF_PROTOCOL_VERSION "1.11"' in text,'SDK protocol changed')
 root=Path('/usr/share/sdformat14/1.11');rows=[];owners={};md5={}
 for f in sorted(root.iterdir()):
  need(f.is_file() and not f.is_symlink(),'unexpected schema file kind');owner=subprocess.check_output(['/usr/bin/dpkg-query','-S',str(f)],text=True).strip().split(': /',1)[0]
  if owner not in owners:
   owners[owner]=subprocess.check_output(['/usr/bin/dpkg-query','-W','-f=${binary:Package}\t${Version}\t${Architecture}\t${source:Package}',owner],text=True)
   record=Path(subprocess.check_output(['/usr/bin/dpkg-query','--control-path',owner,'md5sums'],text=True).strip());md5[owner]={s.split(None,1)[1]:s.split(None,1)[0] for s in record.read_text().splitlines()}
  need(hashlib.md5(f.read_bytes()).hexdigest()==md5[owner][str(f).lstrip('/')],'package control mismatch');rows.append({'path':str(f),'sha256':sha(f),'package':owner})
 paths={Path(r['path']).name for r in rows};need('root.sdf' in paths and '1_10.convert' in paths,'current protocol conversion missing')
 edges=[]
 for r in rows:
  if Path(r['path']).suffix not in ('.sdf','.xsd','.convert'):continue
  dom=ET.parse(r['path'])
  for include in dom.iter('include'):
   filename=include.attrib.get('filename')
   if filename:need(filename in paths,'schema include outside selected set '+filename);edges.append({'from':r['path'],'filename':filename})
 p= B/'reports/actual_plan.json';plan=json.loads(p.read_text())
 for r in rows:
  st=os.stat(r['path']);plan['mounts'][r['path']]={'source':r['path'],'real_path':r['path'],'sha256':r['sha256'],'device':st.st_dev,'inode':st.st_ino,'kind':'SDF_1_11_schema_conversion'}
 plan['resolution']['SDF_current_protocol']='1.11';plan['resolution']['schema_extension_files']=len(rows);dump(p,plan)
 from plan import validate,argv
 validate(plan);sources=sorted({r['source'] for r in plan['mounts'].values()});dump(B/'reports/actual_argv.json',{'argv':argv(plan,dict(zip(sources,range(10,10+len(sources))))),'symbolic_FDs':dict(zip(range(10,10+len(sources)),sources))})
 report=json.loads((B/'reports/resources.json').read_text());report['protocol_extension']={'world_version':'1.10','SDK_protocol':'1.11','config_path':str(config),'config_sha256':sha(config),'packages':owners,'files':rows,'schema_include_edges':edges,'distinction':'SDF_PATH in Sim Util.cc handles URI/include resource paths; internal parser schema/conversion lookup is separate. Pin both protocol sets without assuming environment alone controls internal schema initialization.','remaining':'actual sdformat/Fuel failed-open/silent-fallback access attestation still unresolved'};dump(B/'reports/resources.json',report)
 print('PASS pinned',len(rows),'protocol1.11 files and',len(edges),'schema include edges; dynamic runtime coverage BLOCKED')
if __name__=='__main__':main()
