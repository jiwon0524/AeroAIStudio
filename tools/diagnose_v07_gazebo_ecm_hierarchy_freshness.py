#!/usr/bin/env python3
"""AN-P hierarchy-marker closure only. Static mode builds observers; never launches a server."""
from __future__ import annotations
import argparse
import copy
import gc
import inspect
import json
import math
import os
import shlex
import subprocess
import time
import traceback
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4
from tools import diagnose_v07_gazebo_natural_q_phase_correspondence as legacy
q=legacy.q

d=q.d;g=q.g;ROOT=q.ROOT
DELTA=-4.868844349914525e-8
HEIGHT_REFERENCE_M=2.940583122834628e-8
ZERO='ZERO_TICK_FRESHNESS_CONTROL';ONE='ONE_TICK_FRESHNESS_OBSERVATION'
DEFAULT_OUTPUT=ROOT/'validation/v071-host/gazebo-action24-ecm-hierarchy-freshness-phase3hanp-host1'
SOURCE=ROOT/'tools/gazebo_ecm_hierarchy_freshness_observer.cc'
# The proven capture harness checks this exact intentional exception before UP.
STOP=q.STOP
STATIC={'protocol.json','hierarchy_preflight.json','builds','preflight_sdfs'}
GATES=('DIAGNOSTIC_OBSERVER_BUILDS','CURRENT_PHASE_IS_AN_P','NO_AN_G_RERUN_PATH',
 'SIX_CASE_SCHEDULE_FROZEN','THREE_ZERO_THREE_ONE','ZERO_ADVANCEMENT_EXACT','ONE_ADVANCEMENT_EXACT_1MS',
 'NO_RESETPOSITION','NO_TWIST_TREATMENT','NO_POSE_RPC','NO_WORLDPOSECMD','NO_PRODUCTION_SENSOR_REFRESH',
 'NO_ACTION24_UP','ECM_HIERARCHY_CAPTURED','ENGINE_REFERENCE_CAPTURED','RECONSTRUCTION_MATRIX_DEFINED',
 'CALLBACK_TIMING_CAPTURED','ACTUAL_Q_GUARD_DEFINED','RIGHT_WHEEL_Z_GUARD_DEFINED','CONTACT_SCOPE_LIMITED',
 'FRESH_PROCESS_PER_CASE','NO_AUTOMATIC_RERUN','PRODUCTION_SHA_UNCHANGED')
CLASSES=('ECM_MIXED_HIERARCHY_FRESHNESS_REPRODUCED','ECM_MARKER_ARTIFACT_CLOSED',
 'ECM_HIERARCHY_FRESHNESS_PARTIALLY_LOCALIZED','ECM_HIERARCHY_FRESHNESS_NOT_REPRODUCED',
 'BASELINE_UNSTABLE','CAPTURE_INVALID','ZERO_TICK_FRESHNESS_CONTROL_UNCHANGED')
ENTITIES=('world','model','body','left_wheel','right_wheel','front_caster','rear_caster',
 'body_collision','left_collision','right_collision','front_collision','rear_collision')


def schedule():
    return [{'ordinal':len_before+j+1,'case_id':f'{arm}_R{r}','arm':arm,'replicate':f'R{r}',
             'iterations':int(arm==ONE),'sim_time_delta_ns':1_000_000*int(arm==ONE)}
            for r in range(1,4) for len_before in [(r-1)*2]
            for j,arm in enumerate((ZERO,ONE) if r%2 else (ONE,ZERO))]


def protocol():
    return {'phase':'AN-P','experiment':'READ_ONLY_ECM_HIERARCHY_FRESHNESS_AND_ENGINE_FRAME_COHERENCE_QUALIFICATION',
      'schedule_status':'PROSPECTIVE_CASE_ORDER_FROZEN','schedule':schedule(),'classifications':CLASSES,
      'legacy_marker_reference_rad':DELTA,'RIGHT_Z_reference_m':HEIGHT_REFERENCE_M,
      'legacy_marker_is_causal_candidate':False,'actual_q_is_causal_candidate':False,
      'automatic_reruns':False,'Action24_UP':False,'causal_efficacy_testing':False,
      'boundary':'Fresh canonical RIGHT_HISTORY Actions08-23; DOWN -> LINEAR_REVERSAL -> BRAKE_LINEAR stopped; abort before UP',
      'observation_requests':[0,0,0,1,0,0,0],
      'ZERO':'Three S0 readbacks, arm observation only, no advancing request, matched pause ACK, three S1 readbacks',
      'ONE':'Same observation path; exactly one diagnostic request for one physics iteration between S0 and S1; exactly 1000000ns',
      'pause_sync':'One pause:true without multi_step in each arm; no advancement from synchronization',
      'hierarchy_entities':ENTITIES,'components':['Pose','WorldPose_if_present','ParentEntity','ECM_parent_graph'],
      'hierarchy_semantics':'Pose is local to parent; reconstructed worldPose is distinct from optional WorldPose component. Missing WorldPose stays absent. Collision WorldPose readback requests match accepted AN-N and do not assign pose state.',
      'change_semantics':'Public ECM ComponentState enum and independently serialized value changes since prior observed callback; neither is a producer timestamp or proof of a fresh solve',
      'engine_reference':'Same proven identity-offset body/drive collision WorldPose readback; actual q via Joint::Position',
      'matrix':{'A':['ECM body','ECM RIGHT wheel'],'B':['engine body','engine RIGHT wheel'],
                'C':['engine body','ECM RIGHT wheel'],'D':['ECM body','engine RIGHT wheel']},
      'phase_equation':'wrap(2 atan2(spin.y,spin.w)), spin=conj(body_world_q)*wheel_world_q*conj(Rx(pi/2))',
      'matrix_caution':'A/C/D may mix held/current inputs. Never label a mixed-state combination physical wheel phase.',
      'callback_capture':['PreUpdate','Update/observer_after_Physics_Update','PostUpdate/const_ECM','paused readbacks after advancement'],
      'callback_clock':'UpdateInfo iteration/time label the end of the step even in PreUpdate. Update ordering verified from diagnostic SDF default-priority load order; no inference about unobserved internals.',
      'measurement_policy':legacy.protocol()['measurement_policy'],
      'closure_rule':'All six valid, stable S0; three unchanged ZERO controls; three ONE A and D marker changes, B and C roundoff-scale, unchanged actual RIGHT q; parent-local reconstruction matches and specifically identifies held versus updated path components. Height reported separately.',
      'limited_contacts':'Topology/Fn/depth/wrench and provenance only. Held or filtered components are not promoted to fresh physical recomputation; no contact causal analysis.',
      'next_phase_boundary':'If marker closed, stop generalized-q/legacy-phase causal work. Future physical work may examine wheel Z/support preload/depth/wrench/constraint state, but is not implemented here.',
      'runtime_facts':'HOST_REQUIRED; component localization and marker closure are not established by static tests',
      'production_sha256':g.EXPECTED_SHA}


