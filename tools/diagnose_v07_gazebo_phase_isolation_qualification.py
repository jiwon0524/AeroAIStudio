#!/usr/bin/env python3
"""AN-L diagnostic qualification only. --preflight-only never starts Gazebo."""
from __future__ import annotations
import argparse
import copy
import gc
import json
import math
import os
import re
import shlex
import subprocess
import time
import traceback
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4
from tools import diagnose_v07_gazebo_action24_tick_dose_response as d

g=d.g
ROOT=d.ROOT
DELTA=4.868844349914525e-8
ARMS=('SHAM','PLUS_DELTA','MINUS_DELTA')
HOST1=ROOT/'validation/v071-host/gazebo-action24-phase-isolation-qualification-phase3hanl-host1'
FORENSICS=ROOT/'validation/v071-host/gazebo-action24-phase-isolation-qualification-phase3hanl-host1-forensics'
DEFAULT_OUTPUT=ROOT/'validation/v071-host/gazebo-action24-phase-isolation-qualification-phase3hanl-host2'
SOURCE=ROOT/'tools/gazebo_phase_isolation_qualification.cc'
STOP='QUALIFICATION_COMPLETE_STOP_BEFORE_ACTION24_UP'
STATIC={'protocol.json','qualification_preflight.json','builds','preflight_sdfs'}
LABELS={'generalized_q':'ECM_CURRENT_STATE_FROM_PHYSICS_GETPOSITION',
 'engine_derived_collision_pose':'ENGINE_DERIVED_CURRENT_STATE_VIA_ECM_COLLISION_COMPONENT',
 'ECM_pose':'CACHED_OR_STALE_POSSIBLE','engine_derived_linear_velocity':'ENGINE_DERIVED_CURRENT_STATE_VIA_ECM_COLLISION_COMPONENT',
 'engine_derived_angular_velocity':'ENGINE_DERIVED_CURRENT_STATE_VIA_ECM_COLLISION_COMPONENT',
 'ECM_linear_velocity':'CACHED_OR_STALE_POSSIBLE','ECM_angular_velocity':'CACHED_OR_STALE_POSSIBLE',
 'joint_velocity':'ECM_CURRENT_STATE_FROM_PHYSICS_GETVELOCITY',
 'joint_wrench':'LAST_ADVANCING_STEP_STATE_OR_HELD_REACTION',
 'supports':'LAST_ADVANCING_STEP_STATE','tangential_relative_velocity':'UNVERIFIABLE_WITH_ZERO_ADVANCEMENT',
 'production_cursors':'CURRENT_HOST_BOOKKEEPING_NO_SENSOR_READ',
 'WorldPoseCmd':'CURRENT_ECM_COMPONENT_AUDIT','sim_clock':'RAW_WORLDSTATISTICS_PLUS_CALLBACK_CLOCK'}
GATES=('DIAGNOSTIC_PLUGIN_BUILDS','RIGHT_JOINT_IDENTIFIED','RIGHT_JOINT_AXIS_IDENTIFIED',
 'GENERALIZED_COORDINATE_READBACK_IMPLEMENTED','BIDIRECTIONAL_TARGETS_DEFINED','ZERO_ADVANCEMENT_PROTOCOL_DEFINED',
 'NO_TWIST_PATH','NO_POSE_RPC_PATH','NO_WORLDPOSECMD_PATH','NO_PRODUCTION_SENSOR_REFRESH_PATH',
 'PROVENANCE_TAGGING_IMPLEMENTED','CONTACT_STALENESS_HANDLED','MEASUREMENT_RESOLUTION_POLICY_DEFINED',
 'SHAM_SEMANTICS_RECORDED','FRESH_PROCESS_PER_ARM','NO_AUTOMATIC_RERUN','PRODUCTION_SHA_UNCHANGED',
 'HOST1_PRESERVED','HOST1_FAILURE_UNDERSTOOD','DIAGNOSTIC_TRANSPORT_CODEC_VALIDATED','HOST2_FRESH',
 'PROTOCOL_UNCHANGED','READINESS_DISCOVERY_IMPLEMENTED')


DIAGNOSTIC_TYPES={'StringMsg':'stringmsg','Int32':'int32'}


@contextmanager
def diagnostic_codec(transport):
    """Extend only this diagnostic instance; preserve production class and bytes."""
    missing=object();previous=vars(transport).get('TYPES',missing)
    transport.TYPES={**transport.TYPES,**DIAGNOSTIC_TYPES}
    try:
        descriptors={name:transport.message(name).DESCRIPTOR.full_name for name in DIAGNOSTIC_TYPES}
        if descriptors!={'StringMsg':'gz.msgs.StringMsg','Int32':'gz.msgs.Int32'}:
            raise g.InvalidCapture('qualification message descriptor mismatch')
        yield descriptors
    finally:
        if previous is missing:del transport.TYPES
        else:transport.TYPES=previous


def codec_self_check():
    """Real resolver and installed protobufs; no Node/transport init or RPC."""
    from aero_ai_studio.gazebo.transport import HarmonicTransport
    transport=object.__new__(HarmonicTransport);production_types=dict(HarmonicTransport.TYPES)
    legacy_errors={}
    for name in DIAGNOSTIC_TYPES:
        try:transport.message(name)
        except KeyError as exc:legacy_errors[name]=str(exc)
        else:raise ValueError('legacy missing-codec assumption changed; re-audit required')
    with diagnostic_codec(transport) as descriptors:
        for code in (0,1,2,3):
            msg=transport.message('Int32')();msg.data=code
            decoded=transport.message('Int32')();decoded.ParseFromString(msg.SerializeToString())
            if decoded.data!=code:raise ValueError('Int32 qualification code roundtrip failed')
        msg=transport.message('StringMsg')();msg.data='{"request_id":1}'
        decoded=transport.message('StringMsg')();decoded.ParseFromString(msg.SerializeToString())
        if decoded.data!=msg.data:raise ValueError('StringMsg qualification payload roundtrip failed')
    if HarmonicTransport.TYPES!=production_types or 'TYPES' in vars(transport):raise ValueError('diagnostic codec leaked into production class/instance')
    return {'legacy_errors_reproduced':legacy_errors,'descriptors':descriptors,
      'status':'OFFLINE_CODEC_ROUNDTRIP_PASS','transport_Node_created':False,'runtime_transport':'HOST_REQUIRED'}


