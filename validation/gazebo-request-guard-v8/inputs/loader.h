#ifndef GUARD_LOADER_H
#define GUARD_LOADER_H
#include "bound.h"
#include <stddef.h>
/* Single owner transaction prevents FD close/ADDFD while checked mmap reaches
 * syscall exit. Every close MUST be traced; duplication/close_range stay deny.
 * Not a boolean supplied by target: owner starts from its ptrace stop and
 * controls all descriptor mutations. */
struct load_tx { pid_t task; int fd; long nr; struct bound object; };
int loader_begin(struct load_tx *,pid_t,int,int,const char *,int,uint64_t,uint64_t,uint64_t);
int loader_exit(struct load_tx *,pid_t,long);
int loader_mutation_allowed(const struct load_tx *);
int loader_metadata(int,int,void *,size_t);
int loader_protect(struct load_tx *,pid_t,uint64_t,uint64_t,int,int,const char *);
#endif
