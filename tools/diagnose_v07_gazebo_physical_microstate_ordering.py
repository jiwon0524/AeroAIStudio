#!/usr/bin/env python3
"""AN-R read-only natural-one-tick physical microstate ordering; Host execution explicit only."""
from __future__ import annotations
import argparse
import ast
import copy
import gc
import inspect
import json
import math
import os
import shlex
import statistics
import struct
import subprocess
import time
import traceback
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4
from tools import diagnose_v07_gazebo_phase_isolation_qualification as q
from tools import diagnose_v07_gazebo_ecm_hierarchy_freshness as preservation

d=q.d;g=q.g;ROOT=q.ROOT
ZERO='ZERO_TICK_MICROSTATE_CONTROL';ONE='ONE_TICK_MICROSTATE_OBSERVATION'
HOST1=ROOT/'validation/v071-host/gazebo-action24-physical-microstate-ordering-phase3hanr-host1'
HOST1_FORENSICS=HOST1/'microstate_host1_capture_forensics.json'
DEFAULT_OUTPUT=ROOT/'validation/v071-host/gazebo-action24-physical-microstate-ordering-phase3hanr-host2'
SOURCE=ROOT/'tools/gazebo_physical_microstate_observer.cc'
STOP=q.STOP
STATIC={'protocol.json','microstate_preflight.json','builds','preflight_sdfs','solver_observability.json'}
STAGES=('PreUpdate','Update/before_Physics_Update','Update/after_Physics_Update','PostUpdate/const_ECM')
LINKS=('body','left_wheel','right_wheel','front_caster','rear_caster')
SUPPORTS=LINKS[1:]
COLLISIONS=('body_collision','left_collision','right_collision','front_collision','rear_collision')
RIGHT_Z_REFERENCE=2.940583122834628e-8
FN_REFERENCE={'left_wheel':-8.587732488685162e-6,'right_wheel':-3.3588847454524284e-5,
              'front_caster':2.4585385380859748e-5,'rear_caster':2.2231143423923072e-5}
CLASSES=('PHYSICAL_MICROSTATE_CHANGE_REPLICATED','RIGHT_Z_MARKER_REPLICATED','SUPPORT_PRELOAD_CHANGE_REPLICATED',
 'GEOMETRY_FIRST','CONTACT_DEPTH_FIRST','WRENCH_OR_FORCE_FIRST','SAME_OBSERVABLE_STAGE','ORDERING_UNRESOLVED',
 'SOLVER_INTERNAL_STATE_NOT_PUBLICLY_OBSERVABLE','BASELINE_UNSTABLE','CAPTURE_INVALID')
GATES=('CURRENT_PHASE_IS_AN_R','TEN_CASE_SCHEDULE_FROZEN','FIVE_ZERO_FIVE_ONE','EXACT_ZERO_CONTRACT',
 'EXACT_ONE_1MS_CONTRACT','READ_ONLY_OBSERVERS_BUILD','NO_TREATMENT_COMMANDS','NO_POSE_RESET_PATH',
 'NO_PRODUCTION_SENSOR_CONSUMPTION','NO_PLANNER_MUTATION','STOP_BEFORE_ACTION24_UP',
 'BASELINE_VECTOR_DEFINED','ALL_GEOMETRY_CHANNELS_DEFINED','CONTACT_CHANNELS_DEFINED','JOINT_LINK_CHANNELS_DEFINED',
 'PHYSICS_ADJACENT_TAPS_ORDERED','FIRST_CHANGE_SAME_STAGE_DEFINED','FULL_PRECISION_DELTAS',
 'RIGHT_Z_GUARD_DEFINED','PRELOAD_GUARD_DEFINED','MISSING_CHANNELS_REMAIN_UNAVAILABLE',
 'SOLVER_INTERFACE_AUDIT_COMPLETE','INVALID_CASES_RETAINED','FRESH_PROCESS_PER_CASE','NO_AUTOMATIC_RERUN',
 'PRIOR_EVIDENCE_PRESERVED','PRODUCTION_SHA_UNCHANGED',
 'HOST1_FAILURE_EXPLAINED','HOST1_PRESERVED','REPAIR_DIAGNOSTIC_ONLY','ZERO_ADVANCEMENT_EXACT',
 'ONE_ADVANCEMENT_EXACT_1MS','NO_TREATMENT_COMMAND','NO_POSE_RESET','NO_ACTION24_UP',
 'OPTIONAL_CHANNELS_HONESTLY_UNAVAILABLE','CALLBACK_ASSUMPTIONS_RUNTIME_SUPPORTED',
 'SOLVER_INTERNAL_STATE_NOT_PUBLICLY_OBSERVABLE','HOST2_DESTINATION_FRESH')


def schedule():
    return [{'ordinal':2*(r-1)+j+1,'case_id':f'{arm}_R{r}','arm':arm,'replicate':f'R{r}',
             'iterations':int(arm==ONE),'sim_time_delta_ns':1000000*int(arm==ONE)}
            for r in range(1,6) for j,arm in enumerate((ZERO,ONE) if r%2 else (ONE,ZERO))]


def protocol():
    return {'phase':'AN-R','experiment':'NATURAL_ONE_TICK_PHYSICAL_MICROSTATE_ORDERING_QUALIFICATION',
      'schedule_status':'PROSPECTIVE_CASE_ORDER_FROZEN','schedule':schedule(),'classifications':CLASSES,
      'automatic_reruns':False,'fresh_process_per_case':True,'Action24_UP':False,'causal_efficacy_testing':False,
      'causal_intervention':False,'q_role':'guard only; accepted causal path closed',
      'boundary':'Canonical RIGHT_HISTORY Actions08-23; DOWN -> LINEAR_REVERSAL -> BRAKE_LINEAR stopped; abort before UP',
      'ZERO':{'extra_iterations':0,'extra_sim_time_ns':0,'advancement_requests':0},
      'ONE':{'extra_iterations':1,'extra_sim_time_ns':1000000,'advancement_requests':1},
      'observation_requests':[0,0,0,1,0,0,0],'pause_sync':'one pause:true without multi_step in each arm; never advancing fallback',
      'callbacks':STAGES,'paused_readback':'three immediate requested acknowledgements after matched pause synchronization',
      'callback_limits':'End-of-step UpdateInfo clocks; taps bracket Physics Update, not the internal collision/constraint solver. PostUpdate systems run in parallel. Observed publication order is not producer or causal order.',
      'geometry':{'links':LINKS,'fields':['engine collision XYZ/quaternion/RPY','center pose from verified identity collision offset','world linear/angular velocity','ECM link pose/velocity provenance only'],
                  'freshness':'engine-populated ECM readback, no independent producer timestamp'},
      'contacts':{'supports':SUPPORTS,'fields':['presence','count','point','normal','depth','force vector','reported wrench when available','Fn','producer stamp'],
                  'normal_relative_velocity':None,'tangential_relative_velocity':None,'missing_policy':'null/UNAVAILABLE, never synthesized zero',
                  'Fn_definition':'sum absolute dot(body_1_force_world_n, unit normal_world) over SUPPORT_GROUND points; observation only',
                  'freshness':'ContactSensorData may be held or filtered. Callback execution does not prove a new solve.'},
      'joints':['actual LEFT/RIGHT q guard','actual joint velocity','transmitted force/torque in joint frame'],
      'baseline':{'all_pairwise_valid_S0':True,'channels':['engine chassis XYZ/quaternion/RPY/velocities','LEFT/RIGHT center and collision poses and velocities','caster geometry/velocities where available','LEFT/RIGHT q and joint velocities','support topology/depth/Fn','joint wrench','command/logical DOWN/stopped state','exact clock'],
                  'numeric_caps':{'position_m':1e-10,'angle_rad':1e-11,'velocity':1e-10,'force_N':1e-8,'torque_N_m':1e-9,'depth_m':1e-10},
                  'instability_policy':'Any failed baseline pair blocks aggregate physical interpretation; no averaging away instability'},
      'first_change':{'threshold':'max(128 binary64 ulps over S0/stage values) + observed same-time S0/S1 repeatability and valid ZERO no-advance envelope, per channel',
                      'ties':'SAME_OBSERVABLE_STAGE; never order quantities within a callback','missing':'ORDERING_UNRESOLVED if required candidates unavailable',
                      'outputs':['first bitwise difference','first resolved difference','callback sequence/iteration/time','magnitude','provenance/freshness','replicate agreement']},
      'RIGHT_Z_reference_m':RIGHT_Z_REFERENCE,'RIGHT_Z_comparison_cap_m':1e-10,
      'Fn_delta_reference_N':FN_REFERENCE,'Fn_comparison_cap_N':1e-8,
      'weight_balance':{'expected_weight_N':24.5,'absolute_tolerance_N':0.01,'basis':'production mass 2.5 kg * gravity magnitude 9.8 m/s^2; verified from each generated SDF'},
      'contamination':{k:0 for k in ['treatment_Twist','pose_RPC','WorldPoseCmd','ResetPosition','production_sensor_consumption','planner_mutation','Action24_UP']},
      'closure_rule':'10 valid fresh cases, stable S0, five valid no-advance controls plus five ONE observations; complete observation only, no efficacy or mediator claim',
      'solver_observability':'SOLVER_INTERNAL_STATE_NOT_PUBLICLY_OBSERVABLE through installed Sim system interface; installed public API audit retained',
      'interpretation':'No root cause, engine bug, Z/preload/wrench causality, or mediator selection. Missing solver state stays unavailable.',
      'runtime_facts':'HOST_REQUIRED; static tests cannot establish physical change or ordering',
      'production_sha256':g.EXPECTED_SHA}