def write(path,value):
    path=Path(path).resolve()
    if not path.is_relative_to(DEFAULT_OUTPUT.resolve()):raise ValueError('write outside new AN-P evidence directory refused')
    d.ledger_io.atomic_json(path,value)


def guard_manifest():
    guard=legacy.guard_manifest()
    for p in legacy.DEFAULT_OUTPUT.rglob('*'):
        if p.is_file():guard[str(p.resolve())]=g.sha(p)
    for p in (SOURCE,Path(__file__),ROOT/'tests/test_gazebo_ecm_hierarchy_freshness.py'):
        if p.exists():guard[str(p.resolve())]=g.sha(p)
    return guard


def build(directory):
    directory.mkdir(parents=True,exist_ok=True);library=(directory/'libaero_ecm_hierarchy_freshness.so').resolve()
    flags=subprocess.run(['pkg-config','--cflags','--libs','gz-sim8','gz-plugin2','gz-transport13'],capture_output=True,text=True,check=True)
    command=['c++','-std=c++17','-shared','-fPIC','-Wl,-z,defs',str(SOURCE),'-o',str(library),*shlex.split(flags.stdout)]
    result=subprocess.run(command,capture_output=True,text=True)
    if result.returncode:raise RuntimeError(result.stderr)
    deps=subprocess.run(['ldd','-r',str(library)],capture_output=True,text=True,check=True)
    if 'not found' in deps.stdout or 'undefined symbol' in deps.stdout:raise RuntimeError(deps.stdout)
    return library,{'command':command,'dependency_check':deps.stdout,'source_sha256':g.sha(SOURCE),'library_sha256':g.sha(library)}


def instrument(path,info,library,case,directory):
    tree=ET.parse(path);topic=info['native']['topic']+'/ecm_hierarchy_freshness'
    plugin=ET.SubElement(tree.find('world'),'plugin',filename=str(library),name='aero_diagnostic::EcmHierarchyFreshnessObserver')
    for key,val in {'topic':topic,'service':topic+'/request','output':str(directory/'ecm_hierarchy_freshness.ndjson')}.items():
        ET.SubElement(plugin,key).text=str(val)
    tree.write(path,encoding='utf-8',xml_declaration=True)
    info['hierarchy_observer']={'topic':topic,'service':topic+'/request','case':case,'read_only':True}
    info['diagnostic_sdf_sha256']=g.sha(path)
    return path,info


def decorate(packet):
    legacy.decorate(packet)
    traces=packet.get('callback_trace',[])
    if not traces:raise g.InvalidCapture('AN-P hierarchy callback trace missing')
    packet['hierarchy']=traces[-1]['hierarchy']
    packet['phase']='AN-P'
    return packet


def read_packet(adapter,topic,code,cursor,asynchronous):
    transport=adapter.env.transport;history=len(transport.request_history)
    response=transport.request(topic+'/request','Int32','Boolean',{'data':code},max_attempts=1)
    if response.get('data') is not True:raise g.InvalidCapture('read-only observer request rejected; no retry')
    deadline=time.monotonic()+adapter.env.timeout
    while time.monotonic()<deadline:
        for seq,message in transport.messages_after(topic,cursor,timeout=max(0.,deadline-time.monotonic())):
            cursor=seq;packet=decorate(json.loads(message['data']))
            if packet['event']=='advancing_observation':asynchronous.append(packet);continue
            if packet['operation_code']!=code:raise g.InvalidCapture('observer acknowledgement operation differs')
            requests=transport.request_history[history:]
            if len(requests)!=1 or len(requests[0]['attempts'])!=1:raise g.InvalidCapture('observation request retried')
            return packet,cursor
    raise g.InvalidCapture('paused readback timeout; no advancing fallback')


