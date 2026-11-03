#!/usr/bin/env python3
"""AN-N natural correspondence only. Static mode builds observers; never launches a server."""
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
from tools import diagnose_v07_gazebo_phase_isolation_qualification as q

d=q.d;g=q.g;ROOT=q.ROOT
DELTA=-4.868844349914525e-8
HEIGHT_REFERENCE_M=2.940583122834628e-8
ZERO='ZERO_TICK_NATURAL';ONE='ONE_TICK_NATURAL'
DEFAULT_OUTPUT=ROOT/'validation/v071-host/gazebo-action24-natural-q-phase-correspondence-phase3hann-host1'
SOURCE=ROOT/'tools/gazebo_natural_q_phase_observer.cc'
# The proven capture harness checks this exact intentional exception before UP.
STOP=q.STOP
STATIC={'protocol.json','natural_preflight.json','builds','preflight_sdfs'}
GATES=('DIAGNOSTIC_OBSERVER_BUILDS','ACTUAL_Q_READBACK_REUSED_FROM_HOST2','NO_RESETPOSITION_PATH',
 'ZERO_ONE_SCHEDULE_FROZEN','ZERO_ADVANCEMENT_CONTRACT','ONE_EXACT_1MS_CONTRACT','NO_TWIST_TREATMENT',
 'NO_POSE_RPC','NO_WORLDPOSECMD','NO_PRODUCTION_SENSOR_REFRESH','THREE_REPRESENTATIONS_SEPARATED',
 'WHEEL_HEIGHT_CAPTURED','CONTACT_PROVENANCE_DEFINED','BASELINE_EQUIVALENCE_DEFINED','FRESH_PROCESS_PER_CASE',
 'NO_AUTOMATIC_RERUN','PRODUCTION_SHA_UNCHANGED')
CLASSES=('NATURAL_Q_PHASE_CORRESPONDENCE_CONFIRMED','NATURAL_Q_ENGINE_PHASE_ONLY_CONFIRMED',
 'LEGACY_MARKER_FILTERED_OR_STALE','NATURAL_Q_PHASE_CORRESPONDENCE_NOT_REPRODUCED',
 'BASELINE_STATE_UNSTABLE','CAPTURE_INVALID','ZERO_CONTROL_UNCHANGED_OBSERVED')


def schedule():
    return [{'ordinal':len_before+j+1,'case_id':f'{arm}_R{r}','arm':arm,'replicate':f'R{r}',
             'iterations':int(arm==ONE),'sim_time_delta_ns':1_000_000*int(arm==ONE)}
            for r in range(1,6) for len_before in [(r-1)*2]
            for j,arm in enumerate((ZERO,ONE) if r%2 else (ONE,ZERO))]


def protocol():
    return {'experiment':'NATURAL_ONE_TICK_GENERALIZED_Q_PHASE_CORRESPONDENCE_QUALIFICATION',
      'schedule_status':'PROSPECTIVE_CASE_ORDER_FROZEN','schedule':schedule(),
      'candidate_RIGHT_phase_delta_rad':DELTA,'candidate_RIGHT_height_delta_m':HEIGHT_REFERENCE_M,
      'classifications':CLASSES,'causal_efficacy_testing':False,'automatic_reruns':False,
      'representations':{'ACTUAL_GENERALIZED_Q':'Joint::Position; Physics GetPosition producer; EnablePositionCheck at startup',
        'ENGINE_DERIVED_WHEEL_ORIENTATION':'identity-offset collision WorldPose from Physics, relative to body collision; body-Y spin with Rx(pi/2) mount removed',
        'LEGACY_ECM_DERIVED_PHASE_MARKER':'same equation applied to link world pose; filtered/stale possible'},
      'observation_requests':[0,0,0,1,0,0,0],
      'protocol_order':'canonical Actions08-23, BRAKE_LINEAR stopped, S0x3, arm observer, optional single 1ms step, matched nonadvancing pause, S1x3, intentional abort before UP',
      'synchronization':'Both arms issue exactly one pause:true RPC without multi_step; it is not an advancement or robot command. ZERO issues zero advancing requests.',
      'contact_semantics':{'paused':'LAST_ADVANCING_STEP_STATE; numeric equality is not current contact isolation',
        'advancing_observation':'Snapshot in the one advancing PostUpdate; Physics has executed; ECM contact/wrench components can still be filtered/held. Producer timestamp retained; fresh only if independently time-matched.',
        'tangential_relative_velocity':'UNAVAILABLE: no direct current contact-point relative velocity API implemented'},
      'measurement_policy':{'serialization':'17 significant decimal digits; binary64 parse, no rounding before subtraction',
        'correspondence_max_error_rad':1e-11,'zero_q_phase_max_delta_rad':1e-12,
        'resolution_rule':'128 ulps plus observed same-time repeatability must be <= one tenth of requested comparison bound; otherwise MEASUREMENT_RESOLUTION_INSUFFICIENT',
        'baseline_caps':{'angle_rad':1e-11,'position_m':1e-10,'linear_velocity_m_s':1e-10,
          'angular_velocity_rad_s':1e-10,'wheel_velocity_rad_s':1e-10,'force_N':1e-8,'depth_m':1e-10,'torque_N_m':1e-9},
        'baseline_rule':'all pairwise valid S0 observed vectors; exact categorical/command/clock agreement; no unstable case hidden in an average; held contact comparisons are observational only'},
      'runtime_facts':'HOST_REQUIRED: natural q/phase/height correspondence, baseline repeatability, exact clocks, lifecycle and command audits',
      'production_sha256':g.EXPECTED_SHA}