def target(q,arm):
    if arm not in ARMS or type(q) not in (float,int) or not math.isfinite(q):raise ValueError('finite actual q and known arm required')
    return q+{'SHAM':0.,'PLUS_DELTA':DELTA,'MINUS_DELTA':-DELTA}[arm]


def wrap(x):return math.atan2(math.sin(x),math.cos(x))


def phases(row,channel):
    body=row['links']['body'][channel]['orientation_world_xyzw'];result={}
    for side in ('left','right'):
        wheel=row['links'][side+'_wheel'][channel]['orientation_world_xyzw']
        q=g.dm.qmul(g.dm.qmul(g.dm.qinverse(body),wheel),g.dm.qinverse([math.sqrt(.5),0,0,math.sqrt(.5)]))
        result[side]=wrap(2*math.atan2(q[1],q[3]))
    result.update(differential=wrap(result['left']-result['right'])/2,common=(result['left']+result['right'])/2)
    return result


def protocol():
    return {'experiment':'PAUSED_GENERALIZED_COORDINATE_PHASE_ISOLATION_QUALIFICATION','version':1,
      'arms':[{'ordinal':i+1,'arm':a,'operation_code':i+1,'requested_delta_rad':target(0.,a)} for i,a in enumerate(ARMS)],
      'context':'All3 arms independently execute canonical RIGHT_HISTORY Actions08-23 and DOWN->LINEAR_REVERSAL->BRAKE_LINEAR->stopped. ZERO extra context ticks. Abort before fresh Action24 UP; no physical outcome analysis.',
      'request_protocol':'0=read;1=SHAM;2=PLUS;3=MINUS.3 PRE reads,1 one-shot mutation request,3 POST reads. Target computed in plugin from actual current joint q, never from derived phase.',
      'expected_qualified_axis':{'joint':'simple_agent::right_joint','type':'revolute','parent':'body','child':'right_wheel','axis_model':[0,1,0],'ideal_phase_sign':1},
      'intervention_iteration_delta':0,'intervention_sim_time_delta_ns':0,'no_replacements':True,
      'provenance':LABELS,'measurement_policy':{'repeatability_reads_per_side':3,'numerical_floor_ULPs':128,
        'require_noise_plus_representation_error_below_cap_fraction':.1,
        'caps':{'q_rad':1e-11,'phase_rad':1e-11,'chassis_position_m':1e-11,'wheel_center_m':1e-10,
          'orientation_component_residual':1e-11,'linear_velocity_m_s':1e-11,'angular_velocity_rad_s':1e-11,
          'wheel_velocity_rad_s':1e-12,'contact_depth_m':1e-10,'Fn_N':1e-8,'wrench_force_N':1e-8,'wrench_torque_Nm':1e-10},
        'stale_policy':'Never classify unchanged held contacts/wrench or filtered ECM pose as isolation PASS. Current contact geometry/force recomputation not provided: UNVERIFIABLE_WITH_ZERO_ADVANCEMENT.',
        'unresolved_engine_pose_repeatability':'Host qualification must compare duplicate same-time samples; labels identify producer path, not independent direct engine pointer.',
        'resolution_failure':'MEASUREMENT_RESOLUTION_INSUFFICIENT; never loosen cap'},
      'classifications':['PHASE_RESET_QUALIFICATION_PASS','PHASE_RESET_TARGET_NOT_ATTAINED','PHASE_RESET_REQUIRES_ADVANCEMENT',
        'PHASE_RESET_COLLATERAL_DETECTED','PHASE_RESET_COLLATERAL_UNVERIFIABLE','PHASE_RESET_READBACK_INCOHERENT',
        'SHAM_PATH_NOT_STRUCTURALLY_EQUIVALENT','CAPTURE_INVALID'],
      'primary_priority':['CAPTURE_INVALID','PHASE_RESET_REQUIRES_ADVANCEMENT','PHASE_RESET_READBACK_INCOHERENT',
        'PHASE_RESET_TARGET_NOT_ATTAINED','PHASE_RESET_COLLATERAL_DETECTED','PHASE_RESET_COLLATERAL_UNVERIFIABLE','PHASE_RESET_QUALIFICATION_PASS'],
      'aggregate_policy':'Retain every arm, flags and channel result. Strong kinematic qualification and causal readiness are separate. Contact unverifiability and structurally distinct SHAM are never converted to unchanged/equivalent. No Action24 outcome classifier.',
      'sham_policy':'ResetPosition invoked even for identical target; record numeric/bitwise identity. Expected DART exact equality early-return difference remains SHAM_PATH_NOT_STRUCTURALLY_EQUIVALENT until investigated.'}


def ensure_output(path):
    path=Path(path).resolve()
    if path.is_relative_to(ROOT/'validation') and path!=DEFAULT_OUTPUT:raise FileExistsError('preserved evidence output prohibited')
    if path.exists() and any(p.name not in STATIC for p in path.iterdir()):raise FileExistsError('runtime evidence exists; no resume or primary rerun')
    return path


def guard_manifest():
    guard=d.protected_manifest()
    audit=json.loads((d.DEFAULT_OUTPUT/'right_wheel_phase_intervention_feasibility.json').read_text())
    for path,expected in audit['source_audit']['binary_sha256'].items():
        if g.sha(path)!=expected:raise ValueError('installed physics stack differs from AN-K audit: '+path)
        guard[path]=expected
    for root in (d.DEFAULT_OUTPUT,HOST1,FORENSICS):
        for p in root.rglob('*'):
            if p.is_file():guard[str(p.resolve())]=g.sha(p)
    for p in (SOURCE,Path(__file__),ROOT/'tests/test_gazebo_phase_isolation_qualification.py'):
        if p.exists():guard[str(p.resolve())]=g.sha(p)
    return guard


def write(path,value):
    path=Path(path).resolve()
    if any(path.is_relative_to(root.resolve()) for root in (HOST1,FORENSICS)):
        raise FileExistsError('refusing immutable Host1 or forensic evidence')
    d.ledger_io.atomic_json(path,value)


