#define _GNU_SOURCE
#include "loader.h"
#include <sys/mman.h>
#include <sys/syscall.h>
#include <linux/stat.h>
#include <linux/sched.h>
#include <linux/elf.h>
#include <sys/stat.h>
#include <sys/ptrace.h>
#include <sys/user.h>
#include <sys/uio.h>
#include <unistd.h>
#include <fcntl.h>
#include <string.h>
#include <errno.h>
/* No target pointer is continued after inspection. File mmap uses scalar
 * captured registers; the FD table cannot mutate until syscall-exit receipt. */
int loader_mutation_allowed(const struct load_tx *tx){return tx&&tx->task==0;}
int loader_begin(struct load_tx *tx,pid_t task,int pidfd,int fd,const char *sha,
                 int prot,uint64_t flags,uint64_t length,uint64_t offset) {
    if(!tx||tx->task||task<=0||fd<5||!length||length>2147483648ULL||offset%4096||
       ((flags&~(uint64_t)(MAP_PRIVATE|MAP_FIXED|MAP_DENYWRITE|MAP_EXECUTABLE)) || !(flags&MAP_PRIVATE))||prot&~(PROT_READ|PROT_WRITE|PROT_EXEC)||
       ((prot&PROT_WRITE)&&(prot&PROT_EXEC))||length>UINT64_MAX-offset)return -1;
    int copy=(int)syscall(SYS_pidfd_getfd,pidfd,fd,0);if(copy<0)return -1;
    struct bound object;int rc=bound_verify(copy,sha,NULL,&object);
    if(!rc&&((prot&PROT_EXEC)&&!object.executable))rc=-1;
    /* ld.so reserves the entire PT_LOAD span, including later anonymous BSS.
     * A private mapping may extend past EOF (faults there remain SIGBUS); it
     * cannot supply different bytes or shared writes. Keep the scalar AS cap. */
    if(!rc&&offset>=((object.size+4095)&~4095ULL))rc=-1;
    close(copy);if(rc)return -1;
    tx->task=task;tx->fd=fd;tx->nr=SYS_mmap;tx->object=object;return 0;
}
int loader_exit(struct load_tx *tx,pid_t task,long result) {
    if(!tx||tx->task!=task||result<0)return -1;
    memset(tx,0,sizeof *tx);return 0;
}
int loader_metadata(int fd,int kind,void *out,size_t width) {
    struct stat st;int mode=fcntl(fd,F_GETFL),seals=fcntl(fd,F_GET_SEALS);
    if(!out||mode<0||(mode&O_ACCMODE)!=O_RDONLY||(mode&O_PATH)||seals<0||(seals&0x2f)!=0x2f||fstat(fd,&st))return -1;
    if(kind==SYS_newfstatat&&width==sizeof st){memcpy(out,&st,width);return 0;}
    if(kind==SYS_statx&&width==sizeof(struct statx)) {
        struct statx x;memset(&x,0,sizeof x);
        if(syscall(SYS_statx,fd,"",AT_EMPTY_PATH|AT_STATX_SYNC_AS_STAT,STATX_BASIC_STATS,&x))return -1;
        memcpy(out,&x,width);return 0;
    }
    return -1;
}
#include <stdio.h>
#include <stdlib.h>
#include <sys/sysmacros.h>
int loader_protect(struct load_tx *tx,pid_t pid,uint64_t address,uint64_t length,int prot,int pin,const char *sha) {
    if(!tx||tx->task||pid<=0||!length||address%4096||length%4096||address>UINT64_MAX-length||
       !(prot&PROT_EXEC)||(prot&~(PROT_READ|PROT_EXEC)))return -1;
    struct bound object;if(bound_verify(pin,sha,NULL,&object)||!object.executable)return -1;
    char path[64];snprintf(path,sizeof path,"/proc/%ld/maps",(long)pid);
    FILE *file=fopen(path,"re");if(!file)return -1;
    char *line=NULL;size_t cap=0;uint64_t offset=0;int found=0;
    while(getline(&line,&cap,file)>0) {
        unsigned long long lo,hi,off,ino;unsigned a,b;char permissions[5];
        if(sscanf(line,"%llx-%llx %4s %llx %x:%x %llu",&lo,&hi,permissions,&off,&a,&b,&ino)!=7)continue;
        if(lo<=address&&address+length<=hi&&permissions[0]=='r'&&permissions[1]!='w'&&permissions[3]=='p'&&
           ino==object.ino&&a==gnu_dev_major(object.dev)&&b==gnu_dev_minor(object.dev)) {
            offset=off+address-lo;found=1;break;
        }
    }
    free(line);fclose(file);
    if(!found||offset>object.size||length>((object.size+4095)&~4095ULL)-offset)return -1;
    unsigned char original[65536],actual[65536];uint64_t at=0;
    while(at<length) {
        size_t n=length-at>sizeof actual?sizeof actual:(size_t)(length-at);
        memset(original,0,n);
        size_t bytes=offset+at>=object.size?0:(object.size-offset-at<n?(size_t)(object.size-offset-at):n);
        if(bytes&&pread(pin,original,bytes,(off_t)(offset+at))!=(ssize_t)bytes)return -1;
        struct iovec dst={actual,n},src={(void *)(uintptr_t)(address+at),n};
        if(process_vm_readv(pid,&dst,1,&src,1,0)!=(ssize_t)n||memcmp(original,actual,n))return -1;
        at+=n;
    }
    tx->task=pid;tx->nr=SYS_mprotect;tx->object=object;return 0;
}