def write(path,value):
    path=Path(path).resolve()
    if not path.is_relative_to(DEFAULT_OUTPUT.resolve()):raise ValueError('write outside AN-R refused')
    d.ledger_io.atomic_json(path,value)


def guard_manifest():
    guard=preservation.guard_manifest()
    for root in (preservation.DEFAULT_OUTPUT,):
        for path in root.rglob('*'):
            if path.is_file():guard[str(path.resolve())]=g.sha(path)
    failure=host1_failure_contract()
    for item in failure['original_Host1_inventory']:
        path=HOST1/item['path'];guard[str(path.resolve())]=item['sha256']
    for path in (SOURCE,Path(__file__),ROOT/'tests/test_gazebo_physical_microstate_ordering.py',ROOT/'tools/gazebo_paused_physical_checkpoint.hh'):
        guard[str(path.resolve())]=g.sha(path)
    return guard


def build(directory):
    directory.mkdir(parents=True,exist_ok=True);library=(directory/'libaero_physical_microstate.so').resolve()
    flags=subprocess.run(['pkg-config','--cflags','--libs','gz-sim8','gz-plugin2','gz-transport13'],capture_output=True,text=True,check=True)
    command=['c++','-std=c++17','-shared','-fPIC','-Wl,-z,defs',str(SOURCE),'-o',str(library),*shlex.split(flags.stdout)]
    result=subprocess.run(command,capture_output=True,text=True)
    if result.returncode:raise RuntimeError(result.stderr)
    deps=subprocess.run(['ldd','-r',str(library)],capture_output=True,text=True,check=True)
    if 'not found' in deps.stdout or 'undefined symbol' in deps.stdout:raise RuntimeError(deps.stdout)
    info=subprocess.run(['gz','plugin','--info','--plugin',str(library)],capture_output=True,text=True)
    if info.returncode or any(name not in info.stdout for name in ['PhysicalMicrostateObserver','MicrostateBeforePhysics']):raise RuntimeError('microstate plugin registration failed: '+info.stderr)
    return library,{'command':command,'dependency_check':deps.stdout,'plugin_info':info.stdout,'source_sha256':g.sha(SOURCE),'library_sha256':g.sha(library)}



def instrument(path,info,library,case,directory):
    tree=ET.parse(path);world=tree.find('world');physics=world.findall("plugin[@name='gz::sim::systems::Physics']")
    if len(physics)!=1:raise ValueError('one Physics plugin required')
    topic=info['native']['topic']+'/physical_microstate'
    before=ET.Element('plugin',filename=str(library),name='aero_diagnostic::MicrostateBeforePhysics')
    after=ET.Element('plugin',filename=str(library),name='aero_diagnostic::PhysicalMicrostateObserver')
    for key,value in {'topic':topic,'service':topic+'/request','output':str(directory/'physical_microstate.ndjson')}.items():
        ET.SubElement(after,key).text=str(value)
    index=list(world).index(physics[0]);world.insert(index,before);world.insert(index+2,after)
    tree.write(path,encoding='utf-8',xml_declaration=True)
    validate_sdf(path)
    info['microstate_observer']={'topic':topic,'service':topic+'/request','case':case,'read_only':True,
      'callback_stages':list(STAGES),'link_center_basis':'all five link collision offsets identity, verified from diagnostic SDF'}
    info['diagnostic_sdf_sha256']=g.sha(path)
    # Preserve the shared capture harness exact readback equality check. Runtime
    # metadata must be JSON-native before it enters that check.
    if json.loads(json.dumps(info,allow_nan=False))!=info:raise ValueError('diagnostic metadata is not exactly JSON roundtrip stable')
    return path,info


def validate_sdf(path):
    tree=ET.parse(path);nodes=tree.findall('world/plugin');names=[x.get('name') for x in nodes]
    wanted=['aero_diagnostic::MicrostateBeforePhysics','gz::sim::systems::Physics','aero_diagnostic::PhysicalMicrostateObserver']
    indices=[names.index(x) if names.count(x)==1 else -1 for x in wanted]
    if indices[0]<0 or indices!=list(range(indices[0],indices[0]+3)):raise ValueError('adjacent Physics taps missing or reordered')
    if any('system_priority' in child.tag for node in nodes for child in node):raise ValueError('nondefault priority unsupported')
    if any('PhaseIsolationQualification' in x or 'EcmHierarchyFreshnessObserver' in x or 'NaturalQPhaseObserver' in x for x in names):raise ValueError('unrequested qualification plugin')
    model=tree.find("world/model[@name='simple_agent']")
    for link,col in zip(LINKS,COLLISIONS):
        node=model.find(f"link[@name='{link}']/collision[@name='{col}']")
        if node is None or node.find('pose') is not None:raise ValueError('identity collision offset required: '+link)
    mass=sum(float(x.findtext('inertial/mass')) for x in model.findall('link'))
    gravity=[float(x) for x in tree.findtext('world/gravity').split()]
    if mass!=2.5 or gravity!=[0.,0.,-9.8]:raise ValueError('weight reference changed')
    if tree.findtext('world/physics/max_step_size')!='0.001':raise ValueError('1ms physics required')
    return {'adjacent_taps':wanted,'default_priority':True,'identity_collision_offsets':list(LINKS),'mass_kg':mass,'weight_N':24.5}


def finite_number(x):return type(x) in (int,float) and math.isfinite(x)


def pose(value):
    if value is None:return None
    xyz=value.get('position_world_m');quat=value.get('orientation_world_xyzw')
    if not isinstance(xyz,list) or len(xyz)!=3 or not isinstance(quat,list) or len(quat)!=4 or not all(finite_number(x) for x in xyz+quat):raise g.InvalidCapture('malformed geometry')
    if abs(sum(x*x for x in quat)-1)>1e-10:raise g.InvalidCapture('nonunit geometry quaternion')
    value['roll_pitch_yaw_rad']=list(g.checkpoints.rpy(quat));return value


