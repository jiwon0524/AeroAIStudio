from analyze import *
import difflib
loaded=json.loads((R/'reports/loader_results.json').read_text());inv=json.loads((R/'reports/provider_inventory.json').read_text())
exports={a:{n:v for e in es for n,v in symbols(e['path']).items() if v['section']!='UND'} for a,es in inv.items()}
aux=[]
for p in sorted({p for o in loaded for p in o['installed_auxiliary_modules'].values()}):
 refs={n:v for n,v in symbols(p).items() if v['section']=='UND' and '4dart' in n}
 aux.append(dict(**elf(p),dart_references=refs,missing={a:[n for n in refs if n in exports['A'] and n not in exports[a]] for a in ['B','C']},limits='Installed Bullet is an explicitly retained auxiliary; binary type ABI UNKNOWN'))
save('auxiliary_consumers.json',aux)
objects=[]
for n in exports['A']:
 if n.startswith(('_ZTV','_ZTI','_ZTS')) and '4dart' in n:
  objects.append(dict(name=n,demangled=run(['c++filt',n])['stdout'].strip(),metadata={a:{k:exports[a].get(n,{}).get(k) for k in ['size','type','binding','visibility','version']} for a in exports}))
layout={a:run([V/f'work/abi-{tag}']) for a,tag in [('A','installed'),('B','baseline'),('C','trace')]}
refs=json.loads((R/'reports/consumer_symbols.json').read_text())
save('abi_comparison.json',dict(layout=layout,vtable_rtti=objects,consumer_object_refs=[r['mangled'] for r in refs if r['type']=='OBJECT'],constructor_destructor_refs=[r['mangled'] for r in refs if re.search(r'[CD][012]E',r['mangled'])],cxx11_refs=sum('__cxx11' in r['mangled'] for r in refs),installed_type_dwarf='UNAVAILABLE; prior zero type corpus',call_abi='Mangled parameter signatures/ELF metadata only; return ABI, inline offsets, virtual slot semantics UNKNOWN',baseline_trace_dwarf='Prior V2 core no changes, NOT_RERUN',sources={n:dict(path=str(V/'reports'/n),sha256=sha(V/'reports'/n)) for n in ['dwarf_comparison.json','debug_coverage.json','build_profile.json','neutrality_static_review.json','metadata_call_observation.json','instrumentation_delta.json']}))
changes={}
for rel in ['dart/simulation/World.cpp','dart/constraint/BoxedLcpConstraintSolver.cpp','dart/constraint/ContactConstraint.cpp','dart/constraint/JointConstraint.cpp','dart/external/odelcpsolver/lcp.cpp']:
 a=(V/'work/baseline-source'/rel).read_text();b=(V/'work/trace-source'/rel).read_text();changes[rel]=[l for l in difflib.unified_diff(a.splitlines(),b.splitlines()) if l.startswith(('+','-'))]
save('instrumentation_review.json',dict(source_deltas=changes,OFF='Not identical execution: ctor call_once/env; step scope TLS/status; diagnostic entries; SetRow getDimension argument evaluation remain.',ON='Active getType virtual calls, copying/atomics/cache pressure. Configure arena/post-window serialization allocate. Overflow marks incomplete; no solver retry.',solver='Prior lexical preservation + rerun synthetic fixtures only. No runtime or formal semantic proof.',unknown=['timing/FP','all metadata side effects','thread scheduling/lock contention','actual effective mass/Jacobian neutrality','position integration','flush completeness'],runtime='NOT_RUNTIME_VERIFIED'))
print('aux',len(aux),'objects',len(objects),'layouts',[(a,o['rc']) for a,o in layout.items()])
