from map_slots import *
# Validate unnamed local call correspondences with bounded code, rather than
# discarding all callee names to force a match.
def insns(text):
 out=[]
 for l in text.splitlines():
  m=re.match(r'^\s*([0-9a-f]+):\s+(.*)$',l)
  if m:out.append((int(m[1],16),m[2]))
 return out
if __name__=='__main__':
 d=json.loads((R/'reports/shapenode_slots.json').read_text());es={a:Elf(libs()[a]) for a in ['A','B']};fs={a:frames(e.path)[0] for a,e in es.items()};cache={};comparisons={}
 def get(a,addr):
  key=(a,addr)
  if key in cache:return cache[key]
  f=fs[a].get(addr);vs=es[a].aliases(addr);end=f['end'] if f else max((v['address']+v['size'] for v in vs if v['size']),default=None)
  if not end:cache[key]=None;return None
  text=run(['objdump','-d','--no-show-raw-insn','--start-address='+hex(addr),'--stop-address='+hex(end),es[a].path])['stdout'];p=R/f'work/refine-{a}-{addr:x}.asm';p.write_text(text);cache[key]=(end,insns(text),str(p));return cache[key]
 def compare(aa,bb,depth,seen):
  key=(aa,bb,depth)
  if key in comparisons:return comparisons[key]
  if (aa,bb) in seen:return dict(equal=True,reason='recursive edge to ancestor',edges=[])
  x=get('A',aa);y=get('B',bb)
  if not x or not y:return dict(equal=False,reason='missing code boundary',edges=[])
  if len(x[1])!=len(y[1]):return dict(equal=False,reason='instruction count difference',edges=[])
  edges=[];ok=True;why='normalized instructions and checked edges'
  for (ap,ai),(bp,bi) in zip(x[1],y[1]):
   def parse(s,start,end):
    s=s.split('#')[0].strip();s=re.sub(r'\s+',' ',s);s=re.sub(r'-?0x[0-9a-f]+\(%rip\)','<RIP>(%rip)',s)
    m=re.match(r'((?:call|j\w+)\s+)([0-9a-f]+)(?:\s+<([^>]+)>)?(.*)',s)
    if not m:return s,None,None
    t=int(m[2],16);label=m[3] or ''
    if start<=t<end:return m[1]+'SELF+'+hex(t-start)+m[4],None,None
    return m[1]+'EXTERNAL'+m[4],t,label if '@plt' in label else None
   pa,at,al=parse(ai,aa,x[0]);pb,bt,bl=parse(bi,bb,y[0])
   if pa!=pb:ok=False;why='operand/control-flow difference';break
   if at is not None:
    if al or bl:
     same=al==bl;edges.append(dict(A=hex(at),B=hex(bt),kind='PLT',equal=same,names=[al,bl]));ok &= same
    else:
     av={v['name'] for v in es['A'].aliases(at) if v['name'].startswith('_Z')};bv={v['name'] for v in es['B'].aliases(bt) if v['name'].startswith('_Z')}
     if av and bv:same=bool(av&bv);reason='direct symbol identity'
     elif depth>0:
      child=compare(at,bt,depth-1,seen|{(aa,bb)});same=child['equal'];reason='recursive bounded local-code comparison'
     else:same=False;reason='depth limit; unverified local edge'
     edges.append(dict(A=hex(at),B=hex(bt),kind='local',equal=same,reason=reason,B_names=sorted(bv)));ok &= same
  out=dict(equal=ok,reason=why,edges=edges,paths=[x[2],y[2]],limits='RIP data address values masked; equality supports identity inference, not full semantics or ABI proof');comparisons[key]=out;return out
 for row in d['slots']:
  a=row['arms']['A'];b=row['arms']['B'];c=row['arms']['C'];r=compare(a['address'],b['address'],2,set());row['checked_local_call_comparison']=r
  if not a['aliases'] and r['equal'] and b['identity'] and b['identity']==c['identity']:
   a['identity']=b['identity'];a['identity_status']='INFERRED';row['identity_status']='INFERRED'
  # Existing strictly matched inference remains as a weaker, disclosed evidence tier.
  row['inference_tier']='CHECKED_LOCAL_CALL_GRAPH' if r['equal'] else 'NORMALIZED_WITH_MASKED_CALLEES' if row['identity_status']=='INFERRED' else 'UNRESOLVED'
 d['counts']=dict(collections.Counter(r['identity_status'] for r in d['slots']));d['limits']+='; refinement distinguishes implementation/code difference from identity; all A names remain inferred, not recovered symbols.'
 save('shapenode_slots.json',d);save('local_call_correspondence.json',{'comparisons':[dict(A=hex(k[0]),B=hex(k[1]),depth=k[2],**v) for k,v in comparisons.items()]});print('refined',d['counts'],dict(collections.Counter(r['inference_tier'] for r in d['slots'])))