def hierarchy_hook(case_id,evidence,library):
    spec=next(s for s in schedule() if s['case_id']==case_id)
    def hook(adapter,case,native,row,it,audit):
        if case!=case_id or evidence:raise g.InvalidCapture('unexpected/repeated natural boundary')
        g.y.stopped_chunk(row);completed=g.y.completed_brake_checkpoint(adapter,row)
        marker=g.dm.physics_mark(adapter);bi,bns=d.exact_stats(marker)
        audit['phase']='treatment';audit['adapter']=adapter
        evidence.update(phase='AN-P',spec=spec,completed_brake=completed,stopped_chunk=copy.deepcopy(row),PRE_marker=marker,
          window_start=len(audit['events']),host_PRE=q.boundary_state(adapter))
        evidence['host_PRE']['prohibited_transport_cursors']=q.prohibited_cursors(audit)
        packets=[];automatic=[];topic=native.topic+'/ecm_hierarchy_freshness';transport=adapter.env.transport
        try:
            with q.diagnostic_codec(transport) as descriptors:
                evidence['diagnostic_transport_descriptors']=descriptors
                transport.subscribe(topic,'StringMsg');cursor=transport.cursor(topic)
                evidence['publisher_readiness']=transport.wait_for_topic(topic,'StringMsg',timeout=adapter.env.timeout)
                evidence['service_readiness']=transport.wait_for_service(topic+'/request','Int32','Boolean',timeout=adapter.env.timeout)
                for code in (0,0,0,1):
                    packet,cursor=read_packet(adapter,topic,code,cursor,automatic);packets.append(packet)
                evidence['before_optional_tick_stats']=q.fresh_paused_stats(adapter)
                if spec['iterations']==1:evidence['single_advance']=d.single_advance(adapter,1)
                sync={};evidence['pause_synchronization']=sync
                evidence['after_optional_tick_stats']=g.y.synchronize_paused(adapter,bi+spec['iterations'],bns+spec['sim_time_delta_ns'],sync)
                for _ in range(3):
                    packet,cursor=read_packet(adapter,topic,0,cursor,automatic);packets.append(packet)
                evidence.update(POST_marker=q.fresh_paused_stats(adapter),host_POST=q.boundary_state(adapter),qualification_completed=True)
                evidence['host_POST']['prohibited_transport_cursors']=q.prohibited_cursors(audit)
        except Exception as exc:
            evidence['qualification_error']=g.dm.failure_record(exc);raise
        finally:
            evidence.update(packets=packets,advancing_observations=automatic,window_end=len(audit['events']))
            audit['phase']='qualification_finished_no_acquisition'
        raise g.InvalidCapture(STOP)
    return hook


@contextmanager
def read_only_capture_hooks():
    old_hook,old_instrument=q.qualification_hook,q.instrument
    q.qualification_hook,q.instrument=hierarchy_hook,instrument
    try:yield
    finally:q.qualification_hook,q.instrument=old_hook,old_instrument


def capture(*args):
    # q.capture provides canonical history, lifecycle recording and intentional pre-UP abort.
    # Its setter hook and mutating SDF instrumenter are replaced before it is entered.
    with read_only_capture_hooks():return q.capture(*args)


def numeric_delta(pre,post,angle=False):
    value=post-pre
    return q.wrap(value) if angle else value


def resolved_match(before,after,expected,cap,angle=False):
    vals=[*before,*after]
    if not vals or not all(isinstance(x,(float,int)) and math.isfinite(x) for x in vals):
        raise g.InvalidCapture('nonfinite/missing numeric observation')
    delta=numeric_delta(before[-1],after[0],angle)
    noise=max(max(numeric_delta(before[0],v,angle) for v in before)-min(numeric_delta(before[0],v,angle) for v in before),
              max(numeric_delta(after[0],v,angle) for v in after)-min(numeric_delta(after[0],v,angle) for v in after))
    floor=128*max(math.ulp(float(x)) for x in vals)
    resolution_ok=floor+noise<=cap*.1
    return {'delta':delta,'expected':expected,'error':numeric_delta(expected,delta,angle),
      'same_time_repeatability':noise,'binary64_floor':floor,'resolution_sufficient':resolution_ok,
      'matches':resolution_ok and abs(numeric_delta(expected,delta,angle))<=cap,'cap':cap}


def command_audit(record,e):
    window=record['command_audit'][e['window_start']:e['window_end']]
    g.audit_window(record['command_audit'],e['window_start'],e['window_end'])
    reads=[];controls=[]
    for event in window:
        if event.get('kind')!='RPC':raise g.InvalidCapture('non-RPC event during natural observation')
        if event.get('request_type')=='Int32' and event.get('service','').endswith('/ecm_hierarchy_freshness/request'):reads.append(event)
        elif event.get('request_type')=='WorldControl':controls.append(event)
        else:raise g.InvalidCapture('unexpected RPC in natural treatment: '+str(event))
    if len(reads)!=7:raise g.InvalidCapture('seven read-only observer requests required')
    # Audit concrete payload and attempt count, not merely declared dose.
    payloads=[x.get('payload') for x in controls]
    expected=([{'pause':True,'multi_step':1}] if e['spec']['iterations'] else [])+[{'pause':True}]
    if payloads!=expected:raise g.InvalidCapture('advancement/pause RPC sequence differs: '+str(payloads))
    if any(len(x.get('transport_evidence',{}).get('attempts',[]))!=1 or x.get('response',{}).get('data') is not True for x in controls+reads):raise g.InvalidCapture('diagnostic RPC retry detected')
    if e['host_PRE']!=e['host_POST']:raise g.InvalidCapture('cached production cursor/planner/executor state changed')
    return {'new_Twist':0,'pose_RPC':0,'WorldPoseCmd':0,'joint_reset':0,'production_sensor_consumption':0,
      'planner_mutation':0,'Action24_UP':0,'advancing_requests':e['spec']['iterations'],
      'advancing_iterations_requested':e['spec']['iterations'],'nonadvancing_pause_requests':1,
      'read_only_observation_requests':7,'events':window}


def canonical_pose(value):
    if value is None:return None
    position=value.get('position_m',value.get('position_world_m'))
    orientation=value.get('orientation_xyzw',value.get('orientation_world_xyzw'))
    if not isinstance(position,list) or len(position)!=3 or not isinstance(orientation,list) or len(orientation)!=4:
        raise g.InvalidCapture('malformed pose observation')
    if not all(type(x) in (int,float) and math.isfinite(x) for x in position+orientation):raise g.InvalidCapture('nonfinite pose observation')
    if abs(sum(x*x for x in orientation)-1)>1e-10:raise g.InvalidCapture('nonunit orientation observation')
    return {'position_world_m':position,'orientation_world_xyzw':orientation}


def compose(parent,local):
    # Unit quaternion conjugate, vector rotation, then rigid transform composition.
    p=canonical_pose(parent);l=canonical_pose(local);a=p['orientation_world_xyzw'];b=l['orientation_world_xyzw']
    vector=g.dm.qmul(g.dm.qmul(a,[*l['position_world_m'],0.]),g.dm.qinverse(a))[:3]
    return {'position_world_m':[x+y for x,y in zip(p['position_world_m'],vector)],'orientation_world_xyzw':g.dm.qmul(a,b)}