def decorate_state(s):
    if set(s['geometry'])!=set(LINKS) or set(s['supports'])!=set(SUPPORTS) or set(s['generalized_q'])!={'left','right'}:raise g.InvalidCapture('microstate channel set differs')
    for side in ('left','right'):
        if not finite_number(s['generalized_q'][side]):raise g.InvalidCapture('actual q guard unavailable')
    for name,v in s['geometry'].items():
        v['collision_pose']=pose(v.get('collision_pose'));v['ECM_link_pose']=pose(v.get('ECM_link_pose'))
        v['center_pose']=copy.deepcopy(v['collision_pose'])
        for field in ('linear_velocity_world_m_s','angular_velocity_world_rad_s','ECM_link_linear_velocity','ECM_link_angular_velocity'):
            a=v.get(field)
            if a is not None and (not isinstance(a,list) or len(a)!=3 or not all(finite_number(x) for x in a)):raise g.InvalidCapture('malformed velocity')
        if name in LINKS[:3] and (v['collision_pose'] is None or v.get('linear_velocity_world_m_s') is None or v.get('angular_velocity_world_rad_s') is None):raise g.InvalidCapture('required drive/chassis engine geometry unavailable')
    for v in s['supports'].values():
        available=v.get('component_available') is True
        v['contact_present']=bool(v['contacts']) if available else None
        v['contact_count']=len(v['contacts']) if available else None
        v['point_count']=sum(len(c['points']) for c in v['contacts']) if available else None
        force=0.;complete=available
        for c in v['contacts']:
            for pt in c['points']:
                pt['normal_relative_velocity_m_s']=None;pt['tangential_relative_velocity_m_s']=None
                if c['pair_classification']!='SUPPORT_GROUND':continue
                f=pt.get('body_1_force_world_n');n=pt.get('normal_world')
                if f is None or n is None:complete=False;continue
                if len(f)!=3 or len(n)!=3 or not all(finite_number(x) for x in f+n):raise g.InvalidCapture('malformed contact force/normal')
                norm=math.sqrt(sum(x*x for x in n))
                if norm==0:complete=False;continue
                force+=abs(sum(x*y for x,y in zip(f,n))/norm)
        v['Fn_N']=force if complete else None
        v['freshness']='PRODUCER_STAMP_RECORDED_NOT_ASSUMED_CURRENT' if v.get('component_producer_stamp_ns') is not None else 'HELD_OR_FILTERED_COMPONENT_NO_PRODUCER_STAMP'
    for v in s['joint_wrench'].values():
        v.setdefault('actual_velocity_rad_s',None)
        for field in ('force_xyz_N','torque_xyz_N_m'):
            v.setdefault(field,None)
            if v[field] is not None and (len(v[field])!=3 or not all(finite_number(x) for x in v[field])):raise g.InvalidCapture('malformed joint wrench')
        v['producer_timestamp_ns']=None
    s['normal_relative_velocity_m_s']=None;s['tangential_relative_velocity_m_s']=None
    return s


def decorate(packet):
    decorate_state(packet['microstate'])
    for t in packet['callback_trace']:decorate_state(t['microstate'])
    return packet


def flatten(value,prefix=''):
    if isinstance(value,dict):
        return {k:v for key,x in value.items() for k,v in flatten(x,prefix+'.'+key if prefix else key).items()}
    if isinstance(value,list):return {k:v for i,x in enumerate(value) for k,v in flatten(x,f'{prefix}[{i}]').items()}
    return {prefix:value}


def observed(s):
    # IDs/provenance/timestamps do not become physical numerical variables.
    geometry={k:{f:v.get(f) for f in ['center_pose','collision_pose','linear_velocity_world_m_s','angular_velocity_world_rad_s']} for k,v in s['geometry'].items()}
    supports={k:{'contact_present':v['contact_present'],'contact_count':v['contact_count'],'point_count':v['point_count'],'Fn_N':v['Fn_N'],
      'contacts':[{'pair_classification':c['pair_classification'],'points':c['points']} for c in v['contacts']]} for k,v in s['supports'].items()}
    joints={k:{f:v.get(f) for f in ['actual_velocity_rad_s','force_xyz_N','torque_xyz_N_m','state']} for k,v in s['joint_wrench'].items()}
    return flatten({'geometry':geometry,'generalized_q':s['generalized_q'],'supports':supports,'joint_wrench':joints,
                    'normal_relative_velocity_m_s':None,'tangential_relative_velocity_m_s':None,'solver_internal_state':None})


def bit_equal(a,b):
    if finite_number(a) and finite_number(b):return struct.pack('>d',float(a))==struct.pack('>d',float(b))
    return type(a) is type(b) and a==b


def delta_vector(a,b):
    result={}
    for key in sorted(a.keys()|b.keys()):
        x=a.get(key);y=b.get(key)
        result[key]={'S0':x,'S1':y,'delta':y-x if finite_number(x) and finite_number(y) else None,
          'bitwise_equal':bit_equal(x,y),'status':'NUMERIC' if finite_number(x) and finite_number(y) else 'UNAVAILABLE' if x is None or y is None else 'CATEGORICAL'}
    return result


def statistics_vector(values):
    if not values or not all(finite_number(x) for x in values):return {'vector':values,'status':'UNAVAILABLE','missing_not_zero':True}
    signs=['zero' if x==0 else 'positive' if x>0 else 'negative' for x in values]
    return {'vector':values,'status':'AVAILABLE','min':min(values),'max':max(values),'mean':statistics.mean(values),
      'median':statistics.median(values),'population_standard_deviation':statistics.pstdev(values),
      'sample_standard_deviation':statistics.stdev(values) if len(values)>1 else None,
      'signs':signs,'sign_consistent':len(set(signs))==1,'bitwise_equal':all(bit_equal(values[0],x) for x in values)}


def noise_envelope(packets):
    vectors=[observed(x['microstate']) for x in packets];keys=set().union(*(x.keys() for x in vectors));noise={}
    for k in keys:
        values=[x.get(k) for x in vectors]
        noise[k]=max(values)-min(values) if all(finite_number(x) for x in values) else None
    return noise


def candidate_groups(vector):
    groups={'RIGHT_Z':['geometry.right_wheel.center_pose.position_world_m[2]'],
      'LEFT_Z':['geometry.left_wheel.center_pose.position_world_m[2]'],
      'CHASSIS_Z':['geometry.body.center_pose.position_world_m[2]'],
      'roll':['geometry.body.center_pose.roll_pitch_yaw_rad[0]'],
      'pitch':['geometry.body.center_pose.roll_pitch_yaw_rad[1]']}
    for side in SUPPORTS:
        groups[side+'_Fn']=['supports.'+side+'.Fn_N']
        groups[side+'_depth']=[k for k in vector if k.startswith('supports.'+side+'.contacts') and k.endswith('.depth_m')]
        groups[side+'_topology']=[k for k in vector if k.startswith('supports.'+side) and (k.endswith('count') or k.endswith('contact_present') or k.endswith('pair_classification'))]
    for side in ('left','right'):groups[side+'_transmitted_wrench']=[k for k in vector if k.startswith('joint_wrench.'+side+'.') and ('force_xyz' in k or 'torque_xyz' in k)]
    return groups


