"""Live file mapping identity. map_files preferred; proc-root fd fallback explicit."""
import os,re,time
from pathlib import Path
from identity import check_fd

def start_id(pid):return Path('/proc',str(pid),'stat').read_text().split(') ',1)[1].split()[19]
def parse_maps(text):
    rows=[]
    for line in text.splitlines():
        p=line.split(None,5)
        if len(p)<5:raise ValueError('malformed maps row')
        if not re.fullmatch('[0-9a-f]+-[0-9a-f]+',p[0]):raise ValueError('invalid address range')
        a,b=p[3].split(':');rows.append({'range':p[0],'perms':p[1],'offset':int(p[2],16),'device':os.makedev(int(a,16),int(b,16)),'inode':int(p[4]),'path':p[5] if len(p)==6 else ''})
    return rows

def mapping_entry(row,entries):
    if row['path'].endswith(' (deleted)'):raise ValueError('deleted mapped file')
    found=[e for e in entries if e['sandbox_path']==row['path']]
    if len(found)!=1:raise ValueError('unexpected mapped path '+row['path'])
    e=found[0]
    if (row['device'],row['inode'])!=(e['device'],e['inode']):raise ValueError('maps device/inode mismatch')
    return e

def verify(pid,entries):
    result={'pid':pid,'status':'FAIL','records':[],'map_files_status':'UNAVAILABLE','method':'map_files FD preferred; /proc/PID/root FD metadata fallback, never bare host path','limits':'file identity at bounded snapshots, not private relocated/COW memory equality or initialization safety'}
    try:
        before=start_id(pid);raw=Path('/proc',str(pid),'maps').read_text();rows=parse_maps(raw);seen=set();strong=True
        for row in rows:
            if row['inode']==0:
                if 'x' in row['perms'] and row['path'] not in ('[vdso]','[vsyscall]'):raise ValueError('unexpected anonymous executable mapping')
                continue
            entry=mapping_entry(row,entries);key=(row['device'],row['inode'],row['path'])
            if key in seen:continue
            seen.add(key);record={'path':row['path'],'device':row['device'],'inode':row['inode'],'range':row['range']}
            mf=Path('/proc',str(pid),'map_files',row['range']);fd=None
            try:
                record['map_files_link']=os.readlink(mf)
                fd=os.open(mf,os.O_RDONLY|os.O_CLOEXEC);record['map_files_open']='PASS'
            except OSError as e:
                record['map_files_open']='UNAVAILABLE';record['map_files_errno']=e.errno;strong=False
                root=Path('/proc',str(pid),'root')/row['path'].lstrip('/')
                fd=os.open(root,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW);record['fallback']='proc_root_fd'
            try:record['identity']=check_fd(fd,entry)
            finally:os.close(fd)
            result['records'].append(record)
        required={e['sandbox_path'] for e in entries if e['required']}
        if not required<={k[2] for k in seen}:raise ValueError('required mappings missing')
        if start_id(pid)!=before:raise ValueError('PID reused during observation')
        if Path('/proc',str(pid),'maps').read_text()!=raw:raise ValueError('maps changed during verification')
        result.update(status='PASS_FILE_IDENTITY',map_files_status='PASS' if strong else 'UNAVAILABLE',start=before,all_required=True)
    except (OSError,ValueError) as e:result['error']=str(e)
    return result
