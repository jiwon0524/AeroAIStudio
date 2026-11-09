"""Pure FD evidence validator for the candidate bridge handoff.

Not wired to a live launcher. Snapshots taken later cannot prove absence of
short-lived descriptors; this is not syscall mediation or an audit source.
"""
import os, stat

def need(ok, reason):
    if not ok:
        raise ValueError(reason)

def endpoints(rows):
    need(set(rows)=={0,1,2}, 'bridge input descriptor evidence')
    identities=[]
    for fd,direction in ((0,os.O_RDONLY),(1,os.O_WRONLY),(2,os.O_WRONLY)):
        row=rows[fd]
        flags=row['flags']
        need(type(flags) is int and flags>=0 and not flags & os.O_PATH and flags & os.O_ACCMODE==direction, 'descriptor access mode')
        need(stat.S_ISFIFO(row['mode']), 'inherited descriptor is not FIFO')
        need(type(row['device']) is int and type(row['inode']) is int, 'descriptor identity type')
        identities.append((row['device'],row['inode']))
    need(len(set(identities))==3, 'control/observation/stderr pipe alias')
    return True

def handoff(rows, go, observation, stderr, null_device):
    need(set(rows)==set(range(5)), 'ambient descriptor at target handoff')
    need(stat.S_ISCHR(rows[0]['mode']) and rows[0]['rdev']==null_device and rows[0]['flags'] & os.O_ACCMODE==os.O_RDONLY, 'stdin null identity/mode')
    for fd,identity,direction in ((1,stderr,os.O_WRONLY),(2,stderr,os.O_WRONLY),(3,go,os.O_RDONLY),(4,observation,os.O_WRONLY)):
        row=rows[fd]
        need(stat.S_ISFIFO(row['mode']) and (row['device'],row['inode'])==identity, 'handoff FIFO identity')
        need(not row['flags'] & os.O_PATH and row['flags'] & os.O_ACCMODE==direction, 'handoff FIFO mode')
    need(len({go,observation,stderr})==3,'handoff channel alias')
    return True
