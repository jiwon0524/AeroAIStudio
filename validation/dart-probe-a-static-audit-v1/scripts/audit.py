"""ELF bytes/tools only. Never runs target ELF or a dynamic loader."""
import collections,gzip,hashlib,importlib.util,json,os,re,struct,subprocess
from pathlib import Path
B=Path(__file__).resolve().parents[1];ROOT=B.parents[1];R=B/'reports';W=B/'work'
spec=importlib.util.spec_from_file_location('prior_evidence',ROOT/'validation/dart-targeted-evidence-v1/scripts/evidence.py');prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)

def put(name,x):(R/name).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def run(args):
    p=subprocess.run(args,capture_output=True,text=True,timeout=40,env={'PATH':'/usr/bin:/bin','LC_ALL':'C'})
    if p.returncode:raise RuntimeError('static tool failed '+str(args[:2])+': '+p.stderr[:200])
    return p.stdout

def search_parts(values):
    return [{'raw':value,'components':[{'value':s,'empty_cwd':s=='','relative':bool(s) and not s.startswith('/') and '$ORIGIN' not in s and '${ORIGIN}' not in s,'origin':'$ORIGIN' in s or '${ORIGIN}' in s,'other_token':'$' in s and '$ORIGIN' not in s and '${ORIGIN}' not in s} for s in value.split(':')]} for value in values]

def sections(path):
    data=path.read_bytes()
    if data[:6]!=b'\x7fELF\x02\x01':raise ValueError('expected ELF64LE')
    off=struct.unpack_from('<Q',data,40)[0];size,count,names=struct.unpack_from('<HHH',data,58)
    if size!=64 or not count or names>=count or off+size*count>len(data):raise ValueError('section bounds')
    hs=[struct.unpack_from('<IIQQQQIIQQ',data,off+i*size) for i in range(count)];h=hs[names];strings=data[h[4]:h[4]+h[5]];out={}
    for h in hs:
        end=strings.find(b'\0',h[0]);name=strings[h[0]:end].decode('ascii')
        if name in ('.init_array','.fini_array','.preinit_array','.tdata','.tbss','.eh_frame','.gcc_except_table'):
            row={'address':h[3],'size_bytes':h[5],'section_type':h[1]}
            if name.endswith('_array'):
                if h[5]%8 or h[4]+h[5]>len(data):raise ValueError('array bounds')
                row['file_pointer_values']=[hex(x[0]) for x in struct.iter_unpack('<Q',data[h[4]:h[4]+h[5]])]
                row['pointer_values_not_runtime_addresses']=True
            out[name]=row
    return out

def elf(path):
    p=Path(path);row={'requested_path':str(p),'exists':p.exists(),'is_symlink':p.is_symlink(),'link_target':os.readlink(p) if p.is_symlink() else None}
    if not p.exists():return row
    row.update(prior.elf(p));header=run(['/usr/bin/readelf','-hW',str(p)])
    row['architecture']=re.search(r'Machine:\s*(.*)',header).group(1).strip();row['elf_class']=re.search(r'Class:\s*(.*)',header).group(1).strip()
    row['stat']={'bytes':p.stat().st_size,'mode':oct(p.stat().st_mode & 0o777),'uid':p.stat().st_uid}
    row['special_sections']=sections(p.resolve());dyn=run(['/usr/bin/readelf','-dW',str(p)]);syms=run(['/usr/bin/readelf','--dyn-syms','-W',str(p)])
    row['flags']=[line.strip() for line in dyn.splitlines() if any('('+x+')' in line for x in ('FLAGS','FLAGS_1','INIT','FINI','INIT_ARRAY','FINI_ARRAY'))]
    row['ifunc_count']=sum(' IFUNC ' in line for line in syms.splitlines());row['gnu_unique_count']=sum(' UNIQUE ' in line for line in syms.splitlines())
    row['lifetime_imports']=[re.search(r'\bUND\s+(\S+)',line).group(1) for line in syms.splitlines() if ' UND ' in line and any(x in line for x in ('__cxa_atexit','__cxa_finalize','__cxa_thread_atexit','__cxa_throw','_Unwind','malloc','free','pthread_create','dlopen'))]
    return row

