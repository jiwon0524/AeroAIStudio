from common import *
import difflib,shutil
paths=['dart/simulation/World.cpp','dart/constraint/ContactConstraint.cpp','dart/constraint/JointConstraint.cpp','dart/constraint/BoxedLcpConstraintSolver.cpp','dart/external/odelcpsolver/lcp.cpp','dart/external/odelcpsolver/internal_trace.h','dart/external/odelcpsolver/internal_trace.cpp']
patch=R/'instrumentation/dart_internal_trace_v1.patch'
# Exact same tested source payload, zero context removes literal single-space diff context lines.
parts=[]
for name in paths:
 a=R/'work/baseline-source'/name;b=R/'work/trace-source'/name
 parts+=difflib.unified_diff(a.read_text().splitlines(True) if a.exists() else [],b.read_text().splitlines(True),fromfile='a/'+name if a.exists() else '/dev/null',tofile='b/'+name,n=0)
patch.write_text(''.join(parts))
out=R/'work/patch-roundtrip';out.mkdir()
for name in paths:
 a=R/'work/baseline-source'/name
 if a.exists():
  (out/name).parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(a,out/name)
q=run(['patch','--fuzz=0','-p1','-d',out,'-i',patch]);assert q['rc']==0,q
hashes={name:{'result_sha256':sha(out/name),'tested_trace_sha256':sha(R/'work/trace-source'/name)} for name in paths}
assert all(v['result_sha256']==v['tested_trace_sha256'] for v in hashes.values())
save('patch_roundtrip.json',{'status':'PASS','source_changes':'No change to tested instrumentation source; serialization only','patch_sha256':sha(patch),'source_file_count':len(paths),'files':hashes,'patch_command':q['command'],'stdout':q['stdout']})
print('Patch roundtrip exact match7 source files; no solver/instrumentation change')