def pose_error(a,b):
    a=canonical_pose(a);b=canonical_pose(b)
    dot=sum(x*y for x,y in zip(a['orientation_world_xyzw'],b['orientation_world_xyzw']));sign=1 if dot>=0 else -1
    return {'position_max_abs_m':max(abs(x-y) for x,y in zip(a['position_world_m'],b['position_world_m'])),
      'orientation_component_max_abs':max(abs(x-sign*y) for x,y in zip(a['orientation_world_xyzw'],b['orientation_world_xyzw']))}


def same_pose(a,b):
    if a is None or b is None:return False
    e=pose_error(a,b)
    return e['position_max_abs_m']<=1e-12 and e['orientation_component_max_abs']<=1e-12


def reconstruct_hierarchy(hierarchy):
    if set(hierarchy)!=set(ENTITIES):raise g.InvalidCapture('required hierarchy entity missing/extra')
    by_id={v['entity_id']:key for key,v in hierarchy.items()}
    if len(by_id)!=len(ENTITIES) or any(not v['resolved'] or not v['entity_id'] for v in hierarchy.values()):raise g.InvalidCapture('hierarchy unresolved/aliased entity IDs')
    cache={};active=set();unavailable={}
    identity={'position_world_m':[0.,0.,0.],'orientation_world_xyzw':[0.,0.,0.,1.]}
    def visit(key):
        if key in cache:return cache[key]
        if key in active:raise g.InvalidCapture('cyclic parent graph')
        row=hierarchy[key];parent=row['ParentEntity'];local=row['Pose']
        active.add(key)
        if key=='world':
            if row['graph_parent_entity']!=0:raise g.InvalidCapture('world root parent unexpected')
            result=canonical_pose(local['value']) if local['present'] else identity
        elif not parent['present'] or not local['present']:
            unavailable[key]='local Pose or ParentEntity unavailable';result=None
        else:
            if parent['value']!=row['graph_parent_entity']:raise g.InvalidCapture('component parent disagrees with ECM graph')
            if parent['value'] not in by_id:unavailable[key]='parent outside observed closure';result=None
            else:
                root=visit(by_id[parent['value']]);result=compose(root,local['value']) if root else None
        active.remove(key);cache[key]=result;return result
    for key in hierarchy:visit(key)
    comparisons={key:{'available':value is not None,'matches_gz_sim_worldPose':same_pose(value,hierarchy[key]['reconstructed_world_pose']) if value else False,
      'residual':pose_error(value,hierarchy[key]['reconstructed_world_pose']) if value else None} for key,value in cache.items()}
    return {'world_poses':cache,'checks':comparisons,'unavailable':unavailable,
      'all_reconstructed_match':not unavailable and all(v['matches_gz_sim_worldPose'] for v in comparisons.values()),
      'provenance':'Offline parent-local composition from recorded Pose and ParentEntity; optional cached WorldPose never substituted'}


def phase_from(body,wheel):
    b=canonical_pose(body)['orientation_world_xyzw'];w=canonical_pose(wheel)['orientation_world_xyzw']
    spin=g.dm.qmul(g.dm.qmul(g.dm.qinverse(b),w),g.dm.qinverse([math.sqrt(.5),0,0,math.sqrt(.5)]))
    return q.wrap(2*math.atan2(spin[1],spin[3]))


def matrix(packet):
    h=packet['hierarchy'];body_ecm=h['body']['reconstructed_world_pose'];wheel_ecm=h['right_wheel']['reconstructed_world_pose']
    body_engine=packet['links']['body']['engine_derived_collision_pose'];wheel_engine=packet['links']['right_wheel']['engine_derived_collision_pose']
    rows={'A':(body_ecm,wheel_ecm,'ECM body + ECM RIGHT wheel'),'B':(body_engine,wheel_engine,'engine body + engine RIGHT wheel'),
      'C':(body_engine,wheel_ecm,'engine body + ECM RIGHT wheel'),'D':(body_ecm,wheel_engine,'ECM body + engine RIGHT wheel')}
    result={}
    for key,(body,wheel,provenance) in rows.items():
        coherent=same_pose(body,body_engine) and same_pose(wheel,wheel_engine)
        result[key]={'phase_reconstruction_rad':phase_from(body,wheel),'provenance':provenance,
          'same_simulation_state_observationally_consistent':coherent,
          'freshness':'ENGINE_REFERENCE_CURRENT_AT_CALLBACK' if key=='B' else 'CONSISTENT_WITH_ENGINE_WITHIN_VERIFIED_RESOLUTION' if coherent else 'MIXED_OR_HELD_ECM_INPUT',
          'interpretation':'ENGINE_RELATIVE_ORIENTATION_READBACK' if key=='B' else 'OBSERVATION_LAYER_RECONSTRUCTION_ONLY; not physical wheel phase if mixed',
          'iteration':packet['iteration'],'sim_time_ns':packet['sim_time_ns']}
    return result


