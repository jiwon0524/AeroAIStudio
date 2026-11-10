#ifndef AERO_CONTROL_V4_H
#define AERO_CONTROL_V4_H
#include <sys/types.h>
#include <stdint.h>
#include <stddef.h>
struct control_task { pid_t pid; uint64_t request; long nr; int pending; };
struct control {
    int journal_fd, armed, exec_seen, failed, finished;
    pid_t root;
    unsigned long seq, denied;
    unsigned live;
    size_t journal_bytes;
    struct control_task tasks[64];
};
struct broker;
/* API only. No released entry calls these. arm consumes the trusted child's
 * actual initial SIGSTOP with waitpid and sets options BEFORE first exec. */
int control_arm(struct control *,pid_t,int);
int control_exec_stop(struct control *,pid_t,int);
int control_child(struct control *,pid_t,pid_t,int);
int control_request(struct control *,pid_t,uint64_t,long);
int control_prepare(struct control *,pid_t,uint64_t,int);
int control_reply(struct control *,pid_t,uint64_t,int);
int control_dead(struct control *,pid_t,int);
int control_finish(struct control *);
int control_bind_broker(struct control *,struct broker *);
#endif
