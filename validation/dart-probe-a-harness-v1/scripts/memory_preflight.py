"""Post-exec VmHWM estimate for descriptor validation, not DART loading."""
import json,os
from pathlib import Path
from allowlist import load_manifest,validate

def main():
    m=load_manifest();fds=[]
    try:
        fds+=validate(m,'installed_core_future_only');fds+=validate(m,'harmless_fixture_only')
        status=Path('/proc/self/status').read_text();peak=int(next(x.split()[1] for x in status.splitlines() if x.startswith('VmHWM:')))*1024
        budget=peak+8388608
        print(json.dumps({'VmHWM_bytes':peak,'estimated_stage_plus8MiB_bytes':budget,'MemoryMax_bytes':67108864,'safe_to_attempt_harmless_fixture':budget<67108864,'DART_memory_usage':'NOT_MEASURED','estimate_not_runtime_peak_guarantee':True}))
        return 0 if budget<67108864 else 1
    finally:
        for fd in fds:os.close(fd)
if __name__=='__main__':raise SystemExit(main())
