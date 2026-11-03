#!/usr/bin/env python3
"""AN-T: public contact-event neutrality before event timing; no implicit Stage B."""
from __future__ import annotations
import argparse,copy,gc,inspect,json,math,os,shlex,shutil,struct,subprocess,time,traceback
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4
from tools import diagnose_v07_gazebo_physical_microstate_ordering as r
q=r.q;g=r.g;d=r.d;ROOT=r.ROOT
SOURCE=ROOT/'tools/gazebo_contact_surface_event_observer.cc'
HOST1_ROOT=ROOT/'validation/v071-host/gazebo-action24-contact-event-neutrality-phase3hant-host1'
A_ROOT=ROOT/'validation/v071-host/gazebo-action24-contact-event-neutrality-phase3hant-host2'
B_ROOT=ROOT/'validation/v071-host/gazebo-action24-contact-event-timing-phase3hant-host1'
CONTROL='NO_LISTENER_CONTROL';LISTENER='READ_ONLY_CONTACT_EVENT_LISTENER'
ZERO='EVENT_ZERO_CONTROL';ONE='EVENT_ONE_OBSERVATION'
CLASSES=('CONTACT_EVENT_LISTENER_NEUTRAL','CONTACT_EVENT_LISTENER_NONNEUTRAL','CONTACT_EVENT_LISTENER_NEUTRALITY_UNRESOLVED',
 'CONTACT_GEOMETRY_OBSERVABLE_EARLIER','CONTACT_GEOMETRY_NOT_OBSERVABLE_EARLIER','CONTACT_EVENT_TIMING_UNRESOLVED',
 'PRE_SOLVE_NONPHYSICAL_FORCE_ARGUMENT','BASELINE_UNSTABLE','CAPTURE_INVALID','SOLVER_INTERNAL_STATE_NOT_PUBLICLY_OBSERVABLE')
GATES=('PUBLIC_EVENT_API_IDENTIFIED','LISTENER_READ_ONLY','NO_SURFACE_MUTATION','NO_COMMAND_PATH','STAGE_A_SCHEDULE_FROZEN',
 'STAGE_B_SCHEDULE_FROZEN','STAGE_B_BLOCKED_UNTIL_NEUTRALITY','ZERO_ADVANCEMENT_EXACT','ONE_ADVANCEMENT_EXACT_1MS',
 'NO_ACTION24_UP','PRE_SOLVE_FORCE_NOT_PHYSICAL','BASELINE_CONTRACT_PRESERVED','PRODUCTION_SHA_UNCHANGED',
 'CURRENT_REPAIR_IS_AN_T1','HOST1_PRESERVED','OPT_IN_REQUEST_CONSUMPTION_ACCOUNTED',
 'FIRST_ACTIVATION_SEPARATE_FROM_LATEST_ATTEMPT','REISSUE_BEHAVIOR_UNCHANGED','LIFECYCLE_SCHEMA_2_REQUIRED',
 'FULL_FRESH_STAGE_A_HOST2_REQUIRED','NO_SELECTIVE_RERUNS','NO_HOST1_RESULT_REUSE','STAGE_B_NOT_PREPARED_BY_T1')
STATIC={'protocol.json','contact_event_preflight.json','api_semantics.json','builds','preflight_sdfs','stage_b_blocked.json','opt_in_lifecycle_repair.json'}
ORIGINAL_INSTRUMENT=r.instrument


def schedule(stage):
    arms=(CONTROL,LISTENER) if stage=='A' else (ZERO,ONE)
    return [{'ordinal':2*(rep-1)+i+1,'stage':stage,'case_id':f'{arm}_R{rep}','arm':arm,'replicate':f'R{rep}',
      'listener':arm!=CONTROL,'iterations':int(stage=='A' or arm==ONE),'sim_time_delta_ns':1000000*int(stage=='A' or arm==ONE)}
      for rep in range(1,6) for i,arm in enumerate(arms if rep%2 else tuple(reversed(arms)))]


def protocol(stage):
    return {'phase':'AN-T','experiment':'CONTACT_SURFACE_EVENT_NEUTRALITY_AND_TIMING_QUALIFICATION','stage':stage,
      'stage_A':'INSTRUMENTATION_NEUTRALITY_QUALIFICATION','stage_B':'EVENT_TIMING_OBSERVATION',
      'schedule_status':'PROSPECTIVE_CASE_ORDER_FROZEN','schedule':schedule(stage),'both_frozen_schedules':{s:schedule(s) for s in ('A','B')},
      'classifications':list(CLASSES),'automatic_reruns':False,'fresh_process_per_case':True,'causal_intervention':False,'Action24_UP':False,
      'boundary':r.protocol()['boundary'],'observation_requests':[0,0,0,1,0,0,0],
      'ZERO':{'advancement_requests':0,'iterations':0,'sim_time_delta_ns':0},'ONE':{'advancement_requests':1,'iterations':1,'sim_time_delta_ns':1000000},
      'baseline':r.protocol()['baseline'],
      'neutrality_rule':{'required_valid_cases':10,'pairs':5,'baseline_rule':'existing AN-R all-pairs baseline caps; no unstable pair hidden',
         'endpoint_rule':'Exact binary64 bitwise equality for every available physical S0/S1 observable and S1-S0 vector across matched CONTROL/LISTENER pairs and all 45 S1 pairs; exact categorical/topology agreement. No tolerance widening.',
         'missing_rule':'required geometry, velocities, q, joint velocities/wrench, support depth/Fn/topology missing => UNRESOLVED; optional missing values remain null and must agree',
         'markers':'RIGHT Z and four Fn deltas match frozen AN-R targets in every case and match CONTROL vs LISTENER bitwise',
         'listener_must_work':'all four supports observed in the one tick; event bracket, identity, single-listener and no-mutation checks pass',
         'coverage':'opt-in flag + connection + payload copying/logging overhead versus no flag/no connection; not merely function-body purity'},
      'event_force':'PRE_SOLVE_NONPHYSICAL_FORCE_ARGUMENT; never compared to physical Fn',
      'event_opt_in':'EnableContactSurfaceCustomization(true) routing requests on four support collisions; Physics consumes requests in UpdateSim including paused callbacks; first activation before S0; retain original reissue behavior; no surface/contact-property assignments',
      'event_identity':'collision entity pair + support/ground identity; per-step event sequence is not a persistent contact ID',
      'depth_mapping':{'position_tolerance_m':1e-10,'S0_correspondence_tolerance_m':1e-6,'normal_component_tolerance':1e-10,'depth_tolerance_m':1e-10,
         'ambiguity':'one-to-one pair/point/normal mapping required; ambiguous contacts remain unresolved; compare supplied depth only after validating convention against post-component readback'},
      'timing_rule':'after neutral Stage A only; known ONE RIGHT-Z/preload bundle must replicate; event must be bracketed between public before/after Update taps. Event depth must differ from cached S0 depth beyond 128 ulps + ZERO/readback noise, while same-event coherent geometry, component Fn and wrench remain equivalent to S0. Otherwise no earlier claim.',
      'ZERO_event_rule':'No events between first S0 and last S1 readback cycles; no advancing fallback',
      'stop_rules':['Stage A nonneutral/unresolved/invalid/baseline unstable blocks Stage B','Stage B requires separate explicit Host invocation; never auto-started','Stage B unresolved ends read-only timing investigation; no more invasive hooks'],
      'contamination':r.protocol()['contamination'],'RIGHT_Z_reference_m':r.RIGHT_Z_REFERENCE,'Fn_delta_reference_N':r.FN_REFERENCE,
      'solver_state':'SOLVER_INTERNAL_STATE_NOT_PUBLICLY_OBSERVABLE','runtime_facts':'HOST_REQUIRED; API semantics and static purity do not establish trajectory neutrality',
      'production_sha256':g.EXPECTED_SHA}


