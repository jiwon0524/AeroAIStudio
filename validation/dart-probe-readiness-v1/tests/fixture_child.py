"""Self-contained harmless child; no third-party imports or dynamic library loading."""
import json,os,resource,signal,sys,time
from pathlib import Path
LIMITS={'RLIMIT_CPU':(1,1),'RLIMIT_AS':(128*1024*1024,)*2,'RLIMIT_FSIZE':(65536,)*2,'RLIMIT_NOFILE':(32,32),'RLIMIT_NPROC':(16,16),'RLIMIT_CORE':(0,0)}
for key,value in LIMITS.items(): resource.setrlimit(getattr(resource,key),value)
case=sys.argv[1]
print('fixture-start',flush=True)
print('fixture-stderr',file=sys.stderr,flush=True)
Path('temporary.txt').write_text('owned fixture output')
if case=='normal': print(json.dumps({'pid':os.getpid(),'limits':{k:resource.getrlimit(getattr(resource,k)) for k in LIMITS},'maps_clean':not any(x in Path('/proc/self/maps').read_text().lower() for x in ('libdart','libgz-','libgazebo')),'environment_keys':sorted(os.environ)}))
elif case=='exit': sys.exit(7)
elif case=='signal': os.kill(os.getpid(),signal.SIGTERM)
elif case=='timeout': time.sleep(30)
elif case=='cpu':
    while True: pass
elif case=='memory':
    try: bytearray(256*1024*1024)
    except MemoryError: print('memory-limit-observed'); sys.exit(23)
elif case=='file':
    try:
        with open('bounded.bin','wb') as f: f.write(b'x'*131072)
    except OSError: print('file-limit-observed'); sys.exit(24)
else: sys.exit(64)
