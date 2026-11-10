#define _GNU_SOURCE
#include "broker.h"
#include "catalog.h"
#include <linux/filter.h>
#include <linux/audit.h>
#include <sys/mman.h>
#include <sys/prctl.h>
#include <sys/syscall.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <sys/uio.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <stddef.h>
#include <string.h>
#include <stdio.h>
#include <limits.h>

/* Conservative kernel envelope. No pointer-based request is continued after
 * inspection. Unknown ABI/syscalls cannot silently fall through. This filter
 * deliberately does NOT yet permit exec or clone: no safe launch/tree adapter
 * is released. Inheritance applies if future reviewed creation is enabled. */
#define DIRECT(n) BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K,(n),0,1), \
                  BPF_STMT(BPF_RET|BPF_K,SECCOMP_RET_ALLOW)
int candidate_install_filter(void) {
    struct sock_filter code[]={
        BPF_STMT(BPF_LD|BPF_W|BPF_ABS,offsetof(struct seccomp_data,arch)),
        BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K,AUDIT_ARCH_X86_64,1,0),
        BPF_STMT(BPF_RET|BPF_K,SECCOMP_RET_KILL_PROCESS),
        BPF_STMT(BPF_LD|BPF_W|BPF_ABS,offsetof(struct seccomp_data,nr)),
        BPF_JUMP(BPF_JMP|BPF_JSET|BPF_K,0x40000000,0,1),
        BPF_STMT(BPF_RET|BPF_K,SECCOMP_RET_KILL_PROCESS),
        DIRECT(SYS_exit), DIRECT(SYS_exit_group), DIRECT(SYS_rt_sigreturn),
        DIRECT(SYS_getpid), DIRECT(SYS_gettid),
        /* Everything else requires the independent supervisor, including
         * read/write/mmap/clone/exec/close. Listener disconnect must never
         * become ALLOW; ENOSYS still requires an external death verdict. */
        BPF_STMT(BPF_RET|BPF_K,SECCOMP_RET_USER_NOTIF)
    };
    struct sock_fprog p={(unsigned short)(sizeof code/sizeof code[0]),code};
    if(prctl(PR_SET_NO_NEW_PRIVS,1,0,0,0)) return -1;
    return (int)syscall(SYS_seccomp,SECCOMP_SET_MODE_FILTER,
                       SECCOMP_FILTER_FLAG_NEW_LISTENER,&p);
}

static int valid(struct broker *b,uint64_t id) {
    return ioctl(b->listener,SECCOMP_IOCTL_NOTIF_ID_VALID,&id)==0;
}
static int log_event(struct broker *b,const char *kind,const struct seccomp_notif *r) {
    return b->audit && b->audit(b->audit_ctx,kind,r->id,(pid_t)r->pid,r->data.nr)==0 ? 0:-1;
}
static int deny(struct broker *b,const struct seccomp_notif *r) {
    /* Persist before reply. A denied/cancelled request remains a failed run. */
    if(log_event(b,"DENY",r)) return -1;
    struct seccomp_notif_resp out={.id=r->id,.error=-EPERM};
    if(ioctl(b->listener,SECCOMP_IOCTL_NOTIF_SEND,&out)) {
        if(errno==ENOENT) return log_event(b,"CANCELLED",r);
        return -1;
    }
    return log_event(b,"REPLIED_DENY",r);
}
int candidate_broker_request(struct broker *b,const struct seccomp_notif *r) {
    if(!b || !r || !b->audit || r->pid==0) return -1;
    if(log_event(b,"REQUEST",r)) return -1;
    if(!valid(b,r->id)) return log_event(b,"CANCELLED",r);
    if(r->data.arch!=AUDIT_ARCH_X86_64 || r->flags) return deny(b,r);
    uint64_t ptr=0,flags=0,mode=0;
    if(r->data.nr==SYS_openat) {
        ptr=r->data.args[1]; flags=r->data.args[2]; mode=r->data.args[3];
        /* Absolute names only; dirfd has no authority. */
    } else if(r->data.nr==SYS_open) {
        ptr=r->data.args[0]; flags=r->data.args[1]; mode=r->data.args[2];
    } else return deny(b,r);
    if(mode || (flags & ~(uint64_t)(O_CLOEXEC|O_NONBLOCK|O_NOFOLLOW|O_LARGEFILE)))
        return deny(b,r);
    if(!ptr || ptr>UINT64_MAX-PATH_MAX) return deny(b,r);
    char path[PATH_MAX]; size_t used=0;
    /* Copy bounded bytes exactly once. A racing string can at most select a
     * different catalog entry, never authorize the target's original syscall.
     * Reading bytewise avoids requiring pages after the terminating NUL. */
    for(;used<sizeof path;used++) {
        struct iovec dst={path+used,1},src={(void *)(uintptr_t)(ptr+used),1};
        if(process_vm_readv((pid_t)r->pid,&dst,1,&src,1,0)!=1) return deny(b,r);
        if(!path[used]) break;
    }
    if(used==sizeof path || path[0]!='/') return deny(b,r);
    const struct copy_input *p=NULL;
    for(size_t i=0;i<b->count;i++)
        if(!strcmp(path,b->inputs[i].pin.path)) { p=b->inputs+i; break; }
    if(!p || catalog_verify(p,p->pin.fd)) return deny(b,r);
    /* Open canonical alias under trusted namespace root and compare sealed
     * object/hash, then pass THIS description. No deleted-name proc reopen. */
    int fd=catalog_open(b->root_fd,p);
    if(fd<0) return deny(b,r);
    if((flags&O_NONBLOCK) && fcntl(fd,F_SETFL,fcntl(fd,F_GETFL)|O_NONBLOCK)) {
        close(fd); return deny(b,r);
    }
    int index=catalog_index(p->pin.path);
    if(index<0 || b->audit(b->audit_ctx,"INPUT_OBJECT",r->id,(pid_t)r->pid,index) ||
       log_event(b,"INPUT_PREPARED",r)) { close(fd); return -1; }
    struct seccomp_notif_addfd a={.id=r->id,.flags=SECCOMP_ADDFD_FLAG_SEND,
        .srcfd=(unsigned)fd,.newfd=0,.newfd_flags=(unsigned)(flags&O_CLOEXEC)};
    /* SEND atomically installs the FD and replies to this notification. Never
     * retry uncertain/interrupted ADDFD, never fall back to CONTINUE or a
     * separate add+reply. Post-delivery journal failure fails the whole run. */
    int injected=ioctl(b->listener,SECCOMP_IOCTL_NOTIF_ADDFD,&a);
    int saved=errno; close(fd);
    if(injected<0) {
        if(saved==ENOENT) return log_event(b,"CANCELLED",r);
        return -1;
    }
    return log_event(b,"INPUT_DELIVERED",r);
}
