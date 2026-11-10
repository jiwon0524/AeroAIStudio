#define _GNU_SOURCE
#include "exit_ack.h"
#include <fcntl.h>
#include <stdlib.h>
#include <pthread.h>
#include <sys/wait.h>
static const char bytes[]="AERO_V10_FIXED_INPUT_V1\n";
static pthread_t worker;
static pthread_mutex_t lock=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t wake=PTHREAD_COND_INITIALIZER;
static int finish_worker;
static int input(const char *);
static void *late_worker(void *unused) {
    (void)unused;
    if(pthread_mutex_lock(&lock))_Exit(71);
    while(!finish_worker)if(pthread_cond_wait(&wake,&lock))_Exit(71);
    if(pthread_mutex_unlock(&lock)||input("/input/fixed-alias.txt"))_Exit(71);
    return NULL;
}
static void cleanup(void) {
    if(pthread_mutex_lock(&lock))_Exit(72);
    finish_worker=1;
    if(pthread_cond_signal(&wake)||pthread_mutex_unlock(&lock)||pthread_join(worker,NULL))_Exit(72);
    if(dprintf(4,"{\"kind\":\"fixture_cleanup\",\"joined\":true}\n")<0)_Exit(72);
}
static int input(const char *name) {
    int fd=open(name,O_RDONLY|O_CLOEXEC);if(fd<5)return -1;
    char buffer[sizeof bytes];ssize_t n=read(fd,buffer,sizeof buffer);
    int good=n==(ssize_t)(sizeof bytes-1)&&!memcmp(buffer,bytes,sizeof bytes-1);
    return close(fd)||!good?-1:0;
}
/* Libc-only harmless protocol. No dlopen, DART/Gazebo, physics or marker IO. */
int main(int argc,char **argv) {
    if(argc!=3||strcmp(argv[1],"/input/fixed.txt")||strcmp(argv[2],"/input/fixed-alias.txt"))return 64;
    if(input(argv[1])||input(argv[2])||pthread_create(&worker,NULL,late_worker,NULL)||atexit(cleanup))return 65;
    for(int i=0;i<2;i++)if(dprintf(4,"{\"kind\":\"fixture_ready\",\"iteration\":0,\"sim_time_ns\":0}\n")<0)return 66;
    if(!aero_token(3,"GO\n",5000))return 67;
    pid_t child=fork();if(child<0)return 68;
    if(!child)_Exit(input(argv[1])?73:0);
    int status=-1;if(waitpid(child,&status,0)!=child||status)return 68;
    if(dprintf(4,"{\"kind\":\"fixture_child\",\"status\":0}\n")<0)return 68;
    for(int i=1;i<=100;i++)if(dprintf(4,"{\"kind\":\"fixture_sample\",\"iteration\":%d,\"sim_time_ns\":%d}\n",i,i*1000000)<0)return 69;
    if(!aero_exit_barrier())return 70;
    return 0; /* atexit joins the still-live thread AFTER EXIT_ACK. */
}