def write(path,value):
    path=Path(path).resolve()
    if not any(path.is_relative_to(root.resolve()) for root in (A_ROOT,B_ROOT)):raise ValueError('AN-T output only')
    d.ledger_io.atomic_json(path,value)


def api_semantics():
    paths=[Path('/usr/include/gz/sim8/gz/sim/physics/Events.hh'),Path('/usr/include/gz/physics7/gz/physics/ContactProperties.hh'),
      Path('/usr/include/gz/sim8/gz/sim/components/Collision.hh'),Path('/usr/include/gz/sim8/gz/sim/EventManager.hh'),Path('/usr/include/gz/common5/gz/common/Event.hh'),Path('/usr/include/gz/sim8/gz/sim/System.hh')]
    texts={str(p):p.read_text() for p in paths};event=texts[str(paths[0])];props=texts[str(paths[1])]
    if 'before the physics update has happened' not in event or 'be always zero because the forward step has not yet' not in props:raise ValueError('installed public semantics differ')
    symbols={}
    for path in ['/lib/x86_64-linux-gnu/libgz-sim8-physics-system.so.8','/lib/x86_64-linux-gnu/libgz-physics7-dartsim-plugin.so.7']:
        nm=subprocess.run(['nm','-D','--demangle',path],capture_output=True,text=True,check=True).stdout
        symbols[str(Path(path).resolve())]={'sha256':g.sha(path),'callback_feature_present':'SetContactPropertiesCallbackFeature' in nm,'event_type_present':'CollectContactSurfaceProperties' in nm,
          'short_registration_symbols':[x for x in nm.splitlines() if 'AddContactPropertiesCallback(' in x and len(x)<900]}
    return {'classification':'DOCUMENTED_API_SEMANTICS','event':'gz::sim::events::CollectContactSurfaceProperties',
      'signature':event[event.index('using CollectContactSurfaceProperties'):event.index('struct CollectContactSurfacePropertiesTag')+len('struct CollectContactSurfacePropertiesTag>')],
      'payload':['collision1 Entity const&','collision2 Entity const&','point const Vector3d&','optional force','optional normal','optional depth','numContactsOnCollision','mutable ContactSurfaceParams&'],
      'timing':'During Physics Update after collision checking and before forward update, per installed header; runtime bracketing must be observed independently',
      'force_semantics':'PRE_SOLVE_NONPHYSICAL_FORCE_ARGUMENT','force_rule':'documented pre-forward force is zero because not computed; null stays null; no physical force inference or comparison with Fn',
      'mutation_permission':'API intentionally permits modifying surface params; this implementation passes them into a const-only sink and never writes a field',
      'multiple_listeners':'Installed EventT invokes connected subscribers sequentially with shared arguments. Earlier subscribers may mutate params seen by later subscribers; no scientific reliance on listener order. Require prior count 0 and runtime listener count 1.',
      'opt_in_neutrality':'Public collision flag enables customization routing; neutrality NOT established by constness, compilation, or symbol presence',
      'headers':{str(p):{'sha256':g.sha(p),'text':texts[str(p)]} for p in paths},'installed_symbols':symbols,
      'event_library_sha256':{str(Path('/lib/x86_64-linux-gnu/libgz-common5-events.so.5').resolve()):g.sha('/lib/x86_64-linux-gnu/libgz-common5-events.so.5')},
      'runtime_observation':'NOT_EXECUTED_BY_CODEX; event availability, callback order and neutrality are HOST_REQUIRED'}


def static_contract():
    text=SOURCE.read_text();observe=text[text.index(' void Observe('):text.index(' public: ~ContactSurfaceEventObserver')]
    for token in ['const_cast','ResetPosition','JointPositionReset','SetForce(','SetVelocity(','SetPosition(','WorldControl','msgs::Twist','publish(','Request(','Emit<','params.','p.frictionCoeff=']:
        if token in observe:raise ValueError('mutating event sink token '+token)
    for token in ['SetForce(','SetVelocity(','SetPosition(','const_cast','JointPositionReset','ResetPosition','SetChanged(','node.','transport.','manager->Emit','ecm.Set','params.frictionCoeff =','params.depth =']:
        if token in text:raise ValueError('listener command/mutation path '+token)
    if 'const SurfaceParams &params' not in observe or text.count('const SurfaceParams &params')!=2:raise ValueError('const sink missing')
    if 'before!=SurfaceJSON(params)' not in text or 'events.Connect<ContactEvent>' not in text:raise ValueError('mutation proof/connection missing')
    if text.count('ecm.CreateComponent(')!=1 or 'EnableContactSurfaceCustomization(true)' not in text:raise ValueError('only documented opt-in is allowed')
    return {'listener_const_only':True,'surface_assignments':0,'listener_commands':0,'physics_advancement_calls':0,'documented_opt_in_only':True,
      'neutrality_not_proven_statically':True,'AN_R_source_reused_unchanged':True}


def build(directory):
    directory.mkdir(parents=True,exist_ok=True);library=(directory/'libaero_contact_surface_event.so').resolve()
    flags=subprocess.run(['pkg-config','--cflags','--libs','gz-sim8','gz-plugin2','gz-transport13','gz-common5-events'],capture_output=True,text=True,check=True)
    command=['c++','-std=c++17','-shared','-fPIC','-Wl,-z,defs',str(SOURCE),'-o',str(library),*shlex.split(flags.stdout)]
    compiled=subprocess.run(command,capture_output=True,text=True)
    if compiled.returncode:raise RuntimeError(compiled.stderr)
    deps=subprocess.run(['ldd','-r',str(library)],capture_output=True,text=True,check=True)
    registration=subprocess.run(['nm','-D','-C',str(library)],capture_output=True,text=True,check=True)
    if 'not found' in deps.stdout or 'undefined symbol' in deps.stdout:raise ValueError('observer dependencies unresolved')
    for name in ['PhysicalMicrostateObserver','MicrostateBeforePhysics','ContactSurfaceEventObserver','ContactEventBeforePhysics']:
        if name not in registration.stdout:raise ValueError('plugin registration absent '+name)
    return library,{'command':command,'dependencies':deps.stdout,'registration':registration.stdout,'registration_inspection':'STATIC_ELF_SYMBOLS_ONLY_NO_PLUGIN_EXECUTION','source_sha256':g.sha(SOURCE),'library_sha256':g.sha(library),'included_AN_R_source_sha256':g.sha(r.SOURCE)}


