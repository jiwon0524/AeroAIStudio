#ifndef GUARD_OWNER_BRIDGE_H
#define GUARD_OWNER_BRIDGE_H
/* Single dedicated owner process. All source descriptions are snapshotted
 * above slots0..4 before redirecting. Only newly owned copies are cleaned on
 * failure; original high source descriptors are consumed on success. */
struct owner_bridge_ops {
    int (*copy)(int);
    int (*open_null)(void);
    int (*close_once)(int);
    int (*source_check)(int,int,int,int);
    int (*redirect)(int,int);
    int (*final_check)(void);
};
static int owner_fd_bridge(const struct owner_bridge_ops *ops,int go,int observation,int diagnostic) {
    int in=-1;
    int out=-1;
    int err=-1;
    int null_fd=-1;
    int null_copy=-1;
    int released=-1;
    int status=78;
    if(go<0||observation<0||diagnostic<0) goto cleanup;
    in=ops->copy(go);
    out=ops->copy(observation);
    err=ops->copy(diagnostic);
    if(in<0||out<0||err<0) goto cleanup;
    null_fd=ops->open_null();
    if(null_fd<0) goto cleanup;
    null_copy=ops->copy(null_fd);
    released=null_fd;
    null_fd=-1;
    if(ops->close_once(released)) goto cleanup;
    if(null_copy<0) goto cleanup;
    if(ops->source_check(in,out,err,null_copy)) goto cleanup;
    if(ops->redirect(null_copy,0)!=0) goto cleanup;
    if(ops->redirect(err,1)!=1) goto cleanup;
    if(ops->redirect(err,2)!=2) goto cleanup;
    if(ops->redirect(in,3)!=3) goto cleanup;
    if(ops->redirect(out,4)!=4) goto cleanup;
    if(ops->final_check()) goto cleanup;
    status=0;
    if(go>4&&ops->close_once(go)) status=78;
    if(observation>4&&observation!=go&&ops->close_once(observation)) status=78;
    if(diagnostic>4&&diagnostic!=go&&diagnostic!=observation&&ops->close_once(diagnostic)) status=78;
cleanup:
    if(null_fd>=0&&ops->close_once(null_fd)) status=78;
    if(null_copy>=0&&ops->close_once(null_copy)) status=78;
    if(in>=0&&ops->close_once(in)) status=78;
    if(out>=0&&ops->close_once(out)) status=78;
    if(err>=0&&ops->close_once(err)) status=78;
    return status;
}
#endif
