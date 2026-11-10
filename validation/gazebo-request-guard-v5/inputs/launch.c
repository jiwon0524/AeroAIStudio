#define _GNU_SOURCE
#include "launch.h"
#include <sys/socket.h>
#include <sys/ptrace.h>
#include <sys/user.h>
#include <sys/wait.h>
#include <sys/prctl.h>
#include <sys/resource.h>
#include <sys/syscall.h>
#include <sys/stat.h>
#include <sys/mman.h>
#include <sys/ioctl.h>
#include <sys/sysmacros.h>
#include <linux/seccomp.h>
#include <linux/filter.h>
#include <linux/audit.h>
#include <linux/sched.h>
#include <sys/uio.h>
#include <fcntl.h>
#include <signal.h>
#include <unistd.h>
#include <dirent.h>
#include <errno.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <poll.h>
#include <stddef.h>
#include "policy_counts.h"
static const char *target_environment[]={
#include "target_env.inc"
    NULL};

#define TR(n) BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K,(n),0,1),BPF_STMT(BPF_RET|BPF_K,SECCOMP_RET_TRACE)
#define OK(n) BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K,(n),0,1),BPF_STMT(BPF_RET|BPF_K,SECCOMP_RET_ALLOW)
static int bootstrap_filter(void) {
    struct sock_filter code[]={
        BPF_STMT(BPF_LD|BPF_W|BPF_ABS,offsetof(struct seccomp_data,arch)),
        BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K,AUDIT_ARCH_X86_64,1,0),
        BPF_STMT(BPF_RET|BPF_K,SECCOMP_RET_KILL_PROCESS),
        BPF_STMT(BPF_LD|BPF_W|BPF_ABS,offsetof(struct seccomp_data,nr)),
        BPF_JUMP(BPF_JMP|BPF_JSET|BPF_K,0x40000000,0,1),
        BPF_STMT(BPF_RET|BPF_K,SECCOMP_RET_KILL_PROCESS),
        /* Stateful ptrace guard decides bootstrap ops and legacy clone from
         * captured scalar registers. No unguarded exec/IPC after handoff. */
        BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K,SYS_write,0,8),
        BPF_STMT(BPF_LD|BPF_W|BPF_ABS,offsetof(struct seccomp_data,args[0])+4),
        BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K,0,0,5),
        BPF_STMT(BPF_LD|BPF_W|BPF_ABS,offsetof(struct seccomp_data,args[0])),
        BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K,1,2,0),
        BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K,2,1,0),
        BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K,4,0,1),
        BPF_STMT(BPF_RET|BPF_K,SECCOMP_RET_ALLOW),
        BPF_STMT(BPF_RET|BPF_K,SECCOMP_RET_USER_NOTIF),
        BPF_STMT(BPF_LD|BPF_W|BPF_ABS,offsetof(struct seccomp_data,nr)),
        /* FD0..4 remain occupied/immutable. Automatic ADDFD allocation can
         * never replace protocol channels with an input file. */
        BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K,SYS_close,0,7),
        BPF_STMT(BPF_LD|BPF_W|BPF_ABS,offsetof(struct seccomp_data,args[0])+4),
        BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K,0,0,4),
        BPF_STMT(BPF_LD|BPF_W|BPF_ABS,offsetof(struct seccomp_data,args[0])),
        BPF_JUMP(BPF_JMP|BPF_JGE|BPF_K,5,0,2),
        BPF_JUMP(BPF_JMP|BPF_JSET|BPF_K,0x80000000,1,0),
        BPF_STMT(BPF_RET|BPF_K,SECCOMP_RET_ALLOW),
        BPF_STMT(BPF_RET|BPF_K,SECCOMP_RET_USER_NOTIF),
        BPF_STMT(BPF_LD|BPF_W|BPF_ABS,offsetof(struct seccomp_data,nr)),
        TR(SYS_execveat),TR(SYS_execve),TR(SYS_sendmsg),TR(SYS_recvfrom),TR(SYS_clone),TR(SYS_clone3),
        TR(SYS_mmap),TR(SYS_mprotect),TR(SYS_arch_prctl),
        OK(SYS_exit),OK(SYS_exit_group),OK(SYS_rt_sigreturn),
        OK(SYS_getpid),OK(SYS_gettid),
        /* Only inherited attested pipes/null and broker-supplied sealed RO
         * files exist. No dup/socket/exec or shared mmap path is permitted. */
        OK(SYS_read),OK(SYS_pread64),OK(SYS_fstat),OK(SYS_lseek),
        OK(SYS_brk),OK(SYS_munmap),OK(SYS_clock_gettime),OK(SYS_sched_yield),
        OK(SYS_rt_sigprocmask),OK(SYS_rt_sigaction),OK(SYS_sigaltstack),
        OK(SYS_set_tid_address),OK(SYS_set_robust_list),OK(SYS_rseq),OK(SYS_futex),
        BPF_STMT(BPF_RET|BPF_K,SECCOMP_RET_USER_NOTIF)};
    struct sock_fprog p={(unsigned short)(sizeof code/sizeof code[0]),code};
    if(prctl(PR_SET_NO_NEW_PRIVS,1,0,0,0)) return -1;
    return (int)syscall(SYS_seccomp,SECCOMP_SET_MODE_FILTER,SECCOMP_FILTER_FLAG_NEW_LISTENER,&p);
}
static int initial_fds(void) {
    struct stat st[5];
    for(int i=0;i<5;i++) if(fstat(i,st+i)) return -1;
    int modes[]={O_RDONLY,O_WRONLY,O_WRONLY,O_RDONLY,O_WRONLY};
    for(int i=0;i<5;i++) {
        int flags=fcntl(i,F_GETFL),fdflags=fcntl(i,F_GETFD);
        if(flags<0||(flags&O_PATH)||(flags&O_ACCMODE)!=modes[i]||fdflags<0||(fdflags&FD_CLOEXEC)) return -1;
    }
    if(!S_ISCHR(st[0].st_mode)||major(st[0].st_rdev)!=1||minor(st[0].st_rdev)!=3) return -1;
    for(int i=1;i<5;i++) if(!S_ISFIFO(st[i].st_mode)) return -1;
    if(st[1].st_dev!=st[2].st_dev || st[1].st_ino!=st[2].st_ino) return -1;
    for(int i=2;i<5;i++) for(int j=i+1;j<5;j++)
        if(st[i].st_dev==st[j].st_dev && st[i].st_ino==st[j].st_ino) return -1;
    return 0; /* exact post-fd_bridge ABI; no target sockets/files inherited */
}
static int child_limits(void) {
    struct {int kind;rlim_t value;} bounds[]={{RLIMIT_CPU,10},{RLIMIT_AS,2147483648ULL},
        {RLIMIT_FSIZE,1048576},{RLIMIT_NOFILE,256},{RLIMIT_CORE,0}};
    for(unsigned i=0;i<sizeof bounds/sizeof bounds[0];i++) {
        struct rlimit r={bounds[i].value,bounds[i].value};if(setrlimit(bounds[i].kind,&r)) return -1;
    }
    return 0;
}
static void child_stub(int socket,int execfd,char *const argv[],char *const envp[]) {
    int e=fcntl(execfd,F_DUPFD_CLOEXEC,10),s=fcntl(socket,F_DUPFD_CLOEXEC,10);
    if(e<0||s<0||dup3(e,5,O_CLOEXEC)!=5||dup3(s,6,O_CLOEXEC)!=6||
       close_range(7,~0U,0)||child_limits()||ptrace(PTRACE_TRACEME,0,0,0)||raise(SIGSTOP)) _exit(78);
    int listener=bootstrap_filter();if(listener!=7) _exit(78);
    char payload='L';char ancillary[CMSG_SPACE(sizeof(int))]={0};
    struct iovec v={&payload,1};struct msghdr msg={.msg_iov=&v,.msg_iovlen=1,
        .msg_control=ancillary,.msg_controllen=sizeof ancillary};
    struct cmsghdr *h=CMSG_FIRSTHDR(&msg);h->cmsg_level=SOL_SOCKET;h->cmsg_type=SCM_RIGHTS;
    h->cmsg_len=CMSG_LEN(sizeof(int));memcpy(CMSG_DATA(h),&listener,sizeof listener);
    if(sendmsg(6,&msg,MSG_NOSIGNAL)!=1||close(listener)) _exit(78);
    char ack=0;if(recv(6,&ack,1,0)!=1||ack!='A'||close(6)) _exit(78);
    syscall(SYS_execveat,5,"",argv,envp,AT_EMPTY_PATH);
    _exit(78);
}
static int listener_receive(int socket,pid_t child) {
    char payload=0,ancillary[CMSG_SPACE(sizeof(int))+CMSG_SPACE(sizeof(struct ucred))]={0};
    struct iovec v={&payload,1};struct msghdr msg={.msg_iov=&v,.msg_iovlen=1,
        .msg_control=ancillary,.msg_controllen=sizeof ancillary};
    ssize_t n=recvmsg(socket,&msg,MSG_DONTWAIT|MSG_CMSG_CLOEXEC);
    if(n<0 && (errno==EAGAIN||errno==EWOULDBLOCK)) return -2;
    int fd=-1,rights=0,creds=0,bad=0;
    for(struct cmsghdr *h=CMSG_FIRSTHDR(&msg);h;h=CMSG_NXTHDR(&msg,h)) {
        if(h->cmsg_level!=SOL_SOCKET) { bad=1;continue; }
        if(h->cmsg_type==SCM_RIGHTS && h->cmsg_len>=CMSG_LEN(0)) {
            size_t count=(h->cmsg_len-CMSG_LEN(0))/sizeof(int);
            int *received=(int *)CMSG_DATA(h);
            for(size_t i=0;i<count;i++) { if(fd<0) fd=received[i];else close(received[i]);rights++; }
        } else if(h->cmsg_type==SCM_CREDENTIALS && h->cmsg_len==CMSG_LEN(sizeof(struct ucred))) {
            struct ucred cred;memcpy(&cred,CMSG_DATA(h),sizeof cred);
            if(cred.pid==child && cred.uid==geteuid() && cred.gid==getegid()) creds++;else bad=1;
        } else bad=1;
    }
    if(n!=1||payload!='L'||(msg.msg_flags&(MSG_TRUNC|MSG_CTRUNC))||rights!=1||creds!=1||bad) {
        if(fd>=0) close(fd);
        return -1;
    }
    uint64_t invalid=UINT64_MAX;errno=0;
    if(ioctl(fd,SECCOMP_IOCTL_NOTIF_ID_VALID,&invalid)!=-1 || errno!=ENOENT) {close(fd);return -1;}
    return fd;
}
static int target_fds(pid_t child) {
    char directory[64];snprintf(directory,sizeof directory,"/proc/%ld/fd",(long)child);
    DIR *d=opendir(directory);if(!d) return -1;
    struct dirent *entry;unsigned found=0;int bad=0;
    while((entry=readdir(d))) {
        if(entry->d_name[0]=='.') continue;
        char *end=NULL;long nr=strtol(entry->d_name,&end,10);
        if(!end||*end||nr<0||nr>4) {bad=1;continue;}
        char p[80];snprintf(p,sizeof p,"/proc/%ld/fd/%ld",(long)child,nr);
        struct stat a,b;if(fstat((int)nr,&a)||stat(p,&b)||a.st_dev!=b.st_dev||a.st_ino!=b.st_ino) bad=1;
        found|=1U<<(unsigned)nr;
    }
    closedir(d);return bad||found!=31?-1:0;
}
int candidate_launch(struct control *c,struct broker *b,int execfd,char *const argv[],char *const envp[],int journal,struct launch_result *out) {
    if(!c||!b||!out||!argv||!argv[0]||!envp||journal<5||execfd<5||initial_fds()) return 78;
    if(strcmp(argv[0],TARGET_EXECUTABLE)||!argv[1]||strcmp(argv[1],TARGET_PHYSICS)||
       !argv[2]||strcmp(argv[2],TARGET_DARTSIM)||argv[3]) return 78;
    size_t envcount=0;
    for(;target_environment[envcount];envcount++)
        if(!envp[envcount]||strcmp(envp[envcount],target_environment[envcount])) return 78;
    if(envp[envcount]) return 78;
    memset(out,0,sizeof *out);out->listener=out->audit_read=out->pidfd=-1;
    /* Runtime contract must cover ALL required objects, not only the452
     * prepared aliases. Until the five budget blockers are resolved, there
     * is no reviewed full contract and this API is not deployed or invoked. */
    if(catalog_full_ready(b->root_fd,b->inputs,b->count)) return 78;
    int executable_ok=0;
    for(size_t i=0;i<b->count;i++)
        if(!strcmp(b->inputs[i].pin.path,TARGET_EXECUTABLE) && b->inputs[i].pin.executable &&
           !catalog_verify(b->inputs+i,execfd)) executable_ok=1;
    if(!executable_ok) return 78;
    int pair[2],audit[2];
    if(socketpair(AF_UNIX,SOCK_SEQPACKET|SOCK_CLOEXEC,0,pair)) return 78;
    if(socketpair(AF_UNIX,SOCK_SEQPACKET|SOCK_CLOEXEC|SOCK_NONBLOCK,0,audit)) {close(pair[0]);close(pair[1]);return 78;}
    int one=1;
    if(setsockopt(pair[0],SOL_SOCKET,SO_PASSCRED,&one,sizeof one)) goto before_fork;
    pid_t child=fork();if(child<0) goto before_fork;
    if(!child) child_stub(pair[1],execfd,argv,envp);
    out->child=child;out->audit_read=audit[0];out->cleanup_pending=1;
    close(pair[1]); /* audit writer stays with supervisor, never target */
    struct timespec begin,now;
    int armed=0,phase=0,listener=-1,ack_sent=0,held_recv=0,dead=0;
    out->pidfd=(int)syscall(SYS_pidfd_open,child,0);
    if(out->pidfd<0) goto owned_failure;
    if(clock_gettime(CLOCK_MONOTONIC,&begin)) goto owned_failure;
    for(;;) {
        if(clock_gettime(CLOCK_MONOTONIC,&now)||now.tv_sec-begin.tv_sec>=30) goto owned_failure;
        if(!armed) {
            siginfo_t info;memset(&info,0,sizeof info);
            if(waitid(P_PID,(id_t)child,&info,WSTOPPED|WEXITED|WNOWAIT|WNOHANG)) {
                if(errno==EINTR) continue;
                goto owned_failure;
            }
            if(info.si_pid) {
                if(info.si_code!=CLD_STOPPED||info.si_status!=SIGSTOP||
                   control_arm(c,child,journal,audit[1])) goto owned_failure;
                armed=1;
                unsigned long options=PTRACE_O_EXITKILL|PTRACE_O_TRACESYSGOOD|PTRACE_O_TRACEEXEC|
                    PTRACE_O_TRACEEXIT|PTRACE_O_TRACEFORK|PTRACE_O_TRACEVFORK|PTRACE_O_TRACECLONE|PTRACE_O_TRACESECCOMP;
                if(ptrace(PTRACE_SETOPTIONS,child,0,options)||ptrace(PTRACE_CONT,child,0,0)) goto owned_failure;
            }
        } else {
            if(listener<0 && phase>=1) {
                int fd=listener_receive(pair[0],child);
                if(fd==-1) goto owned_failure;
                if(fd>=0) {
                    listener=fd;
                    if(control_note(c,"FILTER_BOUND",child,-1)||
                       send(pair[0],"A",1,MSG_DONTWAIT|MSG_NOSIGNAL)!=1) goto owned_failure;
                    ack_sent=1;
                    if(held_recv) { held_recv=0;if(ptrace(PTRACE_CONT,child,0,0)) goto owned_failure; }
                }
            }
            int status=0;pid_t got=waitpid(child,&status,__WALL|WNOHANG);
            if(got<0) { if(errno==EINTR) continue;goto owned_failure; }
            if(got==child) {
                if(WIFEXITED(status)||WIFSIGNALED(status)) {dead=1;goto owned_failure;}
                if(!WIFSTOPPED(status)||WSTOPSIG(status)!=SIGTRAP) goto owned_failure;
                unsigned event=(unsigned)status>>16;
                if(event==PTRACE_EVENT_SECCOMP) {
                    struct user_regs_struct regs;
                    if(ptrace(PTRACE_GETREGS,child,0,&regs)) goto owned_failure;
                    if(phase==0 && regs.orig_rax==SYS_sendmsg && regs.rdi==6) phase=1;
                    else if(phase==1 && regs.orig_rax==SYS_recvfrom && regs.rdi==6 && regs.rdx==1) {
                        phase=2;
                        if(!ack_sent) {held_recv=1;continue;}
                    } else if(phase==2 && ack_sent && regs.orig_rax==SYS_execveat && regs.rdi==5 && regs.r8==AT_EMPTY_PATH) {
                        /* Only the trusted single-thread stub exists here;
                         * verify empty path and consume this permission once. */
                        errno=0;long word=ptrace(PTRACE_PEEKDATA,child,(void *)(uintptr_t)regs.rsi,0);
                        if(errno || (word&255)!=0) goto owned_failure;
                        phase=3;
                    } else goto owned_failure;
                    if(ptrace(PTRACE_CONT,child,0,0)) goto owned_failure;
                } else if(event==PTRACE_EVENT_EXEC && phase==3 && listener>=0 && ack_sent) {
                    if(target_fds(child)||control_exec_stop(c,child,status)||
                       control_note(c,"TARGET_FDS",child,5)) goto owned_failure;
                    b->listener=listener;
                    if(control_bind_broker(c,b)) goto owned_failure;
                    close(pair[0]);out->listener=listener;out->stopped=1;
                    return 0; /* no target-loader instruction resumed */
                } else goto owned_failure;
            }
        }
        struct pollfd waitfd={pair[0],POLLIN,0};
        if(poll(&waitfd,1,10)<0 && errno!=EINTR) goto owned_failure;
        if(waitfd.revents&(POLLHUP|POLLERR|POLLNVAL)) {
            /* Child closes bootstrap socket immediately before exec-stop;
             * only the terminal phase may legitimately observe this HUP. */
            if(phase<2 || !ack_sent) goto owned_failure;
        }
    }
owned_failure:
    if(!dead) {
        (void)kill(child,SIGKILL); /* ONLY unreaped child created above */
        struct timespec stop;
        if(!clock_gettime(CLOCK_MONOTONIC,&stop)) for(;;) {
            int status=0;pid_t got=waitpid(child,&status,__WALL|WNOHANG);
            if(got==child && (WIFEXITED(status)||WIFSIGNALED(status))) {dead=1;break;}
            if(clock_gettime(CLOCK_MONOTONIC,&now)||now.tv_sec-stop.tv_sec>=2) break;
            (void)poll(NULL,0,10);
        }
    }
    if(armed) c->failed=1;
    if(listener>=0) close(listener);
    if(out->pidfd>=0) {close(out->pidfd);out->pidfd=-1;}
    close(pair[0]);close(audit[1]);out->cleanup_pending=!dead;
    return 78; /* audit read end remains owned by caller for failure drain */
before_fork:
    close(pair[0]);close(pair[1]);close(audit[0]);close(audit[1]);return 78;
}
int candidate_runtime_trace(struct control *c,pid_t pid,int status) {
    if(!c||!c->exec_seen||!WIFSTOPPED(status)||((unsigned)status>>16)!=PTRACE_EVENT_SECCOMP) return 78;
    struct control_task *t=NULL;unsigned reserved=0;
    for(unsigned i=0;i<64;i++) { if(c->tasks[i].pid==pid) t=c->tasks+i;reserved+=(unsigned)c->tasks[i].spawn_pending; }
    if(!t || t->trace_mode) return 78;
    struct user_regs_struct r;if(ptrace(PTRACE_GETREGS,pid,0,&r)) return 78;
    int scalar_ok=0;
    if(r.orig_rax==SYS_arch_prctl && r.rdi>=0x1001 && r.rdi<=0x1004) scalar_ok=1;
    if(r.orig_rax==SYS_mprotect && !(r.rdx&~(unsigned long)(PROT_READ|PROT_WRITE))) scalar_ok=1;
    if(r.orig_rax==SYS_mmap && !(r.rdx&~(unsigned long)(PROT_READ|PROT_WRITE)) &&
       (r.r10==(MAP_PRIVATE|MAP_ANONYMOUS)||r.r10==(MAP_PRIVATE|MAP_ANONYMOUS|MAP_STACK)) &&
       r.r8==UINT64_MAX && !r.r9) scalar_ok=1;
    if(scalar_ok && !c->failed) return control_note(c,"SCALAR_ALLOWED",pid,(long)r.orig_rax);
    const unsigned long flags=CLONE_VM|CLONE_FS|CLONE_FILES|CLONE_SIGHAND|CLONE_THREAD|
        CLONE_SYSVSEM|CLONE_SETTLS|CLONE_PARENT_SETTID|CLONE_CHILD_CLEARTID;
    long clone_source=(long)r.orig_rax;
    if(r.orig_rax==SYS_clone3 && !c->failed && c->live+reserved<64 &&
       (r.rsi==CLONE_ARGS_SIZE_VER0 || r.rsi==CLONE_ARGS_SIZE_VER1 || r.rsi==CLONE_ARGS_SIZE_VER2)) {
        struct clone_args a;memset(&a,0,sizeof a);
        struct iovec dst={&a,(size_t)r.rsi},src={(void *)(uintptr_t)r.rdi,(size_t)r.rsi};
        if(process_vm_readv(pid,&dst,1,&src,1,0)==(ssize_t)r.rsi && a.flags==flags &&
           !a.pidfd && !a.exit_signal && !a.set_tid && !a.set_tid_size && !a.cgroup &&
           a.stack && a.stack_size && a.stack<=UINT64_MAX-a.stack_size) {
            /* Emulate the approved x86-64 clone3 subset via scalar clone.
             * Kernel NEVER rereads inspected mutable clone_args. Caller is
             * stopped and remains unreaped by this sole wait owner. */
            r.orig_rax=SYS_clone;r.rdi=a.flags;r.rsi=a.stack+a.stack_size;
            r.rdx=a.parent_tid;r.r10=a.child_tid;r.r8=a.tls;r.r9=0;
            if(ptrace(PTRACE_SETREGS,pid,0,&r)) return 78;
        }
    }
    if(r.orig_rax==SYS_clone && r.rdi==flags && !c->failed && c->live+reserved<64) {
        if(control_note(c,"THREAD_ALLOWED",pid,clone_source)) return 78;
        t->trace_mode=2;t->spawn_pending=1;
        return 1; /* SYSCALL exit stop releases failed/successful clone slot */
    }
    if(control_request(c,pid,(uint64_t)r.rip,(long)r.orig_rax)||
       control_prepare(c,pid,(uint64_t)r.rip,1)) return 78;
    r.orig_rax=UINT64_MAX;r.rax=(unsigned long)-EPERM;
    if(ptrace(PTRACE_SETREGS,pid,0,&r)) return 78;
    t->trace_mode=1;
    return 1; /* receipt only at actual syscall-exit or terminal death */
}
int candidate_publish_audit(int collector,struct launch_result *out) {
    if(!out||!out->stopped||out->child<=0||out->audit_read<5||out->pidfd<5) return 78;
    uint64_t root=(uint64_t)out->child;
    char ancillary[CMSG_SPACE(2*sizeof(int))]={0};struct iovec v={&root,sizeof root};
    struct msghdr m={.msg_iov=&v,.msg_iovlen=1,.msg_control=ancillary,.msg_controllen=sizeof ancillary};
    struct cmsghdr *h=CMSG_FIRSTHDR(&m);h->cmsg_level=SOL_SOCKET;h->cmsg_type=SCM_RIGHTS;
    int descriptors[]={out->audit_read,out->pidfd};
    h->cmsg_len=CMSG_LEN(sizeof descriptors);memcpy(CMSG_DATA(h),descriptors,sizeof descriptors);
    /* Collector endpoint must enable SO_PASSCRED before this private exchange.
     * Failure leaves target at exec-stop; caller must not supervise/resume it. */
    if(sendmsg(collector,&m,MSG_DONTWAIT|MSG_NOSIGNAL)!=sizeof root) return 78;
    close(out->audit_read);out->audit_read=-1; /* sole reader is now collector */
    close(out->pidfd);out->pidfd=-1;
    return 0;
}