def instrument(path,info,library,case,directory):
    spec=next(x for s in ('A','B') for x in schedule(s) if x['case_id']==case)
    path,info=ORIGINAL_INSTRUMENT(path,info,library,case,directory)
    tree=ET.parse(path);world=tree.find('world');physics=world.find("plugin[@name='gz::sim::systems::Physics']")
    before=ET.Element('plugin',filename=str(library),name='aero_diagnostic::ContactEventBeforePhysics')
    world.insert(list(world).index(physics),before)
    listener=ET.Element('plugin',filename=str(library),name='aero_diagnostic::ContactSurfaceEventObserver')
    ET.SubElement(listener,'enabled').text=str(spec['listener']).lower();ET.SubElement(listener,'output').text=str(directory/'contact_surface_events.ndjson')
    after=world.find("plugin[@name='aero_diagnostic::PhysicalMicrostateObserver']");world.insert(list(world).index(after)+1,listener)
    tree.write(path,encoding='utf-8',xml_declaration=True)
    info['contact_event_observer']={'enabled':spec['listener'],'stage':spec['stage'],'output':str(directory/'contact_surface_events.ndjson'),'public_event':'CollectContactSurfaceProperties','surface_writes':False,'opt_in_is_part_of_neutrality_test':True}
    info['diagnostic_sdf_sha256']=g.sha(path)
    if json.loads(json.dumps(info,allow_nan=False))!=info:raise ValueError('metadata JSON roundtrip differs')
    validate_sdf(path,spec);return path,info


def validate_sdf(path,spec):
    tree=ET.parse(path);nodes=tree.findall('world/plugin');names=[x.get('name') for x in nodes]
    expected=['aero_diagnostic::MicrostateBeforePhysics','aero_diagnostic::ContactEventBeforePhysics','gz::sim::systems::Physics','aero_diagnostic::PhysicalMicrostateObserver','aero_diagnostic::ContactSurfaceEventObserver']
    indexes=[names.index(x) if names.count(x)==1 else -1 for x in expected]
    if indexes[0]<0 or indexes!=list(range(indexes[0],indexes[0]+5)):raise ValueError('public Update tap order not established')
    if any('system_priority' in c.tag for n in nodes for c in n):raise ValueError('nondefault priority unsupported')
    listener=tree.find("world/plugin[@name='aero_diagnostic::ContactSurfaceEventObserver']")
    if listener.findtext('enabled')!=str(spec['listener']).lower():raise ValueError('listener arm differs')
    model=tree.find("world/model[@name='simple_agent']")
    for link,col in zip(r.LINKS,r.COLLISIONS):
        collision=model.find(f"link[@name='{link}']/collision[@name='{col}']")
        if collision is None or collision.find('pose') is not None:raise ValueError('identity collision offset required')
    if tree.findtext('world/physics/max_step_size')!='0.001':raise ValueError('1ms timestep changed')
    return {'ordered_plugins':expected,'default_priorities':True,'listener_enabled':spec['listener']}


@contextmanager
def capture_hooks():
    old_schedule,old_instrument=r.schedule,r.instrument
    r.schedule=lambda:schedule('A')+schedule('B');r.instrument=instrument
    try:yield
    finally:r.schedule,r.instrument=old_schedule,old_instrument


def capture(*args):
    with capture_hooks():record=r.capture(*args)
    spec=next(x for stage in ('A','B') for x in schedule(stage) if x['case_id']==args[0])
    record['phase_qualification'].update(phase='AN-T',stage=spec['stage'],capture_library_phase='AN-R')
    write(Path(args[2])/'qualification_capture.json',record)
    return record


def installed_opt_in_lifecycle():
    """Fail closed to the exact installed build qualified in AN-T1.

    Evidence: Physics::Update 0xb8525/0xb8685; UpdateSim request view
    0xe0067, processing handler 0xcf070, RemoveComponent 0xb69e4.
    These are static ELF inspections, not a simulator/plugin execution.
    """
    physics=Path('/usr/lib/x86_64-linux-gnu/gz-sim-8/plugins/libgz-sim8-physics-system.so.8.15.0')
    expected='3d2815f980accc5809de76637c66c7bcde1742892d7cc8174f8ab7df3f929e23'
    if g.sha(physics)!=expected:raise ValueError('unqualified Physics binary; repeat public lifecycle qualification')
    ecm=Path('/usr/lib/x86_64-linux-gnu/libgz-sim8.so.8')
    if g.sha(ecm)!='6120bd5d25a28ced3238f91b8a432e364958cd07706afe00911743072bfe4651':raise ValueError('unqualified ECM binary')
    return {'classification':'CONSUMED_ROUTING_REQUEST_IN_PHYSICS_UPDATE_SIM',
      'physics_binary':str(physics),'physics_sha256':expected,'ecm_binary':str(ecm),'ecm_sha256':g.sha(ecm),
      'consumed_in_paused_updates':True,'routing_retained_separately':True,
      'reissue_behavior_changed':False,'physical_neutrality_established':False,
      'proof_reference':str(HOST1_ROOT/'contact_event_opt_in_lifecycle_forensics.json')}


def validate_opt_in_lifecycle(rows,physical,spec):
    """Schema 2 validates observed requests/consumption, never permanent flags.

    Host1 legacy counters cannot provide these prospective measurements. Do not
    retrofit a pass to archived captures. First activation is not latest reissue.
    """
    errors=[];previous_attempts=0;previous_returns=0;entities=None;first=None;expected_before=0
    callbacks={x['cycle']:x for x in rows if x['stage']=='Update/after_Physics_Update'}
    samples=[x for x in rows if x['stage'] in ('configure','PreUpdate')]
    pre_by_cycle={x['cycle']:x for x in samples if x['stage']=='PreUpdate'}
    for row in samples:
        if row.get('opt_in_lifecycle_schema')!=2:
            return {'passed':False,'errors':['LIFECYCLE_SCHEMA_2_REQUIRED_FULL_HOST2'],'full_fresh_Stage_A_required':True}
        ids=row.get('opt_in_entities',{})
        complete=set(ids)==set(r.SUPPORTS) and all(type(v) is int and v>0 for v in ids.values()) and len(set(ids.values()))==4
        before=row.get('opt_in_before_mask');attempt=row.get('opt_in_attempt_mask');returned=row.get('opt_in_returned_true_mask');after=row.get('opt_in_after_mask')
        masks=(before,attempt,returned,after)
        if any(type(v) is not int or not 0<=v<=15 for v in masks):
            errors.append('MALFORMED_LIFECYCLE_MASK');continue
        attempts=row.get('opt_in_creation_attempt_count');returns=row.get('opt_in_creation_returned_true_count')
        if type(attempts) is not int or type(returns) is not int:
            errors.append('MISSING_CREATION_ACCOUNTING');continue
        if (attempts-previous_attempts,returns-previous_returns)!=(attempt.bit_count(),returned.bit_count()):errors.append('CREATION_COUNTER_DELTA')
        previous_attempts,previous_returns=attempts,returns
        if spec['listener']:
            if complete:
                if entities is None:entities=ids
                if ids!=entities:errors.append('COLLISION_ENTITY_ID_CHANGED')
                if row.get('identities_resolved')!=5:errors.append('GROUND_IDENTITY_UNRESOLVED')
                if before!=expected_before:errors.append('REQUEST_PRESENCE_BEFORE_RESOLVE')
                if attempt!=(15^before) or returned!=attempt or after!=15 or row.get('opt_in_present_after_resolve')!=4:errors.append('OPT_IN_REQUEST_OR_RETURN_MISSING')
                activation=row.get('opt_in_first_activation_iteration')
                if first is None:first=row['iteration']
                if type(activation) is not int or activation!=first or activation>=physical['S0'][0]['iteration']:errors.append('FIRST_ACTIVATION_NOT_BEFORE_S0_OR_CHANGED')
                latest=row.get('opt_in_latest_attempt_iteration')
                if type(latest) is not int or latest>row['iteration'] or (attempt and latest!=row['iteration']):errors.append('LATEST_ATTEMPT_CLOCK')
            elif any(masks) or attempts or first is not None:errors.append('PARTIAL_OPT_IN_IDENTITIES')
        elif any(masks) or attempts or returns or row.get('opt_in_present_after_resolve') or row.get('opt_in_first_activation_iteration') is not None:errors.append('CONTROL_OPT_IN_CONTAMINATION')
        expected_before=after if row['stage']=='configure' else 0
        if row['stage']=='PreUpdate':
            post=callbacks.get(row['cycle'])
            if post is None or type(post.get('opt_in_present_after_physics_mask')) is not int or post['opt_in_present_after_physics_mask']!=0:errors.append('PHYSICS_REQUEST_CONSUMPTION_UNOBSERVED')
            # After the preceding UpdateSim consumption, all prior requests
            # must be absent; Configure can precede the very first PreUpdate.
            if callbacks.get(row['cycle']-1) is not None and before!=0:errors.append('REQUEST_PERSISTED_AFTER_CONSUMPTION')
    if spec['listener'] and entities is None:errors.append('NO_COMPLETE_OPT_IN')
    if entities:
        for packet in physical['S0']+physical['S1']:
            if any(packet['microstate']['supports'][k]['collision_entity_id']!=v for k,v in entities.items()):errors.append('OPT_IN_ENDPOINT_IDENTITY_MISMATCH')
        for event in (x for x in rows if x['kind']=='contact_event'):
            supports=[(event.get('collision'+i+'_identity'),event.get('collision'+i)) for i in ('1','2')]
            support=next(((k,e) for k,e in supports if k in entities),None)
            pre=pre_by_cycle.get(event['cycle'])
            if support is None or entities[support[0]]!=support[1] or pre is None or pre.get('opt_in_after_mask')!=15:errors.append('EVENT_WITHOUT_VALID_OPT_IN')
    return {'passed':not errors,'errors':sorted(set(errors)),'first_activation_iteration':first,
      'creation_attempt_count':previous_attempts,'creation_returned_true_count':previous_returns,
      'counter_semantics':'Returned nonnull true pointer; not allocation/new-storage insertion count',
      'full_fresh_Stage_A_required':True,'physical_neutrality_inferred':False}


