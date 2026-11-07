"""Read-only ELF/public-header audit. No loading or calls into audited objects."""
from pathlib import Path
import hashlib,json,subprocess,re,sys,os
B=Path(__file__).resolve().parents[1];ROOT=B.parents[1]
sys.path.insert(0,str(ROOT/'validation/dart-probe-a-harness-v1/scripts'))
from identity import describe_fd

def identity(path):
 fd=os.open(path,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
 try:return {'path':str(path),**describe_fd(fd)}
 finally:os.close(fd)
def disassembly(path,start,end,name):
 raw=subprocess.check_output(['objdump','-d','-C',f'--start-address={start}',f'--stop-address={end}',str(path)],text=True)
 (B/f'work/{name}.disassembly.txt').write_text(raw)
 return raw
def main():
 physics=Path('/usr/lib/x86_64-linux-gnu/libgz-sim8-physics-system.so.8.15.0')
 plugin=Path('/usr/lib/x86_64-linux-gnu/gz-physics-7/engine-plugins/libgz-physics7-dartsim-plugin.so.7.8.0')
 frozen=json.loads((ROOT/'validation/gazebo-minimal-physics-v1/reports/elf_manifest.json').read_text())
 expected={r['real_path']:r['sha256'] for rows in frozen['profiles'].values() for r in rows}
 for p in [physics,plugin]:
  if hashlib.sha256(p.read_bytes()).hexdigest()!=expected[str(p)]:raise ValueError('installed ELF differs from pinned preparation '+str(p))
 update=disassembly(physics,0xb8490,0xb8700,'physics_update')
 create=disassembly(physics,0xb1100,0xb1210,'create_physics_entities')
 configure=disassembly(physics,0xa9870,0xabd80,'physics_configure')
 getter=disassembly(plugin,0x23c1d0,0x23c2d0,'active_detector_name_getter')
 calls=lambda s,needle:[x.strip() for x in s.splitlines() if 'call' in x and needle in x]
 headers=['/usr/include/gz/sim8/gz/sim/Server.hh','/usr/include/gz/sim8/gz/sim/System.hh','/usr/include/gz/sim8/gz/sim/Types.hh','/usr/include/gz/sim8/gz/sim/SystemPluginPtr.hh','/usr/include/gz/sim8/gz/sim/EntityComponentManager.hh','/usr/include/gz/sim8/gz/sim/components/Physics.hh','/usr/include/gz/sim8/gz/sim/components/PhysicsEnginePlugin.hh','/usr/include/gz/sim8/gz/sim/physics/Events.hh','/usr/include/gz/physics7/gz/physics/World.hh','/usr/include/gz/physics7/gz/physics/detail/World.hh','/usr/include/gz/physics7/gz/physics/GetEntities.hh','/usr/include/gz/physics7/gz/physics/RequestEngine.hh']
 paths=[physics,plugin,Path('/usr/lib/x86_64-linux-gnu/libgz-sim8.so.8.15.0'),B/'work/libpublic_api_audit.so']
 pkg=subprocess.check_output(['dpkg-query','-L','libgz-sim8-dev'],text=True).splitlines()
 source_members=[p for p in pkg if p.endswith(('.cc','.cpp')) or '/src/' in p]
 record={'scope':'STATIC_ONLY','baseline_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'ELF_identities':[identity(p) for p in paths],'headers':[{'path':p,'sha256':hashlib.sha256(Path(p).read_bytes()).hexdigest()} for p in headers],'installed_dev_package_source_members':source_members,'source_scope_limit':'No matching PhysicsPrivate source/header or public active-engine bridge found in inspected installed dev headers/package and /usr/src; not a universal proof about all possible external artifacts. Preserved DART baseline source is not matched Gazebo Physics source.','named_call_evidence':{'Physics_Update_CreatePhysicsEntities':calls(update,'<gz::sim::v8::systems::PhysicsPrivate::CreatePhysicsEntities('),'Physics_Update_UpdatePhysics':calls(update,'<gz::sim::v8::systems::PhysicsPrivate::UpdatePhysics('),'Physics_Update_Step':calls(update,'<gz::sim::v8::systems::PhysicsPrivate::Step('),'CreatePhysicsEntities_CreateWorldEntities':calls(create,'<gz::sim::v8::systems::PhysicsPrivate::CreateWorldEntities('),'active_name_getter_getConstraintSolver':calls(getter,'<dart::simulation::World::getConstraintSolver()'),'active_name_getter_getCollisionDetector':calls(getter,'<dart::constraint::ConstraintSolver::getCollisionDetector()')},'configure_direct_named_create_calls':calls(configure,'<gz::sim::v8::systems::PhysicsPrivate::CreatePhysicsEntities('),'configure_indirect_call_sites':sum('call' in x and '*' in x for x in configure.splitlines()),'unknowns':['Configure indirect/private helpers do not establish a complete call graph','No live engine/world/detector object or vtable/provider observation','No installed initialization hook verified at iteration0/sim_time0','No claims derived from unverified PhysicsPrivate member offsets'],'status':{'1_active_detector_provider':'UNRESOLVED_PUBLIC_BRIDGE_MISSING','2_iteration_zero_initialization':'UNRESOLVED_HOOK_NOT_ESTABLISHED','3_runtime_collection':'NOT_CONNECTED_PREREQUISITES_1_2_UNRESOLVED'},'stop_rule':'Do not dereference PhysicsPrivate or guess its layout; no private symbol call/interposition or standalone replacement engine','approval_plan_updated':False,'runtime_launcher_changed':False,'target_loading':False,'artifact_executed':False}
 (B/'reports/api_path_evidence.json').write_text(json.dumps(record,indent=2)+'\n')
 print(json.dumps({'artifact_sha256':record['ELF_identities'][-1]['sha256'],'matched_named_edges':sum(len(v) for v in record['named_call_evidence'].values()),'status':record['status']}))
if __name__=='__main__':main()
