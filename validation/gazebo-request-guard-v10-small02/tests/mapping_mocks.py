"""Small-profile kernel-map/pin/canonical-RO identity proof under mocked OS."""
from common import *
import copy,errno,stat
from unittest.mock import patch
from types import SimpleNamespace as S
import mapping as M

def run(ok,reject,contract):
    groups=contract['records'];pins={};mounts={};canonical={};meta={}
    for i,row in enumerate(groups):
        obj=dict(device=777,inode=2000+i,size=row['size']);r=dict(object=obj,sha256=row['original']['sha256'],original=row['original'],executable_intent=row['executable'])
        pins[(row['original']['device'],row['original']['inode'])]=dict(fd=40+i,receipt=r)
        meta[40+i]=r;meta[70+i]=r
        for p in row['aliases']:
            mounts[p]=dict(obj);canonical['/proc/7/root'+p]=70+i
    plan=dict(mounts=mounts,required_canonical_mappings=contract['manifest']['required_canonical_mappings'])
    text=''.join(f'{(i+1)*4096:x}-{(i+2)*4096:x} r-xp 00000000 {os.major(777):02x}:{os.minor(777):02x} {2000+i} memfd-label-is-ignored\n' for i,row in enumerate(groups) if row['executable'])
    for fault in ('valid','unknown_inode','writable_exec','PID_reuse','canonical_substitution','mount_writable','mount_executable_data','map_files_ENOENT','map_files_IO_error'):
        changed=text.replace(' 2000 memfd',' 9999 memfd',1) if fault=='unknown_inode' else text.replace('r-xp','rwxp',1) if fault=='writable_exec' else text
        class View(M.SmallProc):
            def start(self,pid):return 'wrong' if fault=='PID_reuse' else 's'
            def maps(self,pid):return changed
        ops=View(lambda *a:True,pins)
        def open_file(path,flags):
            if '/map_files/' in path:
                raise OSError(errno.ENOENT if fault=='map_files_ENOENT' else errno.EIO if fault=='map_files_IO_error' else errno.EPERM,'mock map_files permission')
            return canonical[path]
        def same(fd,r):
            if fault=='canonical_substitution' and fd>=70:raise ValueError('wrong canonical immutable inode')
            need(meta[fd]==r,'same-FD receipt')
        def vfs(fd):
            flags=os.ST_RDONLY|os.ST_NOSUID|os.ST_NODEV
            if not meta[fd]['executable_intent']:flags|=os.ST_NOEXEC
            if fault=='mount_writable':flags&=~os.ST_RDONLY
            if fault=='mount_executable_data' and not meta[fd]['executable_intent']:flags&=~os.ST_NOEXEC
            return S(f_flag=flags)
        def verify():
            ops.catalog(7,plan,pins)
            return M.verify(7,'s',plan,pins,ops)
        with patch.object(M.os,'open',open_file),patch.object(M.os,'close',lambda fd:None),patch.object(M.os,'fstatvfs',vfs),patch.object(ops,'same',same):
            if fault=='valid':
                result=verify();ok('small_map_files_EPERM_explicit_identity_fallback',result['status']=='PASS_FILE_IDENTITY' and len(ops.map_files_unavailable)==3)
            else:reject('small_mapping_reject_'+fault,verify)
