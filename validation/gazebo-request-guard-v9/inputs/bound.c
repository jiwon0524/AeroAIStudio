#define _GNU_SOURCE
#include "bound.h"
#include <fcntl.h>
#include <unistd.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include <link.h>
#include <dlfcn.h>
#include <sys/syscall.h>
#include <sys/mount.h>
#include <sys/statvfs.h>
#include <sys/sysmacros.h>
#include <linux/mount.h>
#include <linux/openat2.h>
#include <openssl/evp.h>
#ifndef F_SEAL_EXEC
#define F_SEAL_EXEC 0x20
#endif
int bound_verify(int fd,const char *sha,const struct bound *expected,struct bound *out) {
    struct stat a,b;int flags=fcntl(fd,F_GETFL),seals=fcntl(fd,F_GET_SEALS);
    int required=F_SEAL_WRITE|F_SEAL_GROW|F_SEAL_SHRINK|F_SEAL_SEAL|F_SEAL_EXEC;
    if(!sha||strlen(sha)!=64||!out||flags<0||(flags&O_ACCMODE)!=O_RDONLY||
       (flags&O_PATH)||seals<0||(seals&required)!=required||fstat(fd,&a)||!S_ISREG(a.st_mode)||a.st_size<0) return -1;
    struct bound v={(uint64_t)a.st_dev,(uint64_t)a.st_ino,(uint64_t)a.st_size,!!(a.st_mode&0111)};
    if(expected&&(v.dev!=expected->dev||v.ino!=expected->ino||v.size!=expected->size||v.executable!=expected->executable)) return -1;
    EVP_MD_CTX *ctx=EVP_MD_CTX_new();if(!ctx)return -1;
    unsigned char bytes[65536],digest[32];unsigned width=0;off_t off=0;int result=-1;
    if(EVP_DigestInit_ex(ctx,EVP_sha256(),NULL)!=1)goto done;
    for(;;) {ssize_t n=pread(fd,bytes,sizeof bytes,off);if(n<0)goto done;if(!n)break;
        if(EVP_DigestUpdate(ctx,bytes,(size_t)n)!=1)goto done;
        off+=n;}
    if(EVP_DigestFinal_ex(ctx,digest,&width)!=1||width!=32||fstat(fd,&b)||
       a.st_dev!=b.st_dev||a.st_ino!=b.st_ino||a.st_size!=b.st_size||a.st_mode!=b.st_mode||off!=a.st_size)goto done;
    char hex[65];for(unsigned i=0;i<32;i++)snprintf(hex+2*i,3,"%02x",digest[i]);
    if(strcmp(hex,sha))goto done;
    *out=v;result=0;
done:EVP_MD_CTX_free(ctx);return result;
}
static int beneath(int root,const char *path,int flags) {
    if(!path||path[0]!='/'||strstr(path,"/../")||strstr(path,"//"))return -1;
    struct open_how h={.flags=(uint64_t)(flags|O_CLOEXEC|O_NOFOLLOW),
        .resolve=RESOLVE_IN_ROOT|RESOLVE_NO_MAGICLINKS|RESOLVE_NO_SYMLINKS};
    return (int)syscall(SYS_openat2,root,path,&h,sizeof h);
}
int bound_canonical(int root,const char *path,int pin,const char *sha,struct bound *out) {
    struct bound saved,actual;if(bound_verify(pin,sha,NULL,&saved))return -1;
    int fd=beneath(root,path,O_RDONLY);if(fd<0)return -1;
    int rc=bound_verify(fd,sha,&saved,&actual);close(fd);
    if(!rc)*out=actual;
    return rc;
}
int bound_mount(int root,const char *path,int pin,const char *sha,int executable) {
    /* Trusted single owner, newly built private mount namespace, no target
     * released. Destination placeholders are created separately under root.
     * NO namespace creation, ambient path fallback or readonly-source claim. */
    struct bound saved,actual;
    if(bound_verify(pin,sha,NULL,&saved)||saved.executable!=executable)return -1;
    int destination=beneath(root,path,O_PATH);if(destination<0)return -1;
    struct stat st;if(fstat(destination,&st)||!S_ISREG(st.st_mode)){close(destination);return -1;}
    char src[64],dst[64];snprintf(src,sizeof src,"/proc/self/fd/%d",pin);snprintf(dst,sizeof dst,"/proc/self/fd/%d",destination);
    if(mount(src,dst,NULL,MS_BIND,NULL)){close(destination);return -1;}
    close(destination);
    int mounted=beneath(root,path,O_PATH);if(mounted<0)return -1;
    struct mount_attr attr={.attr_set=MOUNT_ATTR_RDONLY|MOUNT_ATTR_NOSUID|MOUNT_ATTR_NODEV|(executable?0:MOUNT_ATTR_NOEXEC),
        .attr_clr=executable?MOUNT_ATTR_NOEXEC:0};
    int rc=(int)syscall(SYS_mount_setattr,mounted,"",AT_EMPTY_PATH,&attr,sizeof attr);close(mounted);
    /* Failed mount stage invalidates whole new namespace; never release root.
     * Do not umount/delete ambient artifacts or attempt silent fallback. */
    if(rc||bound_canonical(root,path,pin,sha,&actual))return -1;
    int fd=beneath(root,path,O_RDONLY);if(fd<0)return -1;
    struct statvfs fs;
    if(fstatvfs(fd,&fs)||!(fs.f_flag&ST_RDONLY)||!(fs.f_flag&ST_NOSUID)||
       !(fs.f_flag&ST_NODEV)||!!(fs.f_flag&ST_NOEXEC)==!!executable){close(fd);return -1;}
    /* mountinfo RO+nosuid/nodev/noexec is independently checked by owner and
     * collector; same-FD proof alone cannot certify a mount's readonly flag. */
    close(fd);return 0;
}
struct anchor_query {const void *address;uint64_t dev,ino;int found;};
static int anchor_segment(struct dl_phdr_info *info,size_t width,void *opaque) {
    (void)width;struct anchor_query *q=opaque;
    if(!info->dlpi_name||!*info->dlpi_name)return 0;
    uintptr_t address=(uintptr_t)q->address;int in_segment=0;
    for(unsigned i=0;i<info->dlpi_phnum;i++)if(info->dlpi_phdr[i].p_type==PT_LOAD) {
        uintptr_t lo=info->dlpi_addr+info->dlpi_phdr[i].p_vaddr;
        uint64_t length=info->dlpi_phdr[i].p_memsz;
        if(address>=lo&&(uint64_t)(address-lo)<length)in_segment=1;
    }
    if(!in_segment)return 0;
    /* Filename alone is not authority: reopen via approved canonical broker,
     * compare final sealed FD identity. Independent collector also verifies
     * actual kernel map_files+anchor, not target-owned link_map structures. */
    int fd=open(info->dlpi_name,O_RDONLY|O_CLOEXEC|O_NOFOLLOW);if(fd<0)return 0;
    struct stat st;int seals=fcntl(fd,F_GET_SEALS);
    if(!fstat(fd,&st)&&seals>=0&&(seals&0x2f)==0x2f&&(uint64_t)st.st_dev==q->dev&&(uint64_t)st.st_ino==q->ino)q->found=1;
    close(fd);return q->found;
}
int bound_anchor(const void *address,int fd) {
    struct stat st;if(!address||fstat(fd,&st))return -1;
    struct anchor_query q={address,(uint64_t)st.st_dev,(uint64_t)st.st_ino,0};
    dl_iterate_phdr(anchor_segment,&q);return q.found?0:-1;
}