def first_changes(s0,stages,noise):
    baseline=observed(s0);rows={};stage_vectors=[observed(stage['microstate']) for stage in stages]
    for key,x in baseline.items():
        first_bits=None;first_resolved=None;available=finite_number(x);max_floor=0.
        for stage,vector in zip(stages,stage_vectors):
            y=vector.get(key)
            loc={k:stage[k] for k in ['stage','callback_sequence','iteration','sim_time_ns','paused']}
            if not bit_equal(x,y) and first_bits is None:first_bits={**loc,'S0':x,'value':y,'delta':y-x if finite_number(x) and finite_number(y) else None}
            if not finite_number(x) or not finite_number(y):
                if x is not None and y is not None and x!=y and first_resolved is None:first_resolved={**loc,'S0':x,'value':y,'delta':None,'threshold':None}
                continue
            floor=128*max(math.ulp(float(x)),math.ulp(float(y)));max_floor=max(max_floor,floor)
            envelope=noise.get(key,0.)
            if envelope is None:continue
            threshold=floor+envelope
            if abs(y-x)>threshold and first_resolved is None:first_resolved={**loc,'S0':x,'value':y,'delta':y-x,'threshold':threshold}
        rows[key]={'first_bitwise_difference':first_bits,'first_resolved_change':first_resolved,'binary64_floor_max':max_floor,
          'ZERO_and_repeatability_envelope':noise.get(key),'status':'NUMERIC' if available else 'UNAVAILABLE_OR_CATEGORICAL',
          'freshness':'HELD_OR_FILTERED_POSSIBLE; no producer chronology' if key.startswith(('supports.','joint_wrench.')) else 'ENGINE_POPULATED_COMPONENT_OBSERVED_AT_CALLBACK; no producer timestamp'}
    candidates={}
    for group,keys in candidate_groups(baseline).items():
        changed=[rows[k]['first_resolved_change'] for k in keys if rows.get(k,{}).get('first_resolved_change')]
        earliest=min(changed,key=lambda x:stage_rank(x['stage'])) if changed else None
        candidates[group]={'channels':keys,'first_resolved_change':earliest,'channels_available':bool(keys) and all(baseline.get(k) is not None for k in keys),
          'interpretation':'Earliest resolved recorded value change; no within-callback physical order or causality'}
    required=['RIGHT_Z','LEFT_Z','CHASSIS_Z','roll','pitch','right_wheel_depth','left_wheel_depth','right_wheel_Fn','left_wheel_Fn','front_caster_Fn','rear_caster_Fn','right_transmitted_wrench','left_transmitted_wrench']
    core=[candidates[k] for k in required];changed=[x['first_resolved_change'] for x in core]
    if not all(x['channels_available'] for x in core) or any(x is None for x in changed):classification='ORDERING_UNRESOLVED'
    elif len({x['stage'] for x in changed})==1:classification='SAME_OBSERVABLE_STAGE'
    else:
        rank=min(stage_rank(x['stage']) for x in changed);earliest=[k for k,x in zip(required,changed) if stage_rank(x['stage'])==rank]
        families={('GEOMETRY_FIRST' if k in ['RIGHT_Z','LEFT_Z','CHASSIS_Z','roll','pitch'] else 'CONTACT_DEPTH_FIRST' if k.endswith('_depth') else 'WRENCH_OR_FORCE_FIRST') for k in earliest}
        classification=next(iter(families)) if len(families)==1 else 'ORDERING_UNRESOLVED'
    return {'all_observables':rows,'candidates':candidates,'classification':classification,'scope':'EXTERNALLY_OBSERVED_COMPONENT_CHANGE_ONLY; physical producer/substep ordering remains unresolved'}


def stage_rank(stage):return (*STAGES,'paused_readback').index(stage)


def verify_capture(record,spec):
    e=record['phase_qualification'];packets=e.get('packets',[])
    if not e.get('qualification_completed') or len(packets)!=7:raise g.InvalidCapture('microstate capture incomplete; stage='+str(e.get('failed_stage'))+'; '+str(e.get('qualification_error') or record.get('physical_failure')))
    if [x['request_id'] for x in packets]!=list(range(1,8)) or [x['operation_code'] for x in packets]!=[0,0,0,1,0,0,0]:raise g.InvalidCapture('readback request sequence differs')
    if any(x['error'] or not x['paused'] for x in packets):raise g.InvalidCapture('paused acknowledgement error')
    bi,bns=d.exact_stats(e['PRE_marker']);ai,ans=d.exact_stats(e['POST_marker']);n=spec['iterations']
    if (ai-bi,ans-bns)!=(n,n*1000000):raise g.InvalidCapture('exact ZERO/ONE dose violated')
    if d.exact_stats(e['before_optional_tick_stats'])!=(bi,bns):raise g.InvalidCapture('before tick stats differ')
    if d.exact_stats(e['after_optional_tick_stats'])!=(ai,ans):raise g.InvalidCapture('after tick stats differ')
    for packet in packets[:4]:
        if (packet['iteration'],packet['sim_time_ns'])!=(bi,bns):raise g.InvalidCapture('S0 callback clock mismatch')
    for packet in packets[4:]:
        if (packet['iteration'],packet['sim_time_ns'])!=(ai,ans):raise g.InvalidCapture('S1 callback clock mismatch')
    if any(b['postupdate_count']<=a['postupdate_count'] for a,b in zip(packets,packets[1:])):raise g.InvalidCapture('acknowledgements unordered')
    if packets[-1]['advancing_callback_count']-packets[0]['advancing_callback_count']!=n:raise g.InvalidCapture('advancing callbacks differ')
    auto=e['advancing_observations']
    if len(auto)!=n or any(x['paused'] or (x['iteration'],x['sim_time_ns'])!=(ai,ans) for x in auto):raise g.InvalidCapture('advancing snapshot missing/duplicate')
    sequences=[]
    for packet in packets+auto:
        if packet['WorldPoseCmd_active'] or packet['WorldPoseCmd_active_PRE'] or packet['WorldPoseCmd_observations']!=packets[0]['WorldPoseCmd_observations']:raise g.InvalidCapture('WorldPoseCmd contamination')
        trace=packet['callback_trace']
        if [x['stage'] for x in trace]!=list(STAGES):raise g.InvalidCapture('callback stage order differs')
        for t in trace:
            if any(t[k]!=packet[k] for k in ['iteration','sim_time_ns','paused']):raise g.InvalidCapture('callback clock differs')
        for point in trace:
            decorate_state(point['microstate'])
        decorate_state(packet['microstate'])
        seq=[x['callback_sequence'] for x in trace]
        if seq!=sorted(set(seq)):raise g.InvalidCapture('callback sequence unordered')
        sequences.extend(seq)
        if trace[-1]['microstate']!=packet['microstate']:raise g.InvalidCapture('PostUpdate endpoint differs from trace')
    if len(set(sequences))!=len(sequences):raise g.InvalidCapture('duplicate callback trace')
    if sorted(sequences)!=list(range(1,len(sequences)+1)):raise g.InvalidCapture('callback sequence gap')
    if auto:
        temporal=[*packets[:4],*auto,*packets[4:]]
    else:temporal=packets
    if any(b['callback_trace'][0]['callback_sequence']<=a['callback_trace'][-1]['callback_sequence'] for a,b in zip(temporal,temporal[1:])):raise g.InvalidCapture('global callback chronology differs')
    g.y.stopped_chunk(e['stopped_chunk'])
    if e['completed_brake']['active_physics_transactions']!=0 or round(e['stopped_chunk']['simulation_end']*1e9)!=bns:raise g.InvalidCapture('stopped boundary incoherent')
    hist=[x for x in record['events'] if x.get('canonical_index') in range(8,24)]
    if [x['canonical_index'] for x in hist]!=list(range(8,24)) or any(x.get('exception') or x.get('terminated') for x in hist):raise g.InvalidCapture('canonical Actions08-23 incomplete')
    plan=record['terminal_entry_history']['production_plan']
    if plan['request']['previous_command']!=g.dm.gazebo_physics_twist('down') or plan['request']['transition_type']!='LINEAR_REVERSAL' or [x['kind'] for x in plan['phases']]!=['BRAKE_LINEAR','ACQUIRE_LINEAR']:raise g.InvalidCapture('canonical reversal plan differs')
    if STOP not in json.dumps(record['events'][-1].get('exception')):raise g.InvalidCapture('pre-UP abort missing')
    logical=e['host_PRE']['logical']
    if logical.get('env_previous_action')!='down' or logical.get('adapter_previous_action')!='down' or logical.get('controller_command')!={'linear':{'x':0.},'angular':{'z':0.}}:raise g.InvalidCapture('stopped DOWN command boundary differs')
    return command_audit(record,e)


