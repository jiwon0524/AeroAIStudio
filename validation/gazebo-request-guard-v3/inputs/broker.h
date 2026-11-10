#ifndef AERO_BROKER_H
#define AERO_BROKER_H
#include <stdint.h>
#include <stddef.h>
#include <sys/types.h>
#include <linux/seccomp.h>
/* Owned only by the trusted supervisor. Hash/manifest verification is a
 * prerequisite performed against this same FD by snapshots.py, never by target.
 * No writable target memory contains this table. */
struct pinned_input { const char *path; int fd; uint64_t dev, ino; int executable, delivery_ready; };
typedef int (*audit_fn)(void *, const char *, uint64_t, pid_t, long);
struct broker {
    int listener;
    const struct pinned_input *inputs;
    size_t count;
    audit_fn audit; void *audit_ctx;
};
/* Trusted single-thread launch stub only; returns listener or -1. NOT invoked
 * by any released entry point. Listener handoff/initial exec remain blocked. */
int candidate_install_filter(void);
int candidate_tree_monitor(pid_t,int,int,struct broker *);
/* One notification, already received on supervisor-owned listener. serial
 * owner only. Task membership must be proved independently before call. */
int candidate_broker_request(struct broker *, const struct seccomp_notif *);
#endif
