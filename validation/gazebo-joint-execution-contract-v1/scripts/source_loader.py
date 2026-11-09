"""Authenticated source-only local imports; no native library or service load."""
import types,sys,os,hashlib
from contextlib import contextmanager
from pathlib import Path
from contract import validate,check_fd,need,R

@contextmanager
def runtime(manifest):
    validate(manifest)
    names=['common','attestor','protocol','native_gate','collector','stage']
    # Refuse ambient cached app modules rather than trusting their file names.
    for name in names:need(name not in sys.modules,'stale/cached local module '+name)
    before=dict(sys.modules);modules={};loaded={}
    try:
        for name in names:
            p=str(R/'scripts'/(name+'.py'));row=manifest['code'][p]
            fd=os.open(p,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
            try:
                check_fd(fd,row);data=os.pread(fd,os.fstat(fd).st_size,0)
                need(hashlib.sha256(data).hexdigest()==row['sha256'],'import source changed')
            finally:os.close(fd)
            obj=types.ModuleType(name);obj.__file__=p;obj.__sealed_sha256__=row['sha256']
            if name=='common':obj._SEALED_CODE=manifest['code']
            sys.modules[name]=obj;exec(compile(data,p,'exec'),obj.__dict__)
            modules[name]=obj;loaded[p]=row['sha256']
        loaded.update(modules['common'].LOADED)
        yield modules,loaded
    finally:
        for name,obj in list(sys.modules.items()):
            if getattr(obj,'__file__',None) in manifest['code'] and name!='contract':
                if name in before:sys.modules[name]=before[name]
                else:sys.modules.pop(name,None)
