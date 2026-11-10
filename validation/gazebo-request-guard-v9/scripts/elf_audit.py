"""Static ELF/loadability facts only. Never exec/dlopen any candidate/input."""
from pathlib import Path
import json,subprocess,hashlib,struct,re
R=Path(__file__).resolve().parents[1]
policy=json.loads((R/'reports/policy.json').read_text());m=json.loads((R.parent/'gazebo-joint-execution-contract-v1/reports/manifest.json').read_text())
def needed(p):
    text=subprocess.check_output(['readelf','-d',str(p)],text=True)
    return [line.split('[')[1].split(']')[0] for line in text.splitlines() if '(NEEDED)' in line],text
old=Path(m['mounts'][m['roles']['native']]['source']);new=Path(policy['native_replacement']['source'])
def exports(p):
    value=subprocess.check_output(['nm','-D','--defined-only',str(p)],text=True)
    return {line.split()[-1] for line in value.splitlines() if len(line.split())>=3 and line.split()[-1].startswith('_ZN13aero_resource')}
missing=sorted(exports(old)-exports(new));newdeps,newtext=needed(new);olddeps,_=needed(old)
assert not missing and newdeps==olddeps
seen=set();facts=[]
for row in policy['paths']:
    if row['path'] not in m['elfs'] or row['source'] in seen:continue
    seen.add(row['source']);p=Path(row['source'])
    with p.open('rb') as f:
        h=f.read(64);assert h[:6]==b'\x7fELF\x02\x01'
        off=struct.unpack_from('<Q',h,32)[0];width,count=struct.unpack_from('<HH',h,54);assert width==56 and count<=256
        loads=[]
        for i in range(count):
            f.seek(off+i*width);v=f.read(width)
            if struct.unpack_from('<I',v)[0]!=1:continue
            flags=struct.unpack_from('<I',v,4)[0];filesz,memsz=struct.unpack_from('<QQ',v,32)
            loads.append(dict(flags=flags,filesz=filesz,memsz=memsz))
    deps,text=needed(p)
    facts.append(dict(source=str(p),bytes=p.stat().st_size,segments=loads,wx=any(v['flags']&3==3 for v in loads),textrel='(TEXTREL)' in text,needed=deps))
result=dict(status='STATIC_ONLY',native_public_exports_missing=missing,native_needed_unchanged=newdeps==olddeps,native_needed=newdeps,
    objects=facts,native_execution=False,whole_ABI_certificate=False)
(R/'reports/elf_audit.json').write_text(json.dumps(result,indent=2)+'\n')
print(len(facts),'unique ELF metadata inspected; native public exports and dependencies match; no loading')
