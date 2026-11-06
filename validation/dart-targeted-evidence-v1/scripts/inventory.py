from evidence import *
EXP=ROOT.parents[1]
V4=EXP/'validation/dart-destructor-cleanup-v4/reports/verdict.json'
old=json.loads(V4.read_text())['binary_identifiers']
paths={'installed_core':'/usr/lib/x86_64-linux-gnu/libdart.so.6.13','installed_external':'/usr/lib/x86_64-linux-gnu/libdart-external-odelcpsolver.so.6.13','installed_bullet':'/usr/lib/x86_64-linux-gnu/libdart-collision-bullet.so.6.13','gazebo_consumer':'/usr/lib/x86_64-linux-gnu/gz-physics-7/engine-plugins/libgz-physics7-dartsim-plugin.so.7.8.0','baseline_core':old['B']['path'],'trace_core':old['C']['path']}
rows=[]
for name,path in paths.items():
 p=Path(path);e=elf(p);e.update(role=name,requested_path=str(p),is_symlink=p.is_symlink(),link_target=str(p.readlink()) if p.is_symlink() else None)
 e['aliases']=[str(q) for q in [p,p.resolve()] if q.exists()]
 if name=='gazebo_consumer':
  q=Path('/usr/lib/x86_64-linux-gnu/libgz-physics7-dartsim-plugin.so.7.8.0');e['aliases'].append(str(q));e['alias_hash_match']=sha(q)==e['sha256']
 match={'installed_core':'A','installed_bullet':'Bullet','baseline_core':'B','trace_core':'C'}.get(name)
 e['v4_comparison']={'recorded':match,'hash_match':e['sha256']==old[match]['sha256'],'build_id_match':e['build_id']==old[match]['build_id']} if match else {'recorded':None,'status':'not in V4 verdict identifiers'}
 owner=run(['dpkg-query','-S',e['real_path']]);e['package_owner_query']=owner
 if owner['rc']==0:
  package=owner['stdout'].split(': /',1)[0];q=run(['dpkg-query','-s',package]);e['package']=paragraphs(q['stdout'])[0];e['apt_policy']=run(['apt-cache','policy',package])['stdout'];e['apt_metadata']=paragraphs(run(['apt-cache','show',package])['stdout'])
  e['origin']='OSRF candidate metadata/policy; historical installation transaction origin UNKNOWN'
 else:e.update(package=None,origin='local isolated build; not an installed package',architecture='ELF64 x86-64 local build; amd64')
 e['local_debug_candidates']=[]
 bid=e['build_id']; candidates=[Path('/usr/lib/debug/.build-id')/bid[:2]/(bid[2:]+'.debug'),Path('/usr/lib/debug')/Path(e['real_path']).relative_to('/')]
 if e['debuglink']:
  dl=e['debuglink']['filename'];candidates += [p.resolve().parent/dl,p.resolve().parent/'.debug'/dl,Path('/usr/lib/debug')/p.resolve().parent.relative_to('/')/dl]
 for c in candidates:
  item={'path':str(c),'exists':c.is_file()}
  if c.is_file():
   info=elf(c);item.update(info);item['classification']=classify(bid,info['build_id'],info['has_debug_info']);item['crc_match']=crc_match(c,e['debuglink']['crc32']) if e['debuglink'] else None
  e['local_debug_candidates'].append(item)
 rows.append(e)
save('binary_inventory.json',{'unique_elf_count':len({r['real_path'] for r in rows}),'binaries':rows})
debugpkgs=run(['dpkg-query','-W','-f=${Package}\t${Version}\t${Architecture}\t${Status}\n','*dart*','*dbgsym*','*dbg']);(WORK/'local_package_query.txt').write_text(debugpkgs['stdout']+debugpkgs['stderr'])
cache=[str(p) for p in Path('/var/cache/apt/archives').glob('*') if re.search(r'dart|dbgsym|\.ddeb$',p.name)]
save('local_search.json',dict(scope='explicit ELF debug paths, dpkg installed package inventory, /var/cache/apt/archives filenames only',apt_cache_candidates=cache,local_debug_packages=[line for line in debugpkgs['stdout'].splitlines() if 'install ok installed' in line and re.search(r'dart.*(?:dbg|dbgsym)|(?:dbg|dbgsym).*dart',line)],raw_query='work/local_package_query.txt'))
print([(x['role'],x['build_id'],x['debuglink'],x['has_debug_info']) for x in rows])