def analyze(record,spec):
    # Reuse qualified clock/history/no-UP validator only. Never enter a predecessor runner.
    old=legacy.command_audit;legacy.command_audit=command_audit
    try:base=legacy.analyze(record,spec)
    finally:legacy.command_audit=old
    e=record['phase_qualification'];packets=e['packets'];before=packets[:3];after=packets[4:]
    timeline=[];localizations=[]
    for packet in packets+e['advancing_observations']:
        trace=packet.get('callback_trace',[])
        if [x['stage'] for x in trace]!=['PreUpdate','Update/observer_after_Physics_Update','PostUpdate/const_ECM']:
            raise g.InvalidCapture('required callback stages missing or reordered')
        if any(x['iteration']!=packet['iteration'] or x['sim_time_ns']!=packet['sim_time_ns'] or x['paused']!=packet['paused'] for x in trace):raise g.InvalidCapture('callback trace clock mismatch')
        if [x['callback_sequence'] for x in trace]!=sorted({x['callback_sequence'] for x in trace}):raise g.InvalidCapture('callback trace sequence incoherent')
        if trace[-1]['actual_generalized_q']!=packet['generalized_q']:raise g.InvalidCapture('trace/packet actual q incoherent')
        for link in ('body','left_wheel','right_wheel'):
            if not same_pose(trace[-1]['engine_reference'][link]['pose'],packet['links'][link]['engine_derived_collision_pose']):
                raise g.InvalidCapture('trace/packet engine reference incoherent')
            if not same_pose(trace[-1]['hierarchy'][link]['reconstructed_world_pose'],packet['links'][link]['ECM_pose']):
                raise g.InvalidCapture('hierarchy/legacy ECM pose incoherent')

        for point in trace:
            rec=reconstruct_hierarchy(point['hierarchy'])
            point=copy.deepcopy(point);point['offline_reconstruction']=rec;timeline.append(point)
            localizations.append({'callback_sequence':point['callback_sequence'],'all_reconstructed_match':rec['all_reconstructed_match'],'unavailable':rec['unavailable']})
    timeline.sort(key=lambda x:x['callback_sequence'])
    if len({x['callback_sequence'] for x in timeline})!=len(timeline):raise g.InvalidCapture('duplicate callback observations')
    first=before[-1];last=after[0];pre=matrix(first);post=matrix(last)
    comparisons={}
    for key in pre:
        values0=[matrix(x)[key]['phase_reconstruction_rad'] for x in before]
        values1=[matrix(x)[key]['phase_reconstruction_rad'] for x in after]
        target=DELTA if spec['iterations'] and key in ('A','D') else 0.
        comparisons[key]={'S0':pre[key],'S1':post[key],**resolved_match(values0,values1,target,1e-11 if target else 1e-12,True)}
    qguard=resolved_match([p['generalized_q']['right'] for p in before],[p['generalized_q']['right'] for p in after],0.,1e-12)
    zguard=resolved_match([p['links']['right_wheel']['engine_derived_collision_pose']['position_world_m'][2] for p in before],
       [p['links']['right_wheel']['engine_derived_collision_pose']['position_world_m'][2] for p in after],HEIGHT_REFERENCE_M if spec['iterations'] else 0.,1e-10)
    component_deltas={}
    for key in ENTITIES:
        a=first['hierarchy'][key];b=last['hierarchy'][key]
        if a['entity_id']!=b['entity_id']:raise g.InvalidCapture('hierarchy entity identity changed')
        component_deltas[key]={field:{'S0':a[field],'S1':b[field],'value_changed':a[field]['value']!=b[field]['value']} for field in ('Pose','WorldPose','ParentEntity')}
    rec0=reconstruct_hierarchy(first['hierarchy']);rec1=reconstruct_hierarchy(last['hierarchy'])
    all_reconstructed=all(x['all_reconstructed_match'] for x in localizations)
    mechanism={'ECM_body_held':same_pose(first['hierarchy']['body']['reconstructed_world_pose'],last['hierarchy']['body']['reconstructed_world_pose']),
      'ECM_RIGHT_updated':not same_pose(first['hierarchy']['right_wheel']['reconstructed_world_pose'],last['hierarchy']['right_wheel']['reconstructed_world_pose']),
      'engine_body_updated':not same_pose(first['links']['body']['engine_derived_collision_pose'],last['links']['body']['engine_derived_collision_pose']),
      'local_components_changed':[key+'.'+field for key in ENTITIES for field in ('Pose','ParentEntity') if component_deltas[key][field]['value_changed']],
      'local_components_held':[key+'.Pose' for key in ENTITIES if not component_deltas[key]['Pose']['value_changed']],
      'all_callback_parent_local_reconstructions_match':all_reconstructed,
      'limits':'Observed component propagation only; no undocumented engine/solver/cache internals inferred. Change flags are retained as evidence, not producer times.'}
    # Locate the first observed stage with held body and updated RIGHT in the one step.
    mechanism['first_observed_mixed_stage']=None
    for point in timeline:
        h=point['hierarchy']
        body_held=same_pose(h['body']['reconstructed_world_pose'],first['hierarchy']['body']['reconstructed_world_pose'])
        right_new=not same_pose(h['right_wheel']['reconstructed_world_pose'],first['hierarchy']['right_wheel']['reconstructed_world_pose'])
        if body_held and right_new:
            mechanism['first_observed_mixed_stage']={k:point[k] for k in ('stage','callback_sequence','iteration','sim_time_ns','paused')};break
    mixed=spec['iterations']==1 and all(row['matches'] for row in comparisons.values()) and qguard['matches'] and mechanism['ECM_body_held'] and mechanism['ECM_RIGHT_updated'] and mechanism['engine_body_updated']
    if not spec['iterations']:
        zero_unchanged=base['classification']=='ZERO_CONTROL_UNCHANGED_OBSERVED' and all(not field['value_changed'] for row in component_deltas.values() for field in row.values())
        classification='ZERO_TICK_FRESHNESS_CONTROL_UNCHANGED' if zero_unchanged else 'ECM_HIERARCHY_FRESHNESS_NOT_REPRODUCED'
    elif mixed:classification='ECM_MIXED_HIERARCHY_FRESHNESS_REPRODUCED' if all_reconstructed and mechanism['local_components_changed'] else 'ECM_HIERARCHY_FRESHNESS_PARTIALLY_LOCALIZED'
    else:classification='ECM_HIERARCHY_FRESHNESS_NOT_REPRODUCED'
    # Discard predecessor correspondence targets: AN-P treats q only as a zero-change guard.
    base['measurements']={'RIGHT_actual_q_zero_guard':qguard,'RIGHT_Z_guard':zguard,'matrix':comparisons,
      'LEFT_actual_q_zero_guard':resolved_match([p['generalized_q']['left'] for p in before],[p['generalized_q']['left'] for p in after],0.,1e-12)}
    base.update({'phase':'AN-P','classification':classification,'flags':[],'reconstruction_matrix':comparisons,
      'hierarchy_component_deltas':component_deltas,'hierarchy_S0_reconstruction':rec0,'hierarchy_S1_reconstruction':rec1,
      'callback_timeline':timeline,'component_localization':mechanism,'actual_q_guard':qguard,'RIGHT_Z_guard':zguard,
      'limited_contact_scope':'Inherited S0/S1 topology, Fn/depth/wrench and contact producer semantics only; no physical branch or causal contact analysis',
      'causal_interpretation':'NONE. Legacy marker is not a causal candidate; this closes observation semantics only.'})
    return base