int candidate_supervise(struct control *c,struct broker *b,struct launch_result *owned) {
    if(!c||!b||!owned||!owned->stopped||!owned->collector_ready||owned->audit_read!=-1||
       owned->child!=c->root||b->listener!=owned->listener) return 78;
    struct seccomp_notif_sizes sizes;
    if(syscall(SYS_seccomp,SECCOMP_GET_NOTIF_SIZES,0,&sizes)||sizes.seccomp_notif<sizeof(struct seccomp_notif)) return 78;
    struct seccomp_notif *req=calloc(1,sizes.seccomp_notif);if(!req) return 78;
    pid_t unbound[64]={0};unsigned newborn[64]={0};
    struct timespec start,now;int result=78;
    if(clock_gettime(CLOCK_MONOTONIC,&start)||ptrace(PTRACE_CONT,c->root,0,0)) goto done;
    for(;;) {
        if(clock_gettime(CLOCK_MONOTONIC,&now)||now.tv_sec-start.tv_sec>=30) goto done;
        int status=0;pid_t got=waitpid(-1,&status,__WALL|WNOHANG);
        if(got<0) {
            if(errno==EINTR) continue;
            if(errno==ECHILD && !c->live) {result=control_finish(c);owned->cleanup_pending=0;break;}
            goto done;
        }
        if(got>0) {
            struct control_task *t=NULL;unsigned slot=0;
            for(unsigned i=0;i<64;i++) if(c->tasks[i].pid==got) {t=c->tasks+i;slot=i;break;}
            if(WIFEXITED(status)||WIFSIGNALED(status)) {
                if(!t||control_dead(c,got,status)) goto done;
                newborn[slot]=0;continue;
            }
            if(!WIFSTOPPED(status)) goto done;
            if(!t) {
                if((unsigned)status>>16 || WSTOPSIG(status)!=SIGSTOP) goto done;
                int stored=0;
                for(unsigned i=0;i<64;i++) if(unbound[i]==got) goto done;
                for(unsigned i=0;i<64;i++) if(!unbound[i]) {unbound[i]=got;stored=1;break;}
                if(!stored) goto done;
                continue; /* never resume unbound newborn */
            }
            unsigned event=(unsigned)status>>16;int resume_mode=PTRACE_CONT;
            if(event==PTRACE_EVENT_SECCOMP) {
                int action=candidate_runtime_trace(c,got,status);if(action==78) goto done;
                if(action==1) resume_mode=PTRACE_SYSCALL;
            } else if(event==PTRACE_EVENT_CLONE) {
                unsigned long child=0;
                if(!t->spawn_pending||ptrace(PTRACE_GETEVENTMSG,got,0,&child)||child>INT32_MAX||
                   control_child(c,got,(pid_t)child,status)) goto done;
                t->spawn_pending=0;
                for(unsigned i=0;i<64;i++) if(unbound[i]==(pid_t)child) {
                    unbound[i]=0;
                    for(unsigned j=0;j<64;j++) if(c->tasks[j].pid==(pid_t)child) newborn[j]=1;
                    if(ptrace(PTRACE_CONT,(pid_t)child,0,0)) goto done;
                }
                resume_mode=PTRACE_SYSCALL;
            } else if(event==PTRACE_EVENT_EXIT) {
                if(control_note(c,"EXIT_STOP",got,-1)) goto done;
            } else if(!event && WSTOPSIG(status)==(SIGTRAP|0x80) && t->trace_mode) {
                if(t->trace_mode==1) {
                    struct user_regs_struct regs;
                    if(ptrace(PTRACE_GETREGS,got,0,&regs)) goto done;
                    regs.rax=(unsigned long)-EPERM;
                    if(ptrace(PTRACE_SETREGS,got,0,&regs)||control_reply(c,got,t->request,0)) goto done;
                } else {
                    struct user_regs_struct regs;if(ptrace(PTRACE_GETREGS,got,0,&regs)) goto done;
                    if((long)regs.rax<0) {
                        c->failed=1; /* explicit failed clone receipt, no silent success */
                        if(control_note(c,"THREAD_FAILED",got,(long)regs.rax)) goto done;
                    }
                }
                t->trace_mode=0;t->spawn_pending=0;
            } else if(!event && WSTOPSIG(status)==SIGSTOP && got!=c->root && !newborn[slot]) newborn[slot]=1;
            else goto done;
            if(ptrace(resume_mode,got,0,0)) goto done;
            continue;
        }
        struct pollfd p[2]={{b->listener,POLLIN,0},{c->audit_fd,0,0}};
        int ready=poll(p,2,10);if(ready<0) {if(errno==EINTR) continue;goto done;}
        if((p[0].revents|p[1].revents)&(POLLHUP|POLLERR|POLLNVAL)) goto done;
        if(p[0].revents&POLLIN) {
            memset(req,0,sizes.seccomp_notif);
            if(ioctl(b->listener,SECCOMP_IOCTL_NOTIF_RECV,req)) {
                if(errno==EINTR||errno==ENOENT) continue;
                goto done;
            }
            if(candidate_broker_request(b,req)) goto done;
        }
    }
done:
    if(result==78 && c->live) {
        c->failed=1;
        /* Kill only kernel-bound tasks; unknown newborns remain held. Caller
         * must retain ownership or terminate tracer (EXITKILL), never GO. */
        for(unsigned i=0;i<64;i++) if(c->tasks[i].pid>0) (void)kill(c->tasks[i].pid,SIGKILL);
        for(unsigned i=0;i<64;i++) if(unbound[i]>0) (void)kill(unbound[i],SIGKILL);
        struct timespec stop;
        if(!clock_gettime(CLOCK_MONOTONIC,&stop)) for(;;) {
            int status=0;pid_t pid=waitpid(-1,&status,__WALL|WNOHANG);
            if(pid<0 && errno==ECHILD) {
                owned->cleanup_pending=0;
                if(!c->live) (void)control_finish(c);
                break;
            }
            if(pid>0) {
                struct control_task *t=NULL;
                for(unsigned i=0;i<64;i++) if(c->tasks[i].pid==pid) t=c->tasks+i;
                if(WIFEXITED(status)||WIFSIGNALED(status)) {
                    if(t) {
                        if(control_dead(c,pid,status)) {memset(t,0,sizeof *t);c->live--;}
                    } else (void)control_note(c,"UNBOUND_DEAD",pid,status);
                } else if(WIFSTOPPED(status)) {
                    if(t) (void)control_note(c,"EXIT_STOP",pid,-1);
                    (void)kill(pid,SIGKILL); /* newly observed auto-attached child too */
                    (void)ptrace(PTRACE_CONT,pid,0,0); /* SIGKILL pending, no user-code release */
                }
            }
            if(clock_gettime(CLOCK_MONOTONIC,&now)||now.tv_sec-stop.tv_sec>=2) break;
            if(pid==0) (void)poll(NULL,0,10);
        }
    }
    free(req);close(c->audit_fd);c->audit_fd=-1;
    owned->stopped=0;return result;
}
static int collector_byte(int socket,char expected) {
    struct pollfd p={socket,POLLIN,0};
    int n;do {n=poll(&p,1,5000);} while(n<0&&errno==EINTR);
    if(n<=0 || !(p.revents&POLLIN) || (p.revents&(POLLERR|POLLNVAL))) return 78;
    char b[2];return recv(socket,b,sizeof b,MSG_DONTWAIT)==1 && b[0]==expected?0:78;
}
static void abort_stopped(struct control *c,struct launch_result *out) {
    c->failed=1;(void)control_note(c,"AUDIT_FAULT",out->child,-1);
    (void)kill(out->child,SIGKILL);
    struct timespec stop,now;
    if(!clock_gettime(CLOCK_MONOTONIC,&stop)) for(;;) {
        int status=0;pid_t got=waitpid(out->child,&status,__WALL|WNOHANG);
        if(got==out->child) {
            if(WIFEXITED(status)||WIFSIGNALED(status)) {
                if(control_dead(c,got,status)) {
                    for(unsigned i=0;i<64;i++) if(c->tasks[i].pid==got) {memset(c->tasks+i,0,sizeof c->tasks[i]);c->live--;}
                }
                out->cleanup_pending=0;(void)control_finish(c);break;
            }
            if(WIFSTOPPED(status)) (void)ptrace(PTRACE_CONT,got,0,0); /* SIGKILL pending */
        }
        if(clock_gettime(CLOCK_MONOTONIC,&now)||now.tv_sec-stop.tv_sec>=2) break;
        if(!got) (void)poll(NULL,0,10);
    }
    out->stopped=0;close(c->audit_fd);c->audit_fd=-1;
}
int candidate_run(struct control *c,struct broker *b,int exe,char *const argv[],char *const envp[],int journal,int collector,struct launch_result *out) {
    int result=candidate_launch(c,b,exe,argv,envp,journal,out);
    if(result) return 78;
    if(candidate_publish_audit(collector,out)||collector_byte(collector,'A')) {
        abort_stopped(c,out);return 78;
    }
    out->collector_ready=1;
    result=candidate_supervise(c,b,out);
    if(!out->cleanup_pending && out->listener>=0) {
        close(out->listener);out->listener=-1;b->listener=-1;
    }
    if(result || out->cleanup_pending) return 78;
    /* V may be sent ONLY after original GO/live mapping/ACK/stdout+stderr EOF,
     * audit EOF, actual exit, cleanup and integrity verdict all pass. */
    return collector_byte(collector,'V');
}
