/* No DART headers/linkage. Default binary contains no dlopen/dlclose code.
 * Loader-enabled branch is compiled to an object only during this audit. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/statvfs.h>
#include <time.h>
#include <unistd.h>
#ifndef PROBE_A_LOADER_ENABLED
#define PROBE_A_LOADER_ENABLED 0
#endif
#if PROBE_A_LOADER_ENABLED
#include <dlfcn.h>
#endif
static unsigned seq;
static int escape(const char *s,char *out,size_t cap){
 size_t n=0;
 for(;*s && n+7<cap;s++){
  unsigned char c=(unsigned char)*s;
  if(c=='"'||c=='\\'){out[n++]='\\';out[n++]=(char)c;}
  else if(c<32){int k=snprintf(out+n,cap-n,"\\u%04x",c);if(k<0)break;n+=(size_t)k;}
  else out[n++]=(char)c;
 }
 out[n]=0;return *s!=0;
}
static void event(const char *phase,const char *result,const char *detail){
 struct timespec t;char quoted[1024];int truncated=escape(detail,quoted,sizeof quoted);
 if(clock_gettime(CLOCK_MONOTONIC,&t))_exit(74);
 printf("{\"schema\":\"probe_a_events_v1\",\"sequence\":%u,\"pid\":%ld,\"monotonic_ns\":%lld,\"phase\":\"%s\",\"result\":\"%s\",\"detail\":\"%s\",\"loader_compiled\":%s,\"detail_truncated\":%s}\n",++seq,(long)getpid(),(long long)t.tv_sec*1000000000LL+t.tv_nsec,phase,result,quoted,PROBE_A_LOADER_ENABLED?"true":"false",truncated?"true":"false");
 if(fflush(stdout))_exit(74);
}
static void term(int sig){
 const char msg[]="{\"schema\":\"probe_a_signal_v1\",\"phase\":\"signal\",\"signal\":15}\n";
 (void)sig;ssize_t written=write(STDOUT_FILENO,msg,sizeof msg-1);(void)written;_exit(143);
}
static int install_handler(void){
 struct sigaction a;memset(&a,0,sizeof a);a.sa_handler=term;sigemptyset(&a.sa_mask);
 return sigaction(SIGTERM,&a,NULL);
}
static int workflow(int open_failed,int close_failed,int mock){
 event("open_begin",mock?"SIMULATED":"ATTEMPT","core only; no DART symbol calls");
 if(open_failed){event("open_result","ERROR","synthetic \"open\" error\nnot DART");return 20;}
 event("open_result",mock?"SIMULATED":"OK","handle acquired");
 event("close_begin",mock?"SIMULATED":"ATTEMPT","one close; no object API");
 if(close_failed){event("close_result","ERROR","synthetic close error");return 21;}
 event("close_result",mock?"SIMULATED":"OK","success does not certify unmapping");return 0;
}
#if PROBE_A_LOADER_ENABLED
static int exact_file(const char *p,const char *want){
 char buf[128];FILE *f=fopen(p,"r");if(!f)return 0;
 int ok=fgets(buf,sizeof buf,f)!=NULL;fclose(f);
 if(!ok){return 0;}
 buf[strcspn(buf,"\r\n")]=0;return strcmp(buf,want)==0;
}
static int different_ns(const char *path,const char *host){
 char buf[128];ssize_t n=readlink(path,buf,sizeof buf-1);if(n<0)return 0;buf[n]=0;
 return host[0] && strcmp(buf,host)!=0;
}
static int gate(const char *host_mnt,const char *host_net){
 struct statvfs st;
 if(!different_ns("/proc/self/ns/mnt",host_mnt)||!different_ns("/proc/self/ns/net",host_net))return 0;
 if(statvfs("/",&st)||!(st.f_flag&ST_RDONLY))return 0;
 if(!exact_file("/limits/memory.max","67108864")||!exact_file("/limits/pids.max","8")||!exact_file("/limits/cpu.max","25000 100000")||!exact_file("/limits/memory.swap.max","0"))return 0;
 FILE *f=fopen("/proc/self/maps","r");if(!f)return 0;char line[2048];int bad=0;
 while(fgets(line,sizeof line,f))if(strstr(line,"libdart")||strstr(line,"libgz-")||strstr(line,"libgazebo"))bad=1;
 fclose(f);return !bad;
}
static int load_core(const char *host_mnt,const char *host_net){
 if(!gate(host_mnt,host_net)){event("gate","REJECTED","sandbox/resource/preexisting mapping gate");return 78;}
 event("open_begin","ATTEMPT","/audit/libdart.so.6.13.2; external hash manifest required");
 (void)dlerror();void *h=dlopen("/audit/libdart.so.6.13.2",RTLD_NOW|RTLD_LOCAL);
 if(!h){const char *e=dlerror();event("open_result","ERROR",e?e:"unavailable loader error");return 20;}
 event("open_result","OK","constructors have already executed; not safety proof");
 FILE *f=fopen("/proc/self/maps","r");if(!f){event("mapping","ERROR","maps unavailable; leaving process for supervisor cleanup");return 22;}
 char line[2048];unsigned count=0;
 while(fgets(line,sizeof line,f)){
  if(++count>512){fclose(f);event("mapping","ERROR","bounded mapping overflow");return 22;}
  event("mapping","OBSERVED",line);
 }
 if(ferror(f)){fclose(f);return 22;}fclose(f);
 event("close_begin","ATTEMPT","no DART calls or objects; implicit global finalizers possible");
 if(dlclose(h)){const char *e=dlerror();event("close_result","ERROR",e?e:"unavailable loader error");return 21;}
 event("close_result","OK","does not certify all dependencies unmapped");return 0;
}
#endif
int main(int argc,char **argv){
 if(install_handler())return 74;
 if(argc==2 && !strcmp(argv[1],"--contract")){event("contract","STATIC_ONLY","default loader disabled; explicit reviewed rebuild and approval required");return 0;}
 if(argc==3 && !strcmp(argv[1],"--simulate")){
  if(strcmp(argv[2],"success") && strcmp(argv[2],"open-error") && strcmp(argv[2],"close-error"))return 64;
  event("fixture_start","SIMULATED","offline fixture; no native DART load");
  int rc=workflow(!strcmp(argv[2],"open-error"),!strcmp(argv[2],"close-error"),1);
  event("fixture_exit",rc?"ERROR":"SIMULATED","no DART runtime verification");return rc;
 }
 if(argc==2 && !strcmp(argv[1],"--await-signal")){event("ready","SIMULATED","harmless signal/timeout fixture only");alarm(3);for(;;)pause();}
#if PROBE_A_LOADER_ENABLED
 if(argc==4 && !strcmp(argv[1],"--execute-approved-core-load")){
  event("fixture_start","ATTEMPT","requires external immutable closure/supervisor approval");
  int rc=load_core(argv[2],argv[3]);event("fixture_exit",rc?"ERROR":"OK","Probe B-D/World/Stage B never invoked");return rc;
 }
#endif
 event("entry","REJECTED","loader disabled or unsupported command; no retry");return 77;
}