def analyze(record,spec):
    audit=verify_capture(record,spec);e=record['phase_qualification'];packets=e['packets'];before=packets[:3];after=packets[4:]
    s0=before[-1]['microstate'];s1=after[0]['microstate'];a=observed(s0);b=observed(s1)
    noise0=noise_envelope(before);noise1=noise_envelope(after)
    noise={k:max(v,noise1[k]) if v is not None and noise1.get(k) is not None else None for k,v in noise0.items()}
    stages=copy.deepcopy(e['advancing_observations'][0]['callback_trace']) if spec['iterations'] else []
    paused=after[0];stages.append({'stage':'paused_readback','callback_sequence':paused['callback_trace'][-1]['callback_sequence'],
      'iteration':paused['iteration'],'sim_time_ns':paused['sim_time_ns'],'paused':True,'microstate':s1})
    first=first_changes(s0,stages,noise)
    return {'case_id':spec['case_id'],'arm':spec['arm'],'capture_valid':True,'classification':first['classification'],
      'measurements':delta_vector(a,b),'S0':before,'S1':after,'command_audit':audit,
      'delta_iterations':after[0]['iteration']-before[-1]['iteration'],'delta_sim_time_ns':after[0]['sim_time_ns']-before[-1]['sim_time_ns'],
      'baseline_command_state':e['host_PRE'],'baseline_plan':record['terminal_entry_history']['production_plan'],
      'stopped_contract':{'completed':e['completed_brake'],'chunk':e['stopped_chunk']},'stages':stages,'noise_envelope':noise,
      'first_change':first,'q_guard':{k:s1['generalized_q'][k]-s0['generalized_q'][k] for k in ['left','right']},
      'zero_readback_noise':delta_vector(a,b) if spec['iterations']==0 else None,
      'ECM_provenance_comparison_only':delta_vector(flatten({k:{f:v.get(f) for f in ['ECM_link_pose','ECM_link_linear_velocity','ECM_link_angular_velocity']} for k,v in s0['geometry'].items()}),
         flatten({k:{f:v.get(f) for f in ['ECM_link_pose','ECM_link_linear_velocity','ECM_link_angular_velocity']} for k,v in s1['geometry'].items()})),
      'causal_interpretation':'NONE; observational only; q guard is not mediator'}


def baseline_cap(key):
    if 'force_xyz' in key or 'Fn_N' in key:return 1e-8
    if 'torque_xyz' in key:return 1e-9
    if 'orientation' in key or 'roll_pitch_yaw' in key or 'generalized_q' in key:return 1e-11
    return 1e-10


def baseline_vector(r):
    s=r['S0'][-1]
    return {**observed(s['microstate']),**flatten({'command':{'logical':r['baseline_command_state']['logical'],
      'production_sensor':{k:v for k,v in r['baseline_command_state']['production_sensor'].items() if k!='cached_observation_identity'},
      'active_physics_transactions':r['baseline_command_state']['production_step_tracker']['active_depth']},
      'plan':r['baseline_plan'],'clock':{k:s[k] for k in ['iteration','sim_time_ns','paused']},
      'stopped':{'active_physics_transactions':r['stopped_contract']['completed']['active_physics_transactions'],
                 'simulation_end':r['stopped_contract']['chunk']['simulation_end']}})}


def baseline_equivalence(results):
    valid=[r for r in results if r['capture_valid']];pairs=[]
    for i,left in enumerate(valid):
        a=baseline_vector(left)
        for right in valid[i+1:]:
            b=baseline_vector(right);bad=[]
            for key in a.keys()|b.keys():
                x=a.get(key);y=b.get(key)
                numeric=finite_number(x) and finite_number(y)
                exact=key.startswith(('command.','plan.','clock.','stopped.')) or 'count' in key or 'contact_present' in key
                equal=abs(y-x)<=baseline_cap(key) if numeric and not exact else key in a and key in b and x==y
                if not equal:bad.append({'channel':key,'left':x,'right':y,'cap':baseline_cap(key) if numeric and not exact else 0})
            pairs.append({'left':left['case_id'],'right':right['case_id'],'pass':not bad,'differences':bad})
    return {'status':'BASELINE_UNSTABLE' if any(not x['pass'] for x in pairs) else 'OBSERVED_BASELINE_EQUIVALENT' if len(valid)>1 else 'INSUFFICIENT_VALID_BASELINES',
      'valid_cases':len(valid),'pairwise_checks':pairs,'scope':'Observed components, including held contacts; no fresh contact production implied.'}


def target_comparison(values,target,cap):
    stat=statistics_vector(values)
    return {**stat,'target':target,'deviations':[x-target if finite_number(x) else None for x in values],
      'matches':len(values)==5 and all(finite_number(x) and abs(x-target)<=cap for x in values),'cap':cap}


