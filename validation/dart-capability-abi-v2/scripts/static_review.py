from common import *
import re,difflib
paths=['dart/simulation/World.cpp','dart/constraint/ContactConstraint.cpp','dart/constraint/JointConstraint.cpp','dart/constraint/BoxedLcpConstraintSolver.cpp','dart/external/odelcpsolver/lcp.cpp']
pattern=re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//[^\n]*|/\*.*?\*/|[A-Za-z_]\w*|\d+(?:\.\d*)?|[^\s]',re.S)
def tokens(s):return [x for x in pattern.findall(s) if not x.startswith(('//','/*'))]
results={}
for rel in paths:
 a=R/'work/baseline-source'/rel;b=R/'work/trace-source'/rel
 orig=tokens(a.read_text());new=tokens(b.read_text());it=iter(new);preserved=all(any(x==y for y in it) for x in orig)
 results[rel]={'original_tokens_preserved_in_order':preserved,'baseline_sha256':sha(a),'trace_sha256':sha(b),'matches_previous_trace_source':sha(b)==sha(OLD/'work/trace-source'/rel),'diff':''.join(difflib.unified_diff(a.read_text().splitlines(True),b.read_text().splitlines(True),fromfile='baseline/'+rel,tofile='trace/'+rel))}
 assert preserved
headers={str(p.relative_to(R/'work/baseline-source')):sha(p)==sha(R/'work/trace-source'/p.relative_to(R/'work/baseline-source')) for p in (R/'work/baseline-source/dart').rglob('*.hpp')}
rec=R/'work/trace-source/dart/external/odelcpsolver/internal_trace.cpp'
save('neutrality_static_review.json',{'files':results,'class_declaration_headers_checked':len(headers),'changed_headers':[k for k,v in headers.items() if not v],'recorder_unchanged_from_previous':sha(rec)==sha(OLD/'work/trace-source/dart/external/odelcpsolver/internal_trace.cpp'),'limits':['Lexical preservation is not semantic equivalence or runtime neutrality','New branch/copy/TLS/call_once/atomic/cache effects remain unmeasured','BeginAssembly/getType and constraint_type are Active-gated; OFF still executes diagnostic entry points and evaluates SetRow getDimension metadata arguments. ON adds getType virtual queries. No timing neutrality claim.','5-frame arena: default4096*296+262144*8=3309568 bytes on x86_64 layout; max65536*296+1048576*8=27787264 bytes, excluding vector overhead and post-window JSON allocation','World::step hooks compiled but never executed. Position Integration original tokens preserved only, no dynamic validation']})
print('Static review:5 original token sequences preserved; declaration header changes',sum(not v for v in headers.values()))
