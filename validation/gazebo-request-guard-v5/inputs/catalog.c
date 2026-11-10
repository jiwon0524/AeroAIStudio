#define _GNU_SOURCE
#include "catalog.h"
#include <sys/stat.h>
#include <sys/syscall.h>
#include <linux/openat2.h>
#include <fcntl.h>
#include <unistd.h>
#include <string.h>
#include <stdio.h>
#include <openssl/evp.h>
#include <sys/resource.h>
#include <dirent.h>
#include <stdlib.h>
#include "policy_counts.h"
#ifndef F_SEAL_EXEC
#define F_SEAL_EXEC 0x20
#endif
static const struct permitted allow[]={
#include "allowlist.inc"
};
const struct permitted *catalog_policy(const char *path) {
    if(!path) return NULL;
    for(size_t i=0;i<sizeof allow/sizeof allow[0];i++) if(!strcmp(path,allow[i].path)) return allow+i;
    return NULL;
}
int catalog_index(const char *path) {
    const struct permitted *p=catalog_policy(path);return p?(int)(p-allow):-1;
}
int catalog_verify(const struct copy_input *p,int fd) {
    if(!p) return -1;
    const struct permitted *expected=catalog_policy(p->pin.path);
    if(!expected || expected->origin_dev!=p->origin_dev || expected->origin_ino!=p->origin_ino ||
       expected->executable!=p->pin.executable || p->size>67108864) return -1;
    struct stat st; int mode=fcntl(fd,F_GETFL),seals=fcntl(fd,F_GET_SEALS);
    const int required=F_SEAL_WRITE|F_SEAL_GROW|F_SEAL_SHRINK|F_SEAL_SEAL|F_SEAL_EXEC;
    if(mode<0 || (mode&O_ACCMODE)!=O_RDONLY || (mode&O_PATH) || seals<0 || (seals&required)!=required ||
       fstat(fd,&st) || !S_ISREG(st.st_mode) || (uint64_t)st.st_dev!=p->pin.dev ||
       (uint64_t)st.st_ino!=p->pin.ino || (uint64_t)st.st_size!=p->size ||
       (!!(st.st_mode&0111)!=!!p->pin.executable)) return -1;
    EVP_MD_CTX *ctx=EVP_MD_CTX_new(); if(!ctx) return -1;
    unsigned char buffer[65536],hash[32]; unsigned length=0; off_t offset=0; int good=0;
    if(EVP_DigestInit_ex(ctx,EVP_sha256(),NULL)!=1) goto done;
    for(;;) {
        ssize_t n=pread(fd,buffer,sizeof buffer,offset);
        if(n<0) goto done;
        if(!n) break;
        if(EVP_DigestUpdate(ctx,buffer,(size_t)n)!=1) goto done;
        offset+=n;
    }
    if(EVP_DigestFinal_ex(ctx,hash,&length)!=1 || length!=32) goto done;
    char hex[65]; static const char digits[]="0123456789abcdef";
    for(unsigned i=0;i<32;i++) { hex[2*i]=digits[hash[i]>>4];hex[2*i+1]=digits[hash[i]&15]; }
    hex[64]=0; good=!strcmp(hex,expected->sha);
done:
    EVP_MD_CTX_free(ctx); return good?0:-1;
}
int catalog_open(int root_fd,const struct copy_input *p) {
    if(!p || catalog_verify(p,p->pin.fd)) return -1;
    /* No ambient target reopen, magic links or unchecked symlink traversal.
     * Root belongs to the trusted isolated supervisor's mount namespace. */
    struct open_how how={.flags=O_RDONLY|O_CLOEXEC|O_NOFOLLOW,
        .resolve=RESOLVE_IN_ROOT|RESOLVE_NO_MAGICLINKS|RESOLVE_NO_SYMLINKS};
    int fd=(int)syscall(SYS_openat2,root_fd,p->pin.path,&how,sizeof how);
    if(fd<0) return -1;
    if(catalog_verify(p,fd)) { close(fd); return -1; }
    return fd; /* canonical open description -> ADDFD; pinned object is SAME */
}
int catalog_ready(int root_fd,const struct copy_input *rows,size_t count) {
    if(!rows || root_fd<0 || count!=sizeof allow/sizeof allow[0]) return -1;
    for(size_t i=0;i<count;i++) {
        if(strcmp(rows[i].pin.path,allow[i].path)) return -1;
        for(size_t j=0;j<i;j++)
            if(rows[j].origin_dev==rows[i].origin_dev && rows[j].origin_ino==rows[i].origin_ino &&
               (rows[j].pin.dev!=rows[i].pin.dev || rows[j].pin.ino!=rows[i].pin.ino)) return -1;
            else if((rows[j].origin_dev!=rows[i].origin_dev || rows[j].origin_ino!=rows[i].origin_ino) &&
                    rows[j].pin.dev==rows[i].pin.dev && rows[j].pin.ino==rows[i].pin.ino) return -1;
        int fd=catalog_open(root_fd,rows+i); if(fd<0) return -1; close(fd);
    }
    return 0;
}
int catalog_full_ready(int root_fd,const struct copy_input *rows,size_t count) {
    /* Missing mandatory objects cannot be hidden by a successful subset. */
    if(COMPILED_PATHS!=FULL_REQUIRED_PATHS) return -1;
    return catalog_ready(root_fd,rows,count);
}
void catalog_close(struct copy_input *rows,size_t count) {
    if(!rows) return;
    for(size_t i=0;i<count;i++) {
        int fd=rows[i].pin.fd;
        if(fd>=0) {
            for(size_t j=i+1;j<count;j++) if(rows[j].pin.fd==fd) rows[j].pin.fd=-1;
            close(fd);rows[i].pin.fd=-1;
        }
    }
}
int catalog_prepare(struct copy_input *rows,size_t count,uint64_t budget) {
    /* No limit is raised. Caller must separately attest preparer memory cgroup
     * and overhead. budget is an admission cap, not observed peak usage. */
    if(!rows||count!=COMPILED_PATHS||budget>536870912ULL||budget<131072) return -1;
    for(size_t i=0;i<count;i++) {memset(rows+i,0,sizeof rows[i]);rows[i].pin.fd=-1;}
    struct rlimit files,size_limit;
    if(getrlimit(RLIMIT_NOFILE,&files)||getrlimit(RLIMIT_FSIZE,&size_limit)) return -1;
    uint64_t total=131072;size_t groups=0;
    for(size_t i=0;i<count;i++) {
        int duplicate=0;
        for(size_t j=0;j<i;j++) if(allow[j].origin_dev==allow[i].origin_dev&&allow[j].origin_ino==allow[i].origin_ino) duplicate=1;
        if(duplicate) continue;
        struct stat st;
        if(stat(allow[i].source,&st)||st.st_size<0||st.st_size>67108864||
           (uint64_t)st.st_size>(uint64_t)size_limit.rlim_cur) return -1;
        total+=((uint64_t)st.st_size+4095)&~4095ULL;groups++;
        if(total>budget) return -1;
    }
    DIR *d=opendir("/proc/self/fd");if(!d) return -1;
    size_t open_below_limit=0;struct dirent *entry;
    while((entry=readdir(d))) {
        char *end;unsigned long fd=strtoul(entry->d_name,&end,10);
        if(entry->d_name[0]!='.'&&!*end&&fd<files.rlim_cur) open_below_limit++;
    }
    closedir(d);
    if(files.rlim_cur!=RLIM_INFINITY && (uint64_t)open_below_limit+groups+3>files.rlim_cur) return -1;
    uint64_t admitted=131072;
    for(size_t i=0;i<count;i++) {
        const struct permitted *p=allow+i;
        rows[i].pin.path=p->path;rows[i].origin_dev=p->origin_dev;rows[i].origin_ino=p->origin_ino;
        rows[i].pin.executable=p->executable;
        for(size_t j=0;j<i;j++) if(rows[j].origin_dev==p->origin_dev&&rows[j].origin_ino==p->origin_ino) {
            rows[i]=rows[j];rows[i].pin.path=p->path;break;
        }
        if(rows[i].pin.fd>=0) continue;
        int src=open(p->source,O_RDONLY|O_CLOEXEC|O_NOFOLLOW);
        struct stat before,after;
        if(src<0) goto failed;
        if(fstat(src,&before)||!S_ISREG(before.st_mode)||(uint64_t)before.st_dev!=p->origin_dev||
           (uint64_t)before.st_ino!=p->origin_ino||before.st_size<0||before.st_size>67108864) {close(src);goto failed;}
        admitted+=((uint64_t)before.st_size+4095)&~4095ULL;
        if(admitted>budget || (uint64_t)before.st_size>(uint64_t)size_limit.rlim_cur) {close(src);goto failed;}
        int flags=3|(p->executable?0x10:0x08); /* CLOEXEC|ALLOW_SEALING|explicit EXEC/NX */
        int writable=(int)syscall(SYS_memfd_create,"aero-input",flags);
        if(writable<0) {close(src);goto failed;}
        int error=fchmod(writable,p->executable?0500:0400);
        unsigned char chunk[65536];off_t offset=0;
        while(!error && offset<before.st_size) {
            size_t amount=(uint64_t)(before.st_size-offset)>sizeof chunk?sizeof chunk:(size_t)(before.st_size-offset);
            ssize_t n=pread(src,chunk,amount,offset);
            if(n<=0) {error=1;break;}
            ssize_t pos=0;
            while(pos<n) {ssize_t w=pwrite(writable,chunk+pos,(size_t)(n-pos),offset+pos);if(w<=0) {error=1;break;}pos+=w;}
            offset+=n;
        }
        if(fstat(src,&after)||before.st_dev!=after.st_dev||before.st_ino!=after.st_ino||before.st_size!=after.st_size||
           before.st_mtim.tv_sec!=after.st_mtim.tv_sec||before.st_mtim.tv_nsec!=after.st_mtim.tv_nsec||
           before.st_ctim.tv_sec!=after.st_ctim.tv_sec||before.st_ctim.tv_nsec!=after.st_ctim.tv_nsec) error=1;
        close(src);
        if(error || fcntl(writable,F_ADD_SEALS,F_SEAL_WRITE|F_SEAL_GROW|F_SEAL_SHRINK|F_SEAL_SEAL|F_SEAL_EXEC)) {close(writable);goto failed;}
        char path[64];snprintf(path,sizeof path,"/proc/self/fd/%d",writable);
        int fd=open(path,O_RDONLY|O_CLOEXEC);struct stat st;
        close(writable);
        if(fd<0) goto failed;
        rows[i].pin.fd=fd;
        if(fstat(fd,&st)) goto failed;
        rows[i].pin.dev=st.st_dev;rows[i].pin.ino=st.st_ino;rows[i].size=(uint64_t)st.st_size;
        if(catalog_verify(rows+i,fd)) goto failed; /* hash final SEALED bytes */
    }
    return 0;
failed:
    catalog_close(rows,count);return -1;
}
