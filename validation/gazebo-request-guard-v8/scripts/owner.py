"""Authenticate held PID1 worker; O acknowledges identity only, NOT preparation.
Current approved owner ceiling is512MiB. No property/rlimit is changed here.
Every received descriptor is disposed before O; any failure leaves bootstrap
unacknowledged so the dedicated parent cannot resume its worker as ready.
"""
from pathlib import Path,PurePosixPath
import os,socket,struct,fcntl,re
from catalog_channel import attest
from placement import identity,need
CURRENT_OWNER_MAX=536870912

def bind(endpoint,parent_pid,parent_start,elf_sha,owner_cgroup,run,policy,audit,approved_owner_max=CURRENT_OWNER_MAX):
    need(type(parent_pid) is int and parent_pid>0 and type(parent_start) is str and parent_start.isdigit(),'owner parent identity schema')
    need(type(elf_sha) is str and re.fullmatch('[a-f0-9]{64}',elf_sha) and type(policy) is str and re.fullmatch('[a-f0-9]{64}',policy) and type(run) is str and run,'owner run/ELF/policy binding')
    need(type(owner_cgroup) is str and owner_cgroup.startswith('/') and owner_cgroup!='/' and '//' not in owner_cgroup and
         str(PurePosixPath(owner_cgroup))==owner_cgroup and '..' not in PurePosixPath(owner_cgroup).parts and
         not any(c in owner_cgroup for c in '\r\n\x00'),'dedicated owner cgroup path')
    need(type(approved_owner_max) is int and 0<approved_owner_max<=CURRENT_OWNER_MAX,'unapproved owner resource ceiling')
    data,ancillary,flags,address=endpoint.recvmsg(16,socket.CMSG_SPACE(4)+socket.CMSG_SPACE(12),socket.MSG_DONTWAIT|socket.MSG_CMSG_CLOEXEC)
    descriptors=[]
    try:
        creds=[];bad=False
        for level,kind,value in ancillary:
            if level==socket.SOL_SOCKET and kind==socket.SCM_RIGHTS:
                n=len(value)//4
                if n:descriptors.extend(struct.unpack(str(n)+'i',value[:n*4]))
                bad|=len(value)%4!=0
            elif level==socket.SOL_SOCKET and kind==socket.SCM_CREDENTIALS and len(value)==12:creds.append(struct.unpack('3i',value))
            else:bad=True
        need(not bad and not flags&(socket.MSG_TRUNC|socket.MSG_CTRUNC) and len(data)==16 and data[:8]==b'OWNERV8\0' and len(descriptors)==1,'owner handoff framing')
        need(creds==[(parent_pid,os.geteuid(),os.getegid())] and attest(parent_pid,parent_start,elf_sha),'owner bootstrap source identity')
        native=struct.unpack('Q',data[8:])[0];need(native==1,'trusted worker must be PID1 in new namespace')
        need(fcntl.fcntl(descriptors[0],fcntl.F_GETFD)&fcntl.FD_CLOEXEC,'owner pidfd not CLOEXEC')
        pid=audit.pidfd_identity(descriptors[0],native);parent=identity(parent_pid);worker=identity(pid)
        need(parent['pid']==parent_pid and parent['start']==parent_start and worker['pid']==pid and
             worker['ppid']==parent_pid and worker['state'] in ('t','T') and
             parent['cgroup']==worker['cgroup']==owner_cgroup,'owner worker identity/domain')
        need(attest(pid,worker['start'],elf_sha),'owner worker executable differs')
        root=Path('/sys/fs/cgroup')/owner_cgroup.lstrip('/')
        def maximum():
            value=(root/'memory.max').read_text().strip()
            need(value.isdigit() and 0<int(value)<=approved_owner_max,'owner resource domain missing/unbounded/unapproved')
            return int(value)
        bound=maximum()
        again_parent=identity(parent_pid);again_worker=identity(pid)
        need(all(again_parent[k]==parent[k] for k in ('pid','start','cgroup')) and
             all(again_worker[k]==worker[k] for k in ('pid','start','ppid','cgroup')) and
             again_worker['state'] in ('t','T') and maximum()==bound and
             audit.pidfd_identity(descriptors[0],native)==pid,'owner identity/domain changed before ACK')
        result=audit.Owner(pid,worker['start'],elf_sha,0,run,policy)
        fd=descriptors.pop();os.close(fd) # A release error must fail BEFORE O.
        need(endpoint.send(b'O',socket.MSG_DONTWAIT|socket.MSG_NOSIGNAL)==1,'owner worker ACK')
        return result
    finally:
        errors=[]
        for fd in set(descriptors):
            try:os.close(fd)
            except OSError as e:errors.append(e)
        if errors:raise errors[0]
