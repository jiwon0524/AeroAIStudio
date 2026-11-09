"""FD layout adapter, no exec call. Future caller must pass runtime_ready first."""
import os,fcntl
from contextlib import contextmanager
from contract import validate,check_fd,bwrap,runtime_ready

@contextmanager
def inputs(manifest):
    validate(manifest)
    descriptors={}
    try:
        for source in manifest['fd_sources']:
            row=next(x for x in manifest['mounts'].values() if x['source']==source)
            fd=os.open(source,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
            try:mount_fd=fcntl.fcntl(fd,fcntl.F_DUPFD_CLOEXEC,10)
            finally:os.close(fd)
            descriptors[source]=mount_fd
            check_fd(mount_fd,row)
            os.set_inheritable(mount_fd,True)
        yield bwrap(manifest,descriptors),descriptors
    finally:
        for fd in descriptors.values():os.close(fd)

def approved_layout(manifest):
    runtime_ready(manifest)  # before any marker, manager or service is possible
    return inputs(manifest)
