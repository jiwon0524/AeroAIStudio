"""Refusal-only external preflight; authenticate contract source before import."""
import json,sys,hashlib,os,types
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def bootstrap():
    m=json.loads((R/'reports/manifest.json').read_text())
    raw=(json.dumps(m,sort_keys=True,separators=(',',':'))+'\n').encode()
    if hashlib.sha256(raw).hexdigest()!=(R/'inputs/manifest.sha256').read_text().strip():raise ValueError('manifest seal mismatch')
    p=str(R/'scripts/contract.py');row=m['code'][p]
    if row['source']!=p:raise ValueError('contract source path')
    fd=os.open(p,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
    try:
        a=os.fstat(fd);data=os.pread(fd,a.st_size,0);b=os.fstat(fd)
        if (a.st_dev,a.st_ino)!=(row['device'],row['inode']) or (a.st_size,a.st_mtime_ns,a.st_ctime_ns)!=(b.st_size,b.st_mtime_ns,b.st_ctime_ns) or hashlib.sha256(data).hexdigest()!=row['sha256']:raise ValueError('contract FD/source mismatch')
    finally:os.close(fd)
    module=types.ModuleType('contract');module.__file__=p
    exec(compile(data,p,'exec'),module.__dict__)
    module.validate(m);return module,m

def preflight():
    try:
        contract,manifest=bootstrap();contract.runtime_ready(manifest)
    except (ValueError,OSError,KeyError) as error:
        return {'status':'BLOCKED','exit_code':78,'reason':str(error),
                'manager_queried':False,'service_started':False,'marker_created':False,
                'go_sent':False,'stage_b':'BLOCKED','risk_acceptance':'UNDECIDED','actual_runtime':'UNVERIFIED'}
    raise AssertionError('refusal-only launcher cannot authorize execution')
if __name__=='__main__':
    print(json.dumps(preflight(),indent=2));raise SystemExit(78)
