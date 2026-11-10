#ifndef AERO_MAP_IO_H
#define AERO_MAP_IO_H
/* No retries, privilege changes or namespace creation. The production adapter
 * supplies the original open/write/close functions. Unit tests supply only
 * callbacks and never touch /proc or create a namespace. */
#include <errno.h>
#include <fcntl.h>
#include <stddef.h>
#include <string.h>
#include <sys/types.h>
enum map_operation { MAP_OPEN, MAP_WRITE, MAP_CLOSE };
struct map_io_ops {
    int (*open_map)(const char *,int);
    ssize_t (*write_map)(int,const void *,size_t);
    int (*close_map)(int);
    int (*emit)(const char *,enum map_operation,long,int,size_t);
};
static int map_io(const struct map_io_ops *ops,const char *label,
                  const char *path,const char *value) {
    if(!ops||!ops->open_map||!ops->write_map||!ops->close_map||!ops->emit||
       !label||!path||!value){errno=EINVAL;return -1;}
    int entry_errno=errno;
    size_t length=strlen(value);
    errno=0;
    int fd=ops->open_map(path,O_WRONLY|O_CLOEXEC);
    int open_errno=errno; /* Before reporting or any cleanup. */
    int open_log=ops->emit(label,MAP_OPEN,fd,open_errno,length);
    if(fd<0){errno=open_errno;return -1;}
    if(open_log) {
        errno=0;int closed=ops->close_map(fd);int close_errno=errno;
        (void)ops->emit(label,MAP_CLOSE,closed,close_errno,length);
        errno=EIO;return -1; /* Never write when open evidence was not durable. */
    }
    errno=0;
    ssize_t wrote=ops->write_map(fd,value,length);
    int write_errno=errno;
    int write_log=ops->emit(label,MAP_WRITE,(long)wrote,write_errno,length);
    errno=0;
    int closed=ops->close_map(fd);
    int close_errno=errno;
    int close_log=ops->emit(label,MAP_CLOSE,closed,close_errno,length);
    /* Earlier mapping failure wins over close/reporting errors. All available
     * operation records are still emitted, so secondary errors are retained. */
    if(wrote!=(ssize_t)length){errno=wrote<0?write_errno:EIO;return -1;}
    if(closed){errno=close_errno;return -1;}
    if(write_log||close_log){errno=EIO;return -1;}
    errno=entry_errno;return 0;
}
#endif