def aggregate(results):
    baseline=baseline_equivalence(results);valid=[r for r in results if r['capture_valid']];zeros=[r for r in valid if r['arm']==ZERO];ones=[r for r in valid if r['arm']==ONE]
    complete=len(results)==len(valid)==10 and len(zeros)==len(ones)==5
    result={'phase':'AN-R','status':'QUALIFICATION_CAPTURE_COMPLETE' if complete else 'CAPTURE_FAILED','classification':'ORDERING_UNRESOLVED',
      'baseline_equivalence':baseline,'results':results,'physical_interpretation_permitted':False,'causal_runtime_ready':False,
      'Action24_outcomes_tested':False,'solver_observability':'SOLVER_INTERNAL_STATE_NOT_PUBLICLY_OBSERVABLE','mediator_selected':False}
    if baseline['status']!='OBSERVED_BASELINE_EQUIVALENT':
        result['classification']='BASELINE_UNSTABLE' if baseline['status']=='BASELINE_UNSTABLE' else 'ORDERING_UNRESOLVED'
        result['interpretation_blocked']='Baseline unstable or insufficient; no aggregate physical interpretation'
        return result
    keys=set().union(*(r['measurements'].keys() for r in valid)) if valid else set()
    zero_envelope={}
    for key in keys:
        values=[]
        for r in zeros:
            delta=r['measurements'].get(key,{}).get('delta');noise=r['noise_envelope'].get(key)
            values.append(max(abs(delta),noise) if finite_number(delta) and finite_number(noise) else None)
        zero_envelope[key]=max(values) if values and all(finite_number(x) for x in values) else None
    # Re-evaluate earliest resolved changes against all valid ZERO controls before interpreting order.
    for r in valid:
        noise={key:max(zero_envelope[key],r['noise_envelope'][key]) if finite_number(zero_envelope.get(key)) and finite_number(r['noise_envelope'].get(key)) else None for key in keys}
        r['first_change']=first_changes(r['S0'][-1]['microstate'],r['stages'],noise)
    result['ZERO_noise_envelope']=zero_envelope
    result['ONE_delta_statistics']={key:statistics_vector([r['measurements'].get(key,{}).get('delta') for r in ones]) for key in sorted(keys)}
    result['ZERO_delta_statistics']={key:statistics_vector([r['measurements'].get(key,{}).get('delta') for r in zeros]) for key in sorted(keys)}
    zkey='geometry.right_wheel.center_pose.position_world_m[2]'
    right=target_comparison([r['measurements'][zkey]['delta'] for r in ones],RIGHT_Z_REFERENCE,1e-10)
    right['ZERO_measurement_stable']=len(zeros)==5 and all(finite_number(r['measurements'].get(zkey,{}).get('delta')) for r in zeros) and finite_number(zero_envelope.get(zkey)) and zero_envelope[zkey]<=1e-11
    right['matches']=right['matches'] and right['ZERO_measurement_stable']
    preload={k:target_comparison([r['measurements']['supports.'+k+'.Fn_N']['delta'] for r in ones],ref,1e-8) for k,ref in FN_REFERENCE.items()}
    for k,v in preload.items():
        key='supports.'+k+'.Fn_N'
        v['ZERO_measurement_stable']=len(zeros)==5 and all(finite_number(r['measurements'].get(key,{}).get('delta')) for r in zeros) and finite_number(zero_envelope.get(key)) and zero_envelope[key]<=1e-9
        v['matches']=v['matches'] and v['ZERO_measurement_stable']
    result['RIGHT_Z_replication']=right;result['support_preload_replication']=preload
    result['actual_q_guard']={'RIGHT_delta_vector_rad':[r['q_guard']['right'] for r in ones],
      'unchanged':len(ones)==5 and all(r['q_guard']['right']==0. for r in ones),'role':'guard only; no intervention or causal analysis'}
    weights=[]
    for r in ones:
        item={'case_id':r['case_id']}
        for label,index in [('S0',-1),('S1',0)]:
            f=[v['Fn_N'] for v in r[label][index]['microstate']['supports'].values()]
            total=sum(f) if all(finite_number(x) for x in f) else None
            item[label]={'sum_Fn_N':total,'expected_weight_N':24.5,'residual_N':total-24.5 if total is not None else None,'approximately_balanced':total is not None and abs(total-24.5)<=.01}
        weights.append(item)
    result['weight_balance']=weights
    result['ordering_table']={name:{'replicate_rows':[r['first_change']['candidates'][name] for r in ones],
       'same_first_stage_across_replicates':len({(r['first_change']['candidates'][name]['first_resolved_change'] or {}).get('stage') for r in ones})==1,
       'first_change_magnitude_statistics':statistics_vector([(r['first_change']['candidates'][name]['first_resolved_change'] or {}).get('delta') for r in ones]),
       'provenance':'Physics-populated collision geometry/world velocities via ECM; ContactSensorData; Joint.TransmittedWrench; no producer timestamps fabricated',
       'freshness_confidence':'Observed component readbacks only; no substep/producer ordering'} for name in candidate_groups(observed(valid[0]['S0'][-1]['microstate']))}
    labels=[]
    if complete and right['matches']:labels.append('RIGHT_Z_MARKER_REPLICATED')
    if complete and all(v['matches'] for v in preload.values()):labels.append('SUPPORT_PRELOAD_CHANGE_REPLICATED')
    if complete and all(r['first_change']['candidates']['RIGHT_Z']['first_resolved_change'] is not None for r in ones):labels.append('PHYSICAL_MICROSTATE_CHANGE_REPLICATED')
    ordering={r['first_change']['classification'] for r in ones}
    result['classification']=next(iter(ordering)) if len(ordering)==1 and complete else 'ORDERING_UNRESOLVED'
    result['replication_classes']=labels;result['physical_interpretation_permitted']=complete
    result['interpretation']='Observation-stage ordering only; held/filtered contact and wrench production times remain unknown. No causal mediator, root cause, or engine defect inferred.'
    return result



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


def microstate_hook(case_id,evidence,library):
    spec=next(s for s in schedule() if s['case_id']==case_id)
    def hook(adapter,case,native,row,it,audit):
        if case!=case_id or evidence:raise g.InvalidCapture('unexpected/repeated natural boundary')
        evidence.update(phase='AN-R',spec=spec,failed_stage='stopped_boundary_certification')
        g.y.stopped_chunk(row);completed=g.y.completed_brake_checkpoint(adapter,row)
        marker=g.dm.physics_mark(adapter);bi,bns=d.exact_stats(marker)
        audit['phase']='treatment';audit['adapter']=adapter
        evidence.update(phase='AN-R',spec=spec,completed_brake=completed,stopped_chunk=copy.deepcopy(row),PRE_marker=marker,
          window_start=len(audit['events']),host_PRE=q.boundary_state(adapter))
        evidence['host_PRE']['prohibited_transport_cursors']=q.prohibited_cursors(audit)
        packets=[];automatic=[];topic=native.topic+'/physical_microstate';transport=adapter.env.transport
        try:
            with q.diagnostic_codec(transport) as descriptors:
                evidence['diagnostic_transport_descriptors']=descriptors
                transport.subscribe(topic,'StringMsg');cursor=transport.cursor(topic)
                evidence['publisher_readiness']=transport.wait_for_topic(topic,'StringMsg',timeout=adapter.env.timeout)
                evidence['service_readiness']=transport.wait_for_service(topic+'/request','Int32','Boolean',timeout=adapter.env.timeout)
                evidence['failed_stage']='S0_and_arm_readbacks'
                for code in (0,0,0,1):
                    packet,cursor=read_packet(adapter,topic,code,cursor,automatic);packets.append(packet)
                evidence['before_optional_tick_stats']=q.fresh_paused_stats(adapter)
                evidence['failed_stage']='optional_single_tick'
                if spec['iterations']==1:evidence['single_advance']=d.single_advance(adapter,1)
                evidence['failed_stage']='pause_synchronization'
                sync={};evidence['pause_synchronization']=sync
                evidence['after_optional_tick_stats']=g.y.synchronize_paused(adapter,bi+spec['iterations'],bns+spec['sim_time_delta_ns'],sync)
                evidence['failed_stage']='S1_readbacks'
                for _ in range(3):
                    packet,cursor=read_packet(adapter,topic,0,cursor,automatic);packets.append(packet)
                evidence.update(POST_marker=q.fresh_paused_stats(adapter),host_POST=q.boundary_state(adapter),qualification_completed=True,failed_stage=None)
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
    q.qualification_hook,q.instrument=microstate_hook,instrument
    try:yield
    finally:q.qualification_hook,q.instrument=old_hook,old_instrument


def capture(*args):
    # q.capture provides canonical history, lifecycle recording and intentional pre-UP abort.
    # Its setter hook and mutating SDF instrumenter are replaced before it is entered.
    with read_only_capture_hooks():return q.capture(*args)


def command_audit(record,e):
    window=record['command_audit'][e['window_start']:e['window_end']]
    if any(not isinstance(event.get('service'),str) or not isinstance(event.get('kind'),str) for event in window):raise g.InvalidCapture('malformed command audit event')
    g.audit_window(record['command_audit'],e['window_start'],e['window_end'])
    reads=[];controls=[]
    for event in window:
        if event.get('kind')!='RPC':raise g.InvalidCapture('non-RPC event during natural observation')
        if event.get('request_type')=='Int32' and event.get('service','').endswith('/physical_microstate/request'):reads.append(event)
        elif event.get('request_type')=='WorldControl':controls.append(event)
        else:raise g.InvalidCapture('unexpected RPC in natural treatment: '+str(event))
    if len(reads)!=7 or [x.get('payload') for x in reads]!=[{'data':c} for c in (0,0,0,1,0,0,0)]:raise g.InvalidCapture('seven ordered read-only observer requests required')
    expected_order=[('Int32',{'data':c}) for c in (0,0,0,1)]
    if e['spec']['iterations']:expected_order.append(('WorldControl',{'pause':True,'multi_step':1}))
    expected_order += [('WorldControl',{'pause':True})]+[('Int32',{'data':0}) for _ in range(3)]
    if [(x.get('request_type'),x.get('payload')) for x in window]!=expected_order:raise g.InvalidCapture('observation/control chronological sequence differs')
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