def event_capture(directory,physical,spec):
    path=Path(directory)/'contact_surface_events.ndjson'
    if not path.exists():raise g.InvalidCapture('event observer raw file missing')
    def reject_constant(value):raise g.InvalidCapture('nonfinite event JSON '+value)
    rows=[json.loads(x,parse_constant=reject_constant) for x in path.read_text().splitlines()]
    if not rows or rows[0].get('stage')!='configure' or rows[-1].get('stage')!='shutdown':raise g.InvalidCapture('event observer startup/shutdown missing')
    seq=[x['callback_sequence'] for x in rows]
    if seq!=list(range(1,len(seq)+1)):raise g.InvalidCapture('event observer sequence gap')
    if rows[-1].get('io_failed') or rows[-1].get('surface_mutation_count') or rows[-1].get('outside_window_count'):raise g.InvalidCapture('event output failure or surface mutation detected')
    packets=physical['S0']+physical['S1'];lo=packets[0]['postupdate_count'];hi=packets[-1]['postupdate_count']
    window=[x for x in rows if x.get('kind')!='health' and lo<=x.get('cycle',-1)<=hi]
    for packet in packets:
        associated=[x for x in rows if x.get('cycle')==packet['postupdate_count'] and x.get('kind')=='stage']
        if [x['stage'] for x in associated]!=list(r.STAGES) or any(any(x[k]!=packet[k] for k in ('iteration','sim_time_ns','paused')) for x in associated):raise g.InvalidCapture('event/AN-R callback cycle alignment differs')
    events=[x for x in window if x['kind']=='contact_event'];all_events=[x for x in rows if x['kind']=='contact_event']
    if rows[-1].get('event_count')!=len(all_events):raise g.InvalidCapture('event shutdown count differs from raw stream')
    if [x['event_sequence'] for x in all_events]!=list(range(1,len(all_events)+1)):raise g.InvalidCapture('event ordinal gap')
    for event in events:
        point=event.get('point_world_m')
        if not isinstance(point,list) or len(point)!=3 or not all(r.finite_number(x) for x in point):raise g.InvalidCapture('malformed event contact point')
        for key in ('normal_world','force_argument'):
            value=event.get(key)
            if value is not None and (not isinstance(value,list) or len(value)!=3 or not all(r.finite_number(x) for x in value)):raise g.InvalidCapture('malformed optional event vector')
        if event.get('depth_argument_m') is not None and not r.finite_number(event['depth_argument_m']):raise g.InvalidCapture('malformed optional event depth')
        if event.get('producer_timestamp_ns') is not None:raise g.InvalidCapture('event producer timestamp is not supplied by public API')
        if event['force_semantics']!='PRE_SOLVE_NONPHYSICAL_FORCE_ARGUMENT':raise g.InvalidCapture('pre-solve force label missing')
        cycle=[x for x in window if x['cycle']==event['cycle']]
        before=next((x for x in cycle if x['stage']=='Update/before_Physics_Update'),None);after=next((x for x in cycle if x['stage']=='Update/after_Physics_Update'),None)
        if not before or not after or not before['callback_sequence']<event['callback_sequence']<after['callback_sequence'] or event['paused'] or not event['inside_physics_window']:raise g.InvalidCapture('event not runtime-bracketed in advancing Physics Update')
    expected_count=1 if spec['listener'] else 0
    single=rows[0]['prior_listener_count']==0 and all(x['listener_count']==expected_count and x['listener_enabled']==spec['listener'] for x in window)
    pre_rows=[x for x in window if x['stage']=='PreUpdate']
    lifecycle=validate_opt_in_lifecycle(rows,physical,spec)
    activated_before=lifecycle['passed']
    support_events={k:[] for k in r.SUPPORTS}
    for event in events:
        a,b=event['collision1_identity'],event['collision2_identity'];support=a if b=='ground' else b if a=='ground' else None
        if support in support_events:support_events[support].append(event)
    if not spec['listener'] and events:raise g.InvalidCapture('control emitted listener event')
    if not spec['iterations'] and events:raise g.InvalidCapture('ZERO readback emitted contact physics event')
    force_defaults=all(x.get('force_argument') is None or all(v==0. for v in x['force_argument']) for x in events)
    return {'health':{'configure':rows[0],'shutdown':rows[-1]},'documented_pre_solve_force_default_agrees':force_defaults,'single_listener_contract':single,'activation_before_S0':activated_before,'opt_in_lifecycle':lifecycle,
      'window_cycle_range':[lo,hi],'window':window,'events':events,'support_events':support_events,
      'availability':spec['listener'] and all(support_events.values()),'raw_event_count_total':len(all_events),'force_semantics':'PRE_SOLVE_NONPHYSICAL_FORCE_ARGUMENT'}


