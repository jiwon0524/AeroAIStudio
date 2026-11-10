"""Generate compile-time path/hash policy and resource facts. Read-only inputs.
Does not prepare copies, change limits, mount, load, fork or execute targets.
"""
from pathlib import Path
import hashlib,importlib.util,json,os,struct
R=Path(__file__).resolve().parents[1]
p=R.parent/'gazebo-request-guard-v4/scripts/inputs.py'
s=importlib.util.spec_from_file_location('v4_inputs',p);old=importlib.util.module_from_spec(s);s.loader.exec_module(old)

def segments(path):
    with open(path,'rb') as f:
        h=f.read(64)
        if h[:6]!=b'\x7fELF\x02\x01':raise ValueError('ELF64 LE required')
        off=struct.unpack_from('<Q',h,32)[0];width,count=struct.unpack_from('<HH',h,54)
        if width!=56 or count>256:raise ValueError('ELF program header bounds')
        result=[]
        for i in range(count):
            f.seek(off+i*width);row=f.read(width)
            if len(row)!=width:raise ValueError('truncated program header')
            if struct.unpack_from('<I',row)[0]==1:
                result.append(dict(filesz=struct.unpack_from('<Q',row,32)[0],memsz=struct.unpack_from('<Q',row,40)[0]))
        return result

def generate():
    c,m,prior,seal=old.load_verified();records=old.classify(m,prior)
    prepared=[r for r in records if r['required'] and r['prepared']]
    lines=['/* Generated from sealed original hash policy; copied inodes are run-specific. */']
    for r in prepared:
        o=r['original']
        for path in sorted(r['aliases']):
            lines.append('{'+','.join([json.dumps(path),str(o['device'])+'ULL',str(o['inode'])+'ULL',
                json.dumps(o['sha256']),str(int(r['executable'])),json.dumps(m['mounts'][path]['source'])])+'},')
    (R/'inputs/allowlist.inc').write_text('\n'.join(lines)+'\n')
    required_paths=sum(len(r['aliases']) for r in records if r['required'])
    header='#define COMPILED_PATHS '+str(len(lines)-1)+'\n#define FULL_REQUIRED_PATHS '+str(required_paths)+'\n'
    for key,role in [('TARGET_EXECUTABLE','harness'),('TARGET_PHYSICS','physics'),('TARGET_DARTSIM','dartsim')]:
        header+='#define '+key+' '+json.dumps(m['roles'][role])+'\n'
    (R/'inputs/policy_counts.h').write_text(header)
    args=m['ordered_bwrap_argv'];env=[]
    for i,word in enumerate(args):
        if word=='--setenv':env.append(json.dumps(args[i+1]+'='+args[i+2])+',')
    (R/'inputs/target_env.inc').write_text('\n'.join(env)+'\n')
    page=os.sysconf('SC_PAGE_SIZE');roundup=lambda n:(n+page-1)//page*page
    blocked=[];required_bytes=0;prepared_bytes=0
    for r in records:
        if not r['required']:continue
        src=m['mounts'][r['aliases'][0]]['source'];size=os.stat(src).st_size
        required_bytes+=roundup(size)
        if r['prepared']:prepared_bytes+=roundup(size);continue
        loads=segments(src)
        blocked.append(dict(source=src,aliases=r['aliases'],bytes=size,page_rounded_output=roundup(size),
            bounded_copy_buffers=2*1048576,known_output_plus_buffer_bytes=roundup(size)+2*1048576,
            native_copy_and_digest_buffers=131072,native_output_plus_buffers=roundup(size)+131072,
            exact_peak='UNKNOWN_NOT_EXECUTED; add interpreter/allocator/kernel/page-cache overhead',
            pt_load_file_bytes=sum(x['filesz'] for x in loads),pt_load_mem_bytes=sum(x['memsz'] for x in loads),
            generation='v3 chunked copy; WRITE/GROW/SHRINK/SEAL/EXEC; final sealed FD SHA256',
            current_object_limit=64*1048576,minimum_object_limit=size,
            creator_FSIZE_needed_at_least=size,target_FSIZE=m['rlimits']['FSIZE'],
            target_MemoryMax=int(m['resources']['MemoryMax']),target_AS=m['rlimits']['AS'],
            meets_current_preparation_limit=False,required=True))
    result=dict(parent_contract_sha256=seal,compiled_paths=sum(len(r['aliases']) for r in prepared),
        compiled_objects=len(prepared),blocked_objects=blocked,required_objects=sum(r['required'] for r in records),
        prepared_required_page_bytes=prepared_bytes,full_required_page_bytes=required_bytes,
        full_required_native_output_plus_buffers=required_bytes+131072,
        minimum_preparer_NOFILE=len(prepared)+10,
        full_minimum_preparer_NOFILE=sum(r['required'] for r in records)+10,
        minimum_supervisor_NOFILE=len(prepared)+13,
        full_minimum_supervisor_NOFILE=sum(r['required'] for r in records)+13,
        NOFILE_model='prep: pins+FD0..4+root+journal+source+RWcopy+ROreopen; launch: pins+FD0..4+root+journal+bootstrap pair+audit pair+listener+pidfd; lower bounds exclude ambient/sparse FD overhead',
        target_NOFILE=m['rlimits']['NOFILE'],preparer_limits='UNVERIFIED_SEPARATE_OWNER',
        target_limits_unchanged=m['rlimits'],target_MemoryMax=m['resources']['MemoryMax'],
        memory_relation='memfd creation charges belong to creator context; external ownership does not make charge free',
        target_mapping_relation='ELF PT_LOAD and actual resident/fault charges differ from whole-file/debug size',
        deployed=False,runtime_verified_inputs=0)
    (R/'reports/resources.json').write_text(json.dumps(result,indent=2)+'\n')
    return result
if __name__=='__main__':
    r=generate();print('compile-time required paths',r['compiled_paths'],'; no limits changed')