def write(path,value):
    path=Path(path).resolve()
    if not path.is_relative_to(DEFAULT_OUTPUT.resolve()):raise ValueError('write outside new AN-N evidence directory refused')
    d.ledger_io.atomic_json(path,value)


def guard_manifest():
    guard=q.guard_manifest()
    for p in q.DEFAULT_OUTPUT.rglob('*'):
        if p.is_file():guard[str(p.resolve())]=g.sha(p)
    for p in (SOURCE,Path(__file__),ROOT/'tests/test_gazebo_natural_q_phase_correspondence.py'):
        if p.exists():guard[str(p.resolve())]=g.sha(p)
    return guard


def build(directory):
    directory.mkdir(parents=True,exist_ok=True);library=(directory/'libaero_natural_q_phase.so').resolve()
    flags=subprocess.run(['pkg-config','--cflags','--libs','gz-sim8','gz-plugin2','gz-transport13'],capture_output=True,text=True,check=True)
    command=['c++','-std=c++17','-shared','-fPIC','-Wl,-z,defs',str(SOURCE),'-o',str(library),*shlex.split(flags.stdout)]
    result=subprocess.run(command,capture_output=True,text=True)
    if result.returncode:raise RuntimeError(result.stderr)
    deps=subprocess.run(['ldd','-r',str(library)],capture_output=True,text=True,check=True)
    if 'not found' in deps.stdout or 'undefined symbol' in deps.stdout:raise RuntimeError(deps.stdout)
    return library,{'command':command,'dependency_check':deps.stdout,'source_sha256':g.sha(SOURCE),'library_sha256':g.sha(library)}


def instrument(path,info,library,case,directory):
    tree=ET.parse(path);topic=info['native']['topic']+'/natural_q_phase'
    plugin=ET.SubElement(tree.find('world'),'plugin',filename=str(library),name='aero_diagnostic::NaturalQPhaseObserver')
    for key,val in {'topic':topic,'service':topic+'/request','output':str(directory/'natural_q_phase.ndjson')}.items():
        ET.SubElement(plugin,key).text=str(val)
    tree.write(path,encoding='utf-8',xml_declaration=True)
    info['natural_observer']={'topic':topic,'service':topic+'/request','case':case,'read_only':True}
    info['diagnostic_sdf_sha256']=g.sha(path)
    return path,info


