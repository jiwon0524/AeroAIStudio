"""Candidate factories reuse sealed Python sessions; no launcher/service entry."""
from pathlib import Path
import importlib.util,sys,copy,json,os,hashlib
R=Path(__file__).resolve().parents[1]
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m
N=load('guard_v8_native_audit',R/'scripts/native_audit.py')
channel=load('guard_v8_catalog_channel',R/'scripts/catalog_channel.py')
mapping=load('guard_v8_mapping',R/'scripts/mapping.py')
placement=load('guard_v8_placement',R/'scripts/placement.py')
control=load('guard_v7_controller_reused',R.parent/'gazebo-request-guard-v7/scripts/controller.py')
def candidate_inputs(manifest,records,policy):
    m=copy.deepcopy(manifest);rows=copy.deepcopy(records)
    for row in rows:
        if not row['required']:continue
        incoming=next(r for r in policy['paths'] if r['path']==row['aliases'][0])
        row['original']=copy.deepcopy(incoming['original'])
        for path in row['aliases']:
            m['mounts'][path].update(incoming['original'],source=incoming['source'],real_path=incoming['source'])
            if path in m['elfs']:
                m['elfs'][path].update(m['mounts'][path])
                if path==m['roles']['native']:m['elfs'][path]['build_id']=policy['native_build_id']
    m['allowlist_text']=manifest['allowlist_text'].replace(policy['native_replacement']['parent_sha256']+' '+m['roles']['native'],policy['native_replacement']['sha256']+' '+m['roles']['native'])
    return m,rows

def project_runtime(manifest,catalog):
    N.need(catalog.complete and not catalog.closed,'live catalog missing')
    plan=catalog.plan;m=copy.deepcopy(manifest)
    for path,obj in plan['mounts'].items():
        m['mounts'][path].update(device=obj['device'],inode=obj['inode'])
        if path in m['elfs']:m['elfs'][path].update(device=obj['device'],inode=obj['inode'])
    m['native']['expected']=copy.deepcopy(plan['native_expected'])
    # Same sealed contract algorithms, new live identities. Original manifest,
    # validation and refusal launcher are never rewritten/resealed.
    m['mounts']={p:v for p,v in m['mounts'].items() if p in plan['mounts']}
    m['attestation']['allowed_mappings']={p:dict(m['elfs'][p],path=p) for p in m['attestation']['allowed_mappings'] if p in plan['mounts']}
    for role,key in [('dartsim','engine_provider'),('dart_ode',None)]:
        path=m['roles'][role];row=m['elfs'][path]
        fp={k:row[k] for k in ('real_path','sha256','build_id','device','inode')}
        if key:m['attestation'][key]=fp
        else:m['attestation']['detector_candidates']['ode']=fp
    return m

def session(modules,manifest,catalog,attestor,write):
    N.need(type(catalog) is channel.Catalog,'collector requires owned live catalog capability')
    runtime=project_runtime(manifest,catalog)
    class BoundAttestor(modules['attestor'].Attestor):
        def mappings(self):
            result=mapping.verify(self.pid,self.start,catalog.plan,catalog.pins,mapping.Proc(channel.S.validate_object,catalog.pins))
            self.last_mapping=result;return result
    a=BoundAttestor(runtime,attestor.pid,attestor.start,attestor.cgroup,attestor.go_stat,attestor.obs_stat)
    window=modules['protocol'].AckWindow(write,a.mappings,a.start,a.pid)
    native=modules['native_gate'].NativeSession(runtime['native']['expected'],runtime['native']['schema_closure'],modules['protocol'].AckSession(runtime['attestation'],a.ready,window))
    return native,window,a