def baseline_equivalence(results):
    baseline=legacy.baseline_equivalence(results);valid=[r for r in results if r['capture_valid']]
    def signature(r):
        h=r['S0'][-1]['hierarchy'];names={v['entity_id']:key for key,v in h.items()}
        return legacy.flatten_all({key:{'Pose':v['Pose']['value'],'WorldPose':v['WorldPose']['value'],
          'parent':names.get(v['graph_parent_entity'],'WORLD_ROOT' if not v['graph_parent_entity'] else 'UNOBSERVED_PARENT')} for key,v in h.items()})
    checks=[]
    for i,left in enumerate(valid):
        for right in valid[i+1:]:
            a=signature(left);b=signature(right);bad=[]
            for key in a.keys()|b.keys():
                x=a.get(key);y=b.get(key)
                if type(x) in (int,float) and type(y) in (int,float):same=abs(x-y)<=1e-12
                else:same=key in a and key in b and x==y
                if not same:bad.append({'component':key,'left':x,'right':y})
            checks.append({'left':left['case_id'],'right':right['case_id'],'pass':not bad,'differences':bad})
    baseline['hierarchy_baseline_pairs']=checks
    if baseline['status']=='BASELINE_STATE_UNSTABLE' or any(not x['pass'] for x in checks):baseline['status']='BASELINE_UNSTABLE'
    return baseline


def aggregate(results):
    baseline=baseline_equivalence(results);valid=[r for r in results if r['capture_valid']]
    zeros=[r for r in valid if r['arm']==ZERO];ones=[r for r in valid if r['arm']==ONE]
    complete=len(results)==6 and len(valid)==6
    zero_ok=len(zeros)==3 and all(r['classification']=='ZERO_TICK_FRESHNESS_CONTROL_UNCHANGED' for r in zeros)
    mixed_ok=len(ones)==3 and all(r['classification']=='ECM_MIXED_HIERARCHY_FRESHNESS_REPRODUCED' for r in ones)
    if baseline['status']=='BASELINE_UNSTABLE':classification='BASELINE_UNSTABLE'
    elif complete and zero_ok and mixed_ok:classification='ECM_MARKER_ARTIFACT_CLOSED'
    elif any(r['classification'] in ('ECM_MIXED_HIERARCHY_FRESHNESS_REPRODUCED','ECM_HIERARCHY_FRESHNESS_PARTIALLY_LOCALIZED') for r in ones):classification='ECM_HIERARCHY_FRESHNESS_PARTIALLY_LOCALIZED'
    else:classification='ECM_HIERARCHY_FRESHNESS_NOT_REPRODUCED'
    return {'phase':'AN-P','status':'QUALIFICATION_CAPTURE_COMPLETE' if complete else 'CAPTURE_FAILED',
      'classification':classification,'baseline_equivalence':baseline,'results':results,
      'inventory':{arm:{'valid':sum(r['arm']==arm and r['capture_valid'] for r in results),'invalid':sum(r['arm']==arm and not r['capture_valid'] for r in results)} for arm in (ZERO,ONE)},
      'causal_runtime_ready':False,'Action24_outcomes_tested':False,
      'marker_closure_scope':'Observation-layer mixed-freshness marker for this transition only; Action24 mechanism unresolved.',
      'next_phase_boundary':protocol()['next_phase_boundary'],'next_physical_experiment_implemented':False}



def static_contract():
    source=SOURCE.read_text();runtime='\n'.join(inspect.getsource(f) for f in (hierarchy_hook,read_packet,capture,instrument))
    for token in ('.ResetPosition(', 'JointPositionReset','SetPosition(', 'SetVelocity(', 'SetForce(', 'SetChanged(', 'SetParentEntity(', 'msgs::Twist','multi_step','step_simulation'):
        if token in source:raise ValueError('mutating observer source token: '+token)
    for token in ('joint.Position(ecm)','EnablePositionCheck(ecm)','ComponentState(e,type)','components::ParentEntity','ISystemUpdate','Trace("PreUpdate"','Trace("PostUpdate/const_ECM"'):
        if token not in source:raise ValueError('required observer API missing: '+token)
    for token in ('_refresh(', 'publish(', 'set_pose', 'ResetPosition('):
        if token in runtime:raise ValueError('forbidden AN-P runner path: '+token)
    tree=__import__('ast').parse(Path(__file__).read_text())
    for call in __import__('ast').walk(tree):
        if isinstance(call,__import__('ast').Call) and isinstance(call.func,__import__('ast').Attribute):
            if call.func.attr in ('run','preflight','main') and isinstance(call.func.value,__import__('ast').Name) and call.func.value.id in ('g','q','legacy','d'):
                raise ValueError('predecessor experiment entry point forbidden')
    if len(schedule())!=6 or [s['arm'] for s in schedule()]!=[ZERO,ONE,ONE,ZERO,ZERO,ONE]:raise ValueError('AN-P six-case order differs')
    if not all(s['iterations']==int(s['arm']==ONE) and s['sim_time_delta_ns']==s['iterations']*1000000 for s in schedule()):raise ValueError('dose contract differs')
    if 'd.single_advance(adapter,1)' not in inspect.getsource(hierarchy_hook):raise ValueError('single advancing request path missing')
    return {'phase':'AN-P','read_only_source':True,'no_predecessor_runner_entrypoint':True,
      'capture_dependency':'accepted canonical stopped-boundary capture library only; no AN-G run/preflight invocation',
      'actual_q_producer':'same proven Joint::Position readback','all_runtime_assertions':'HOST_REQUIRED',
      'component_change_flags':'public ECM ComponentState, not producer timestamps','intentional_abort_before_UP':True,
      'contact_scope':'read-only endpoints and provenance only','no_physics_parameter_edits':True}


