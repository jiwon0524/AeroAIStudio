/* Compile-only candidate. No enabled runtime entry point. x86-64 Linux only.
 * Caller must create a private journal not inherited by the tracee, establish
 * pinned FD identities and isolated namespaces, and stop the single child at
 * PTRACE_EVENT_EXEC before any target loader instruction. No caller exists yet.
 */
#define _GNU_SOURCE
#include <sys/ptrace.h>
#include <linux/ptrace.h>
#include <linux/audit.h>
#include <sys/user.h>
#include <sys/wait.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/mman.h>
#include <unistd.h>
#include <fcntl.h>
#include <stdint.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>

/* Default deny: no pathname/pointer inspection and no open-then-CONTINUE race.
 * No file reopening, socket, exec, clone, FD alias/change, ioctl, io_uring,
 * process_vm, ptrace, namespace or executable mapping is permitted.
 * This intentionally cannot initialize the existing dynamic workload. */
int guard_allowed(long nr, const uint64_t a[6]) {
    switch(nr) {
    case SYS_read: return a[0]==0 || a[0]==3;
    case SYS_write: return a[0]==1 || a[0]==2 || a[0]==4;
    case SYS_exit: case SYS_exit_group: case SYS_rt_sigreturn:
    case SYS_brk: case SYS_munmap: case SYS_getpid: case SYS_gettid:
    case SYS_clock_gettime: return 1;
    case SYS_mmap:
        return (a[2]&PROT_EXEC)==0 && a[3]==(MAP_PRIVATE|MAP_ANONYMOUS)
            && a[4]==UINT64_MAX && a[5]==0;
    case SYS_mprotect: return (a[2]&PROT_EXEC)==0;
    default: return 0;
    }
}

struct journal { int fd; unsigned long seq, denied; };
/* Supervisor-owned journal. Never parse target stdout/stderr as audit events.
 * Commit each record before skipping a request; failure leaves tracee stopped.
 * No unbounded queue: disk full, short write, sync failure all abort monitoring.
 */
static int record(struct journal *j,const char *kind,pid_t pid,long nr) {
    char b[192];
    int n=snprintf(b,sizeof b,"%lu %s %ld %ld %lu\n",j->seq+1,kind,(long)pid,nr,j->denied);
    if(n<=0 || (size_t)n>=sizeof b) return -1;
    ssize_t w; do { w=write(j->fd,b,(size_t)n); } while(w<0 && errno==EINTR);
    if(w!=n || fdatasync(j->fd)) return -1;
    j->seq++; return 0;
}

/* Requires exec-event stop. PTRACE_O_EXITKILL must have been set *before*
 * the first exec by a future trusted launch adapter. No attach to existing jobs.
 * Returns 78 on any denial/error even when target exit status was zero.
 * A root death/ECHILD receipt proves only this restrictive no-clone candidate.
 */
int guard_monitor(pid_t child,int journal_fd,int exec_stop_status) {
    const unsigned long opts=PTRACE_O_EXITKILL|PTRACE_O_TRACESYSGOOD|
        PTRACE_O_TRACEEXEC|PTRACE_O_TRACEEXIT|PTRACE_O_TRACEFORK|
        PTRACE_O_TRACEVFORK|PTRACE_O_TRACECLONE;
    struct stat st; int f=fcntl(journal_fd,F_GETFL);
    if(child<=0 || f<0 || (f&O_ACCMODE)!=O_WRONLY || !(f&O_APPEND) ||
       fstat(journal_fd,&st) || !S_ISREG(st.st_mode) || st.st_nlink!=1 ||
       st.st_uid!=geteuid() || (st.st_mode&077)!=0 || st.st_size!=0) return 78;
    if(!WIFSTOPPED(exec_stop_status) || WSTOPSIG(exec_stop_status)!=SIGTRAP ||
       (unsigned)exec_stop_status>>16!=PTRACE_EVENT_EXEC) return 78;
    if(ptrace(PTRACE_SETOPTIONS,child,0,opts)) return 78;
    struct journal j={journal_fd,0,0};
    if(record(&j,"EXEC_STOP",child,-1)) return 78;
    int pending=0, root_dead=0, status=0;
    for(;;) {
        if(ptrace(PTRACE_SYSCALL,child,0,0)) return 78;
        pid_t got; do { got=waitpid(-1,&status,__WALL); } while(got<0 && errno==EINTR);
        if(got!=child) return 78; /* Unexpected task never resumed. */
        if(WIFEXITED(status)||WIFSIGNALED(status)) {
            root_dead=1;
            if(!WIFEXITED(status)||WEXITSTATUS(status)!=0||pending) return 78;
            break;
        }
        if(!WIFSTOPPED(status)) return 78;
        unsigned event=(unsigned)status>>16;
        if(event==PTRACE_EVENT_EXIT) {
            if(record(&j,"EXIT_STOP",child,-1)) return 78;
            continue; /* Not terminal: wait for actual death. */
        }
        /* No detach, signal handler shortcut, exec or descendant exception. */
        if(event || WSTOPSIG(status)!=(SIGTRAP|0x80)) return 78;
        struct ptrace_syscall_info info; memset(&info,0,sizeof info);
        long n=ptrace(PTRACE_GET_SYSCALL_INFO,child,sizeof info,&info);
        if(n<(long)__builtin_offsetof(struct ptrace_syscall_info,entry) ||
           info.arch!=AUDIT_ARCH_X86_64) return 78;
        if(info.op==PTRACE_SYSCALL_INFO_ENTRY) {
            if(n<(long)(__builtin_offsetof(struct ptrace_syscall_info,entry)+sizeof info.entry) || pending) return 78;
            uint64_t args[6]; memcpy(args,info.entry.args,sizeof args);
            if(!guard_allowed((long)info.entry.nr,args)) {
                j.denied++;
                if(record(&j,"DENY",child,(long)info.entry.nr)) return 78;
                struct user_regs_struct regs;
                if(ptrace(PTRACE_GETREGS,child,0,&regs)) return 78;
                regs.orig_rax=UINT64_MAX; /* Kernel executes no requested syscall. */
                if(ptrace(PTRACE_SETREGS,child,0,&regs)) return 78;
                pending=1;
            }
        } else if(info.op==PTRACE_SYSCALL_INFO_EXIT) {
            if(pending) {
                struct user_regs_struct regs;
                if(ptrace(PTRACE_GETREGS,child,0,&regs)) return 78;
                regs.rax=(unsigned long)-EPERM;
                if(ptrace(PTRACE_SETREGS,child,0,&regs)) return 78;
                pending=0;
            }
        } else return 78;
    }
    if(!root_dead) return 78;
    pid_t got=waitpid(-1,&status,__WALL|WNOHANG);
    if(got!=-1 || errno!=ECHILD) return 78;
    if(record(&j,"ALL_DEAD",child,-1) || record(&j,"COMPLETE",child,-1)) return 78;
    return j.denied?78:0;
}
/* Refusal precedes fork/exec/manager/service/marker. Even direct invocation is inert. */
int main(void) { return 78; }