def decorate(packet):
    q.decorate_packet(packet)
    packet['representations']={
      'ACTUAL_GENERALIZED_Q':{'value':packet['generalized_q'],'provenance':q.LABELS['generalized_q']},
      'ENGINE_DERIVED_WHEEL_ORIENTATION':{'value':packet['engine_derived_collision_pose_derived_phase'],'provenance':q.LABELS['engine_derived_collision_pose']},
      'LEGACY_ECM_DERIVED_PHASE_MARKER':{'value':packet['ECM_pose_derived_phase'],'provenance':q.LABELS['ECM_pose']}}
    packet['contact_freshness']={'observation_iteration':packet['iteration'],'observation_sim_time_ns':packet['sim_time_ns'],
      'callback_is_advancing':not packet['paused'],'supports':{},
      'joint_wrench':'CURRENT_ADVANCING_CALLBACK_COMPONENT_FILTERING_POSSIBLE' if not packet['paused'] else 'LAST_ADVANCING_STEP_STATE_OR_HELD_REACTION',
      'note':'Callback execution alone does not prove each component was updated. Producer stamp must match this solve to label a contact freshly recomputed.'}
    for name,s in packet['supports'].items():
        stamp=s.get('component_producer_stamp_ns')
        # Use the exact producer field exposed by the helper, if present. Never substitute callback time.
        packet['contact_freshness']['supports'][name]={'producer_sim_time_ns':stamp,
          'status':'TIME_MATCHED_ADVANCING_STEP_COMPONENT' if not packet['paused'] and stamp==packet['sim_time_ns'] else 'LAST_ADVANCING_STEP_STATE_OR_FILTERED_COMPONENT'}
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


def natural_hook(case_id,evidence,library):
    spec=next(s for s in schedule() if s['case_id']==case_id)
    def hook(adapter,case,native,row,it,audit):
        if case!=case_id or evidence:raise g.InvalidCapture('unexpected/repeated natural boundary')
        g.y.stopped_chunk(row);completed=g.y.completed_brake_checkpoint(adapter,row)
        marker=g.dm.physics_mark(adapter);bi,bns=d.exact_stats(marker)
        audit['phase']='treatment';audit['adapter']=adapter
        evidence.update(spec=spec,completed_brake=completed,stopped_chunk=copy.deepcopy(row),PRE_marker=marker,
          window_start=len(audit['events']),host_PRE=q.boundary_state(adapter))
        evidence['host_PRE']['prohibited_transport_cursors']=q.prohibited_cursors(audit)
        packets=[];automatic=[];topic=native.topic+'/natural_q_phase';transport=adapter.env.transport
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
    q.qualification_hook,q.instrument=natural_hook,instrument
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
        if event.get('request_type')=='Int32' and event.get('service','').endswith('/natural_q_phase/request'):reads.append(event)
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


