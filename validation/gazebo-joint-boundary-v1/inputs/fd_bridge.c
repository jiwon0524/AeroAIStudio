/* Candidate only. Never executed by this phase.
 * Reject inherited sockets/files before any subject exec. Output pipes must
 * be distinct from the control and observation pipes, including stderr.
 */
#define _GNU_SOURCE
#include <unistd.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <sys/resource.h>
#include <sys/sysmacros.h>

static int endpoint(int fd,int direction,struct stat *st) {
  const int flags=fcntl(fd,F_GETFL);
  return flags>=0 && !(flags&O_PATH) && (flags&O_ACCMODE)==direction &&
    fstat(fd,st)==0 && S_ISFIFO(st->st_mode);
}
static int same_pipe(const struct stat *a,const struct stat *b) {
  return a->st_dev==b->st_dev && a->st_ino==b->st_ino;
}
int main(int argc,char **argv) {
  struct stat in,out,err,nullst;
  if(argc!=4 || !endpoint(0,O_RDONLY,&in) ||
     !endpoint(1,O_WRONLY,&out) || !endpoint(2,O_WRONLY,&err) ||
     same_pipe(&in,&out) || same_pipe(&in,&err) || same_pipe(&out,&err))
    return 78;
  const char *exe=argv[1];
  if(exe[0]!='/' || argv[2][0]!='/' || argv[3][0]!='/') return 78;
  if(dup2(0,3)!=3 || dup2(1,4)!=4) return 78;
  if(fcntl(3,F_SETFD,0) || fcntl(4,F_SETFD,0)) return 78;
  int nullfd=open("/dev/null",O_RDONLY|O_CLOEXEC|O_NOFOLLOW);
  if(nullfd<0 || fstat(nullfd,&nullst) || !S_ISCHR(nullst.st_mode) ||
     major(nullst.st_rdev)!=1 || minor(nullst.st_rdev)!=3 ||
     dup2(nullfd,0)!=0 || dup2(2,1)!=1) return 78;
  if(nullfd>4 && close(nullfd)) return 78;
  /* Mandatory success before exec: no mount source or ambient socket FD. */
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
