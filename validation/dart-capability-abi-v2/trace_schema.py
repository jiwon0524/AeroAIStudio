"""Offline schema/collection checks. Never upgrades runtime/capture qualification."""
import json,struct,math
from pathlib import Path

def values(record):
    bits=record['data_bits']
    if any(not isinstance(x,str) or len(x)!=16 or any(c not in '0123456789abcdef' for c in x) for x in bits):
        raise ValueError('invalid IEEE754 payload')
    return [struct.unpack('>d',bytes.fromhex(x))[0] for x in bits]

def inspect(path):
    d=json.loads(Path(path).read_text());issues=[]
    if d.get('schema_version')!=1 or d.get('protocol')!='DART_INTERNAL_TRACE_V1':raise ValueError('schema/protocol')
    if d.get('time_alignment')!='UNVERIFIED_DART_FRAME_ONLY':raise ValueError('unverified alignment must remain explicit')
    records=d['records'];groups={};steps=[]
    for r in records:
        if not isinstance(r.get('source'),str) or not r['source']:raise ValueError('source provenance missing')
        values(r)
        if r['kind']=='step_begin':steps.append(r['step'])
        if r['assembly']:groups.setdefault(r['assembly'],[]).append(r)
    expected=list(range(d['first_frame'],d['last_frame']+1))
    if steps!=expected:issues.append('missing/duplicate/out-of-order steps')
    if d['fault_bits']:issues.append('recorder faults')
    if not groups:issues.append('no solver assemblies recorded')
    has_v_free=any(r['kind']=='v_free' for r in records)
    identity_complete=True
    for gid,rs in groups.items():
        kinds={r['kind'] for r in rs}
        required={'assembly_begin','assembly_end','A0','b0','x0','lo0','hi0','findex0','primary_raw_return','fallback_called','final_x'}
        if not required<=kinds:issues.append('assembly missing fields: '+str(gid));continue
        n=int(values(next(r for r in rs if r['kind']=='assembly_begin'))[0])
        mat=[r for r in rs if r['kind']=='A0']
        if [r['row'] for r in mat]!=list(range(n)) or any(len(values(r))!=n for r in mat):issues.append('invalid A shape')
        for k in ['b0','x0','lo0','hi0','findex0','final_x']:
            matches=[r for r in rs if r['kind']==k]
            if len(matches)!=1 or len(values(matches[0]))!=n:issues.append('invalid '+k)
        called=bool(values(next(r for r in rs if r['kind']=='fallback_called'))[0])
        if called and 'fallback_raw_return' not in kinds:issues.append('fallback return missing')
        covered=set()
        for r in rs:
            if r['kind']=='contact_parameters':covered.update(range(r['row'],r['row']+int(values(r)[10])))
            if r['kind']=='joint_row':covered.add(r['row']+int(values(r)[1]))
        if covered!=set(range(n)):identity_complete=False
    return {'schema':'VALID','collection':'INCOMPLETE' if issues else 'COMPLETE','issues':issues,
            'row_identity_complete':identity_complete,'time_alignment':'UNVERIFIED',
            'runtime_verified':False,'qualification':'UNQUALIFIED',
            'qualification_blockers':['DART_GZ_TIME_UNVERIFIED']+(['COLLECTION_INCOMPLETE'] if issues else [])+([] if identity_complete else ['ROW_IDENTITIES_INCOMPLETE'])+([] if has_v_free else ['V_FREE_MISSING']),'Stage_B':'BLOCKED'}


def bounded_residual(path):
    """A0*x-b0 in original row order; separate from capture/clock decisions."""
    d=json.loads(Path(path).read_text());groups={}
    for r in d['records']:
        if r['assembly']:groups.setdefault(r['assembly'],[]).append(r)
    result=[]
    for gid,rs in groups.items():
        def first(k):return next((r for r in rs if r['kind']==k),None)
        required=['A0','b0','lo0','hi0','findex0','final_x','primary_effective_success','fallback_called']
        if any(first(k) is None for k in required):
            result.append({'assembly':gid,'status':'UNAVAILABLE_MISSING_INPUTS'});continue
        fallback=bool(values(first('fallback_called'))[0])
        if not values(first('primary_effective_success'))[0] and not fallback:
            result.append({'assembly':gid,'status':'UNAVAILABLE_FAILED_PRIMARY_MAPPING'});continue
        A=[values(r) for r in rs if r['kind']=='A0'];b=values(first('b0'));x=values(first('final_x'));lo=values(first('lo0'));hi=values(first('hi0'));fi=values(first('findex0'));n=len(x)
        if len(A)!=n or any(len(row)!=n for row in A) or not all(math.isfinite(v) for row in A for v in row) or not all(math.isfinite(v) for v in b+x):
            result.append({'assembly':gid,'status':'UNAVAILABLE_INVALID_ARRAYS'});continue
        if any(i>=0 for i in fi):
            perm=first('freeze_permutation');lh=first('freeze_hi_effective');ll=first('freeze_lo_effective')
            if fallback or None in [perm,lh,ll]:
                result.append({'assembly':gid,'status':'UNAVAILABLE_EFFECTIVE_FRICTION_BOUNDS'});continue
            p=[int(v) for v in values(perm)]
            if sorted(p)!=list(range(n)):
                result.append({'assembly':gid,'status':'UNAVAILABLE_PERMUTATION'});continue
            el,eh=values(ll),values(lh)
            for i,j in enumerate(p):lo[j],hi[j]=el[i],eh[i]
        w=[sum(a*v for a,v in zip(row,x))-bi for row,bi in zip(A,b)]
        bound=max([0.]+[max(0.,l-v,v-h) for v,l,h in zip(x,lo,hi)])
        kkt=[]
        for v,l,h,wi in zip(x,lo,hi,w):
            if l==h:kkt.append(0.)
            elif abs(v-l)<=1e-12:kkt.append(max(0.,-wi))
            elif abs(v-h)<=1e-12:kkt.append(max(0.,wi))
            else:kkt.append(abs(wi))
        result.append({'assembly':gid,'status':'COMPUTED_OFFLINE_NOT_CAPTURE_VERDICT','w_Ax_minus_b':w,'bound_violation_impulse':bound,'kkt_velocity_residual':max(kkt,default=0.)})
    return result