def analyze(record,spec):
    e=record['phase_qualification'];packets=e.get('packets',[])
    if not e.get('qualification_completed') or len(packets)!=7:raise g.InvalidCapture('natural observation incomplete: '+str(e.get('qualification_error')))
    if [p['request_id'] for p in packets]!=list(range(1,8)) or [p['operation_code'] for p in packets]!=[0,0,0,1,0,0,0]:
        raise g.InvalidCapture('read-only request sequence mismatch')
    if any(p['error'] or not p['paused'] for p in packets):raise g.InvalidCapture('paused readback error')
    bi,bns=d.exact_stats(e['PRE_marker']);ai,ans=d.exact_stats(e['POST_marker'])
    if (ai-bi,ans-bns)!=(spec['iterations'],spec['sim_time_delta_ns']):raise g.InvalidCapture('exact WorldStatistics tick/time mismatch')
    if d.exact_stats(e['before_optional_tick_stats'])!=(bi,bns):raise g.InvalidCapture('S0 stats not coherent')
    for p in packets[:4]:
        if (p['iteration'],p['sim_time_ns'])!=(bi,bns):raise g.InvalidCapture('S0 callback clock mismatch')
    for p in packets[4:]:
        if (p['iteration'],p['sim_time_ns'])!=(ai,ans):raise g.InvalidCapture('S1 callback clock mismatch')
    if any(b['postupdate_count']<=a['postupdate_count'] for a,b in zip(packets,packets[1:])):raise g.InvalidCapture('callback acknowledgements unordered')
    if packets[-1]['advancing_callback_count']-packets[0]['advancing_callback_count']!=spec['iterations']:
        raise g.InvalidCapture('advancing callback audit differs from exact dose')
    automatic=e['advancing_observations']
    if len(automatic)!=spec['iterations'] or any(p['paused'] or p['iteration']!=ai or p['sim_time_ns']!=ans for p in automatic):
        raise g.InvalidCapture('advancing solve snapshot absent/duplicated/incoherent')
    if any(p['WorldPoseCmd_active'] or p['WorldPoseCmd_active_PRE'] or p['WorldPoseCmd_observations']!=packets[0]['WorldPoseCmd_observations'] for p in packets+automatic):
        raise g.InvalidCapture('pose component contamination')
    g.y.stopped_chunk(e['stopped_chunk'])
    if e['completed_brake']['active_physics_transactions']!=0 or round(e['stopped_chunk']['simulation_end']*1e9)!=bns:
        raise g.InvalidCapture('stopped boundary incoherent')
    history=[x for x in record['events'] if x.get('canonical_index') in range(8,24)]
    if [x['canonical_index'] for x in history]!=list(range(8,24)) or any(x.get('exception') or x.get('terminated') for x in history):raise g.InvalidCapture('canonical Actions08-23 incomplete')
    entry=record['terminal_entry_history'];plan=entry['production_plan']
    if plan['request']['previous_command']!=g.dm.gazebo_physics_twist('down') or plan['request']['transition_type']!='LINEAR_REVERSAL' or [p['kind'] for p in plan['phases']]!=['BRAKE_LINEAR','ACQUIRE_LINEAR']:
        raise g.InvalidCapture('DOWN/reversal production plan changed')
    if STOP not in json.dumps(record['events'][-1].get('exception')):raise g.InvalidCapture('pre-UP abort not corroborated')
    logical=e['host_PRE']['logical']
    if logical.get('env_previous_action')!='down' or logical.get('adapter_previous_action')!='down' or logical.get('controller_command')!={'linear':{'x':0.},'angular':{'z':0.}}:
        raise g.InvalidCapture('stopped DOWN logical/command boundary changed')
    audit=command_audit(record,e)
    before=packets[:3];after=packets[4:];measurements={};expected=DELTA if spec['iterations'] else 0.
    cap=1e-11 if spec['iterations'] else 1e-12
    for side in ('left','right'):
        measurements['actual_q.'+side]=resolved_match([p['generalized_q'][side] for p in before],[p['generalized_q'][side] for p in after],expected if side=='right' else 0.,cap)
        for source in ('engine_derived_collision_pose','ECM_pose'):
            measurements[source+'.phase.'+side]=resolved_match([q.phases(p,source)[side] for p in before],
              [q.phases(p,source)[side] for p in after],expected if side=='right' else 0.,cap,True)
            measurements[source+'.Z.'+side]=resolved_match([p['links'][side+'_wheel'][source]['position_world_m'][2] for p in before],
              [p['links'][side+'_wheel'][source]['position_world_m'][2] for p in after],HEIGHT_REFERENCE_M if side=='right' and spec['iterations'] else 0.,1e-10)
    qr=measurements['actual_q.right'];engine=measurements['engine_derived_collision_pose.phase.right'];legacy=measurements['ECM_pose.phase.right']
    for name in ('engine_derived_collision_pose','ECM_pose'):
        measurements[name+'.ratio_to_q']=measurements[name+'.phase.right']['delta']/qr['delta'] if abs(qr['delta'])>cap else None
        pre=q.phases(before[-1],name);post=q.phases(after[0],name)
        dl=q.wrap(post['left']-pre['left']);dr=q.wrap(post['right']-pre['right'])
        measurements[name+'.aliases']={'differential_delta':(dl-dr)/2,'common_delta':(dl+dr)/2,'raw_PRE':pre,'raw_POST':post}
    flags=[]
    if spec['iterations']==0:
        unchanged=all(v['matches'] for v in measurements.values() if isinstance(v,dict) and 'matches' in v)
        classification='NATURAL_Q_PHASE_CORRESPONDENCE_NOT_REPRODUCED' if not unchanged else 'ZERO_CONTROL_UNCHANGED_OBSERVED'
    elif qr['matches'] and engine['matches']:
        classification='NATURAL_Q_PHASE_CORRESPONDENCE_CONFIRMED' if legacy['matches'] else 'NATURAL_Q_ENGINE_PHASE_ONLY_CONFIRMED'
        if not legacy['matches']:
            flags.append('LEGACY_MARKER_FILTERED_OR_STALE' if abs(legacy['delta'])<=1e-12 else 'LEGACY_MARKER_DELTA_DIFFERS')
    else:classification='NATURAL_Q_PHASE_CORRESPONDENCE_NOT_REPRODUCED'
    if any(not v['resolution_sufficient'] for v in measurements.values() if isinstance(v,dict) and 'resolution_sufficient' in v):flags.append('MEASUREMENT_RESOLUTION_INSUFFICIENT')
    result={'case_id':spec['case_id'],'arm':spec['arm'],'capture_valid':True,'classification':classification,'flags':flags,
      'measurements':measurements,'S0':before,'S1':after,'advancing_observations':automatic,
      'baseline_command_state':e['host_PRE'],'baseline_plan':plan,'command_audit':audit,
      'raw_WorldStatistics':{'PRE':e['PRE_marker'],'POST':e['POST_marker'],'tick_PRE':e['before_optional_tick_stats'],
        'tick_POST_pause_sync':e['pause_synchronization']},'delta_iterations':ai-bi,'delta_sim_time_ns':ans-bns,
      'paused_callback_progress':packets[-1]['postupdate_count']-packets[0]['postupdate_count'],
      'causal_interpretation':'NONE: no acquisition/Action24 physical outcome tested; all natural microstate changes remain bundled'}
    if not spec['iterations']:
        post_result={**result,'S0':after,'baseline_command_state':e['host_POST']}
        pre_vector=baseline_vector(result);post_vector=baseline_vector(post_result)
        differences=[]
        for key in sorted(pre_vector.keys()|post_vector.keys()):
            a=pre_vector.get(key);b=post_vector.get(key)
            if type(a) in (int,float) and type(b) in (int,float):
                error=abs(q.wrap(b-a)) if 'phase' in key or 'yaw' in key else abs(b-a)
                same=math.isfinite(error) and error<=baseline_cap(key)
            else:same=key in pre_vector and key in post_vector and a==b
            if not same:differences.append({'channel':key,'PRE':a,'POST':b,'bound':baseline_cap(key)})
        result['zero_observer_state_audit']={'differences':differences,'observed_unchanged':not differences,
          'contact_limit':'Held evidence equality does not establish current contact state.'}
        if differences:result['classification']='NATURAL_Q_PHASE_CORRESPONDENCE_NOT_REPRODUCED'
    return result



