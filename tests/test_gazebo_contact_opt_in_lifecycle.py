"""AN-T1: static ELF evidence and isolated ECM/Resolve tests; no simulator."""
import copy,json,shlex,subprocess
from pathlib import Path
import pytest
from tools import diagnose_v07_gazebo_contact_surface_event as t
from test_gazebo_contact_surface_event import physical,event_rows


def test_installed_physics_consumes_requests_including_paused_updates():
    proof=t.installed_opt_in_lifecycle()
    asm=subprocess.run(['objdump','-d','-C',proof['physics_binary']],capture_output=True,text=True,check=True).stdout
    assert 'b69e4:' in asm and 'RemoveComponent(unsigned long, unsigned long const&)@plt' in asm
    assert 'b69c2:' in asm and 'EnableContactSurfaceCustomizationTag' in asm
    assert 'b8525:' in asm and 'b8685:' in asm and 'PhysicsPrivate::UpdateSim(' in asm
    assert proof['consumed_in_paused_updates'] and proof['routing_retained_separately']
    assert not proof['physical_neutrality_established']


def test_actual_resolve_and_installed_ecm_without_server_or_physics(tmp_path):
    # Expose diagnostics for an isolated unit harness; compile the actual Resolve
    # implementation rather than a second implementation of its accounting.
    source=t.SOURCE.read_text().replace('public gz::sim::ISystemUpdate, public gz::sim::ISystemPostUpdate {',
      'public gz::sim::ISystemUpdate, public gz::sim::ISystemPostUpdate { public:')
    code=source+r'''
#include <cassert>
#include <gz/sim/components/Name.hh>
int main(){
 using namespace gz::sim;using Flag=components::EnableContactSurfaceCustomization;
 EntityComponentManager ecm;
 auto model=ecm.CreateEntity();ecm.CreateComponent(model,components::Name("simple_agent"));
 const char *links[]={"left_wheel","right_wheel","front_caster","rear_caster"};
 const char *cols[]={"left_collision","right_collision","front_collision","rear_collision"};
 Entity collisions[4];
 for(int i=0;i<4;++i){auto link=ecm.CreateEntity();ecm.CreateComponent(link,components::Name(links[i]));ecm.CreateComponent(link,components::ParentEntity(model));
  auto c=ecm.CreateEntity();collisions[i]=c;ecm.CreateComponent(c,components::Name(cols[i]));ecm.CreateComponent(c,components::ParentEntity(link));}
 aero_diagnostic::ContactSurfaceEventObserver observer;observer.enabled=true;
 observer.Resolve(ecm);assert(observer.optInsCreated==4&&observer.creationSuccesses==4&&observer.afterMask==15&&observer.firstActivation==0);
 observer.iteration=10;observer.Resolve(ecm);
 assert(observer.optInsCreated==4&&observer.beforeMask==15&&observer.attemptMask==0&&observer.firstActivation==0);
 // Change-state bookkeeping is not component consumption.
 ecm.SetChanged(collisions[0],Flag::typeId,ComponentState::OneTimeChange);ecm.SetAllComponentsUnchanged();assert(ecm.Component<Flag>(collisions[0]));
 auto p=ecm.Component<Flag>(collisions[0]);auto duplicate=ecm.CreateComponent(collisions[0],Flag(false));
 assert(duplicate==p&&!p->Data());assert(ecm.CreateComponent(collisions[0],Flag(true))==p&&p->Data());
 // Reproduce Physics' publicly observed RemoveComponent path, without Physics.
 for(auto c:collisions){assert(ecm.RemoveComponent<Flag>(c));assert(!ecm.Component<Flag>(c));}
 observer.iteration=11;observer.Resolve(ecm);
 assert(observer.optInsCreated==8&&observer.creationSuccesses==8&&observer.beforeMask==0&&observer.attemptMask==15&&observer.afterMask==15&&observer.firstActivation==0);
 assert(!ecm.CreateComponent<Flag>(9999999,Flag(true)));
 return 0;
}
'''
    src=tmp_path/'resolve_unit.cc';src.write_text(code);binary=tmp_path/'resolve_unit'
    flags=shlex.split(subprocess.run(['pkg-config','--cflags','--libs','gz-sim8','gz-plugin2','gz-transport13','gz-common5-events'],capture_output=True,text=True,check=True).stdout)
    built=subprocess.run(['c++','-std=c++17','-I'+str(t.SOURCE.parent),str(src),'-o',str(binary),*flags],capture_output=True,text=True)
    assert built.returncode==0,built.stderr
    ran=subprocess.run([str(binary)],capture_output=True,text=True)
    assert ran.returncode==0,ran.stderr


def test_host1_repeated_attempts_are_not_physical_nonneutrality():
    report=json.loads((t.HOST1_ROOT/'contact_event_stage_a_host1_forensics.json').read_text())
    for case in report['ten_case_matrix']:
        if not case['listener']:continue
        calls=report['opt_in_lifecycle'][case['case_id']]['calls']
        assert all(x['opt_in_created_count']==4*x['cycle'] and x['opt_in_present_count']==4 for x in calls)
        assert case['surface_mutation_count']==case['listener_command_count']==case['competing_listeners_at_configure']==0
    assert not report['endpoint_comparison']['physical_listener_endpoint_difference_observed']
    assert not report['endpoint_comparison']['neutrality_established']