def cache_map(text):
    out=collections.defaultdict(list)
    for line in text.splitlines():
        m=re.match(r'\s*(\S+) \(([^)]*)\) => (.+)',line)
        if m and 'x86-64' in m[2]:out[m[1]].append(m[3])
    return dict(out)

def candidates(name,cache):
    paths=[]
    for p in cache.get(name,[])+['/usr/lib/x86_64-linux-gnu/'+name,'/lib/x86_64-linux-gnu/'+name]:
        p=Path(p)
        if p.exists() and str(p.resolve()) not in [x['real_path'] for x in paths]:paths.append({'requested_path':str(p),'real_path':str(p.resolve()),'is_symlink':p.is_symlink(),'link_target':os.readlink(p) if p.is_symlink() else None})
    return paths

def main():
    arms=json.loads((ROOT/'validation/dart-targeted-evidence-v1/reports/probe_library_arms.json').read_text());inventory=[]
    for arm,entry in arms.items():
        for old in entry['libraries']:
            row=elf(old.get('real_path',old.get('path')));row['arm']=arm
            if old.get('sha256'):row['historical_sha_match']=row.get('sha256')==old['sha256'];row['historical_build_id_match']=row.get('build_id')==old['build_id']
            inventory.append(row)
    # The old expected B/C lib/ location stays missing. Locate, do not relocate, actual external artifact.
    for variant in ('baseline','trace'):
        p=ROOT/f'validation/dart-capability-abi-v2/work/build-{variant}-final/dart/external/odelcpsolver/libdart-external-odelcpsolver.so.6.13.2'
        row=elf(p);row['role']='located_'+variant+'_external';inventory.append(row)
    cache_text=run(['/sbin/ldconfig','-p']);cache=cache_map(cache_text)
    (W/'ldconfig-p.txt').write_text(cache_text)
    core='/usr/lib/x86_64-linux-gnu/libdart.so.6.13.2';nodes={};edges=[];queue=collections.deque([core]);missing=[];ambiguous=[]
    while queue:
        p=str(Path(queue.popleft()).resolve())
        if p in nodes:continue
        row=elf(p);nodes[p]=row
        for name in row['needed']:
            cs=candidates(name,cache);edge={'parent':p,'needed':name,'candidates':cs,'resolution':'STATIC_CANDIDATE_NOT_RUNTIME_RESOLVED'};edges.append(edge)
            if not cs:missing.append(edge)
            elif len(cs)>1:ambiguous.append(edge)
            for c in cs:queue.append(c['real_path'])
    optional_nodes={};optional_edges=[]
    q=collections.deque(['/usr/lib/x86_64-linux-gnu/libdart-collision-bullet.so.6.13.2','/usr/lib/x86_64-linux-gnu/libdart-collision-ode.so.6.13.2'])
    while q:
        p=str(Path(q.popleft()).resolve())
        if p in optional_nodes or p in nodes:continue
        row=elf(p);optional_nodes[p]=row
        for name in row['needed']:
            cs=candidates(name,cache);optional_edges.append({'parent':p,'needed':name,'candidates':cs})
            for c in cs:q.append(c['real_path'])
    put('optional_collision_dependencies.json',{'nodes':optional_nodes,'edges':optional_edges,'not_in_core_DT_NEEDED':True,'probe_A_core_only_excludes_explicit_collision_plugin_load':True})
    put('elf_identity.json',{'inventory':inventory,'A_core_sha256':nodes[core]['sha256'],'A_core_build_id':nodes[core]['build_id'],'target_libraries_executed':False})
    put('dependency_audit.json',{'root':core,'nodes':nodes,'edges':edges,'node_count':len(nodes),'missing':missing,'ambiguous':ambiguous,'method':'ldconfig -p cache metadata + canonical existing default-path candidates; no ldd/no target execution','runtime_resolution':'UNVERIFIED','closure_scope':'DT_NEEDED only, not constructor dlopen, optional plugins or NSS/gconv','cache_sha256':prior.sha('/etc/ld.so.cache'),'same_name_cache_entries':{k:v for k,v in cache.items() if len(v)>1 and any(e['needed']==k for e in edges)}})
    put('runpath_audit.json',{'libraries':[{'path':r['real_path'],'arm':r.get('arm'),'rpath':search_parts(r['rpath']),'runpath':search_parts(r['runpath'])} for r in inventory if r['exists']],'closure_runpaths':[{'path':p,'rpath':search_parts(r['rpath']),'runpath':search_parts(r['runpath'])} for p,r in nodes.items() if r['rpath'] or r['runpath']],'absolute_root_does_not_pin_transitive_dependencies':True,'loader_execution':False})
    init=[]
    for path,row in nodes.items():
        init.append({'path':path,'sections':row['special_sections'],'flags':row['flags'],'ifunc_count':row['ifunc_count'],'gnu_unique_count':row['gnu_unique_count'],'lifetime_imports':row['lifetime_imports'],'callback_semantics':'UNVERIFIED'})
    put('initialization_risks.json',{'libraries':init,'global_constructor_semantics':'UNVERIFIED','dlclose_unmaps_all':'NOT_GUARANTEED','cross_module_allocator_EH':'UNVERIFIED','direct_DART_object_creation':'PROHIBITED','implicit_global_initialization_on_future_dlopen':'POSSIBLE_UNVERIFIED'})
    docs={}
    for path in ('/usr/share/man/man8/ld.so.8.gz','/usr/share/man/man3/dlopen.3.gz'):
        raw=Path(path).read_bytes();text=gzip.decompress(raw).decode();docs[path]={'sha256':hashlib.sha256(raw).hexdigest(),'lines':len(text.splitlines())}
    put('loader_documentation.json',{'installed_manuals':docs,'references':['https://man7.org/linux/man-pages/man8/ld.so.8.html','https://man7.org/linux/man-pages/man3/dlopen.3.html'],'rules':['slash in target pathname selects pathname, DT_NEEDED recursively resolved separately','DT_RPATH used if DT_RUNPATH absent; RUNPATH applies to direct dependencies, unlike inherited RPATH','environment library paths, cache, defaults and hwcaps influence resolution','empty path elements can denote cwd; $ORIGIN expands relative to containing ELF','constructors execute before dlopen returns; close decrements refcount and may execute finalizers; close success does not prove unmap','TLS, GNU_UNIQUE/NODELETE and references can extend lifetimes'],'no_dynamic_loader_invoked':True})
    # Keep bounded actual disassembly and relocations for core init/fini; no symbol-name invention.
    pointers=nodes[core]['special_sections']['.init_array']['file_pointer_values']+nodes[core]['special_sections']['.fini_array']['file_pointer_values']
    snippets=[]
    relocs=run(['/usr/bin/readelf','-rW',core]);arrs=[nodes[core]['special_sections'][k] for k in ('.init_array','.fini_array')]
    snippets.append('\n'.join(line for line in relocs.splitlines() if re.match(r'^[0-9a-f]+',line.strip()) and any(a['address']<=int(line.split()[0],16)<a['address']+a['size_bytes'] for a in arrs)))
    for pointer in pointers:
        n=int(pointer,16);snippets.append(run(['/usr/bin/objdump','-dC','--start-address='+hex(n),'--stop-address='+hex(n+192),core]))
    raw_disassembly='\n'.join(snippets)
    (W/'core_init_fini_disassembly_raw.txt').write_text(raw_disassembly)
    (R/'core_init_fini_disassembly.txt').write_text('\n'.join(line.rstrip() for line in raw_disassembly.splitlines())+'\n')
    print(json.dumps({'inventory':len(inventory),'closure_nodes':len(nodes),'edges':len(edges),'missing':len(missing),'ambiguous':len(ambiguous)}))
if __name__=='__main__':main()
