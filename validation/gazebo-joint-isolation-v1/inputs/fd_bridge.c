/* No subject is loaded here until a separately authorized sandbox exec.
 * bwrap/systemd preserve only stdin/stdout; move these FIFOs to harness 3/4.
 */
#define _GNU_SOURCE
#include <unistd.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <sys/resource.h>
#include <string.h>
#include <stdlib.h>
int main(int argc,char **argv) {
  struct stat in,out;
  if(argc!=4 || fstat(0,&in) || fstat(1,&out) ||
     !S_ISFIFO(in.st_mode) || !S_ISFIFO(out.st_mode)) return 78;
  const char *exe=argv[1];
  if(exe[0]!='/' || argv[2][0]!='/' || argv[3][0]!='/') return 78;
  if(dup2(0,3)!=3 || dup2(1,4)!=4) return 78;
  if(fcntl(3,F_SETFD,0) || fcntl(4,F_SETFD,0)) return 78;
  int nullfd=open("/dev/null",O_RDWR|O_CLOEXEC);
  if(nullfd<0 || dup2(nullfd,0)!=0 || dup2(2,1)!=1) return 78;
  if(nullfd>4) close(nullfd);
  if(close_range(5,~0U,0)) return 78;
  struct { int kind; rlim_t value; } bounds[] = {
    {RLIMIT_CPU,10},{RLIMIT_AS,2147483648ULL},{RLIMIT_FSIZE,1048576},
    {RLIMIT_NOFILE,256},{RLIMIT_CORE,0}};
  for(unsigned i=0;i<sizeof(bounds)/sizeof(bounds[0]);++i) {
    struct rlimit lim={bounds[i].value,bounds[i].value};
    if(setrlimit(bounds[i].kind,&lim)) return 78;
  }
  execv(exe,argv+1);
  return 78;
}