def flatten_all(value,prefix=''):
    if isinstance(value,dict):return {key:v for k,x in value.items() for key,v in flatten_all(x,prefix+'.'+str(k) if prefix else str(k)).items()}
    if isinstance(value,list):return {key:v for k,x in enumerate(value) for key,v in flatten_all(x,prefix+'.'+str(k)).items()}
    return {prefix:value}


def baseline_vector(result):
    p=result['S0'][-1];cmd=result['baseline_command_state']
    vector={'generalized_q':p['generalized_q'],'clock':{'iteration':p['iteration'],'sim_time_ns':p['sim_time_ns']},
      'logical':cmd['logical'],'sensor':{k:v for k,v in cmd['production_sensor'].items() if k!='cached_observation_identity'},
      'active_physics_transactions':cmd['production_step_tracker']['active_depth'],'production_plan':result['baseline_plan']}
    for source in ('ECM_pose','engine_derived_collision_pose'):
        vector[source+'_phases']=q.phases(p,source)
    vector['links']={name:{k:v for k,v in link.items() if k not in ('link_entity','collision_entity')} for name,link in p['links'].items()}
    vector['supports']={name:{k:v for k,v in s.items() if k not in ('collision_entity_id','component_producer_stamp_ns','contacts','provenance')} for name,s in p['supports'].items()}
    # Preserve physical contact arrays, stripping only scoped entity IDs and producer metadata.
    for name,s in p['supports'].items():
        vector['supports'][name]['contact_depths_m']=[pt['depth_m'] for c in s['contacts'] if c['pair_classification']=='SUPPORT_GROUND' for pt in c['points']]
    vector['joint_wrench']={name:{k:v for k,v in j.items() if k!='entity_id'} for name,j in p['joint_wrench'].items()}
    return flatten_all(vector)


def baseline_cap(key):
    caps=protocol()['measurement_policy']['baseline_caps']
    if any(x in key for x in ('clock.','logical.','active_physics_transactions','production_plan.','sensor.sequence','sensor.previous_timestamp')):return 0.
    if 'depth' in key:return caps['depth_m']
    if 'force' in key or 'Fn_' in key:return caps['force_N']
    if 'torque' in key:return caps['torque_N_m']
    if 'actual_velocity_rad_s' in key:return caps['wheel_velocity_rad_s']
    if 'linear_velocity' in key:return caps['linear_velocity_m_s']
    if 'angular_velocity' in key:return caps['angular_velocity_rad_s']
    if 'position_world_m' in key or 'cached_production_pose' in key and key.rsplit('.',1)[-1] in ('x','y','z'):return caps['position_m']
    return caps['angle_rad']