def solver_audit():
    roots=[Path('/usr/include/gz/physics7/gz/physics'),Path('/usr/include/gz/sim8/gz/sim')]
    files=[f for root in roots for f in sorted(root.rglob('*.hh'))]
    signatures=['GetContactsFromLastStep','GetTransmittedWrench','GetJointForce','GetSolver']
    matches={name:[] for name in signatures}
    for f in files:
        for number,line in enumerate(f.read_text().splitlines(),1):
            for name in signatures:
                if name in line:matches[name].append({'path':str(f),'line':number,'text':line.strip()})
    binaries={}
    dart_symbols=[]
    for path in [Path('/lib/x86_64-linux-gnu/libdart.so.6.13'),Path('/lib/x86_64-linux-gnu/libgz-physics7-dartsim-plugin.so.7'),Path('/lib/x86_64-linux-gnu/libgz-sim8-physics-system.so.8')]:
        if path.exists():binaries[str(path.resolve())]=g.sha(path)
    dart=Path('/lib/x86_64-linux-gnu/libdart.so.6.13')
    if dart.exists():
        symbols=subprocess.run(['nm','-D','--demangle',str(dart)],capture_output=True,text=True,check=True)
        dart_symbols=[line.split(' T ',1)[-1] for line in symbols.stdout.splitlines() if ' T ' in line and any(x in line for x in ['getConstraintForces(', 'getConstraintImpulses(', 'getConstraintSolver(', 'getLastCollisionResult(', 'getNumConstraints('])]
    return {'classification':'SOLVER_INTERNAL_STATE_NOT_PUBLICLY_OBSERVABLE',
      'scope':'Installed Gazebo Sim system/ECM and gz-physics7 public headers; no private Physics engine handle or separate DART world created',
      'public_readbacks':matches,'public_header_sha256':{str(f):g.sha(f) for f in files},
      'installed_binary_sha256':binaries,'DART_exported_getters':dart_symbols,
      'DART_access_limit':'Exported getters exist, but installed public Sim observer APIs do not supply live DART world/skeleton handles. Symbols alone do not establish usable ABI access; no opaque-pointer casts, private engine access, or independently constructed world.',
      'DART_development_headers_present':any(Path(x).exists() for x in ['/usr/include/dart','/usr/include/dart6','/usr/include/dart6/dart']),
      'available':['ContactSensorData point/normal/depth/force','WorldPose and world velocities','Joint.Position/Velocity/TransmittedWrench'],
      'not_exposed_to_this_Sim_system':['constraint impulse','contact lambda','solver iteration diagnostics','constraint Jacobian','generalized constraint force vector'],
      'limits':'GetJointForce is a public joint applied-force getter, not proof of a solver multiplier. GetSolver returns solver identity, not iteration state. GetContactsFromLastStep provides contact outputs, not solve-internal chronology. DART engine encapsulation is not bypassed.',
      'private_engine_access':False,'engine_mutation':False,'Gazebo_patch':False}


def static_contract():
    text=SOURCE.read_text();runtime='\n'.join(inspect.getsource(f) for f in (microstate_hook,read_packet,capture,instrument))
    for token in ('.ResetPosition(', 'JointPositionReset','SetPosition(', 'SetVelocity(', 'SetForce(', 'SetChanged(', 'SetParentEntity(', 'msgs::Twist','JointForceCmd','JointVelocityCmd','multi_step','step_simulation'):
        if token in text:raise ValueError('observer mutation token: '+token)
    for token in ('_refresh(', 'publish(', 'set_pose', 'ResetPosition('):
        if token in runtime:raise ValueError('runner treatment mutation token: '+token)
    for token in ('Snapshot(ecm)','Update/before_Physics_Update','Update/after_Physics_Update','PreUpdate','PostUpdate/const_ECM','std::setprecision(17)','front_caster','rear_caster','joint.Position(ecm)'):
        if token not in text:raise ValueError('observer channel/stage missing: '+token)
    if len(schedule())!=10 or sum(s['arm']==ZERO for s in schedule())!=5:raise ValueError('ten-case contract differs')
    if [x['arm'] for x in schedule()]!=[ZERO,ONE,ONE,ZERO,ZERO,ONE,ONE,ZERO,ZERO,ONE]:raise ValueError('frozen order differs')
    if 'd.single_advance(adapter,1)' not in inspect.getsource(microstate_hook):raise ValueError('one-step path missing')
    # Accepted capture library only; no inherited experiment entry point or legacy phase evaluation.
    for node in ast.walk(ast.parse(Path(__file__).read_text())):
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and isinstance(node.func.value,ast.Name):
            if node.func.value.id in ('q','preservation','g','d') and node.func.attr in ('run','preflight','analyze','phases','phase_from','matrix'):
                raise ValueError('predecessor experiment/phase path forbidden')
    return {'observer_read_only':True,'runner_observation_only':True,'no_predecessor_experiment_entrypoint':True,
      'guard_only_actual_q':True,'legacy_phase_not_computed':True,'callbacks':STAGES,
      'runtime_assertions':'HOST_REQUIRED','no_solver_internals_inferred':True}


def host1_failure_contract():
    failure=json.loads(HOST1_FORENSICS.read_text())
    if failure['classification']!='PHASE_3H_AN_R_HOST1_CAPTURE_FAILURE' or failure['aggregate_failure_classification']!='SERIALIZATION_FAILURE':raise ValueError('Host1 common failure not proven')
    signatures=failure['normalized_failure_signatures']
    if len(signatures)!=1 or signatures[0]['count']!=10 or signatures[0]['signature']['message']!='case result readback mismatch':raise ValueError('Host1 failure signature differs')
    if not all(x['old_predicate_fails'] and x['metadata_with_only_this_field_corrected_roundtrips_exactly'] for x in failure['repair_proof']['per_case_exact_metadata_roundtrip']):raise ValueError('metadata repair unproven')
    if len(failure['repair_proof']['per_case_exact_metadata_roundtrip'])!=10:raise ValueError('ten Host1 proofs required')
    for item in failure['original_Host1_inventory']:
        if g.sha(HOST1/item['path'])!=item['sha256']:raise ValueError('immutable Host1 evidence changed: '+item['path'])
    if not all(v['all_required_callbacks_present'] for v in failure['callback_availability_matrix'].values()):raise ValueError('Host1 callback runtime support not proven')
    return failure


def safety(output):
    prior=preservation.safety(output)
    # Include this phase's immutable prior runtime partition set too.
    for path in HOST1.glob('*/process_lifecycle.json'):
        life=json.loads(path.read_text())
        if not life.get('shutdown_proven'):raise g.InvalidCapture('Host1 shutdown not proven')
    return prior