def safety(output):
    q.safety(output);d.process_safety()
    roots=(q.HOST1,q.DEFAULT_OUTPUT,legacy.DEFAULT_OUTPUT,Path(output));partitions=set()
    for root in roots:
        for path in root.glob('*/process_lifecycle.json'):
            for event in json.loads(path.read_text()).get('events',[]):
                part=event.get('partition') or event.get('status',{}).get('partition')
                if part:partitions.add(part)
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit() or int(proc.name)==os.getpid():continue
        try:
            cmd=(proc/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace')
            try:env=(proc/'environ').read_bytes().split(b'\0')
            except PermissionError:env=[]
        except (FileNotFoundError,ProcessLookupError,PermissionError):continue
        if any(('GZ_PARTITION='+part).encode() in env for part in partitions) or (any(str(root) in cmd for root in roots) and 'world_joint_state_diagnostic.sdf' in cmd):
            raise g.InvalidCapture('prior diagnostic process still active; no unrelated process killed')
    return {'prior_diagnostic_process_check':'PASS','processes_killed':False}


def preflight(output=DEFAULT_OUTPUT):
    output=Path(output).resolve()
    if output!=DEFAULT_OUTPUT.resolve():raise ValueError('only fresh AN-P Host1 output allowed')
    if output.exists() and any(p.name not in STATIC for p in output.iterdir()):raise FileExistsError('runtime block already exists; never resume or overwrite')
    guard=guard_manifest();contract=static_contract();codec=q.codec_self_check();safety(output)
    output.mkdir(parents=True,exist_ok=True);frozen=output/'protocol.json'
    # JSON normalizes tuples, so compare canonical JSON rather than Python tuple/list identity.
    if frozen.exists() and json.loads(frozen.read_text())!=json.loads(json.dumps(protocol())):raise ValueError('frozen protocol changed')
    write(frozen,protocol());scenario,seed,_=g.history.source(g.ab.DEFAULT_ARTIFACT)
    libraries,builds=g.ab._build_all(output/'builds');g.verify_static_builds(builds)
    library,built=build(output/'builds/hierarchy_observer');definitions=[];production_hashes=[]
    for spec in schedule():
        directory=output/'preflight_sdfs'/spec['case_id']
        prod=g.ab.GazeboWorldGenerator().generate(scenario,directory/'world',closed_loop=True,control_mode='PHYSICS')
        digest=g.sha(prod);production_hashes.append(digest)
        tree=ET.parse(prod);model=tree.find("world/model[@name='simple_agent']");joint=model.find("joint[@name='right_joint']")
        if digest!=g.EXPECTED_SHA:raise ValueError('production SHA changed')
        if joint.get('type')!='revolute' or joint.findtext('parent')!='body' or joint.findtext('child')!='right_wheel' or joint.findtext('axis/xyz')!='0 1 0':raise ValueError('joint identity/axis changed')
        for link,name in [('body','body_collision'),('left_wheel','left_collision'),('right_wheel','right_collision')]:
            col=model.find(f"link[@name='{link}']/collision[@name='{name}']")
            if col is None or col.find('pose') is not None:raise ValueError('engine collision pose requires identity offset')
        diag,info=g.ab._instrument_world(prod,directory,libraries,topic_identity='AN-P/'+spec['case_id']+'/'+uuid4().hex)
        diag,info=instrument(diag,info,library,spec['case_id'],directory)
        diag,info=g.checkpoints.instrument(diag,info);diag,info=g.instrument_audit(diag,info)
        plugins=[p.get('name') for p in ET.parse(diag).findall('world/plugin')]
        plugin_nodes=ET.parse(diag).findall('world/plugin')
        physics=[i for i,p in enumerate(plugin_nodes) if p.get('name')=='gz::sim::systems::Physics']
        observer=[i for i,p in enumerate(plugin_nodes) if p.get('name')=='aero_diagnostic::EcmHierarchyFreshnessObserver']
        if len(physics)!=1 or len(observer)!=1 or physics[0]>=observer[0]:raise ValueError('Physics/observer Update order not established')
        if any('system_priority' in child.tag for p in plugin_nodes for child in p):raise ValueError('nondefault system priority requires separate ordering qualification')

        if 'aero_diagnostic::PhaseIsolationQualification' in plugins:raise ValueError('setter plugin present')
        if plugins.count('aero_diagnostic::EcmHierarchyFreshnessObserver')!=1:raise ValueError('observer missing/duplicate')
        definitions.append({'spec':spec,'sdf':str(diag),'sdf_sha256':g.sha(diag),'identity':info['hierarchy_observer']})
    g.production_sensor_order_contract();g.history.verify_manifest(guard)
    if list(output.rglob('*.ndjson')):raise ValueError('runtime evidence created before Host')
    pf={'status':'PREFLIGHT_PASS','gates':{gate:True for gate in GATES},'contract':contract,'codec':codec,
      'protocol_sha256':g.sha(frozen),'runner_sha256':g.sha(__file__),'library':str(library),'observer_build':built,
      'standard_observer_builds':builds,'definitions':definitions,'guard_manifest':guard,
      'production_sha_before':production_hashes[0],'production_sha_after':production_hashes[-1],
      'production_changed':False,'gazebo_executed':False,'Host_executed':False,'runtime_facts':'HOST_REQUIRED','phase':'AN-P',
      'no_Action24_efficacy_testing':True,'seed':seed}
    write(output/'hierarchy_preflight.json',pf);return pf


def validate_ledger(ledger):
    if [s['spec'] for s in ledger['slots']]!=schedule():raise ValueError('prospective schedule differs')
    for slot in ledger['slots']:
        state=slot['state']
        if state not in ('SCHEDULED','STARTED','FINALIZED'):raise ValueError('unknown ledger state')
        if state=='FINALIZED':
            result=slot.get('result',{})
            if type(result.get('capture_valid')) is not bool or result.get('classification') not in CLASSES:raise ValueError('incomplete finalized result')
            required=('case_id','arm','measurements','S0','S1','command_audit','delta_iterations','delta_sim_time_ns') if result['capture_valid'] else ('case_id','arm','invalid_reason','traceback')
            if any(key not in result for key in required):raise ValueError('incomplete finalized result')
            if result['case_id']!=slot['spec']['case_id'] or result['arm']!=slot['spec']['arm']:raise ValueError('final result belongs to another slot')
        elif 'result' in slot:raise ValueError('future/unfinalized case cannot have a final result')
    return ledger


def persist_ledger(output,ledger):write(output/'hierarchy_case_ledger.json',validate_ledger(ledger))


def run(output=DEFAULT_OUTPUT):
    output=Path(output).resolve()
    if output!=DEFAULT_OUTPUT.resolve() or any(p.name not in STATIC for p in output.iterdir()):raise FileExistsError('prospective block cannot resume or overwrite')
    pf=json.loads((output/'hierarchy_preflight.json').read_text())
    if pf['status']!='PREFLIGHT_PASS' or pf['runner_sha256']!=g.sha(__file__) or pf['protocol_sha256']!=g.sha(output/'protocol.json'):raise g.InvalidCapture('static preflight mismatch')
    g.history.verify_manifest(pf['guard_manifest']);safety(output);q.codec_self_check()
    library=Path(pf['library'])
    if g.sha(library)!=pf['observer_build']['library_sha256']:raise g.InvalidCapture('observer library changed')
    scenario,seed,_=g.history.source(g.ab.DEFAULT_ARTIFACT)
    libraries,builds=g.ab._build_all(output/'builds');g.verify_static_builds(builds)
    ledger={'protocol_sha256':pf['protocol_sha256'],'slots':[{'spec':s,'state':'SCHEDULED'} for s in schedule()]}
    persist_ledger(output,ledger);print('CURRENT_PHASE_IS_AN_P',flush=True);print('PROSPECTIVE_CASE_ORDER_FROZEN',flush=True)
    previous_shutdown=True;previous_close=None;partitions=set();topics=set()
    for slot in ledger['slots']:
        spec=slot['spec'];directory=output/spec['case_id']
        if not previous_shutdown:
            slot['not_started_reason']='prior shutdown unproven; scheduled slot retained';persist_ledger(output,ledger);continue
        safety(output);directory.mkdir(parents=True);slot.update(state='STARTED',wall_start=time.monotonic());persist_ledger(output,ledger)
        try:
            record=capture(spec['case_id'],scenario,directory,libraries,seed,uuid4().hex,library)
            life=json.loads((directory/'process_lifecycle.json').read_text())
            previous_shutdown=life['shutdown_proven'] and record.get('shutdown_completed') is True
            launches=[e for e in life['events'] if e['event']=='launch'];closes=[e for e in life['events'] if e['event']=='close']
            if not previous_shutdown or not life['fresh_single_server']:raise g.InvalidCapture('fresh process/shutdown unproven')
            if previous_close is not None and launches[0]['wall_monotonic_s']<previous_close:raise g.InvalidCapture('server overlap')
            previous_close=max(e['wall_monotonic_s'] for e in closes)
            identity=record['runtime_identity']
            if identity['partition'] in partitions or identity['topic'] in topics:raise g.InvalidCapture('transport identity reused')
            partitions.add(identity['partition']);topics.add(identity['topic'])
            result=analyze(record,spec);write(directory/'hierarchy_analysis.json',result)
            slot.update(state='FINALIZED',result=result,runtime_identity=identity,lifecycle=life)
        except Exception as exc:
            life_path=directory/'process_lifecycle.json';life=json.loads(life_path.read_text()) if life_path.exists() else {}
            previous_shutdown=life.get('shutdown_proven') is True
            slot.update(state='FINALIZED',result={'case_id':spec['case_id'],'arm':spec['arm'],'capture_valid':False,
              'classification':'CAPTURE_INVALID','invalid_reason':type(exc).__name__+': '+str(exc),'traceback':traceback.format_exc()},lifecycle=life)
        persist_ledger(output,ledger);print(spec['case_id']+': '+slot['result']['classification'],flush=True);gc.collect()
    g.history.verify_manifest(pf['guard_manifest'])
    results=[s['result'] for s in ledger['slots'] if 'result' in s];result=aggregate(results)
    result['original_slots']=ledger['slots'];result['production_sha_before']=pf['production_sha_before'];result['production_sha_after']=pf['production_sha_after']
    write(output/'ecm_hierarchy_freshness_qualification.json',result);return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);choice=parser.add_mutually_exclusive_group(required=True)
    choice.add_argument('--preflight-only',action='store_true');choice.add_argument('--host-run',action='store_true')
    args=parser.parse_args(argv)
    try:
        if args.preflight_only:
            result=preflight()
            for gate in GATES:print(gate)
            print(result['status']);print('HOST_EXECUTION_REQUIRED');return 0
        result=run();print(result['status']);print(result['classification']);print('CAUSAL_RUNTIME_NOT_READY')
        return 0 if result['status']=='QUALIFICATION_CAPTURE_COMPLETE' else 1
    except Exception as exc:
        print('CAPTURE_FAILED: '+type(exc).__name__+': '+str(exc));return 1


if __name__=='__main__':raise SystemExit(main())
