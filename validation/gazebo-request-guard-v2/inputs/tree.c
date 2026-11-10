/* All-task lifetime candidate. Reuses v1 journal and ptrace options, while
 * seccomp broker is responsible for syscall decisions. Compile only. Caller
 * must already have set EXITKILL/TRACE* before the first trusted exec.
 * This does not solve that launch/listener handoff prerequisite. */
#define main legacy_refusal_entry
#include "../../gazebo-request-guard-v1/inputs/guard.c"
#undef main
#include <poll.h>
#include <sys/ioctl.h>
#include <time.h>
#include <stdlib.h>
#include "broker.h"

#define TASK_LIMIT 64
struct task { pid_t pid; int bound, held; };
struct tree {
    struct task task[TASK_LIMIT]; size_t live;
    struct journal journal;
    struct broker *broker;
    int failed, root_dead;
    pid_t root;
};
/* Callback shared by tree and broker: a single event-loop writer, no target
 * FD and no second independently sequenced stream. Numeric request IDs are
 * deliberately not accepted as task identity or authentication evidence. */
static int tree_audit(void *ctx,const char *kind,uint64_t id,pid_t pid,long nr) {
    struct tree *t=ctx; (void)id;
    if(!strcmp(kind,"DENY")) { t->failed=1; t->journal.denied++; }
    if(!strcmp(kind,"CANCELLED")) t->failed=1;
    return record(&t->journal,kind,pid,nr);
}
static struct task *find(struct tree *t,pid_t pid,int create) {
    for(size_t i=0;i<TASK_LIMIT;i++) if(t->task[i].pid==pid) return t->task+i;
    if(create) for(size_t i=0;i<TASK_LIMIT;i++) if(!t->task[i].pid) {
        t->task[i].pid=pid; t->live++; return t->task+i;
    }
    return NULL;
}
static int resume(pid_t pid) { return ptrace(PTRACE_CONT,pid,0,0) ? -1:0; }
static int drain_wait(struct tree *t) {
    int status;
    for(;;) {
        pid_t pid=waitpid(-1,&status,__WALL|WNOHANG);
        if(pid==0) return 0;
        if(pid<0) {
            if(errno==EINTR) continue;
            if(errno==ECHILD && !t->live && t->root_dead) return 1;
            return -1;
        }
        struct task *q=find(t,pid,0);
        if(WIFEXITED(status)||WIFSIGNALED(status)) {
            if(!q || !q->bound) return -1;
            if(!WIFEXITED(status)||WEXITSTATUS(status)!=0) t->failed=1;
            if(record(&t->journal,"TASK_DEAD",pid,status)) return -1;
            if(pid==t->root) t->root_dead=1;
            memset(q,0,sizeof *q); t->live--; continue;
        }
        if(!WIFSTOPPED(status)) return -1;
        unsigned event=(unsigned)status>>16;
        if(!q || !q->bound) {
            /* Kernel can report child initial stop before creator event.
             * Hold unknown child; never resume until eventmsg binds it. */
            if(event || WSTOPSIG(status)!=SIGSTOP) return -1;
            if(!q) q=find(t,pid,1);
            if(!q || q->held) return -1;
            q->held=1; continue;
        }
        if(event==PTRACE_EVENT_FORK || event==PTRACE_EVENT_VFORK || event==PTRACE_EVENT_CLONE) {
            unsigned long child=0;
            if(ptrace(PTRACE_GETEVENTMSG,pid,0,&child) || !child || child>INT32_MAX) return -1;
            struct task *c=find(t,(pid_t)child,1);
            if(!c || c->bound) return -1;
            c->bound=1;
            if(record(&t->journal,"TASK_BORN",(pid_t)child,pid)) return -1;
            if(c->held) { c->held=2; if(resume(c->pid)) return -1; }
        } else if(event==PTRACE_EVENT_EXIT) {
            if(record(&t->journal,"EXIT_STOP",pid,-1)) return -1;
        } else if(!event && WSTOPSIG(status)==SIGSTOP && pid!=t->root) {
            /* Newborn stop. Explicitly consume it once only. */
            if(q->held!=0) return -1;
            q->held=2;
        } else return -1; /* unexpected signal/exec/seccomp event: never resume */
        if(resume(pid)) return -1;
    }
}
int candidate_tree_monitor(pid_t root,int journal_fd,int exec_status,struct broker *broker) {
    struct stat st; int f=fcntl(journal_fd,F_GETFL);
    if(!broker || root<=0 || f<0 || (f&O_ACCMODE)!=O_WRONLY || !(f&O_APPEND) ||
       fstat(journal_fd,&st) || !S_ISREG(st.st_mode) || st.st_size ||
       st.st_uid!=geteuid() || st.st_nlink!=1 || (st.st_mode&077) ||
       !WIFSTOPPED(exec_status) || WSTOPSIG(exec_status)!=SIGTRAP ||
       (unsigned)exec_status>>16!=PTRACE_EVENT_EXEC) return 78;
    struct tree t={.journal={journal_fd,0,0},.broker=broker,.root=root};
    struct task *q=find(&t,root,1); q->bound=1;
    const unsigned long opts=PTRACE_O_EXITKILL|PTRACE_O_TRACEEXEC|PTRACE_O_TRACEEXIT|
        PTRACE_O_TRACEFORK|PTRACE_O_TRACEVFORK|PTRACE_O_TRACECLONE;
    if(ptrace(PTRACE_SETOPTIONS,root,0,opts)) return 78;
    struct seccomp_notif_sizes sizes;
    if(syscall(SYS_seccomp,SECCOMP_GET_NOTIF_SIZES,0,&sizes) ||
       sizes.seccomp_notif<sizeof(struct seccomp_notif)) return 78;
    struct seccomp_notif *req=calloc(1,sizes.seccomp_notif);
    if(!req) return 78;
    int result=78;
    struct timespec begin,now;
    if(clock_gettime(CLOCK_MONOTONIC,&begin)) { free(req); return 78; }
    broker->audit=tree_audit; broker->audit_ctx=&t;
    if(record(&t.journal,"EXEC_STOP",root,-1) || resume(root)) goto finished;
    for(;;) {
        if(clock_gettime(CLOCK_MONOTONIC,&now) || now.tv_sec-begin.tv_sec>=30) break;
        int done=drain_wait(&t);
        if(done<0) break;
        if(done==1) {
            if(record(&t.journal,"ALL_DEAD",root,-1) || record(&t.journal,"COMPLETE",root,-1)) break;
            result=t.failed?78:0; break;
        }
        struct pollfd p={broker->listener,POLLIN,0};
        int n=poll(&p,1,10);
        if(n<0) { if(errno==EINTR) continue; break; }
        if(p.revents&(POLLHUP|POLLERR|POLLNVAL)) break;
        if(p.revents&POLLIN) {
            memset(req,0,sizes.seccomp_notif);
            if(ioctl(broker->listener,SECCOMP_IOCTL_NOTIF_RECV,req)) {
                if(errno==EINTR || errno==ENOENT) continue;
                break;
            }
            struct task *owner=find(&t,(pid_t)req->pid,0);
            if(!owner || !owner->bound || candidate_broker_request(broker,req)) break;
        }
    }
finished:
    free(req); broker->audit=NULL; broker->audit_ctx=NULL;
    /* A failure cannot produce COMPLETE. Caller must fail and retain audit
     * channel; trusted owner termination/EXITKILL remains an integration need. */
    return result;
}
