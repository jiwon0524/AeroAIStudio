#define _GNU_SOURCE
#include "exit_ack.h"
#include <sys/stat.h>
/* Deliberately libc-only: no dlopen, exec, Gazebo, DART or physical state. */
int main(int argc,char **argv) {
 (void)argv;struct stat a,b;
 if(argc!=3 || fstat(3,&a) || fstat(4,&b) || !S_ISFIFO(a.st_mode) || !S_ISFIFO(b.st_mode)) return 64;
 for(int i=0;i<2;++i)
  if(dprintf(4,"{\"kind\":\"fixture_ready\",\"iteration\":0,\"sim_time_ns\":0}\n")<0) return 65;
 if(!aero_token(3,"GO\n",30000)) return 66;
 for(int i=1;i<=100;++i)
  if(dprintf(4,"{\"kind\":\"fixture_sample\",\"iteration\":%d,\"sim_time_ns\":%d}\n",i,i*1000000)<0) return 67;
 if(!aero_exit_barrier()) return 68;
 return 0;
}