def baseline_equivalence(results):
    valid=[r for r in results if r['capture_valid']];vectors={r['case_id']:baseline_vector(r) for r in valid};pairs=[]
    unstable=set()
    for i,left in enumerate(valid):
        for right in valid[i+1:]:
            a=vectors[left['case_id']];b=vectors[right['case_id']];bad=[]
            for key in sorted(a.keys()|b.keys()):
                x=a.get(key);y=b.get(key)
                if type(x) in (int,float) and type(y) in (int,float):
                    error=abs(q.wrap(y-x)) if 'phase' in key or 'yaw' in key else abs(y-x)
                    equal=math.isfinite(error) and error<=baseline_cap(key)
                else:equal=key in a and key in b and x==y
                if not equal:bad.append({'channel':key,'LEFT':x,'RIGHT':y,'cap':baseline_cap(key)})
            if bad:unstable.update((left['case_id'],right['case_id']))
            pairs.append({'left':left['case_id'],'right':right['case_id'],'pass':not bad,'differences':bad})
    return {'status':'BASELINE_STATE_UNSTABLE' if unstable else 'OBSERVED_BASELINE_EQUIVALENT' if len(valid)>1 else 'BASELINE_COMPARISON_INADEQUATE',
      'unstable_case_ids':sorted(unstable),'valid_cases_compared':len(valid),'all_pairs':pairs,
      'held_contact_warning':'This compares observed baseline evidence; it does not assert independently recomputed contacts.',
      'within_checkpoint_repeatability':'Recorded per measurement; unresolved representation channels cannot support strong correspondence.'}


def aggregate(results):
    baseline=baseline_equivalence(results);valid=[r for r in results if r['capture_valid']]
    zeros=[r for r in valid if r['arm']==ZERO];ones=[r for r in valid if r['arm']==ONE]
    complete=len(valid)==10
    zero_ok=len(zeros)==5 and all(r['classification']=='ZERO_CONTROL_UNCHANGED_OBSERVED' for r in zeros)
    if baseline['status']=='BASELINE_STATE_UNSTABLE':classification='BASELINE_STATE_UNSTABLE'
    elif complete and zero_ok and all(r['classification']=='NATURAL_Q_PHASE_CORRESPONDENCE_CONFIRMED' for r in ones):classification='NATURAL_Q_PHASE_CORRESPONDENCE_CONFIRMED'
    elif complete and zero_ok and all(r['classification'] in CLASSES[:2] for r in ones):classification='NATURAL_Q_ENGINE_PHASE_ONLY_CONFIRMED'
    else:classification='NATURAL_Q_PHASE_CORRESPONDENCE_NOT_REPRODUCED'
    return {'status':'QUALIFICATION_CAPTURE_COMPLETE' if len(results)==10 and complete else 'CAPTURE_FAILED',
      'classification':classification,'baseline_equivalence':baseline,'results':results,
      'inventory':{arm:{'valid':sum(r['arm']==arm and r['capture_valid'] for r in results),
        'invalid':sum(r['arm']==arm and not r['capture_valid'] for r in results)} for arm in (ZERO,ONE)},
      'incomplete_capture_limits_interpretation':not complete,'causal_runtime_ready':False,'Action24_outcomes_tested':False,
      'causal_limit':'Correspondence only: natural q, height, contact and unobserved physics state may change together. No q mediation conclusion.'}


def static_contract():
    source=SOURCE.read_text();runner='\n'.join(inspect.getsource(f) for f in (natural_hook,read_packet,capture,instrument))
    for token in ('.ResetPosition(', 'JointPositionReset','SetPosition(', 'SetVelocity(', 'SetForce(', 'msgs::Twist','multi_step','step_simulation'):
        if token in source:raise ValueError('mutating observer source token: '+token)
    if 'joint.Position(ecm)' not in source or 'EnablePositionCheck(ecm)' not in source:raise ValueError('proven q readback missing')
    for token in ('_refresh(', 'publish(', 'set_pose', 'ResetPosition('):
        if token in runner:raise ValueError('forbidden natural runner path: '+token)
    return {'read_only_source':True,'actual_q_producer':'same Joint::Position readback and EnablePositionCheck as accepted Host2',
      'all_runtime_assertions':'HOST_REQUIRED','intentional_abort_before_UP':True,'no_physics_parameter_edits':True}