def build(path):
    path.mkdir(parents=True,exist_ok=True);library=(path/'libaero_phase_isolation.so').resolve()
    flags=subprocess.run(['pkg-config','--cflags','--libs','gz-sim8','gz-plugin2','gz-transport13'],capture_output=True,text=True,check=True)
    command=['c++','-std=c++17','-shared','-fPIC','-Wl,-z,defs',str(SOURCE),'-o',str(library),*shlex.split(flags.stdout)]
    result=subprocess.run(command,capture_output=True,text=True)
    if result.returncode:raise RuntimeError('diagnostic plugin build failed: '+result.stderr)
    loadcheck=subprocess.run(['ldd','-r',str(library)],capture_output=True,text=True,check=True)
    if 'not found' in loadcheck.stdout or 'undefined symbol' in loadcheck.stdout:raise RuntimeError('diagnostic plugin dependencies unresolved: '+loadcheck.stdout)
    return library,{'dependency_check':loadcheck.stdout,'command':command,'source_sha256':g.sha(SOURCE),'library_sha256':g.sha(library),'stderr':result.stderr}


def instrument(path,info,library,arm,directory):
    tree=ET.parse(path);topic=info['native']['topic']+'/phase_qualification'
    plugin=ET.SubElement(tree.find('world'),'plugin',filename=str(library),name='aero_diagnostic::PhaseIsolationQualification')
    for key,val in {'topic':topic,'service':topic+'/request','output':str(directory/'phase_qualification.ndjson'),
                    'operation_code':ARMS.index(arm)+1}.items():ET.SubElement(plugin,key).text=str(val)
    tree.write(path,encoding='utf-8',xml_declaration=True)
    info['qualification']={'topic':topic,'service':topic+'/request','arm':arm,'diagnostic_mutation_only_on_request':True}
    info['diagnostic_sdf_sha256']=g.sha(path)
    return path,info


def static_contract():
    text=SOURCE.read_text()
    for forbidden in ('.SetVelocity(','.ResetVelocity(','.SetForce(','.Publish<gz::msgs::Twist>','WorldControl','set_pose','JointVelocityCmd','JointForceCmd'):
        if forbidden in text:raise ValueError('forbidden mutation source token: '+forbidden)
    if text.count('.ResetPosition(')!=1:raise ValueError('one isolated coordinate-reset call site required')
    if 'JointPositionReset' not in text and '.ResetPosition(ecm,{target})' not in text:raise ValueError('real reset path missing')
    if 'if(!info.paused)' not in text or 'std::setprecision(17)' not in text:raise ValueError('paused precision guards missing')
    return {'source_forbidden_path_scan':'PASS','actual_api_build':'HOST_INDEPENDENT_COMPILE_REQUIRED',
            'runtime_target_attainment':'HOST_REQUIRED','runtime_mapping':'HOST_REQUIRED','runtime_collateral':'HOST_REQUIRED'}


def boundary_state(adapter):
    return {'logical':g.logical_state(adapter),'production_sensor':g.sensor_cursor(adapter),
      'production_step_tracker':copy.deepcopy(getattr(adapter,'_yaw_step_tracker',{})),
      'planner_executor':'Completed accepted production brake callback; live plan is recorded separately; no diagnostic state writes.',
      'production_sensor_consumption':'No read; cached cursor/timestamp/observation identity only'}


def decorate_packet(packet):
    packet['channel_provenance']=copy.deepcopy(LABELS)
    for source in ('ECM_pose','engine_derived_collision_pose'):
        packet[source+'_derived_phase']=phases(packet,source)
        for link in packet['links'].values():
            link[source]['roll_pitch_yaw_rad']=list(g.checkpoints.rpy(link[source]['orientation_world_xyzw']))
    for support in packet['supports'].values():
        force=0.
        for contact in support['contacts']:
            if contact['pair_classification']!='SUPPORT_GROUND':continue
            for point in contact['points']:
                projection=g.history.project_force(point['body_1_force_world_n'],point['normal_world'])
                if projection is None:raise g.InvalidCapture('invalid held contact force')
                force+=projection['Fn_N']
        support['Fn_N']=force if support.get('component_available') is True else None
        support['provenance']=LABELS['supports']
    for joint in packet['joint_wrench'].values():
        for field in ('force','torque'):
            joint[field+'_norm']=math.sqrt(sum(v*v for v in joint[field+'_xyz_'+('N' if field=='force' else 'N_m')]))
    packet['tangential_relative_velocity']={'value':None,'provenance':LABELS['tangential_relative_velocity'],
        'reason':'Current contact geometry not independently refreshed by a paused solve.'}
    return packet


def read_packet(adapter,topic,code,cursor):
    transport=adapter.env.transport;history=len(transport.request_history)
    response=transport.request(topic+'/request','Int32','Boolean',{'data':code},max_attempts=1)
    if response.get('data') is not True:raise g.InvalidCapture('qualification queue rejected request; no rerun')
    deadline=time.monotonic()+adapter.env.timeout
    while time.monotonic()<deadline:
        for seq,message in transport.messages_after(topic,cursor,timeout=max(0.,deadline-time.monotonic())):
            cursor=seq;packet=json.loads(message['data'])
            if packet['operation_code']!=code:raise g.InvalidCapture('qualification acknowledgement code mismatch')
            if len(transport.request_history[history:])!=1 or len(transport.request_history[-1]['attempts'])!=1:
                raise g.InvalidCapture('request must execute exactly once')
            return decorate_packet(packet),cursor
    raise g.InvalidCapture('paused qualification acknowledgement missing; no advancing fallback')


def fresh_paused_stats(adapter):
    """Wait for a new /stats publication after readback; never issue control."""
    transport=adapter.env.transport;topic=adapter.env.stepper.topic
    cursor=transport.cursor(topic);deadline=time.monotonic()+adapter.env.timeout
    while time.monotonic()<deadline:
        messages=transport.messages_after(topic,cursor,timeout=max(0.,deadline-time.monotonic()))
        for sequence,raw in messages:
            cursor=sequence
            if raw.get('paused') is not True:continue
            sim=raw.get('sim_time',{})
            ns=int(sim.get('sec',0))*1000000000+int(sim.get('nsec',0))
            iteration=raw.get('iterations_normalized',raw.get('iterations'))
            marker={'iteration':iteration,'sim_time_ns':ns,'paused':True,'stats_source':'transport_snapshot',
                'observed_snapshot':copy.deepcopy(raw),'stats_receive_sequence':sequence,
                'freshness':'new WorldStatistics publication received after all qualification readbacks'}
            d.exact_stats(marker);return marker
    raise g.InvalidCapture('fresh paused WorldStatistics missing after readback; no advancing fallback')