def neutrality_endpoints(record,spec):
    # Stage A computes endpoint equality only, never first-change/timing claims.
    audit=r.verify_capture(record,spec);e=record['phase_qualification'];before=e['packets'][:3];after=e['packets'][4:]
    a=r.observed(before[-1]['microstate']);b=r.observed(after[0]['microstate'])
    noise0=r.noise_envelope(before);noise1=r.noise_envelope(after)
    return {'case_id':spec['case_id'],'arm':spec['arm'],'capture_valid':True,
      'classification':'CONTACT_EVENT_LISTENER_NEUTRALITY_UNRESOLVED','measurements':r.delta_vector(a,b),
      'S0':before,'S1':after,'command_audit':audit,'delta_iterations':after[0]['iteration']-before[-1]['iteration'],
      'delta_sim_time_ns':after[0]['sim_time_ns']-before[-1]['sim_time_ns'],
      'baseline_command_state':e['host_PRE'],'baseline_plan':record['terminal_entry_history']['production_plan'],
      'stopped_contract':{'completed':e['completed_brake'],'chunk':e['stopped_chunk']},
      'noise_envelope':{k:max(v,noise1[k]) if v is not None and noise1.get(k) is not None else None for k,v in noise0.items()},
      'physical_timing_interpreted':False}


def analyze(record,spec,directory):
    physical=neutrality_endpoints(record,spec) if spec['stage']=='A' else r.analyze(record,spec)
    event=event_capture(directory,physical,spec)
    physical.update(phase='AN-T',stage=spec['stage'],listener=spec['listener'],event_capture=event,
      classification='CONTACT_EVENT_LISTENER_NEUTRALITY_UNRESOLVED' if spec['stage']=='A' else 'CONTACT_EVENT_TIMING_UNRESOLVED')
    return physical


def bit_equal(a,b):
    if r.finite_number(a) and r.finite_number(b):return struct.pack('>d',float(a))==struct.pack('>d',float(b))
    return type(a) is type(b) and a==b


def exact_compare(a,b):
    return [{'channel':k,'left':a.get(k),'right':b.get(k)} for k in sorted(a.keys()|b.keys()) if k not in a or k not in b or not bit_equal(a[k],b[k])]


def mandatory_available(result):
    vector=r.observed(result['S0'][-1]['microstate']);post=r.observed(result['S1'][0]['microstate'])
    required=[k for k in vector if k.startswith(('geometry.','generalized_q.','joint_wrench.')) and not k.endswith('.state')]
    required += [k for k in vector if k.startswith('supports.') and (k.endswith('Fn_N') or k.endswith('depth_m'))]
    supports_present=all(state['supports'][side]['component_available'] and contact_points(state,side) for state in [result['S0'][-1]['microstate'],result['S1'][0]['microstate']] for side in r.SUPPORTS)
    return bool(supports_present) and all(r.finite_number(vector.get(k)) and r.finite_number(post.get(k)) for k in required)


def marker_ok(result):
    m=result['measurements'];z=m['geometry.right_wheel.center_pose.position_world_m[2]']['delta']
    return z is not None and abs(z-r.RIGHT_Z_REFERENCE)<=1e-10 and all(m['supports.'+k+'.Fn_N']['delta'] is not None and abs(m['supports.'+k+'.Fn_N']['delta']-v)<=1e-8 for k,v in r.FN_REFERENCE.items())


def aggregate_a(results):
    valid=[x for x in results if x['capture_valid']];base=r.baseline_equivalence(results)
    out={'phase':'AN-T','stage':'A','status':'QUALIFICATION_CAPTURE_COMPLETE' if len(results)==len(valid)==10 else 'CAPTURE_FAILED',
      'classification':'CONTACT_EVENT_LISTENER_NEUTRALITY_UNRESOLVED','baseline_equivalence':base,'results':results,'Stage_B_permitted':False,'physical_timing_interpreted':False}
    if base['status']=='BASELINE_UNSTABLE':out['classification']='BASELINE_UNSTABLE';return out
    if len(valid)!=10 or base['status']!='OBSERVED_BASELINE_EQUIVALENT':return out
    comparisons=[]
    for rep in range(1,6):
        control=next(x for x in valid if x['case_id']==f'{CONTROL}_R{rep}');listener=next(x for x in valid if x['case_id']==f'{LISTENER}_R{rep}')
        s0=exact_compare(r.observed(control['S0'][-1]['microstate']),r.observed(listener['S0'][-1]['microstate']))
        s1=exact_compare(r.observed(control['S1'][0]['microstate']),r.observed(listener['S1'][0]['microstate']))
        delta=exact_compare({k:v['delta'] for k,v in control['measurements'].items()},{k:v['delta'] for k,v in listener['measurements'].items()})
        comparisons.append({'replicate':rep,'S0_differences':s0,'S1_differences':s1,'delta_differences':delta,'pass':not(s0 or s1 or delta)})
    endpoint_pairs=[]
    for i,a in enumerate(valid):
        for b in valid[i+1:]:endpoint_pairs.append({'left':a['case_id'],'right':b['case_id'],'differences':exact_compare(r.observed(a['S1'][0]['microstate']),r.observed(b['S1'][0]['microstate']))})
    out.update(matched_comparisons=comparisons,all_S1_pairwise_comparisons=endpoint_pairs)
    listener_ok=all(x['event_capture']['single_listener_contract'] and x['event_capture']['activation_before_S0'] and x['event_capture']['documented_pre_solve_force_default_agrees'] and (not x['listener'] or x['event_capture']['availability']) for x in valid)
    if not all(mandatory_available(x) for x in valid) or not listener_ok:return out
    if not all(marker_ok(x) for x in valid if not x['listener']):
        out['unresolved_reason']='NO_LISTENER controls did not replicate historical markers';return out
    unequal=any(not x['pass'] for x in comparisons) or any(x['differences'] for x in endpoint_pairs) or not all(marker_ok(x) for x in valid)
    out['classification']='CONTACT_EVENT_LISTENER_NONNEUTRAL' if unequal else 'CONTACT_EVENT_LISTENER_NEUTRAL'
    out['Stage_B_permitted']=not unequal;return out


def contact_points(state,support):
    return [p for c in state['supports'][support]['contacts'] if c['pair_classification']=='SUPPORT_GROUND' for p in c['points']]


def unique_point(point,normal,points,tolerance):
    candidates=[]
    if point is None or normal is None:return None
    for i,p in enumerate(points):
        q=p.get('position_world_m');n=p.get('normal_world')
        if q is None or n is None:continue
        distance=max(abs(x-y) for x,y in zip(point,q))
        same=max(abs(x-y) for x,y in zip(normal,n));reverse=max(abs(x+y) for x,y in zip(normal,n))
        if distance<=tolerance and min(same,reverse)<=1e-10:candidates.append({'index':i,'point':p,'distance_max_m':distance,'normal_relation':'SAME' if same<=reverse else 'REVERSED'})
    return candidates[0] if len(candidates)==1 else None


def event_fn(support):
    if not support.get('component_available'):return None
    total=0.
    for c in support['contacts']:
        if c['pair_classification']!='SUPPORT_GROUND':continue
        for p in c['points']:
            f=p.get('body_1_force_world_n');n=p.get('normal_world')
            if f is None or n is None or not all(r.finite_number(x) for x in f+n):return None
            length=math.sqrt(sum(x*x for x in n))
            if not length:return None
            total+=abs(sum(x*y for x,y in zip(f,n))/length)
    return total


