/* Harmless protocol fixture. No loader API, DART linkage, or runtime entry. */
#define _POSIX_C_SOURCE 200809L
#include <poll.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
int main(void) {
  puts("POST_OPEN_SIMULATED"); if(fflush(stdout)) return 74;
  struct pollfd p={STDIN_FILENO,POLLIN,0};
  if(poll(&p,1,1000)!=1 || !(p.revents&POLLIN)) return 78;
  char buf[16]; if(!fgets(buf,sizeof buf,stdin) || strcmp(buf,"CLOSE\n")) return 78;
  puts("CLOSE_SIMULATED"); return fflush(stdout)?74:0;
}