def prohibited_cursors(audit):
    return {'Twist_publication_cursor':sum(e.get('kind')=='TWIST' and e.get('published') is True for e in audit['events']),
        'pose_RPC_cursor':sum(e.get('kind')=='RPC' and g.is_pose_service(e.get('service','')) for e in audit['events'])}


def qualification_hook(arm,evidence,library):
    def hook(adapter,case,native,row,it,audit):
        if case!=arm or evidence:raise g.InvalidCapture('unexpected/repeated qualification boundary')
        g.y.stopped_chunk(row);completed=g.y.completed_brake_checkpoint(adapter,row)
        marker=g.dm.physics_mark(adapter);d.exact_stats(marker)
        audit['phase']='treatment';audit['adapter']=adapter
        evidence.update(arm=arm,completed_brake=completed,stopped_chunk=copy.deepcopy(row),
            PRE_marker=marker,window_start=len(audit['events']),host_PRE=boundary_state(adapter))
        evidence['host_PRE']['prohibited_transport_cursors']=prohibited_cursors(audit)
        topic=native.topic+'/phase_qualification';transport=adapter.env.transport
        packets=[]
        def stage(name):
            evidence['current_stage']=name
            evidence.setdefault('progress',[]).append({'stage':name,'wall_monotonic_s':time.monotonic()})
        try:
            stage('DIAGNOSTIC_CODEC_RESOLUTION')
            with diagnostic_codec(transport) as descriptors:
                evidence['diagnostic_transport_descriptors']=descriptors
                stage('QUALIFICATION_SUBSCRIPTION')
                transport.subscribe(topic,'StringMsg');cursor=transport.cursor(topic)
                stage('QUALIFICATION_PUBLISHER_DISCOVERY')
                evidence['publisher_readiness']=transport.wait_for_topic(topic,'StringMsg',timeout=adapter.env.timeout)
                stage('QUALIFICATION_SERVICE_DISCOVERY')
                evidence['service_readiness']=transport.wait_for_service(topic+'/request','Int32','Boolean',timeout=adapter.env.timeout)
                for index,code in enumerate((0,0,0,ARMS.index(arm)+1,0,0,0)):
                    stage('RESET_REQUEST' if index==3 else ('PRE_READ_' if index<3 else 'POST_READ_')+str(index+1))
                    packet,cursor=read_packet(adapter,topic,code,cursor);packets.append(packet)
                stage('FRESH_POST_WORLDSTATISTICS')
                evidence.update(packets=packets,POST_marker=fresh_paused_stats(adapter),host_POST=boundary_state(adapter),
                    window_end=len(audit['events']),qualification_completed=True)
                evidence['host_POST']['prohibited_transport_cursors']=prohibited_cursors(audit)
                evidence['host_PRE']['WorldPoseCmd_observation_cursor']=packets[0]['WorldPoseCmd_observations']
                evidence['host_POST']['WorldPoseCmd_observation_cursor']=packets[-1]['WorldPoseCmd_observations']
                stage('QUALIFICATION_CAPTURE_COMPLETE')
        except Exception as exc:
            evidence['failed_stage']=evidence.get('current_stage')
            evidence['qualification_error']=g.dm.failure_record(exc)
            raise
        finally:
            evidence['packets']=packets
            evidence['window_end']=len(audit['events'])
            # Includes codec/subscription failures; ordinary close is outside window.
            audit['phase']='qualification_finished_no_acquisition'
        raise g.InvalidCapture(STOP)
    return hook


def group_gone(pid):
    try:os.killpg(pid,0)
    except ProcessLookupError:return True
    except PermissionError:return False
    return False


def capture(arm,scenario,directory,libraries,seed,namespace,library):
    from aero_ai_studio.gazebo.process_manager import GazeboProcessManager
    from aero_ai_studio.gazebo.transport import HarmonicTransport
    Native=g.ab.native.NativeVelocityCapture
    old_plan,old_treatment,old_instrument=g.plan,g.perform_treatment,g.ab._instrument_world
    old_launch,old_close,old_subscribe,old_publish=GazeboProcessManager.launch,GazeboProcessManager.close,Native.subscribe,HarmonicTransport.publish
    events=[];observers=[];transports=[];evidence={};record=None
    def plan(case):
        if case!=arm:raise ValueError(case)
        return {**g.history.candidate(15),'name':case,'extra_pre_acquisition_iterations':0,'extra_pre_acquisition_sim_time_ns':0}
    def inst(path,out,libs,topic_identity=None):
        diag,info=old_instrument(path,out,libs,topic_identity=topic_identity)
        return instrument(diag,info,library,arm,directory)
    def launch(manager,*a,**k):
        result=old_launch(manager,*a,**k)
        events.append({'event':'launch','wall_monotonic_s':time.monotonic(),'status':manager.status()});return result
    def close(manager):
        try:return old_close(manager)
        finally:
            proc=manager.process;pid=proc.pid if proc else None
            events.append({'event':'close','wall_monotonic_s':time.monotonic(),'partition':manager.partition,
                'pid':pid,'exit_code':proc.poll() if proc else None,
                'shutdown_proven':bool(proc and proc.poll() is not None and group_gone(pid))})
    def subscribe(observer,adapter,*a,**k):
        observers.append(observer);transports.append(adapter.env.transport);return old_subscribe(observer,adapter,*a,**k)
    def publish(transport,topic,kind,payload):
        if evidence and kind.split('.')[-1]=='Twist' and any(v!=0 for v in d.flatten(payload).values()):
            raise g.InvalidCapture('no acquisition publication permitted after qualification boundary')
        return old_publish(transport,topic,kind,payload)
    g.plan=plan;g.perform_treatment=qualification_hook(arm,evidence,library);g.ab._instrument_world=inst
    GazeboProcessManager.launch=launch;GazeboProcessManager.close=close;Native.subscribe=subscribe;HarmonicTransport.publish=publish
    try:
        record=g.capture(arm,scenario,directory,libraries,seed,namespace)
        evidence['terminal_planner_executor_entry']=copy.deepcopy(record['terminal_entry_history'])
        record['phase_qualification']=copy.deepcopy(evidence)
        record['terminal_event_semantics']='Intentional diagnostic abort before Action24 UP; inherited terminal exception is not a physical qualification outcome.'
        write(directory/'qualification_capture.json',record)
        return record
    finally:
        g.plan,g.perform_treatment,g.ab._instrument_world=old_plan,old_treatment,old_instrument
        GazeboProcessManager.launch,GazeboProcessManager.close,Native.subscribe,HarmonicTransport.publish=old_launch,old_close,old_subscribe,old_publish
        launches=[e for e in events if e['event']=='launch'];closes=[e for e in events if e['event']=='close']
        life={'arm':arm,'events':events,'observer_subscriptions_closed':bool(observers) and all(not o.subscribed for o in observers),
          'qualification_transport_closed':bool(transports) and all(t.closed for t in transports),
          'fresh_single_server':len(launches)==1,'shutdown_proven':bool(transports) and all(t.closed for t in transports) and bool(closes) and all(e['shutdown_proven'] for e in closes) and bool(observers) and all(not o.subscribed for o in observers),
          'observer_process_model':'Fresh observer/plugin instances in fresh server process, fresh Python subscription; all close before next arm.'}
        write(directory/'process_lifecycle.json',life)