def event_bundle_held(event,s0):
    read=event.get('readback')
    if not read:return None
    before={};at={}
    for link in r.LINKS:
        pose=s0['geometry'][link]['collision_pose'];other=read['engine_collision_pose'].get(link)
        if pose is None or other is None:return None
        before.update(r.flatten(pose,'geometry.'+link));at.update(r.flatten(other,'geometry.'+link))
    for side in r.SUPPORTS:
        x=s0['supports'][side]['Fn_N'];y=event_fn(read['supports'][side])
        if x is None or y is None:return None
        before['Fn.'+side]=x;at['Fn.'+side]=y
    for side in ('left','right'):
        for field in ('force_xyz_N','torque_xyz_N_m'):
            x=s0['joint_wrench'][side].get(field);y=read['joint_wrench'][side].get(field)
            if x is None or y is None:return None
            before.update(r.flatten(x,side+'.'+field));at.update(r.flatten(y,side+'.'+field))
    return all(abs(at[k]-x)<=128*max(math.ulp(float(x)),math.ulp(float(at[k]))) for k,x in before.items())


def timing_case(result,zero_noise):
    event=result['event_capture'];s0=result['S0'][-1]['microstate'];s1=result['S1'][0]['microstate'];mapping=[];earlier=[];complete=True;used={side:set() for side in r.SUPPORTS}
    if not event['availability'] or not event['single_listener_contract'] or not event['activation_before_S0'] or not event['documented_pre_solve_force_default_agrees']:complete=False
    for side in r.SUPPORTS:
        post=contact_points(s1,side);pre=contact_points(s0,side)
        for e in event['support_events'][side]:
            support_id=e['collision1'] if e['collision1_identity']==side else e['collision2']
            if support_id!=s1['supports'][side]['collision_entity_id']:complete=False;continue
            match=unique_point(e['point_world_m'],e.get('normal_world'),post,1e-10)
            old=unique_point(e['point_world_m'],e.get('normal_world'),pre,1e-6)
            depth=e.get('depth_argument_m')
            if not match or not old or not r.finite_number(depth) or not r.finite_number(match['point'].get('depth_m')) or not r.finite_number(old['point'].get('depth_m')):
                complete=False;mapping.append({'support':side,'event_sequence':e['event_sequence'],'status':'UNRESOLVED_MAPPING_OR_OPTIONAL_DEPTH'});continue
            if match['index'] in used[side]:complete=False
            used[side].add(match['index'])
            error=depth-match['point']['depth_m'];agreement=abs(error)<=1e-10
            if not agreement:complete=False
            baseline_depth=old['point']['depth_m'];difference=depth-baseline_depth
            repeats=[v for k,v in result['noise_envelope'].items() if k.startswith('supports.'+side+'.') and k.endswith('.depth_m')]
            if side not in zero_noise or not repeats or not all(r.finite_number(x) for x in repeats):complete=False;continue
            threshold=128*max(math.ulp(depth),math.ulp(baseline_depth))+zero_noise[side]+max(repeats)
            held=event_bundle_held(e,s0)
            if held is None:complete=False
            qualifies=agreement and abs(difference)>threshold and held is True
            mapping.append({'support':side,'event_sequence':e['event_sequence'],'callback_sequence':e['callback_sequence'],'iteration':e['iteration'],'sim_time_ns':e['sim_time_ns'],
              'S0_point_index':old['index'],'S1_point_index':match['index'],'event_depth_m':depth,'S0_component_depth_m':baseline_depth,'S1_component_depth_m':match['point']['depth_m'],
              'event_minus_S0_m':difference,'event_minus_S1_m':error,'threshold_m':threshold,'normal_relation':match['normal_relation'],
              'convention_agrees_with_post_component':agreement,'event_bundle_component_readbacks_held_at_S0':held,'earlier_public_geometry_evidence':qualifies,
              'identity_limit':'unique entity-pair/point/normal correspondence; not a persistent solver contact ID',
              'semantics':'event is pre-forward collision geometry; post component is later readback and may be held; numeric agreement alone is not a producer timestamp'})
            if qualifies:earlier.append(side)
        if len(used[side])!=len(post) or not post:complete=False
    if complete and earlier:classification='CONTACT_GEOMETRY_OBSERVABLE_EARLIER'
    elif complete and all(x.get('event_minus_S0_m',float('inf'))==0 for x in mapping) and all(result['measurements'][k]['delta']==0 for k in result['measurements'] if k.endswith('.depth_m')):classification='CONTACT_GEOMETRY_NOT_OBSERVABLE_EARLIER'
    else:classification='CONTACT_EVENT_TIMING_UNRESOLVED'
    return {'classification':classification,'complete_unique_mapping':complete,'earlier_supports':sorted(set(earlier)),'mapping':mapping,
      'stage_matrix':{'outer_stages':result['stages'],'event_stages':event['events']},'scope':'PUBLIC_OBSERVATION_ONLY; no solver causality or force-argument/Fn equivalence'}


def aggregate_b(results,stage_a):
    valid=[x for x in results if x['capture_valid']];base=r.baseline_equivalence(stage_a+results)
    out={'phase':'AN-T','stage':'B','status':'QUALIFICATION_CAPTURE_COMPLETE' if len(results)==len(valid)==10 else 'CAPTURE_FAILED',
      'classification':'CONTACT_EVENT_TIMING_UNRESOLVED','baseline_equivalence':base,'results':results,'further_invasive_hooks_permitted':False,'mediator_selected':False}
    if base['status']=='BASELINE_UNSTABLE':out['classification']='BASELINE_UNSTABLE';return out
    if len(valid)!=10 or base['status']!='OBSERVED_BASELINE_EQUIVALENT':return out
    zeros=[x for x in valid if x['arm']==ZERO];ones=[x for x in valid if x['arm']==ONE]
    if len(zeros)!=5 or len(ones)!=5:return out
    out['known_ONE_marker_checks']={x['case_id']:marker_ok(x) for x in ones}
    if not all(out['known_ONE_marker_checks'].values()):
        out['unresolved_reason']='known RIGHT-Z/preload ONE bundle did not replicate';return out
    noise={}
    for side in r.SUPPORTS:
        values=[]
        for x in zeros:
            for k,v in x['measurements'].items():
                if k.startswith('supports.'+side+'.') and k.endswith('.depth_m'):
                    repeat=x['noise_envelope'].get(k)
                    if not r.finite_number(v['delta']) or not r.finite_number(repeat):return out
                    values.append(max(abs(v['delta']),repeat))
        if not values:return out
        noise[side]=max(values)
    out['ZERO_event_counts']=[len(x['event_capture']['events']) for x in zeros]
    if any(out['ZERO_event_counts']):return out
    timing=[timing_case(x,noise) for x in ones];out['ONE_timing']=timing
    labels={x['classification'] for x in timing}
    if len(labels)==1:out['classification']=next(iter(labels))
    if out['classification']=='CONTACT_GEOMETRY_OBSERVABLE_EARLIER':
        if len({tuple(x['earlier_supports']) for x in timing})!=1:out['classification']='CONTACT_EVENT_TIMING_UNRESOLVED'
        else:out['public_observation_refinement']='CONTACT_GEOMETRY_OBSERVABLE_EARLIER_THAN_POSTPHYSICS_BUNDLE'
    out['stop_rule']='If unresolved, read-only timing investigation stops; no increasingly invasive hooks'
    return out


