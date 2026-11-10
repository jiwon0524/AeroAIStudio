#define _GNU_SOURCE
#include "metadata.h"
#include "catalog.h"
#include "loader.h"
#include <sys/syscall.h>
#include <sys/ioctl.h>
#include <sys/uio.h>
#include <linux/stat.h>
#include <linux/openat2.h>
#include <fcntl.h>
#include <unistd.h>
#include <string.h>
#include <errno.h>
#include <limits.h>
#include <stdlib.h>
#include <stdio.h>
#include "policy_counts.h"
static const char *dirs[]={
#include "directories.inc"
};
static const char *absent[]={
#include "negative.inc"
};
static const struct {const char *path,*target;} links[]={
#include "links.inc"
};
static int valid(struct broker *b,uint64_t id){return ioctl(b->listener,SECCOMP_IOCTL_NOTIF_ID_VALID,&id)==0;}
static int copy_path(pid_t pid,uint64_t ptr,char *out) {
    if(!ptr||ptr>UINT64_MAX-PATH_MAX)return -1;
    for(size_t i=0;i<PATH_MAX;i++) {
        struct iovec a={out+i,1},z={(void *)(uintptr_t)(ptr+i),1};
        if(process_vm_readv(pid,&a,1,&z,1,0)!=1)return -1;
        if(!out[i])return out[0]=='/'?0:-1;
    }
    return -1;
}
static int response(struct broker *b,const struct seccomp_notif *r,int code,long value) {
    struct seccomp_notif_resp out={.id=r->id,.error=code,.val=value};
    if(!valid(b,r->id)||ioctl(b->listener,SECCOMP_IOCTL_NOTIF_SEND,&out))return -1;
    return b->audit(b->audit_ctx,"META_DONE",r->id,(pid_t)r->pid,code?code:value)?-1:1;
}
int candidate_metadata(struct broker *b,const struct seccomp_notif *r) {
    uint64_t ptr=0,dst=0;size_t width=0;int access_mode=-1,link_probe=0,opening=0;
    if(r->data.nr==SYS_open || r->data.nr==SYS_openat) {
        opening=1;
        ptr=r->data.args[r->data.nr==SYS_open?0:1];
        uint64_t flags=r->data.args[r->data.nr==SYS_open?1:2],mode=r->data.args[r->data.nr==SYS_open?2:3];
        if(mode||(flags&~(uint64_t)(O_CLOEXEC|O_NONBLOCK|O_NOFOLLOW|O_LARGEFILE|O_DIRECTORY)))return 0;
    } else if(r->data.nr==SYS_newfstatat) {
        if(r->data.args[3]&~(uint64_t)AT_SYMLINK_NOFOLLOW)return 0;
        ptr=r->data.args[1];dst=r->data.args[2];width=sizeof(struct stat);
    } else if(r->data.nr==SYS_statx) {
        if(r->data.args[2]&~(uint64_t)(AT_SYMLINK_NOFOLLOW|AT_STATX_SYNC_TYPE)||
           r->data.args[3]&~(uint64_t)STATX_BASIC_STATS)return 0;
        ptr=r->data.args[1];dst=r->data.args[4];width=sizeof(struct statx);
    } else if(r->data.nr==SYS_access) {ptr=r->data.args[0];access_mode=(int)r->data.args[1];}
    else if(r->data.nr==SYS_faccessat||r->data.nr==SYS_faccessat2) {
        if(r->data.nr==SYS_faccessat2 && r->data.args[3])return 0;
        ptr=r->data.args[1];access_mode=(int)r->data.args[2];
    } else if(r->data.nr==SYS_readlink) {ptr=r->data.args[0];dst=r->data.args[1];width=r->data.args[2];link_probe=1;}
    else if(r->data.nr==SYS_readlinkat) {ptr=r->data.args[1];dst=r->data.args[2];width=r->data.args[3];link_probe=1;}
    else return 0;
    if(access_mode>=0&&(access_mode&~(R_OK|W_OK|X_OK)))return 0;
    char path[PATH_MAX];if(copy_path((pid_t)r->pid,ptr,path))return 0;
    /* Optional absence is an explicit policy, not a general ENOENT fallback.
     * Recheck it in the trusted namespace; an unexpected object is a failure. */
    if(link_probe)for(size_t i=0;i<sizeof links/sizeof links[0];i++)if(!strcmp(path,links[i].path)) {
        if(!width||width>PATH_MAX||!dst||dst>UINT64_MAX-width)return 0;
        char actual[PATH_MAX];
        /* This root is the owner's trusted same namespace, not target pointers. */
        ssize_t n=readlinkat(b->root_fd,path+1,actual,sizeof actual);
        if(n<0||(size_t)n!=strlen(links[i].target)||memcmp(actual,links[i].target,(size_t)n))return -1;
        size_t copied=(size_t)n<width?(size_t)n:width;
        struct iovec a={actual,copied},z={(void *)(uintptr_t)dst,copied};
        if(!valid(b,r->id)||b->audit(b->audit_ctx,"META_OBJECT",r->id,(pid_t)r->pid,COMPILED_PATHS+DIRECTORY_COUNT+NEGATIVE_COUNT+(long)i)||
           process_vm_writev((pid_t)r->pid,&a,1,&z,1,0)!=(ssize_t)copied)return -1;
        return response(b,r,0,(long)copied);
    }
    if(candidate_normalize(path,sizeof path))return 0;
    for(size_t i=0;i<sizeof absent/sizeof absent[0];i++)if(!strcmp(path,absent[i])) {
        struct open_how h={.flags=O_PATH|O_CLOEXEC,.resolve=RESOLVE_IN_ROOT|RESOLVE_NO_MAGICLINKS|RESOLVE_NO_SYMLINKS};
        errno=0;int probe=(int)syscall(SYS_openat2,b->root_fd,path,&h,sizeof h);int error=errno;
        if(probe>=0){close(probe);return -1;}
        if(error!=ENOENT)return -1;
        if(b->audit(b->audit_ctx,"META_OBJECT",r->id,(pid_t)r->pid,COMPILED_PATHS+DIRECTORY_COUNT+(long)i))return -1;
        return response(b,r,-ENOENT,0);
    }
    if(opening)return 0;
    for(size_t i=0;i<sizeof dirs/sizeof dirs[0];i++)if(!strcmp(path,dirs[i])) {
        struct open_how h={.flags=O_PATH|O_DIRECTORY|O_CLOEXEC,.resolve=RESOLVE_IN_ROOT|RESOLVE_NO_MAGICLINKS|RESOLVE_NO_SYMLINKS};
        int fd=(int)syscall(SYS_openat2,b->root_fd,path,&h,sizeof h);struct stat st;
        if(fd<0)return -1;
        if(fstat(fd,&st)||!S_ISDIR(st.st_mode)){close(fd);return -1;}
        if(b->audit(b->audit_ctx,"META_OBJECT",r->id,(pid_t)r->pid,COMPILED_PATHS+(long)i)){close(fd);return -1;}
        if(link_probe){close(fd);return response(b,r,-EINVAL,0);}
        if(access_mode>=0){close(fd);return response(b,r,(access_mode&W_OK)?-EACCES:0,0);}
        union {struct stat st;struct statx sx;} data;memset(&data,0,sizeof data);
        if(r->data.nr==SYS_newfstatat)data.st=st;
        else if(syscall(SYS_statx,fd,"",AT_EMPTY_PATH,STATX_BASIC_STATS,&data.sx)){close(fd);return -1;}
        close(fd);
        struct iovec a={&data,width},z={(void *)(uintptr_t)dst,width};
        if(!dst||dst>UINT64_MAX-width||!valid(b,r->id)||process_vm_writev((pid_t)r->pid,&a,1,&z,1,0)!=(ssize_t)width)return -1;
        return response(b,r,0,0);
    }
    const struct copy_input *input=NULL;
    for(size_t i=0;i<b->count;i++)if(!strcmp(path,b->inputs[i].pin.path)){input=b->inputs+i;break;}
    if(!input)return 0; /* Unknown probes are denied by the original broker. */
    int fd=catalog_open(b->root_fd,input);if(fd<0)return 0;
    int index=catalog_index(input->pin.path),code=0;
    if(index<0||b->audit(b->audit_ctx,"META_OBJECT",r->id,(pid_t)r->pid,index)){close(fd);return -1;}
    if(link_probe)code=-EINVAL; /* Approved canonical files are not symlinks. */
    else if(access_mode>=0) {
        if(access_mode&W_OK)code=-EACCES;
        if((access_mode&X_OK)&&!input->pin.executable)code=-EACCES;
    } else {
        union {struct stat st;struct statx sx;} bytes;memset(&bytes,0,sizeof bytes);
        if(loader_metadata(fd,(int)r->data.nr,&bytes,width)){close(fd);return -1;}
        if(!valid(b,r->id)||!dst||dst>UINT64_MAX-width){close(fd);return -1;}
        struct iovec a={&bytes,width},z={(void *)(uintptr_t)dst,width};
        if(process_vm_writev((pid_t)r->pid,&a,1,&z,1,0)!=(ssize_t)width){close(fd);return -1;}
    }
    close(fd);return response(b,r,code,0);
}

int candidate_normalize(char *path,size_t capacity) {
    if(!path||path[0]!='/'||strstr(path,"//")||strstr(path,"/../")||strstr(path,"/./"))return -1;
    size_t len=strlen(path);if((len>=3&&!strcmp(path+len-3,"/.."))||(len>=2&&!strcmp(path+len-2,"/.")))return -1;
    char result[PATH_MAX];
    if(!strncmp(path,"/lib/",5))snprintf(result,sizeof result,"/usr/lib/%s",path+5);
    else if(!strcmp(path,"/lib"))strcpy(result,"/usr/lib");
    else if(!strcmp(path,"/lib64")||!strcmp(path,"/usr/lib64"))strcpy(result,"/usr/lib64");
    else if(!strcmp(path,"/lib64/ld-linux-x86-64.so.2")||!strcmp(path,"/usr/lib64/ld-linux-x86-64.so.2"))strcpy(result,"/usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2");
    else return 0;
    if(strlen(result)>=capacity)return -1;
    strcpy(path,result);return 0;
}
