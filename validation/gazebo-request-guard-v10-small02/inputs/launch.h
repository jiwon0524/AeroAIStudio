#ifndef LAUNCH_V8_H
#define LAUNCH_V8_H
#include "control.h"
#include "catalog.h"
struct launch_result { pid_t child; int collector,listener,audit_read,pidfd,stopped,cleanup_pending,collector_ready; };
/* Compile-only API for a dedicated trusted supervisor ALREADY inside the
 * intended sealed namespace with attested FD0..4. No released caller exists.
 * Successful return leaves the root at exec-stop, before loader instructions. */
int candidate_launch(struct control *,struct broker *,int,char *const[],char *const[],int,int,struct launch_result *);
int candidate_runtime_trace(struct control *,struct broker *,pid_t,int);
int candidate_supervise(struct control *,struct broker *,struct launch_result *);
int candidate_publish_audit(int,struct launch_result *);
int candidate_run(struct control *,struct broker *,int,char *const[],char *const[],int,int,struct launch_result *);
int candidate_stage(struct control *,int,int,int,char *const[],char *const[],struct launch_result *);
pid_t candidate_owner_bootstrap(int,int,char *const[],char *const[]);
int candidate_owner_fds(int,int,int);
int candidate_owner_diagnostic_fd(int);
int candidate_owner_diagnostic(const char *,int);
#endif
