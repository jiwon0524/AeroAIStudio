#define _GNU_SOURCE
#include "map_io.h"
#include <assert.h>
#include <stdio.h>
struct event {enum map_operation op;long result;int error;size_t requested;};
static struct event events[3];
static int opened,written,closed,event_count;
static int open_error,write_error,close_error,short_write,log_fail;
static int mock_open(const char *path,int flags) {
    opened++;assert(!strcmp(path,"/mock/uid_map"));
    assert(flags==(O_WRONLY|O_CLOEXEC));
    if(open_error){errno=open_error;return -1;}return 41;
}
static ssize_t mock_write(int fd,const void *value,size_t size) {
    written++;assert(fd==41&&size==9&&!memcmp(value,"0 1000 1\n",9));
    if(write_error){errno=write_error;return -1;}
    return (ssize_t)size-short_write;
}
static int mock_close(int fd) {
    closed++;assert(fd==41);
    if(close_error){errno=close_error;return -1;}return 0;
}
static int mock_emit(const char *label,enum map_operation op,long result,int error,size_t size) {
    assert(!strcmp(label,"uid-map")&&event_count<3);
    events[event_count++]=(struct event){op,result,error,size};
    errno=ENOTTY; /* A reporting operation must not replace the captured errno. */
    return !!(log_fail&(1<<op));
}
int main(void) {
    static const struct map_io_ops ops={mock_open,mock_write,mock_close,mock_emit};
    struct {int oe,we,ce,shortened,lf,expected;} cases[]={
        {0,0,0,0,0,0},
        {EACCES,0,0,0,0,EACCES},
        {EPERM,0,0,0,0,EPERM},
        {0,EPERM,0,0,0,EPERM},
        {0,EPERM,EBADF,0,0,EPERM},
        {0,0,0,1,0,EIO},
        {0,0,EBADF,0,0,EBADF},
        {0,0,0,0,1<<MAP_OPEN,EIO},
        {0,0,0,0,1<<MAP_WRITE,EIO},
        {0,0,0,0,1<<MAP_CLOSE,EIO},
        {0,EPERM,EBADF,0,(1<<MAP_WRITE)|(1<<MAP_CLOSE),EPERM},
        {EPERM,0,0,0,1<<MAP_OPEN,EPERM},
        {0,0,EBADF,1,1<<MAP_WRITE,EIO}
    };
    for(size_t i=0;i<sizeof cases/sizeof cases[0];i++) {
        opened=written=closed=event_count=0;
        open_error=cases[i].oe;write_error=cases[i].we;close_error=cases[i].ce;
        short_write=cases[i].shortened;log_fail=cases[i].lf;
        errno=EBUSY;
        int rc=map_io(&ops,"uid-map","/mock/uid_map","0 1000 1\n");
        int outcome_errno=errno;
        assert(rc==(cases[i].expected?-1:0));
        assert(outcome_errno==(cases[i].expected?cases[i].expected:EBUSY));
        assert(opened==1&&closed==!open_error);
        assert(written==(!open_error&&!(log_fail&(1<<MAP_OPEN))));
        assert(events[0].op==MAP_OPEN&&events[0].result==(open_error?-1:41));
        assert(events[0].error==open_error&&events[0].requested==9);
        if(written) {
            assert(event_count==3&&events[1].op==MAP_WRITE&&events[2].op==MAP_CLOSE);
            assert(events[1].result==(write_error?-1:9-short_write));
            assert(events[1].error==write_error&&events[2].error==close_error);
        }
        if(!open_error&&!written)assert(event_count==2&&events[1].op==MAP_CLOSE);
    }
    errno=0;assert(map_io(NULL,"uid-map","/mock/uid_map","x")==-1&&errno==EINVAL);
    puts("PASS 14 callback-only map I/O cases; namespace/map filesystem operations 0");
    return 0;
}
