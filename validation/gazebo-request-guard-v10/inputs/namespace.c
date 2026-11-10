#define _GNU_SOURCE
#include "namespace.h"
#include <sys/mount.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include <stdio.h>
#include <errno.h>
#include <string.h>
#include <linux/openat2.h>
#include <sys/syscall.h>
#include <linux/mount.h>
static int dir(int root,const char *name) {
    if(mkdirat(root,name,0700)&&errno!=EEXIST)return -1;
    struct open_how h={.flags=O_PATH|O_DIRECTORY|O_CLOEXEC,.resolve=RESOLVE_IN_ROOT|RESOLVE_NO_SYMLINKS|RESOLVE_NO_MAGICLINKS};
    int fd=(int)syscall(SYS_openat2,root,name,&h,sizeof h);return fd;
}
static int tmp(int root,const char *name,const char *size) {
    int fd=dir(root,name);if(fd<0)return -1;
    char target[64];snprintf(target,sizeof target,"/proc/self/fd/%d",fd);
    int rc=mount("tmpfs",target,"tmpfs",MS_NOSUID|MS_NODEV|MS_NOEXEC,size);close(fd);return rc;
}
int candidate_namespace_aux(int root) {
    /* Called only in fresh private mount/user/PID/network namespace, before
     * root RO sealing and target creation. No filesystem or namespace fallback. */
    const char *dirs[]={"cwd","input/resources","proc"};
    for(unsigned i=0;i<sizeof dirs/sizeof dirs[0];i++){int fd=dir(root,dirs[i]);if(fd<0)return -1;close(fd);}
    if(tmp(root,"dev","size=1048576,mode=0755")||tmp(root,"dev/shm","size=1048576,mode=0700")||
       tmp(root,"scratch","size=16777216,mode=0700")||tmp(root,"run","size=16777216,mode=0700"))return -1;
    int proc=dir(root,"proc");if(proc<0)return -1;
    char dst[64];snprintf(dst,sizeof dst,"/proc/self/fd/%d",proc);
    int rc=mount("proc",dst,"proc",MS_NOSUID|MS_NODEV|MS_NOEXEC|MS_RDONLY,NULL);close(proc);
    if(rc)return -1;
    int dev=dir(root,"dev");if(dev<0)return -1;
    struct mount_attr attr={.attr_set=MOUNT_ATTR_RDONLY};
    rc=(int)syscall(SYS_mount_setattr,dev,"",AT_EMPTY_PATH,&attr,sizeof attr);close(dev);if(rc)return -1;
    /* FD0 is already the attested /dev/null inherited by target. No device
     * node creation or ambient host-tree bind is required in this namespace. */
    return 0;
}
int candidate_enter_root(int root) {
    struct stat a,b;
    if(fstat(root,&a)||fchdir(root)||chroot(".")||chdir("/cwd")||stat("/",&b))return -1;
    return a.st_dev==b.st_dev&&a.st_ino==b.st_ino?0:-1;
}
