#ifndef GUARD_METADATA_H
#define GUARD_METADATA_H
#include "broker.h"
/* Return1 handled (actual response sent),0 not metadata,-1 transport failure. */
int candidate_metadata(struct broker *,const struct seccomp_notif *);
int candidate_normalize(char *,size_t);
#endif