def safety(output):
    q.safety(output);d.process_safety()
    roots=(q.HOST1,q.DEFAULT_OUTPUT,Path(output));partitions=set()
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
    if output!=DEFAULT_OUTPUT.resolve():raise ValueError('only fresh AN-N Host1 output allowed')
    if output.exists() and any(p.name not in STATIC for p in output.iterdir()):raise FileExistsError('runtime block already exists; never resume or overwrite')
    guard=guard_manifest();contract=static_contract();codec=q.codec_self_check();safety(output)
    output.mkdir(parents=True,exist_ok=True);frozen=output/'protocol.json'
    # JSON normalizes tuples, so compare canonical JSON rather than Python tuple/list identity.
    if frozen.exists() and json.loads(frozen.read_text())!=json.loads(json.dumps(protocol())):raise ValueError('frozen protocol changed')
    write(frozen,protocol());scenario,seed,_=g.history.source(g.ab.DEFAULT_ARTIFACT)
    libraries,builds=g.ab._build_all(output/'builds');g.verify_static_builds(builds)
    library,built=build(output/'builds/natural_observer');definitions=[];production_hashes=[]
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
        diag,info=g.ab._instrument_world(prod,directory,libraries,topic_identity='natural/'+spec['case_id']+'/'+uuid4().hex)
        diag,info=instrument(diag,info,library,spec['case_id'],directory)
        diag,info=g.checkpoints.instrument(diag,info);diag,info=g.instrument_audit(diag,info)
        plugins=[p.get('name') for p in ET.parse(diag).findall('world/plugin')]
        if 'aero_diagnostic::PhaseIsolationQualification' in plugins:raise ValueError('setter plugin present')
        if plugins.count('aero_diagnostic::NaturalQPhaseObserver')!=1:raise ValueError('observer missing/duplicate')
        definitions.append({'spec':spec,'sdf':str(diag),'sdf_sha256':g.sha(diag),'identity':info['natural_observer']})
    g.production_sensor_order_contract();g.history.verify_manifest(guard)
    if list(output.rglob('*.ndjson')):raise ValueError('runtime evidence created before Host')
    pf={'status':'PREFLIGHT_PASS','gates':{gate:True for gate in GATES},'contract':contract,'codec':codec,
      'protocol_sha256':g.sha(frozen),'runner_sha256':g.sha(__file__),'library':str(library),'observer_build':built,
      'standard_observer_builds':builds,'definitions':definitions,'guard_manifest':guard,
      'production_sha_before':production_hashes[0],'production_sha_after':production_hashes[-1],
      'production_changed':False,'gazebo_executed':False,'Host_executed':False,'runtime_facts':'HOST_REQUIRED',
      'no_Action24_efficacy_testing':True,'seed':seed}
    write(output/'natural_preflight.json',pf);return pf


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


def persist_ledger(output,ledger):write(output/'natural_case_ledger.json',validate_ledger(ledger))


def run(output=DEFAULT_OUTPUT):
    output=Path(output).resolve()
    if output!=DEFAULT_OUTPUT.resolve() or any(p.name not in STATIC for p in output.iterdir()):raise FileExistsError('prospective block cannot resume or overwrite')
    pf=json.loads((output/'natural_preflight.json').read_text())
    if pf['status']!='PREFLIGHT_PASS' or pf['runner_sha256']!=g.sha(__file__) or pf['protocol_sha256']!=g.sha(output/'protocol.json'):raise g.InvalidCapture('static preflight mismatch')
    g.history.verify_manifest(pf['guard_manifest']);safety(output);q.codec_self_check()
    library=Path(pf['library'])
    if g.sha(library)!=pf['observer_build']['library_sha256']:raise g.InvalidCapture('observer library changed')
    scenario,seed,_=g.history.source(g.ab.DEFAULT_ARTIFACT)
    libraries,builds=g.ab._build_all(output/'builds');g.verify_static_builds(builds)
    ledger={'protocol_sha256':pf['protocol_sha256'],'slots':[{'spec':s,'state':'SCHEDULED'} for s in schedule()]}
    persist_ledger(output,ledger);print('PROSPECTIVE_CASE_ORDER_FROZEN',flush=True)
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
            result=analyze(record,spec);write(directory/'natural_analysis.json',result)
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
    write(output/'natural_q_phase_correspondence.json',result);return result


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