def measurement(values,post,cap,fresh=True):
    numbers=[*values,*post]
    if not numbers or not all(type(v) in (float,int) and math.isfinite(v) for v in numbers):
        return {'status':'PHASE_RESET_READBACK_INCOHERENT','cap':cap}
    representation=128*max(math.ulp(max(1.,abs(float(v)))) for v in numbers)
    repeatability=max(max(values)-min(values),max(post)-min(post))
    change=post[0]-values[-1]
    if not fresh:status='UNVERIFIABLE_WITH_ZERO_ADVANCEMENT'
    elif representation+repeatability>cap*.1:status='MEASUREMENT_RESOLUTION_INSUFFICIENT'
    elif abs(change)>cap:status='COLLATERAL_DETECTED'
    else:status='VERIFIED_WITHIN_NUMERICAL_CAP'
    return {'status':status,'pre_values':values,'post_values':post,'delta':change,'cap':cap,
      'binary64_representation_floor':representation,'same_time_repeatability':repeatability,
      'serialization':'17 significant digits','meaningful_detectable_delta':representation+repeatability,
      'freshness_basis':'engine-populated producer path, paired callback readback; not an independent engine pointer' if fresh else 'stale/cached risk'}


def analyze(record,arm):
    e=record['phase_qualification'];packets=e.get('packets',[])
    if not e.get('qualification_completed') or len(packets)!=7:
        failure=e.get('qualification_error') or record.get('one_tick_treatment',{}).get('diagnostic_error') or {}
        raise g.InvalidCapture('qualification incomplete; stage='+str(e.get('failed_stage','unrecorded'))+'; '+str(failure.get('type',''))+': '+str(failure.get('message',''))+'; no physical interpretation')
    if [p['request_id'] for p in packets]!=list(range(1,8)):raise g.InvalidCapture('request acknowledgement sequence differs')
    if [p['operation_code'] for p in packets]!=[0,0,0,ARMS.index(arm)+1,0,0,0]:raise g.InvalidCapture('one mutation and six readbacks required')
    before=packets[:3];after=packets[3:];reset=after[0]
    if any(p['error'] or not p['paused'] for p in packets):raise g.InvalidCapture('plugin paused/readback error')
    bi,bns=d.exact_stats(e['PRE_marker']);ai,ans=d.exact_stats(e['POST_marker'])
    g.y.stopped_chunk(e['stopped_chunk'])
    if e['completed_brake']['active_physics_transactions']!=0 or round(e['stopped_chunk']['simulation_end']*1e9)!=bns:raise g.InvalidCapture('stopped brake boundary incoherent')
    advance=ai-bi!=0 or ans-bns!=0 or any(p['iteration']!=bi or p['sim_time_ns']!=bns or
      p['advancing_callback_count']!=before[0]['advancing_callback_count'] or p['last_advancing_iteration']!=bi or p['last_advancing_time_ns']!=bns for p in packets)
    if any(b['postupdate_count']<=a['postupdate_count'] for a,b in zip(packets,packets[1:])):raise g.InvalidCapture('paused callback acknowledgements unordered')
    if sum(p['ResetPosition_invoked'] for p in packets)!=1:raise g.InvalidCapture('exactly one ResetPosition invocation required')
    window=record['command_audit'][e['window_start']:e['window_end']]
    if len(window)!=7 or any(x['kind']!='RPC' or x['request_type']!='Int32' or not x['service'].endswith('/phase_qualification/request') for x in window):
        raise g.InvalidCapture('unexpected treatment command/RPC, including physics control')
    g.audit_window(record['command_audit'],e['window_start'],e['window_end'])
    if e['host_PRE']!=e['host_POST']:raise g.InvalidCapture('production sensor/logical cursor changed')
    if any(p['WorldPoseCmd_active'] or p.get('WorldPoseCmd_active_PRE',0) or p['WorldPoseCmd_observations']!=before[0]['WorldPoseCmd_observations'] for p in packets):raise g.InvalidCapture('WorldPoseCmd observed in qualification')
    if STOP not in json.dumps(record['events'][-1].get('exception')):raise g.InvalidCapture('intentional pre-UP qualification stop not corroborated')
    history=[x for x in record['events'] if x.get('canonical_index') in range(8,24)]
    if [x['canonical_index'] for x in history]!=list(range(8,24)) or any(x.get('exception') or x.get('terminated') for x in history):raise g.InvalidCapture('canonical Actions08-23 incomplete')
    entry=record['terminal_entry_history'];plan=entry['production_plan']
    if plan['request']['previous_command']!=g.dm.gazebo_physics_twist('down') or plan['request']['transition_type']!='LINEAR_REVERSAL' or [p['kind'] for p in plan['phases']]!=['BRAKE_LINEAR','ACQUIRE_LINEAR']:
        raise g.InvalidCapture('canonical production reversal plan changed')
    if any(x['kind']=='TWIST' and x.get('phase')=='production_acquisition' for x in record['command_audit']):raise g.InvalidCapture('Action24 acquisition was executed')
    q0=before[-1]['generalized_q']['right'];q1=reset['generalized_q']['right'];want=target(q0,arm)
    if reset['q_actual_pre']!=q0 or reset['left_actual_pre']!=before[-1]['generalized_q']['left'] or reset['requested_target']!=want:
        raise g.InvalidCapture('target not derived from coherent actual PRE coordinate')
    cap=protocol()['measurement_policy']['caps'];dq=q1-q0;err=abs(q1-want)
    expected=target(0.,arm)
    if reset['requested_delta']!=expected:raise g.InvalidCapture('requested delta differs from frozen arm')
    if any(p['apply_callback']!=p['postupdate_count'] for p in packets):raise g.InvalidCapture('apply/read callback provenance differs')
    qrepeat=measurement([p['generalized_q']['right'] for p in before],[p['generalized_q']['right']-expected for p in after],cap['q_rad'])
    collateral={};mapping={}
    for channel in ('ECM_pose','engine_derived_collision_pose'):
        prephase=[phases(p,channel) for p in before];postphase=[phases(p,channel) for p in after]
        dp=wrap(postphase[0]['right']-prephase[-1]['right'])
        mapping[channel]={'PRE':prephase,'POST':postphase,'RIGHT_phase_delta':dp,
            'ratio_phase_delta_to_generalized_delta':dp/dq if abs(dq)>cap['q_rad'] else None,
            'residual_from_positive_axis_prediction':wrap(dp-dq),
            'provenance':LABELS[channel],
            'agreement_with_ideal_positive_axis':abs(wrap(dp-dq))<=cap['phase_rad']}
        left_delta=lambda p:wrap(p['left']-prephase[-1]['left'])
        right_delta=lambda p:wrap(p['right']-prephase[-1]['right'])
        collateral[channel+'.LEFT_phase']=measurement([left_delta(p) for p in prephase],[left_delta(p) for p in postphase],cap['phase_rad'],fresh=channel!='ECM_pose')
        for name in ('differential','common'):
            expected_change=-dq/2 if name=='differential' else dq/2
            local_alias=lambda p:(left_delta(p)+(-right_delta(p) if name=='differential' else right_delta(p)))/2
            collateral[channel+'.'+name]=measurement([local_alias(p) for p in prephase],[local_alias(p)-expected_change for p in postphase],cap['phase_rad'],fresh=channel!='ECM_pose')
        mapping[channel]['alias_delta_semantics']='Local continuous LEFT/RIGHT wrapped differences; raw common/differential markers retained separately. No 2pi branch jump interpreted as collateral.'
    collateral['LEFT_generalized_q']=measurement([p['generalized_q']['left'] for p in before],[p['generalized_q']['left'] for p in after],cap['q_rad'])
    # Orientation residual uses quaternion multiplication, not acos(dot), which loses tiny rotations.
    for link in ('body','left_wheel','right_wheel'):
        for source in ('engine_derived_collision_pose','ECM_pose'):
            for axis in range(3):
                collateral[f'{link}.{source}.XYZ.{axis}']=measurement([p['links'][link][source]['position_world_m'][axis] for p in before],
                    [p['links'][link][source]['position_world_m'][axis] for p in after],cap['chassis_position_m'] if link=='body' else cap['wheel_center_m'],fresh=source!='ECM_pose')
            base=before[-1]['links'][link][source]['orientation_world_xyzw']
            expected_q=base
            if link=='right_wheel':
                body=before[-1]['links']['body'][source]['orientation_world_xyzw']
                expected_q=g.dm.qmul(g.dm.qmul(g.dm.qmul(body,[0,math.sin(dq/2),0,math.cos(dq/2)]),g.dm.qinverse(body)),base)
            def aligned(q):return [v*(1 if sum(a*b for a,b in zip(q,base))>=0 else -1) for v in q]
            for axis in range(4):
                collateral[f'{link}.{source}.orientation_residual.{axis}']=measurement(
                    [aligned(p['links'][link][source]['orientation_world_xyzw'])[axis]-base[axis] for p in before],
                    [aligned(p['links'][link][source]['orientation_world_xyzw'])[axis]-expected_q[axis] for p in after],cap['orientation_component_residual'],fresh=source!='ECM_pose')
        for source in ('engine_derived_linear_velocity','engine_derived_angular_velocity','ECM_linear_velocity','ECM_angular_velocity'):
            for axis in range(3):
                collateral[f'{link}.{source}.{axis}']=measurement([p['links'][link][source][axis] for p in before],[p['links'][link][source][axis] for p in after],cap['linear_velocity_m_s'] if 'linear' in source else cap['angular_velocity_rad_s'],fresh=source.startswith('engine_derived'))
    for side in ('left','right'):
        collateral[side+'.wheel_velocity']=measurement([p['joint_wrench'][side]['actual_velocity_rad_s'] for p in before],[p['joint_wrench'][side]['actual_velocity_rad_s'] for p in after],cap['wheel_velocity_rad_s'])
    for name in ('supports','joint_wrench'):
        collateral[name]={'status':'UNVERIFIABLE_WITH_ZERO_ADVANCEMENT','provenance':LABELS[name],
            'PRE':[p[name] for p in before],'POST':[p[name] for p in after],
            'note':'Producer time retained where available. Equality of held values is not contact/reaction isolation.'}
    collateral['tangential_relative_velocity']={'status':'UNVERIFIABLE_WITH_ZERO_ADVANCEMENT','reason':'Current native twist is available but contact geometry belongs to last advancing step; no current tangential-contact claim.'}
    flags=[]
    if arm=='SHAM':flags.append('SHAM_PATH_NOT_STRUCTURALLY_EQUIVALENT')
    if not mapping['ECM_pose']['agreement_with_ideal_positive_axis']:flags.append('LEGACY_PHASE_MARKER_FILTERED_OR_INCOHERENT')
    if any(x.get('status')=='MEASUREMENT_RESOLUTION_INSUFFICIENT' for x in collateral.values()):flags.append('MEASUREMENT_RESOLUTION_INSUFFICIENT')
    if advance:classification='PHASE_RESET_REQUIRES_ADVANCEMENT'
    elif qrepeat['status']=='MEASUREMENT_RESOLUTION_INSUFFICIENT':classification='PHASE_RESET_READBACK_INCOHERENT'
    elif err>cap['q_rad']:classification='PHASE_RESET_TARGET_NOT_ATTAINED'
    elif not mapping['engine_derived_collision_pose']['agreement_with_ideal_positive_axis']:classification='PHASE_RESET_READBACK_INCOHERENT'
    elif any(x['status']=='PHASE_RESET_READBACK_INCOHERENT' for x in collateral.values()):classification='PHASE_RESET_READBACK_INCOHERENT'
    elif any(x['status']=='COLLATERAL_DETECTED' for x in collateral.values()):classification='PHASE_RESET_COLLATERAL_DETECTED'
    else:classification='PHASE_RESET_COLLATERAL_UNVERIFIABLE'
    if not reset['target_numerically_differs'] and arm!='SHAM':classification='PHASE_RESET_TARGET_NOT_ATTAINED'
    return {'arm':arm,'classification':classification,'flags':flags,'capture_valid':True,
      'requested_delta_rad':expected,'q_actual_pre':q0,'q_actual_post':q1,'actual_generalized_delta_rad':dq,
      'absolute_target_error_rad':err,'target_attained':err<=cap['q_rad'],'q_repeatability':qrepeat,
      'nominal_surface_arc_m':.1*dq,'radius_m':.1,'radius_source':'validated production SDF',
      'axis_sign':'Expected positive from SDF body-Y axis and mount; measured ratios retained, not forced.',
      'zero_advancement':not advance,'raw_world_statistics_PRE':e['PRE_marker'],'raw_world_statistics_POST':e['POST_marker'],
      'paused_callback_progress':[p['postupdate_count'] for p in packets],
      'advancing_callback_progress':[p['advancing_callback_count'] for p in packets],
      'ResetPosition_invoked':reset['ResetPosition_invoked'],'target_bitwise_differs':reset['target_bitwise_differs'],
      'target_numerically_differs':reset['target_numerically_differs'],'acknowledgement_path':'service queue ACK -> PreUpdate apply -> PostUpdate raw/published request id -> three same-time duplicate readbacks',
      'generalized_target_and_native_mapping_qualified':not advance and err<=cap['q_rad'] and qrepeat['status']=='VERIFIED_WITHIN_NUMERICAL_CAP' and mapping['engine_derived_collision_pose']['agreement_with_ideal_positive_axis'],
      'legacy_phase_marker_mapping_confirmed':mapping['ECM_pose']['agreement_with_ideal_positive_axis'],
      'mapping':mapping,'collateral':collateral,'channel_provenance':LABELS,'host_bookkeeping_PRE':e['host_PRE'],'host_bookkeeping_POST':e['host_POST'],
      'terminal_planner_executor_entry':record['terminal_entry_history'],
      'raw_packets':packets,'contact_collateral':'UNVERIFIABLE_WITH_ZERO_ADVANCEMENT','causal_runtime_ready':False,
      'Action24_outcome_interpretation':'NOT_PERFORMED; capture stopped before fresh UP'}


