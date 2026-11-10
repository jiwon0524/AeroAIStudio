#define _GNU_SOURCE
#include "launch.h"
#include "policy_counts.h"
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <errno.h>
#include <fcntl.h>
static int number(const char *s) {
    char *end=NULL;long n=strtol(s,&end,10);
    return !s[0]||!end||*end||n<5||n>1048575?-1:(int)n;
}
int main(int argc,char **argv) {
    if(argc!=7||strcmp(argv[1],"--harmless-owner-v10"))return 78;
    int fd[5];for(int i=0;i<5;i++){fd[i]=number(argv[i+2]);if(fd[i]<0)return 78;}
    for(int i=0;i<5;i++)for(int j=0;j<i;j++)if(fd[i]==fd[j])return 78;
    /* pass_fds clears CLOEXEC across exec. Restore private control slots
     * before the v9 gate; fail closed if either descriptor cannot be set. */
    if(fcntl(fd[3],F_SETFD,FD_CLOEXEC)||fcntl(fd[4],F_SETFD,FD_CLOEXEC))return 78;
    if(candidate_owner_fds(fd[0],fd[1],fd[2]))return 78;
    char *target[]={TARGET_EXECUTABLE,TARGET_INPUT,TARGET_ALIAS,NULL};
    char *environment[]={"LC_ALL=C","TMPDIR=/scratch","HOME=/scratch",NULL};
    pid_t child=candidate_owner_bootstrap(fd[3],fd[4],target,environment);
    if(child<0)return 78;
    int status=0;pid_t got;
    do {got=waitpid(child,&status,0);}while(got<0&&errno==EINTR);
    return got==child&&WIFEXITED(status)&&!WEXITSTATUS(status)?0:78;
}
