/* Compile-only preexec/lifetime spine. Reuse v1 independent synchronous writer.
 * This is not a launch adapter: no fork/exec, listener handoff or resume here.
 * The future trusted wait owner must invoke child/exec/death with kernel
 * events; caller dictionaries are never proof of OS ownership. */
#define _GNU_SOURCE
#define main legacy_refusal_entry
#include "../../gazebo-request-guard-v1/inputs/guard.c"
#undef main
#include "control.h"
#include "../../gazebo-request-guard-v3/inputs/broker.h"
#include <limits.h>

static int append(struct control *c,const char *kind,pid_t pid,long nr) {
    if(c->seq==ULONG_MAX) { c->failed=1; return 78; }
    char b[192];
    int n=snprintf(b,sizeof b,"%lu %s %ld %ld %lu\n",c->seq+1,kind,(long)pid,nr,c->denied);
    if(n<=0 || (size_t)n>=sizeof b || c->journal_bytes+(size_t)n>1048576) {
        c->failed=1; return 78;
    }
    struct journal j={c->journal_fd,c->seq,c->denied};
    if(record(&j,kind,pid,nr)) { c->failed=1; return 78; }
    c->seq=j.seq;
    c->journal_bytes+=(size_t)n;
    return 0;
}
static struct control_task *task(struct control *c,pid_t pid) {
    if(c->finished) return NULL;
    for(unsigned i=0;i<64;i++) if(c->tasks[i].pid==pid) return c->tasks+i;
    return NULL;
}
static int fail(struct control *c) { c->failed=1; return 78; }
int control_arm(struct control *c,pid_t child,int fd) {
    if(!c) return 78;
    memset(c,0,sizeof *c); c->journal_fd=fd; c->root=child;
    struct stat st; int flags=fcntl(fd,F_GETFL),fdflags=fcntl(fd,F_GETFD);
    if(child<=0 || flags<0 || fdflags<0 || !(fdflags&FD_CLOEXEC) ||
       (flags&O_ACCMODE)!=O_WRONLY || !(flags&O_APPEND) || fstat(fd,&st) ||
       !S_ISREG(st.st_mode) || st.st_size || st.st_nlink!=1 ||
       st.st_uid!=geteuid() || (st.st_mode&077)) return fail(c);
    int status=0;
    pid_t got=waitpid(child,&status,__WALL|WNOHANG);
    if(got!=child || !WIFSTOPPED(status) || WSTOPSIG(status)!=SIGSTOP ||
       ((unsigned)status>>16)!=0) return fail(c);
    if(append(c,"PREEXEC_STOP",child,-1)) return 78;
    const unsigned long options=PTRACE_O_EXITKILL|PTRACE_O_TRACESYSGOOD|
        PTRACE_O_TRACEEXEC|PTRACE_O_TRACEEXIT|PTRACE_O_TRACEFORK|
        PTRACE_O_TRACEVFORK|PTRACE_O_TRACECLONE;
    if(ptrace(PTRACE_SETOPTIONS,child,0,options)) return fail(c);
    if(append(c,"PREEXEC_ARMED",child,-1)) return 78;
    c->armed=1; c->live=1; c->tasks[0].pid=child;
    return 0; /* child remains stopped; never blindly CONT/PTRACE_DETACH */
}
int control_exec_stop(struct control *c,pid_t pid,int status) {
    if(!c->armed || c->exec_seen || pid!=c->root || !WIFSTOPPED(status) ||
       WSTOPSIG(status)!=SIGTRAP || ((unsigned)status>>16)!=PTRACE_EVENT_EXEC)
        return fail(c);
    if(append(c,"EXEC_STOP",pid,-1)) return 78;
    c->exec_seen=1; return 0;
}
int control_child(struct control *c,pid_t parent,pid_t child,int status) {
    if(!c->armed || !c->exec_seen || !task(c,parent) || child<=0 || task(c,child)) return fail(c);
    unsigned event=(unsigned)status>>16; unsigned long observed=0;
    if(!WIFSTOPPED(status) || WSTOPSIG(status)!=SIGTRAP ||
       (event!=PTRACE_EVENT_CLONE && event!=PTRACE_EVENT_FORK && event!=PTRACE_EVENT_VFORK) ||
       ptrace(PTRACE_GETEVENTMSG,parent,0,&observed) || observed!=(unsigned long)child) return fail(c);
    for(unsigned i=0;i<64;i++) if(!c->tasks[i].pid) {
        if(append(c,"TASK_BORN",child,parent)) return 78;
        c->tasks[i]=(struct control_task){.pid=child}; c->live++; return 0;
    }
    return fail(c); /* overflow never authorizes untracked child */
}
int control_request(struct control *c,pid_t pid,uint64_t id,long nr) {
    struct control_task *t=task(c,pid);
    if(!c->exec_seen || !t || t->pending) return fail(c);
    if(append(c,"REQUEST",pid,nr)) return 78;
    t->request=id; t->nr=nr; t->pending=1; return 0;
}
/* Durable decision BEFORE kernel response. pending:1=request,2=input,3=deny. */
int control_prepare(struct control *c,pid_t pid,uint64_t id,int denied) {
    struct control_task *t=task(c,pid);
    if(!t || t->pending!=1 || t->request!=id) return fail(c);
    if(denied) {
        if(c->denied==ULONG_MAX) return fail(c);
        c->denied++; c->failed=1;
        if(append(c,"DENY",pid,t->nr)) return 78;
        t->pending=3;
    } else {
        if(append(c,"INPUT_PREPARED",pid,t->nr)) return 78;
        t->pending=2;
    }
    return 0;
}
/* Invoke only AFTER the broker's actual ADDFD_SEND/SEND result. Not a substitute
 * for that result: this standalone API is not released as a trusted producer. */