@pytest.mark.parametrize('defect',['missing_schema','missing_opt_in','bad_return','bad_counter','wrong_first','persisted','missing_consumption','wrong_entity','event_without_opt_in'])
def test_malformed_or_missing_lifecycle_does_not_validate(defect,tmp_path):
    spec=t.schedule('A')[1];record,a=physical(spec);rows=event_rows(spec,record,a)
    pre=next(x for x in rows if x['stage']=='PreUpdate' and x['cycle']==a['S0'][0]['postupdate_count'])
    if defect=='missing_schema':pre.pop('opt_in_lifecycle_schema')
    elif defect=='missing_opt_in':pre['opt_in_after_mask']=0
    elif defect=='bad_return':pre['opt_in_returned_true_mask']=0
    elif defect=='bad_counter':pre['opt_in_creation_attempt_count']+=4
    elif defect=='wrong_first':pre['opt_in_first_activation_iteration']=pre['iteration']
    elif defect=='persisted':pre['opt_in_before_mask']=15
    elif defect=='missing_consumption':next(x for x in rows if x['stage']=='Update/after_Physics_Update')['opt_in_present_after_physics_mask']=15
    elif defect=='wrong_entity':pre['opt_in_entities']={**pre['opt_in_entities'],'left_wheel':99999}
    else:next(x for x in rows if x['kind']=='contact_event')['collision1']=99999
    proof=t.validate_opt_in_lifecycle(rows,a,spec)
    assert not proof['passed'] and proof['errors'] and proof['full_fresh_Stage_A_required']


def test_consumed_requests_accept_repetition_and_keep_first_activation():
    spec=t.schedule('A')[1];rec,a=physical(spec);rows=event_rows(spec,rec,a)
    proof=t.validate_opt_in_lifecycle(rows,a,spec)
    assert proof['passed'] and proof['first_activation_iteration']==0 and proof['creation_attempt_count']>4
    assert proof['creation_attempt_count']==proof['creation_returned_true_count']
    assert not proof['physical_neutrality_inferred']


def test_fresh_preflight_and_completed_host_evidence_are_distinct(tmp_path):
    assert t.preflight_evidence_state(tmp_path)=='FRESH_PREFLIGHT_ROOT'
    (tmp_path/'events.ndjson').write_text('{}\n')
    with pytest.raises(ValueError,match='unexpected runtime'):t.preflight_evidence_state(tmp_path)
    (tmp_path/'contact_event_qualification.json').write_text(json.dumps({'results':[{'capture_valid':False}]}))
    assert t.preflight_evidence_state(tmp_path)=='COMPLETED_PRESERVED_HOST_EVIDENCE'
    assert (tmp_path/'events.ndjson').exists()


def test_full_fresh_host2_required_and_stage_b_still_blocked():
    assert t.A_ROOT.name.endswith('host2') and len(t.schedule('A'))==10
    assert not t.protocol('A')['automatic_reruns'] and t.protocol('A')['fresh_process_per_case']
    assert not (t.A_ROOT/'contact_event_qualification.json').exists()
    with pytest.raises(t.g.InvalidCapture,match='Stage B blocked'):t.stage_b_gate()


def test_t1_preflight_only_prepares_full_stage_a_host2():
    import inspect
    source=inspect.getsource(t.preflight)
    assert "for stage,root in [('A',A_ROOT)]" in source
    assert 'B_ROOT.mkdir' not in source and "write(B_ROOT/" not in source
    assert 'full_Stage_A_Host2_required' in source and 'Stage_B_prepared_by_T1' in source
    assert t.A_ROOT!=t.HOST1_ROOT and t.A_ROOT.name.endswith('host2')


def test_t1_guard_covers_host1_and_preserved_stage_b():
    import inspect
    source=inspect.getsource(t.guard_manifest)
    assert 'for root in (HOST1_ROOT,B_ROOT)' in source
    for gate in ('HOST1_PRESERVED','FIRST_ACTIVATION_SEPARATE_FROM_LATEST_ATTEMPT','NO_HOST1_RESULT_REUSE','STAGE_B_NOT_PREPARED_BY_T1'):
        assert gate in t.GATES


def test_post_physics_false_boolean_is_not_an_integer_mask():
    spec=t.schedule('A')[1];rec,a=physical(spec);rows=event_rows(spec,rec,a)
    next(x for x in rows if x['stage']=='Update/after_Physics_Update')['opt_in_present_after_physics_mask']=False
    proof=t.validate_opt_in_lifecycle(rows,a,spec)
    assert not proof['passed'] and 'PHYSICS_REQUEST_CONSUMPTION_UNOBSERVED' in proof['errors']


def test_frozen_host1_schedule_not_redesigned():
    original=json.loads((t.HOST1_ROOT/'protocol.json').read_text())
    assert t.schedule('A')==original['schedule']
    assert t.protocol('A')['neutrality_rule']==original['neutrality_rule']
    assert t.protocol('A')['depth_mapping']==original['depth_mapping']


def test_host1_legacy_schema_not_retroactively_promoted():
    spec=t.schedule('A')[1];rec,a=physical(spec);rows=event_rows(spec,rec,a)
    for row in rows:row.pop('opt_in_lifecycle_schema',None)
    proof=t.validate_opt_in_lifecycle(rows,a,spec)
    assert not proof['passed'] and proof['errors']==['LIFECYCLE_SCHEMA_2_REQUIRED_FULL_HOST2']
    assert not proof.get('physical_neutrality_inferred',False)
