#ifndef GUARD_BOUND_H
#define GUARD_BOUND_H
#include <stdint.h>
#include <sys/types.h>
#include <sys/stat.h>
#ifdef __cplusplus
extern "C" {
#endif
struct bound { uint64_t dev,ino,size; int executable; };
/* Same final FD, immutable bytes and mode, exact pinned SHA256. No size limit
 * policy is raised here: caller catalog admission still enforces current caps. */
int bound_verify(int,const char *,const struct bound *,struct bound *);
int bound_canonical(int,const char *,int,const char *,struct bound *);
int bound_mount(int,const char *,int,const char *,int);
int bound_anchor(const void *,int);
#ifdef __cplusplus
}
#endif
#endif