def guard_manifest():
    guard=r.guard_manifest()
    for path in r.DEFAULT_OUTPUT.rglob('*'):
        if path.is_file():guard[str(path.resolve())]=g.sha(path)
    for root in (HOST1_ROOT,B_ROOT):
        for path in root.rglob('*'):
            if path.is_file():guard[str(path.resolve())]=g.sha(path)
    for path in (SOURCE,Path(__file__),ROOT/'tests/test_gazebo_contact_surface_event.py',ROOT/'tests/test_gazebo_contact_opt_in_lifecycle.py'):
        guard[str(path.resolve())]=g.sha(path)
    return guard


def preflight_evidence_state(root):
    """Runtime NDJSON is expected in preserved Host roots, absent in fresh roots."""
    root=Path(root)
    if (root/'contact_event_qualification.json').exists():
        saved=json.loads((root/'contact_event_qualification.json').read_text())
        if not saved.get('results'):raise ValueError('completed Host root has no case results')
        return 'COMPLETED_PRESERVED_HOST_EVIDENCE'
    if list(root.rglob('*.ndjson')):raise ValueError('fresh preflight root contains unexpected runtime evidence')
    return 'FRESH_PREFLIGHT_ROOT'


def preflight():
    # AN-T1 prepares Stage A Host2 only; never rewrite Host1 or prepare Stage B.
    lifecycle=installed_opt_in_lifecycle()
    if A_ROOT.exists():raise FileExistsError('fresh full Stage A Host2 root required; no resume/overwrite')
    for root in (A_ROOT,):
        if root.exists() and any(p.name not in STATIC for p in root.iterdir()):raise FileExistsError('AN-T runtime evidence exists; no resume/overwrite')
    guard=guard_manifest();semantics=api_semantics();semantics['opt_in_lifecycle']=lifecycle;contract=static_contract();q.codec_self_check();r.safety(A_ROOT)
    A_ROOT.mkdir(parents=True,exist_ok=False)
    library,built=build(A_ROOT/'builds/contact_event_observer')
    # Reuse byte-identical accepted common observers; no plugin/runtime process.
    prior=json.loads((HOST1_ROOT/'contact_event_preflight.json').read_text())
    standard=copy.deepcopy(prior['standard_builds']);libraries={}
    sources={'support':g.ab.support.PLUGIN_SOURCE,'wrench':g.ab.wrench.SOURCE,'native':g.ab.native.PLUGIN_SOURCE}
    for name,original in prior['libraries'].items():
        original=Path(original)
        if g.sha(original)!=prior['standard_library_hashes'][name] or g.sha(sources[name])!=standard[name]['source_sha256']:raise ValueError('common observer source/library changed')
        target=A_ROOT/'builds'/original.parent.name/original.name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(original,target);libraries[name]=target
        dependencies=subprocess.run(['ldd','-r',str(target)],capture_output=True,text=True,check=True)
        if 'not found' in dependencies.stdout+dependencies.stderr or 'undefined symbol' in dependencies.stdout+dependencies.stderr:raise ValueError('copied common observer dependency failure')
        standard[name]['T1_reuse']={'original_library':str(original),'copied_library':str(target),'sha256':g.sha(target),'dependency_inspection':dependencies.stdout,'no_plugin_execution':True}
    g.verify_static_builds(standard)
    scenario,seed,_=g.history.source(g.ab.DEFAULT_ARTIFACT)
    for stage,root in [('A',A_ROOT)]:
        frozen=root/'protocol.json'
        if frozen.exists() and json.loads(frozen.read_text())!=protocol(stage):raise ValueError('frozen AN-T protocol differs')
        write(frozen,protocol(stage));write(root/'api_semantics.json',semantics);definitions=[];hashes=[]
        for spec in schedule(stage):
            directory=root/'preflight_sdfs'/spec['case_id'];prod=g.ab.GazeboWorldGenerator().generate(scenario,directory/'world',closed_loop=True,control_mode='PHYSICS')
            digest=g.sha(prod);hashes.append(digest)
            if digest!=g.EXPECTED_SHA:raise ValueError('production SHA changed')
            diag,info=g.ab._instrument_world(prod,directory,libraries,topic_identity='AN-T/'+spec['case_id']+'/'+uuid4().hex)
            diag,info=instrument(diag,info,library,spec['case_id'],directory)
            diag,info=g.checkpoints.instrument(diag,info);diag,info=g.instrument_audit(diag,info)
            order=validate_sdf(diag,spec)
            if g.ab._semantic(ET.parse(prod).getroot())!=g.ab._semantic(ET.parse(diag).getroot()):raise ValueError('physical SDF changed')
            definitions.append({'spec':spec,'sdf':str(diag),'sdf_sha256':g.sha(diag),'production_sdf':str(prod),'contract':order,'metadata':info['contact_event_observer']})
        pf={'phase':'AN-T','stage':stage,'status':'PREFLIGHT_PASS','gates':{gate:True for gate in GATES},'contract':contract,'protocol_sha256':g.sha(frozen),'runner_sha256':g.sha(__file__),
          'library':str(library),'observer_build':built,'libraries':{k:str(v) for k,v in libraries.items()},'standard_builds':standard,'standard_library_hashes':{k:g.sha(v) for k,v in libraries.items()},
          'definitions':definitions,'guard_manifest':guard,'api_semantics_sha256':g.sha(root/'api_semantics.json'),'production_sha_before':hashes[0],'production_sha_after':hashes[-1],
          'production_changed':False,'Gazebo_executed':False,'Host_executed':False,'runtime_facts':'HOST_REQUIRED','seed':seed,
          'runtime_gate':'Full fresh ten-process Stage A Host2 required; Stage B blocked until separately qualified',
          'repair_phase':'AN-T1','opt_in_lifecycle':lifecycle,'full_Stage_A_Host2_required':True,'selective_reruns':False,'Stage_B_prepared_by_T1':False}
        write(root/'contact_event_preflight.json',pf)
    g.production_sensor_order_contract();g.history.verify_manifest(guard)
    return {'status':'PREFLIGHT_PASS','gates':list(GATES),'Stage_A_ready':True,'Stage_B_blocked':True}


def stage_b_gate():
    path=A_ROOT/'contact_event_qualification.json'
    if not path.exists():raise g.InvalidCapture('Stage B blocked: Stage A neutrality has not passed')
    saved=json.loads(path.read_text())
    if saved['status']!='QUALIFICATION_CAPTURE_COMPLETE' or saved['classification']!='CONTACT_EVENT_LISTENER_NEUTRAL' or not saved.get('Stage_B_permitted'):raise g.InvalidCapture('Stage B blocked: Stage A not neutral')
    pf=json.loads((A_ROOT/'contact_event_preflight.json').read_text())
    if pf['runner_sha256']!=g.sha(__file__) or pf['protocol_sha256']!=g.sha(A_ROOT/'protocol.json'):raise g.InvalidCapture('Stage A design changed')
    g.history.verify_manifest(saved['runtime_evidence_sha256'])
    ledger=json.loads((A_ROOT/'contact_event_case_ledger.json').read_text())
    if [s['spec'] for s in ledger['slots']]!=schedule('A') or any(s['state']!='FINALIZED' for s in ledger['slots']):raise g.InvalidCapture('Stage A frozen block incomplete')
    repeated=aggregate_a([s['result'] for s in ledger['slots']])
    if repeated['classification']!='CONTACT_EVENT_LISTENER_NEUTRAL' or not repeated['Stage_B_permitted']:raise g.InvalidCapture('Stage A neutrality did not reproduce offline')
    return repeated['results']


