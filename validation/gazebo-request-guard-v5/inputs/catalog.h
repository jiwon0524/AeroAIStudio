#ifndef CATALOG_V5_H
#define CATALOG_V5_H
#include <stdint.h>
#include <sys/types.h>
#include <stddef.h>
#include "broker.h"
struct permitted { const char *path; uint64_t origin_dev,origin_ino; const char *sha; int executable; const char *source; };
/* Runtime copy identity is separate from immutable original/hash authority. */
struct copy_input { struct pinned_input pin; uint64_t origin_dev,origin_ino,size; };
int catalog_verify(const struct copy_input *,int);
int catalog_open(int,const struct copy_input *);
int catalog_ready(int,const struct copy_input *,size_t);
int catalog_full_ready(int,const struct copy_input *,size_t);
const struct permitted *catalog_policy(const char *);
int catalog_index(const char *);
int catalog_prepare(struct copy_input *,size_t,uint64_t);
void catalog_close(struct copy_input *,size_t);
#endif