int control_reply(struct control *c,pid_t pid,uint64_t id,int error) {
    struct control_task *t=task(c,pid);
    if(!t || t->pending<2 || t->request!=id) return fail(c);
    if(error) {
        c->failed=1;
        if(error!=-ENOENT) return fail(c); /* uncertain result: no retry */
        if(append(c,"CANCELLED",pid,t->nr)) return 78;
    } else if(append(c,t->pending==3?"REPLIED_DENY":"INPUT_DELIVERED",pid,t->nr)) return 78;
    t->pending=0; return 0;
}
int control_dead(struct control *c,pid_t pid,int status) {
    struct control_task *t=task(c,pid);
    if(!t || !(WIFEXITED(status)||WIFSIGNALED(status))) return fail(c);
    if(t->pending || !WIFEXITED(status) || WEXITSTATUS(status)!=0) c->failed=1;
    if(append(c,"TASK_DEAD",pid,status)) return 78;
    memset(t,0,sizeof *t); c->live--; return 0;
}
int control_finish(struct control *c) {
    if(c->finished || !c->exec_seen || c->live) return fail(c);
    int status=0; errno=0;
    if(waitpid(-1,&status,__WALL|WNOHANG)!=-1 || errno!=ECHILD) return fail(c);
    if(append(c,"ALL_DEAD",c->root,-1) || append(c,"COMPLETE",c->root,-1)) return 78;
    c->finished=1;
    return c->failed?78:0;
}
/* The reused native broker's durable callbacks now share this sequence and
 * per-task notification identity. Actual kernel reply precedes *_DELIVERED. */
static int broker_audit(void *opaque,const char *kind,uint64_t id,pid_t pid,long nr) {
    struct control *c=opaque;
    if(!strcmp(kind,"REQUEST")) return control_request(c,pid,id,nr)?-1:0;
    if(!strcmp(kind,"DENY")) return control_prepare(c,pid,id,1)?-1:0;
    if(!strcmp(kind,"INPUT_PREPARED")) return control_prepare(c,pid,id,0)?-1:0;
    if(!strcmp(kind,"INPUT_DELIVERED") || !strcmp(kind,"REPLIED_DENY"))
        return control_reply(c,pid,id,0)?-1:0;
    if(!strcmp(kind,"CANCELLED")) {
        struct control_task *t=task(c,pid);
        if(!t || !t->pending || t->request!=id) { fail(c); return -1; }
        c->failed=1;
        if(append(c,"CANCELLED",pid,nr)) return -1;
        t->pending=0; return 0;
    }
    fail(c); return -1;
}
int control_bind_broker(struct control *c,struct broker *b) {
    if(!c->armed || !c->exec_seen || c->finished || !b || b->listener<0) return fail(c);
    b->audit=broker_audit; b->audit_ctx=c; return 0;
}
