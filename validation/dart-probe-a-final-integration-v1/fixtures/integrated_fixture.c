/* Harmless native harness. Loader branch cannot be enabled in this build. */
#ifdef PROBE_A_LOADER_ENABLED
#error external loader define prohibited for harmless harness
#endif
#define PROBE_A_LOADER_ENABLED 0
#define main base_fixture_main
#include "../../dart-probe-a-harness-v1/fixtures/base_probe_a.c"
#undef main
#include <arpa/inet.h>
#include <netinet/in.h>
#include <stddef.h>
#include <sys/poll.h>
#include <sys/socket.h>
#include <sys/un.h>
static int matches(const char *path,const char *expected){
 char b[128];FILE *f=fopen(path,"r");if(!f)return 0;
 int ok=fgets(b,sizeof b,f)!=NULL;fclose(f);if(!ok)return 0;
 b[strcspn(b,"\r\n")]=0;return strcmp(b,expected)==0;
}
static int readonly(const char *path){struct statvfs s;return !statvfs(path,&s) && (s.f_flag&ST_RDONLY);}
static int ns_different(const char *kind,const char *host){
 char path[80],b[128];snprintf(path,sizeof path,"/proc/self/ns/%s",kind);
 ssize_t n=readlink(path,b,sizeof b-1);if(n<0)return 0;b[n]=0;return *host && strcmp(b,host)!=0;
}
static int cannot_write(const char *path){
 int fd=open(path,O_WRONLY|O_CLOEXEC);if(fd>=0){close(fd);return 0;}return errno==EROFS;
}
static int tcp_error(int family,const char *address,unsigned short port){
 int fd=socket(family,SOCK_STREAM|SOCK_CLOEXEC,0);if(fd<0)return errno;
 int rc;
 if(family==AF_INET){struct sockaddr_in a;memset(&a,0,sizeof a);a.sin_family=AF_INET;a.sin_port=htons(port);if(inet_pton(AF_INET,address,&a.sin_addr)!=1){close(fd);return EINVAL;}rc=connect(fd,(struct sockaddr *)&a,sizeof a);}
 else {struct sockaddr_in6 a;memset(&a,0,sizeof a);a.sin6_family=AF_INET6;a.sin6_port=htons(port);if(inet_pton(AF_INET6,address,&a.sin6_addr)!=1){close(fd);return EINVAL;}rc=connect(fd,(struct sockaddr *)&a,sizeof a);}
 int e=rc<0?errno:0;close(fd);return e;
}
static int unix_error(const char *path,int abstract){
 struct sockaddr_un a;memset(&a,0,sizeof a);a.sun_family=AF_UNIX;
 size_t n=strlen(path);if(n+1>=sizeof a.sun_path)return EINVAL;
 if(abstract)memcpy(a.sun_path+1,path,n);else memcpy(a.sun_path,path,n+1);
 socklen_t len=(socklen_t)(offsetof(struct sockaddr_un,sun_path)+n+1);
 int fd=socket(AF_UNIX,SOCK_STREAM|SOCK_CLOEXEC,0);if(fd<0)return errno;
 int rc=connect(fd,(struct sockaddr *)&a,len);int e=rc<0?errno:0;close(fd);return e;
}
static int reject_gate(const char *why){event("gate_failure","REJECTED",why);return 0;}
static int gate(int argc,char **argv){
 if(argc!=9 || strcmp(argv[1],"--harness"))return reject_gate("argument contract");
 const char *kinds[]={"mnt","net","user","pid"};
 for(int i=0;i<4;i++)if(!ns_different(kinds[i],argv[i+2]))return reject_gate(kinds[i]);
 if(!readonly("/")||!readonly("/dev")||!readonly("/fixture/native_fixture")||!readonly("/input/canary")||!readonly("/limits"))return reject_gate("read-only mounts");
 const char *keys[]={"memory.max","memory.swap.max","pids.max","cpu.max"};
 const char *vals[]={"67108864","0","8","25000 100000"};
 for(int i=0;i<4;i++){char path[100];snprintf(path,sizeof path,"/limits/%s",keys[i]);if(!matches(path,vals[i]))return reject_gate(keys[i]);}
 const char *tmp[]={"/tmp","/run","/dev/shm"};unsigned long caps[]={4194304,4194304,1048576};
 for(int i=0;i<3;i++){struct statvfs s;if(statvfs(tmp[i],&s)||s.f_blocks*s.f_frsize!=caps[i])return reject_gate(tmp[i]);}
 if(!cannot_write("/input/canary"))return reject_gate("canary write unexpectedly allowed");
 /* An executable may reject open with ETXTBSY before the ro-filesystem error.
    Require independently verified readonly mount in either case; never write. */
 int binfd=open("/fixture/native_fixture",O_WRONLY|O_CLOEXEC);int bine=errno;
 if(binfd>=0){close(binfd);return reject_gate("binary writable");}
 if(!readonly("/fixture/native_fixture")||(bine!=EROFS&&bine!=ETXTBSY))return reject_gate("binary write-open failed unexpectedly");
 char detail[100];snprintf(detail,sizeof detail,"binary open errno=%d; independent ST_RDONLY required; canary EROFS",bine);event("readonly_binary","OBSERVED",detail);
 int fd=open("/tmp/own-test",O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600);if(fd<0)return reject_gate("private tmp file open");
 ssize_t n=write(fd,"owned",5);close(fd);if(n!=5||unlink("/tmp/own-test"))return reject_gate("private tmp write/delete");
 fd=open("/run/own-test",O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600);if(fd<0)return reject_gate("private tmp file open");close(fd);if(unlink("/run/own-test"))return reject_gate("private run delete");
 int e4=tcp_error(AF_INET,"192.0.2.1",9),e6=tcp_error(AF_INET6,"2001:db8::1",9);
 int h6=tcp_error(AF_INET6,"::1",(unsigned short)strtoul(argv[6],NULL,10));
 int ux=unix_error(argv[7],0),ab=unix_error(argv[8],1);
 if(e4!=ENETUNREACH||e6!=ENETUNREACH||(h6!=ECONNREFUSED&&h6!=ENETUNREACH)||ux!=ENOENT||(ab!=ECONNREFUSED&&ab!=ENOENT))return reject_gate("network/socket isolation");
 event("isolation","PASS","mnt/net/user/pid distinct; root/dev/fixture/input/limits ro; private tmpfs4M/4M/1M; write EROFS; IPv4/IPv6 ENETUNREACH; host TCP/UNIX blocked");
 return 1;
}
int main(int argc,char **argv){
 if(install_handler())return 74;
 if(!gate(argc,argv)){event("harness_gate","REJECTED","no body executed");return 78;}
 event("post_open_ready","WAITING_FOR_IDENTITY","simulated open complete; no close before external GO");
 char go[4]={0};size_t used=0;struct timespec begun,now;
 if(clock_gettime(CLOCK_MONOTONIC,&begun))return 74;
 while(used<3){
  if(clock_gettime(CLOCK_MONOTONIC,&now))return 74;
  long ms=3000-(long)((now.tv_sec-begun.tv_sec)*1000+(now.tv_nsec-begun.tv_nsec)/1000000);
  if(ms<=0)break;
  struct pollfd p={STDIN_FILENO,POLLIN,0};
  if(poll(&p,1,(int)ms)!=1 || !(p.revents&POLLIN))break;
  ssize_t n=read(STDIN_FILENO,go+used,1);if(n!=1)break;used++;
 }
 if(used!=3||strcmp(go,"GO\n")){event("identity_gate","REJECTED","missing GO, EOF or timeout; no body");return 78;}
 event("post_open_accepted","SIMULATED","GO received; no DART load");
 event("body_entered","SIMULATED","harmless close simulation only");
 char *args[]={"base_fixture","--simulate","success",NULL};return base_fixture_main(3,args);
}
