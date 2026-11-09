"""Compile one changed ODE wrapper TU and relink a candidate; never load it."""
from pathlib import Path
import hashlib,json,shlex,subprocess,difflib
R=Path(__file__).resolve().parents[1];B=R.parents[1]
H=B/'validation/gazebo-joint-header-fix-v1'
build=H/'work/config-01/build/dart'
N=B/'validation/gazebo-joint-native-resource-v1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
src=H/'work/config-01/src/dart/dart/collision/ode/OdeCollisionDetector.cpp'
old=src.read_text()
begin=old.index('  const auto initialized = dInitODE2(0);')
end=old.index('\n}',begin)
new=old[:begin]+'''  // Fail the native resource ledger before ready/GO, including NDEBUG builds.
  if (!dInitODE2(0))
    aero_resource::Fail("ODE initialization failed");
  if (!dAllocateODEDataForThread(dAllocateMaskAll))
  {
    dCloseODE();
    aero_resource::Fail("ODE per-thread initialization failed");
  }
  mWorldId = dWorldCreate();
  if (!mWorldId)
  {
    dCloseODE();
    aero_resource::Fail("ODE world initialization failed");
  }'''+old[end:]
new='#include "native_resource.hh"\n'+new
work=R/'work';(work/'prefix/lib').mkdir(parents=True,exist_ok=True)
copy=work/'OdeCollisionDetector.cpp';copy.write_text(new)
patch=''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/OdeCollisionDetector.cpp',tofile='b/OdeCollisionDetector.cpp',n=0))
(R/'reports/ode_init_guard.patch').write_text(patch)
row=next(x for x in json.loads((build/'compile_commands.json').read_text()) if x['file']==str(src))
argv=shlex.split(row['command']);obj=work/'OdeCollisionDetector.o'
argv[argv.index('-o')+1]=str(obj);argv[argv.index('-c')+1]=str(copy)
argv.extend(['-I'+str(N/'inputs'),'-MD','-MF',str(work/'OdeCollisionDetector.d')])
commands=[argv]
with (work/'compile.log').open('w') as log:subprocess.run(argv,cwd=build,stdout=log,stderr=subprocess.STDOUT,check=True)
raw=subprocess.check_output(['ninja','-t','commands','lib/libdart-collision-ode.so.6.13.2'],cwd=build,text=True).splitlines()[-1]
tokens=shlex.split(raw);assert tokens[:2]==[':','&&'] and tokens[-2:]==['&&',':']
link=tokens[2:-2];out=work/'prefix/lib/libdart-collision-ode.so.6.13.2'
link[link.index('-o')+1]=str(out)
original_object='dart/collision/ode/CMakeFiles/dart-collision-ode.dir/OdeCollisionDetector.cpp.o'
assert original_object in link;link[link.index(original_object)]=str(obj)
native=N/'work/prefix/lib/libaero-resource.so'
link.extend([str(native),'-Wl,-rpath,'+str(native.parent)])
commands.append(link)
with (work/'link.log').open('w') as log:subprocess.run(link,cwd=build,stdout=log,stderr=subprocess.STDOUT,check=True)
def symbols(p,mode):
    return sorted(line.split()[-1] for line in subprocess.check_output(['nm','-D',mode,str(p)],text=True).splitlines() if line.split())
previous=build/'lib/libdart-collision-ode.so.6.13.2'
assert symbols(previous,'--defined-only')==symbols(out,'--defined-only')
st=out.stat()
receipt=dict(status='COMPILED_LINKED_STATIC_ONLY_NOT_DEPLOYED',source_sha256=sha(src),candidate_source_sha256=sha(copy),
  elf=dict(path=str(out),sha256=sha(out),device=st.st_dev,inode=st.st_ino,
           readelf=subprocess.check_output(['readelf','-d','-n',str(out)],text=True)),
  reused_objects=[dict(path=str(build/t),sha256=sha(build/t)) for t in link if t.endswith('.o') and not Path(t).is_absolute()],
  native_observer=dict(path=str(native),sha256=sha(native)),commands=commands,
  export_names_unchanged=True,new_imports=sorted(set(symbols(out,'--undefined-only'))-set(symbols(previous,'--undefined-only'))),
  abi_scope='No headers, layout, virtual interfaces, solver or success-path numerical operations changed. New dependency on existing native failure ledger; consumer rebuild unnecessary for type ABI. Runtime exception/cleanup remains unverified.',
  manifest_status='Original sealed manifest intentionally unchanged: candidate not authorized by it. Candidate deployment/projection reseal remains pending while external closure is blocked.',
  stage_b='BLOCKED',runtime='UNVERIFIED')
(R/'reports/build_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print('One TU compiled; ODE candidate linked, exports unchanged; NOT DEPLOYED')