def safety(root):
    r.safety(root)
    prior_partitions=set()
    for prior in (HOST1_ROOT,A_ROOT,B_ROOT,r.DEFAULT_OUTPUT):
        for path in prior.glob('*/process_lifecycle.json'):
            life=json.loads(path.read_text())
            if not life.get('shutdown_proven'):raise g.InvalidCapture('prior diagnostic shutdown unproven')
            prior_partitions.update(x['status']['partition'] for x in life['events'] if x.get('event')=='launch')
    for process in Path('/proc').iterdir():
        if not process.name.isdigit() or int(process.name)==os.getpid():continue
        try:environment=(process/'environ').read_bytes().split(b'\0')
        except (FileNotFoundError,ProcessLookupError,PermissionError):continue
        if any(('GZ_PARTITION='+part).encode() in environment for part in prior_partitions):raise g.InvalidCapture('prior diagnostic partition still active; no process killed')


def run(stage):
    # This gate precedes every Stage B filesystem/runtime action.
    stage_a=stage_b_gate() if stage=='B' else None
    root=A_ROOT if stage=='A' else B_ROOT
    if not root.exists() or any(p.name not in STATIC for p in root.iterdir()):raise FileExistsError('fresh AN-T block only; never resume or rerun')
    pf=json.loads((root/'contact_event_preflight.json').read_text())
    if pf['status']!='PREFLIGHT_PASS' or pf['runner_sha256']!=g.sha(__file__) or pf['protocol_sha256']!=g.sha(root/'protocol.json'):raise g.InvalidCapture('frozen preflight mismatch')
    g.history.verify_manifest(pf['guard_manifest']);installed_opt_in_lifecycle();safety(root);q.codec_self_check()
    semantics=json.loads((root/'api_semantics.json').read_text())
    if g.sha(root/'api_semantics.json')!=pf['api_semantics_sha256']:raise g.InvalidCapture('API semantics changed')
    g.history.verify_manifest({p:x['sha256'] for p,x in semantics['headers'].items()});g.history.verify_manifest({p:x['sha256'] for p,x in semantics['installed_symbols'].items()});g.history.verify_manifest(semantics['event_library_sha256'])
    if g.sha(pf['library'])!=pf['observer_build']['library_sha256']:raise g.InvalidCapture('listener library changed')
    for definition in pf['definitions']:
        if g.sha(definition['sdf'])!=definition['sdf_sha256'] or g.sha(definition['production_sdf'])!=g.EXPECTED_SHA:raise g.InvalidCapture('SDF changed')
        validate_sdf(definition['sdf'],definition['spec'])
    g.history.verify_manifest({pf['libraries'][k]:v for k,v in pf['standard_library_hashes'].items()})
    scenario,seed,_=g.history.source(g.ab.DEFAULT_ARTIFACT);libraries={k:Path(v) for k,v in pf['libraries'].items()}
    ledger={'phase':'AN-T','stage':stage,'slots':[{'spec':s,'state':'SCHEDULED'} for s in schedule(stage)]}
    write(root/'contact_event_case_ledger.json',ledger)
    print('CURRENT_PHASE_IS_AN_T',flush=True);print('STAGE_'+stage,flush=True);print('PROSPECTIVE_CASE_ORDER_FROZEN',flush=True)
    close=None;partitions=set();topics=set();previous_shutdown=True
    if stage=='B':
        previous=json.loads((A_ROOT/'contact_event_case_ledger.json').read_text())
        partitions.update(s['runtime_identity']['partition'] for s in previous['slots'])
        topics.update(s['runtime_identity']['topic'] for s in previous['slots'])
    for slot in ledger['slots']:
        if not previous_shutdown:slot['not_started_reason']='prior shutdown unproven';write(root/'contact_event_case_ledger.json',ledger);continue
        spec=slot['spec'];directory=root/spec['case_id'];safety(root);directory.mkdir();slot['state']='STARTED';write(root/'contact_event_case_ledger.json',ledger)
        try:
            record=capture(spec['case_id'],scenario,directory,libraries,seed,uuid4().hex,Path(pf['library']))
            life=json.loads((directory/'process_lifecycle.json').read_text());close=r.verify_lifecycle(record,life,close,partitions,topics)
            result=analyze(record,spec,directory);write(directory/'contact_event_analysis.json',result)
            slot.update(state='FINALIZED',result=result,lifecycle=life,runtime_identity=record['runtime_identity']);previous_shutdown=True
        except Exception as exc:
            life_path=directory/'process_lifecycle.json';life=json.loads(life_path.read_text()) if life_path.exists() else {}
            previous_shutdown=life.get('shutdown_proven') is True
            slot.update(state='FINALIZED',result={'case_id':spec['case_id'],'arm':spec['arm'],'capture_valid':False,'classification':'CAPTURE_INVALID','invalid_reason':type(exc).__name__+': '+str(exc),'traceback':traceback.format_exc()},lifecycle=life)
        write(root/'contact_event_case_ledger.json',ledger);print(spec['case_id']+': '+slot['result']['classification'],flush=True);gc.collect()
    results=[s['result'] for s in ledger['slots'] if 'result' in s]
    result=aggregate_a(results) if stage=='A' else aggregate_b(results,stage_a)
    result['original_slots']=ledger['slots'];result['runtime_evidence_sha256']={str(p.resolve()):g.sha(p) for s in ledger['slots'] for p in (root/s['spec']['case_id']).rglob('*') if p.is_file()}
    result['runtime_evidence_sha256'][str((root/'contact_event_case_ledger.json').resolve())]=g.sha(root/'contact_event_case_ledger.json')
    result.update(production_sha_before=pf['production_sha_before'],production_sha_after=pf['production_sha_after'],mediator_selected=False,Action24_outcomes_tested=False)
    g.history.verify_manifest(pf['guard_manifest']);write(root/'contact_event_qualification.json',result)
    if stage=='A':print('STAGE_B_REMAINS_UNEXECUTED_SEPARATE_INVOCATION_REQUIRED',flush=True)
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);choice=parser.add_mutually_exclusive_group(required=True)
    choice.add_argument('--preflight-only',action='store_true');choice.add_argument('--host-stage-a',action='store_true');choice.add_argument('--host-stage-b',action='store_true')
    args=parser.parse_args(argv)
    try:
        if args.preflight_only:
            result=preflight()
            for gate in GATES:print(gate)
            print(result['status']);print('STAGE_B_BLOCKED_UNTIL_NEUTRALITY');return 0
        result=run('A' if args.host_stage_a else 'B');print(result['status']);print(result['classification']);print('OBSERVATIONAL_ONLY_NO_MEDIATOR_SELECTED')
        if args.host_stage_a:return 0 if result['status']=='QUALIFICATION_CAPTURE_COMPLETE' and result['classification']=='CONTACT_EVENT_LISTENER_NEUTRAL' else 1
        return 0 if result['status']=='QUALIFICATION_CAPTURE_COMPLETE' else 1
    except Exception as exc:print('CAPTURE_FAILED: '+type(exc).__name__+': '+str(exc));return 1

if __name__=='__main__':raise SystemExit(main())
