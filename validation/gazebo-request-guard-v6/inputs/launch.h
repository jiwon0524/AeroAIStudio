#ifndef LAUNCH_V6_H
#define LAUNCH_V6_H
#include "control.h"
#include "catalog.h"
struct launch_result { pid_t child; int collector,listener,audit_read,pidfd,stopped,cleanup_pending,collector_ready; };
/* Compile-only API for a dedicated trusted supervisor ALREADY inside the
 * intended sealed namespace with attested FD0..4. No released caller exists.
 * Successful return leaves the root at exec-stop, before loader instructions. */
int candidate_launch(struct control *,struct broker *,int,char *const[],char *const[],int,struct launch_result *);
int candidate_runtime_trace(struct control *,pid_t,int);
int candidate_supervise(struct control *,struct broker *,struct launch_result *);
int candidate_publish_audit(int,struct launch_result *);
int candidate_run(struct control *,struct broker *,int,char *const[],char *const[],int,int,struct launch_result *);
#endif