def preflight(output):
    output=ensure_output(output);guard=guard_manifest();static=static_contract();codec=codec_self_check()
    inventory=json.loads((FORENSICS/'inventory.json').read_text())
    g.history.verify_manifest({x['path']:x['sha256'] for x in inventory})
    if json.loads((HOST1/'protocol.json').read_text())!=protocol():raise ValueError('qualification protocol differs from frozen Host1')
    safety(output);output.mkdir(parents=True,exist_ok=True)
    frozen=output/'protocol.json'
    if frozen.exists() and json.loads(frozen.read_text())!=protocol():raise ValueError('frozen protocol changed')
    write(frozen,protocol());scenario,seed,_=g.history.source(g.ab.DEFAULT_ARTIFACT)
    libraries,builds=g.ab._build_all(output/'builds');g.verify_static_builds(builds)
    library,built=build(output/'builds/qualification');definitions=[]
    for arm in ARMS:
        directory=output/'preflight_sdfs'/arm
        prod=g.ab.GazeboWorldGenerator().generate(scenario,directory/'world',closed_loop=True,control_mode='PHYSICS')
        tree=ET.parse(prod);model=tree.find("world/model[@name='simple_agent']")
        joint=model.find("joint[@name='right_joint']")
        if joint.get('type')!='revolute' or joint.findtext('parent')!='body' or joint.findtext('child')!='right_wheel' or joint.findtext('axis/xyz')!='0 1 0':raise ValueError('RIGHT identity/axis changed')
        for link,name in [('body','body_collision'),('left_wheel','left_collision'),('right_wheel','right_collision')]:
            col=model.find(f"link[@name='{link}']/collision[@name='{name}']")
            if col is None or col.find('pose') is not None:raise ValueError('native collision readback requires verified identity offset')
        if float(model.findtext("link[@name='right_wheel']/collision/geometry/cylinder/radius"))!=.1 or g.sha(prod)!=g.EXPECTED_SHA:raise ValueError('production geometry/hash changed')
        diag,info=g.ab._instrument_world(prod,directory,libraries,topic_identity='qualification/'+arm+'/'+uuid4().hex)
        diag,info=instrument(diag,info,library,arm,directory)
        diag,info=g.checkpoints.instrument(diag,info);diag,info=g.instrument_audit(diag,info)
        definitions.append({'arm':arm,'diagnostic_sdf':str(diag),'identity':info['qualification']})
    g.production_sensor_order_contract();g.history.verify_manifest(guard)
    if list(output.rglob('*.ndjson')):raise ValueError('runtime evidence created by preflight')
    report={'status':'PREFLIGHT_PASS','gates':{k:True for k in GATES},'runtime_proofs':'HOST_REQUIRED; no target, zero-advance, precision or isolation result fabricated',
      'production_sha_before':g.EXPECTED_SHA,'production_sha_after':g.EXPECTED_SHA,'production_changed':False,'gazebo_launched':False,
      'source_contract':static,'diagnostic_codec':codec,'Host1_classification':'QUALIFICATION_CAPTURE_INFRASTRUCTURE_FAILURE',
      'Host1_forensic_findings':str(FORENSICS/'findings.json'),'Host1_inventory_sha256':g.sha(FORENSICS/'inventory.json'),
      'definitions':definitions,'observer_builds':builds,'qualification_build':built,
      'library':str(library),'guard_manifest':guard,'protocol_sha256':g.sha(frozen),'runner_sha256':g.sha(__file__),'seed':seed}
    write(output/'qualification_preflight.json',report);return report