def preflight(output=DEFAULT_OUTPUT):
    output=Path(output).resolve()
    if output!=DEFAULT_OUTPUT.resolve():raise ValueError('only fresh AN-R Host2 output allowed')
    if output.exists() and any(p.name not in STATIC for p in output.iterdir()):raise FileExistsError('runtime evidence exists; never resume/overwrite')
    guard=guard_manifest();contract=static_contract();codec=q.codec_self_check();safety(output)
    output.mkdir(parents=True,exist_ok=True);frozen=output/'protocol.json'
    if frozen.exists() and json.loads(frozen.read_text())!=json.loads(json.dumps(protocol())):raise ValueError('frozen protocol changed')
    write(frozen,protocol())
    audit=solver_audit();write(output/'solver_observability.json',audit)
    scenario,seed,_=g.history.source(g.ab.DEFAULT_ARTIFACT)
    libraries,builds=g.ab._build_all(output/'builds');g.verify_static_builds(builds)
    library,built=build(output/'builds/microstate_observer');definitions=[];hashes=[]
    for spec in schedule():
        directory=output/'preflight_sdfs'/spec['case_id']
        prod=g.ab.GazeboWorldGenerator().generate(scenario,directory/'world',closed_loop=True,control_mode='PHYSICS')
        digest=g.sha(prod);hashes.append(digest)
        if digest!=g.EXPECTED_SHA:raise ValueError('production SHA changed')
        diag,info=g.ab._instrument_world(prod,directory,libraries,topic_identity='AN-R/'+spec['case_id']+'/'+uuid4().hex)
        diag,info=instrument(diag,info,library,spec['case_id'],directory)
        diag,info=g.checkpoints.instrument(diag,info);diag,info=g.instrument_audit(diag,info)
        verified=validate_sdf(diag)
        if g.ab._semantic(ET.parse(prod).getroot())!=g.ab._semantic(ET.parse(diag).getroot()):raise ValueError('non-observation SDF change')
        definitions.append({'spec':spec,'sdf':str(diag),'sdf_sha256':g.sha(diag),'production_sdf':str(prod),
          'identity':info['microstate_observer'],'geometry_and_callback_contract':verified})
    g.production_sensor_order_contract();g.history.verify_manifest(guard)
    if list(output.rglob('*.ndjson')):raise ValueError('runtime evidence before Host')
    pf={'status':'PREFLIGHT_PASS','phase':'AN-R','gates':{gate:True for gate in GATES},'contract':contract,'codec':codec,
      'protocol_sha256':g.sha(frozen),'runner_sha256':g.sha(__file__),'library':str(library),'observer_build':built,
      'libraries':{k:str(v) for k,v in libraries.items()},'standard_library_sha256':{k:g.sha(v) for k,v in libraries.items()},
      'standard_observer_builds':builds,'definitions':definitions,'guard_manifest':guard,
      'solver_audit_sha256':g.sha(output/'solver_observability.json'),'production_sha_before':hashes[0],
      'production_sha_after':hashes[-1],'production_changed':False,'gazebo_executed':False,'Host_executed':False,
      'runtime_facts':'HOST_REQUIRED; NO_PHYSICAL_RESULT_FROM_STATIC_TESTS','seed':seed,
      'host1_failure_classification':'SERIALIZATION_FAILURE',
      'repair':'JSON-native callback_stages list; exact readback equality unchanged; no observer or physics change',
      'host1_forensics':str(HOST1_FORENSICS),'host_version':2}
    write(output/'microstate_preflight.json',pf);return pf



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


def persist_ledger(output,ledger):write(output/'microstate_case_ledger.json',validate_ledger(ledger))


def verify_lifecycle(record,life,previous_close,partitions,topics):
    if not all(life.get(k) is True for k in ['shutdown_proven','fresh_single_server','observer_subscriptions_closed','qualification_transport_closed']) or record.get('shutdown_completed') is not True:raise g.InvalidCapture('fresh process/shutdown unproven')
    launches=[e for e in life['events'] if e['event']=='launch'];closes=[e for e in life['events'] if e['event']=='close']
    if len(launches)!=1 or len(closes)!=1 or launches[0]['status'].get('status')!='Running' or not launches[0]['status'].get('available') or closes[0].get('exit_code')!=0:raise g.InvalidCapture('clean startup/shutdown unproven')
    launch=launches[0];close=closes[0];identity=record['runtime_identity']
    if close['wall_monotonic_s']<launch['wall_monotonic_s'] or (previous_close is not None and launch['wall_monotonic_s']<previous_close):raise g.InvalidCapture('server overlap or lifecycle chronology invalid')
    if identity['partition']!=launch['status']['partition'] or identity['partition']!=close['partition'] or launch['status']['pid']!=close['pid']:raise g.InvalidCapture('lifecycle identity differs')
    if identity['partition'] in partitions or identity['topic'] in topics:raise g.InvalidCapture('transport identity reused')
    partitions.add(identity['partition']);topics.add(identity['topic'])
    return close['wall_monotonic_s']


def run(output=DEFAULT_OUTPUT):
    output=Path(output).resolve()
    if output!=DEFAULT_OUTPUT.resolve() or any(p.name not in STATIC for p in output.iterdir()):raise FileExistsError('prospective block cannot resume or overwrite')
    pf=json.loads((output/'microstate_preflight.json').read_text())
    if pf['status']!='PREFLIGHT_PASS' or pf['runner_sha256']!=g.sha(__file__) or pf['protocol_sha256']!=g.sha(output/'protocol.json'):raise g.InvalidCapture('static preflight mismatch')
    g.history.verify_manifest(pf['guard_manifest']);safety(output);q.codec_self_check()
    if g.sha(output/'solver_observability.json')!=pf['solver_audit_sha256']:raise g.InvalidCapture('solver audit changed')
    installed=json.loads((output/'solver_observability.json').read_text())
    g.history.verify_manifest(installed['public_header_sha256']);g.history.verify_manifest(installed['installed_binary_sha256'])
    for definition in pf['definitions']:
        if g.sha(definition['sdf'])!=definition['sdf_sha256'] or g.sha(definition['production_sdf'])!=g.EXPECTED_SHA:raise g.InvalidCapture('preflight SDF changed')
        validate_sdf(definition['sdf'])
    library=Path(pf['library'])
    if g.sha(library)!=pf['observer_build']['library_sha256']:raise g.InvalidCapture('observer library changed')
    scenario,seed,_=g.history.source(g.ab.DEFAULT_ARTIFACT)
    libraries={k:Path(v) for k,v in pf['libraries'].items()}
    g.verify_static_builds(pf['standard_observer_builds'])
    for k,v in libraries.items():
        if g.sha(v)!=pf['standard_library_sha256'][k]:raise g.InvalidCapture('standard observer library changed')
    ledger={'protocol_sha256':pf['protocol_sha256'],'slots':[{'spec':s,'state':'SCHEDULED'} for s in schedule()]}
    persist_ledger(output,ledger);print('CURRENT_PHASE_IS_AN_R',flush=True);print('PROSPECTIVE_CASE_ORDER_FROZEN',flush=True)
    previous_shutdown=True;previous_close=None;partitions=set();topics=set()
    for slot in ledger['slots']:
        spec=slot['spec'];directory=output/spec['case_id']
        if not previous_shutdown:
            slot['not_started_reason']='prior shutdown unproven; scheduled slot retained';persist_ledger(output,ledger);continue
        safety(output);directory.mkdir(parents=True);slot.update(state='STARTED',wall_start=time.monotonic());persist_ledger(output,ledger)
        try:
            record=capture(spec['case_id'],scenario,directory,libraries,seed,uuid4().hex,library)
            life=json.loads((directory/'process_lifecycle.json').read_text())
            previous_close=verify_lifecycle(record,life,previous_close,partitions,topics)
            previous_shutdown=True
            identity=record['runtime_identity']
            result=analyze(record,spec);write(directory/'microstate_analysis.json',result)
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
    write(output/'physical_microstate_ordering_qualification.json',result);return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);choice=parser.add_mutually_exclusive_group(required=True)
    choice.add_argument('--preflight-only',action='store_true');choice.add_argument('--host-run',action='store_true')
    args=parser.parse_args(argv)
    try:
        if args.preflight_only:
            result=preflight()
            for gate in GATES:print(gate)
            print(result['status']);print('HOST_EXECUTION_REQUIRED');return 0
        result=run();print(result['status']);print(result['classification']);print('OBSERVATIONAL_ONLY_NO_MEDIATOR_SELECTED')
        return 0 if result['status']=='QUALIFICATION_CAPTURE_COMPLETE' else 1
    except Exception as exc:
        print('CAPTURE_FAILED: '+type(exc).__name__+': '+str(exc));return 1


if __name__=='__main__':raise SystemExit(main())
