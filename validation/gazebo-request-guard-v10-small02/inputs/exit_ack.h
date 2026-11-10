#ifndef AERO_EXIT_ACK_H
#define AERO_EXIT_ACK_H
#include <poll.h>
#include <unistd.h>
#include <time.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
static inline long long aero_ms(void) {
 struct timespec t; if(clock_gettime(CLOCK_MONOTONIC,&t)) return -1;
 return (long long)t.tv_sec*1000+t.tv_nsec/1000000;
}
static inline int aero_token(int fd,const char *token,int timeout_ms) {
 long long deadline=aero_ms()+timeout_ms;
 for(size_t i=0;i<strlen(token);++i) {
  long long left=deadline-aero_ms(); if(left<=0) return 0;
  struct pollfd p={fd,POLLIN,0};int rc;
  do {
   left=deadline-aero_ms();if(left<=0) return 0;
   rc=poll(&p,1,(int)left);
  } while(rc<0 && errno==EINTR);
  if(rc!=1 || !(p.revents&POLLIN)) return 0;
  char c;if(read(fd,&c,1)!=1 || c!=token[i]) return 0;
 }
 return 1;
}
static inline int aero_exit_barrier(void) {
 if(dprintf(4,"{\"kind\":\"final_wait\",\"iteration\":100,\"sim_time_ns\":100000000}\n")<0) return 0;
 return aero_token(3,"EXIT_ACK\n",5000);
}
#endif