def safety(output):
    d.process_safety()
    partitions=set()
    for root in (HOST1,output):
      for p in root.glob('*/process_lifecycle.json'):
        for e in json.loads(p.read_text())['events']:
            part=e.get('partition') or e.get('status',{}).get('partition')
            if part:partitions.add(part)
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit() or int(proc.name)==os.getpid():continue
        try:
            cmd=(proc/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace')
            try:env=(proc/'environ').read_bytes().split(b'\0')
            except PermissionError:env=[]
        except (FileNotFoundError,ProcessLookupError,PermissionError):continue
        if any(('GZ_PARTITION='+p).encode() in env for p in partitions) or (any(str(root) in cmd for root in (HOST1,output)) and 'world_joint_state_diagnostic.sdf' in cmd):
            raise g.InvalidCapture('prior qualification process still active; no process killed')


def run(output):
    output=ensure_output(output);pf=json.loads((output/'qualification_preflight.json').read_text())
    if pf['status']!='PREFLIGHT_PASS' or pf['runner_sha256']!=g.sha(__file__) or pf['protocol_sha256']!=g.sha(output/'protocol.json'):
        raise g.InvalidCapture('preflight mismatch')
    g.history.verify_manifest(pf['guard_manifest']);codec_self_check();safety(output)
    scenario,seed,_=g.history.source(g.ab.DEFAULT_ARTIFACT)
    libraries,builds=g.ab._build_all(output/'builds');g.verify_static_builds(builds)
    library=Path(pf['library'])
    if g.sha(library)!=pf['qualification_build']['library_sha256']:raise g.InvalidCapture('qualification plugin changed')
    ledger={'protocol_sha256':pf['protocol_sha256'],'slots':[{'arm':a,'state':'SCHEDULED'} for a in ARMS]}
    write(output/'qualification_ledger.json',ledger);previous_shutdown=True;partitions=set();topics=set();previous_close=None
    for slot in ledger['slots']:
        arm=slot['arm'];directory=output/arm
        if not previous_shutdown:
            slot['not_started_reason']='prior shutdown unproven; original slot retained SCHEDULED';write(output/'qualification_ledger.json',ledger);continue
        safety(output);directory.mkdir(parents=True);slot.update(state='STARTED',wall_start=time.monotonic());write(output/'qualification_ledger.json',ledger)
        try:
            record=capture(arm,scenario,directory,libraries,seed,uuid4().hex,library)
            life=json.loads((directory/'process_lifecycle.json').read_text());previous_shutdown=life['shutdown_proven'] and record.get('shutdown_completed') is True
            launches=[e for e in life['events'] if e['event']=='launch'];closes=[e for e in life['events'] if e['event']=='close']
            if not previous_shutdown or not life['fresh_single_server']:raise g.InvalidCapture('fresh process/shutdown unproven')
            if previous_close is not None and launches[0]['wall_monotonic_s']<previous_close:raise g.InvalidCapture('process overlap')
            previous_close=max(e['wall_monotonic_s'] for e in closes)
            identity=record['runtime_identity']
            if identity['partition'] in partitions or identity['topic'] in topics:raise g.InvalidCapture('transport identity reused')
            partitions.add(identity['partition']);topics.add(identity['topic'])
            result=analyze(record,arm);write(directory/'qualification_analysis.json',result)
            slot.update(state='FINALIZED',result=result,runtime_identity=identity,lifecycle=life)
        except Exception as exc:
            life_path=directory/'process_lifecycle.json';life=json.loads(life_path.read_text()) if life_path.exists() else {}
            previous_shutdown=life.get('shutdown_proven') is True
            slot.update(state='FINALIZED',result={'arm':arm,'classification':'CAPTURE_INVALID','capture_valid':False,
                'invalid_reason':type(exc).__name__+': '+str(exc),'traceback':traceback.format_exc()},lifecycle=life)
        write(output/'qualification_ledger.json',ledger)
        print(arm+': '+slot['result']['classification'],flush=True);gc.collect()
    g.history.verify_manifest(pf['guard_manifest'])
    results=[s['result'] for s in ledger['slots'] if s.get('result')]
    aggregate={'status':'QUALIFICATION_CAPTURE_COMPLETE' if len(results)==3 and all(r['capture_valid'] for r in results) else 'CAPTURE_FAILED',
      'results':results,'original_slots':ledger['slots'],'causal_runtime_ready':False,
      'bidirectional_target_and_native_mapping_attained':all(any(r.get('arm')==arm and r.get('capture_valid') and r.get('generalized_target_and_native_mapping_qualified') for r in results) for arm in ('PLUS_DELTA','MINUS_DELTA')),
      'bidirectional_legacy_marker_mapping_confirmed':all(any(r.get('arm')==arm and r.get('capture_valid') and r.get('legacy_phase_marker_mapping_confirmed') for r in results) for arm in ('PLUS_DELTA','MINUS_DELTA')),
      'aggregate_classifications':{r['arm']:{'primary':r['classification'],'flags':r.get('flags',[])} for r in results},
      'contact_collateral':'UNVERIFIABLE_WITH_ZERO_ADVANCEMENT','sham':'SHAM_PATH_NOT_STRUCTURALLY_EQUIVALENT',
      'production_sha_before':g.EXPECTED_SHA,'production_sha_after':g.EXPECTED_SHA,'production_changed':False,
      'no_Action24_outcome_testing':True,'qualification_pass_note':'Target attainment or mapping alone cannot establish causal readiness. Existing contact and ECM channels prevent unconditional isolation PASS.'}
    write(output/'phase_isolation_qualification.json',aggregate);return aggregate


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--preflight-only',action='store_true');mode.add_argument('--host-run',action='store_true')
    p.add_argument('--output',type=Path,default=DEFAULT_OUTPUT);args=p.parse_args(argv)
    try:report=preflight(args.output) if args.preflight_only else run(args.output)
    except Exception as exc:print('CAPTURE_FAILED: '+type(exc).__name__+': '+str(exc));return 1
    if args.preflight_only:
        for gate in GATES:print(gate)
    print(report['status']);print('CAUSAL_RUNTIME_NOT_READY');print('evidence: '+str(args.output))
    return 0 if report['status']!='CAPTURE_FAILED' else 1


if __name__=='__main__':raise SystemExit(main())
