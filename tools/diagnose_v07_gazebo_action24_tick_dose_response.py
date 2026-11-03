#!/usr/bin/env python3
"""Prospectively frozen 5x5 tick-dose diagnostic. Host runtime requires --host-run."""
from __future__ import annotations
import argparse
import copy
import gc
import hashlib
import json
import math
import os
import re
import statistics
import tempfile
import time
import traceback
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4
from tools import diagnose_v07_gazebo_action24_one_tick_control as g
from tools import action24_tick_ledger as ledger_io

ROOT=g.ROOT
HOST1=ROOT/'validation/v071-host/gazebo-action24-tick-dose-response-phase3hai-host1'
FORENSICS=ROOT/'validation/v071-host/gazebo-action24-tick-dose-response-phase3hai-host1-forensics'
DEFAULT_OUTPUT=ROOT/'validation/v071-host/gazebo-action24-tick-dose-response-phase3hai-host2'
REFERENCE=g.DEFAULT_OUTPUT/'one_tick_causal_forensics.json'
FAILURE='CANONICAL_ACTION24_FAILURE_REPRODUCED'
SUCCESS='SUPPORT_RECOVERY_AND_TRANSLATION_SUCCESS'
InvalidCapture=g.InvalidCapture
STATIC={'observer_builds','preflight_sdfs','prospective_schedule.json','protocol.json','tick_dose_preflight.json','prospective_ledger_template.json'}


def write_json(path,value,validator=None):
    path=Path(path).resolve()
    if path.is_relative_to(HOST1.resolve()) or path.is_relative_to(FORENSICS.resolve()):
        raise FileExistsError('refusing preserved Host1/forensics evidence')
    ledger_io.atomic_json(path,value,validator)


def initial_ledger():return ledger_io.new_ledger(schedule(),digest(schedule()),digest(protocol()))


def validate_ledger(value):
    return ledger_io.validate_ledger(value,schedule(),digest(schedule()),digest(protocol()))


def ledger_contract_self_check():
    """Exercise the production-used writer offline, including the exact tuple bug."""
    with tempfile.TemporaryDirectory(prefix='action24-ledger-preflight-') as directory:
        path=Path(directory)/'ledger.json';value=initial_ledger()
        write_json(path,value,validate_ledger)
        slot=value['slots'][0]
        slot.update(state='STARTED',started_wall_monotonic_s=time.monotonic())
        slot['transitions'].append('STARTED');write_json(path,value,validate_ledger)
        slot.update(state='CAPTURE_INVALID',capture_outcome='CAPTURE_INVALID',
            invalid_reasons=['OFFLINE_CONTRACT_FIXTURE'],artifact_paths={})
        slot['transitions'].append('CAPTURE_INVALID');write_json(path,value,validate_ledger)
        slot.update(state='FINALIZED',process_lifecycle={},
            result={'case_id':slot['case_id'],'case_valid':False,'status':'CAPTURE_INVALID',
                    'invalid_reasons':['OFFLINE_CONTRACT_FIXTURE']})
        slot['transitions'].append('FINALIZED');write_json(path,value,validate_ledger)
        del slot['result']['invalid_reasons']
        try:validate_ledger(value)
        except ValueError:pass
        else:raise InvalidCapture('incomplete finalized result accepted')
        witness={'vector':(0.,0.,0.)}
        try:g.history.write_json(Path(directory)/'legacy.json',witness)
        except InvalidCapture as exc:
            if 'incomplete result serialization' not in str(exc):raise
        else:raise InvalidCapture('legacy serialization failure not reproduced')
        write_json(Path(directory)/'repaired.json',witness)


def process_safety(proc_root=Path('/proc')):
    """Read-only proc scan; refuse matching experiment processes, never kill."""
    partitions=set()
    for root in (HOST1,DEFAULT_OUTPUT):
        for p in root.glob('TICK_*/process_lifecycle.json'):
            for event in json.loads(p.read_text()).get('events',[]):
                if event.get('partition'):partitions.add(event['partition'])
    matches=[]
    for proc in proc_root.iterdir():
        if not proc.name.isdigit() or int(proc.name)==os.getpid():continue
        try:
            cmd=(proc/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace')
            try:env=(proc/'environ').read_bytes().split(b'\0')
            except PermissionError:env=[]
        except (FileNotFoundError,ProcessLookupError,PermissionError):continue
        partition_match=any(('GZ_PARTITION='+p).encode() in env for p in partitions)
        path_match=any(str(root) in cmd for root in (HOST1,DEFAULT_OUTPUT)) and any(
            marker in cmd for marker in ('world_joint_state_diagnostic.sdf','gz sim','gz-sim'))
        if partition_match or path_match:matches.append({'pid':int(proc.name),'command':cmd})
    if matches:raise InvalidCapture('prior diagnostic process still active: '+json.dumps(matches))
    return {'status':'NO_MATCHING_EXPERIMENT_PROCESS','matching_processes':[],
            'scope':'read-only /proc cmdline and available environment; saved partition and diagnostic SDF identities'}


def canonical_bytes(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(value):return hashlib.sha256(canonical_bytes(value)).hexdigest()


def schedule():
    # Cyclic Latin schedule: every dose appears once in each block and each slot.
    return [{'ordinal':5*r+j+1,'case_id':f'TICK_{(r+j)%5}_R{r+1}',
             'tick_count':(r+j)%5,'replicate_id':f'R{r+1}'} for r in range(5) for j in range(5)]


def parse_case(case):
    match=re.fullmatch(r'TICK_([0-4])_R([1-5])',case)
    if not match:raise ValueError('unknown prospective case')
    return int(match[1]),int(match[2])


def plan(case):
    n,r=parse_case(case)
    return {**g.history.candidate(15),'name':case,'tick_count':n,'replicate_id':f'R{r}',
            'scenario_seed':42,'reset_seed':43,'extra_pre_acquisition_iterations':n,
            'extra_pre_acquisition_sim_time_ns':n*1_000_000,
            'treatment_window_pose_rpc_count_required':0,'treatment_command_publications_required':0}


@contextmanager
def dose_plans():
    old,old_advance=g.plan,g.advance_ticks
    g.plan=plan;g.advance_ticks=single_advance
    try:yield
    finally:g.plan=old;g.advance_ticks=old_advance


def ensure_output(path):
    path=Path(path).resolve()
    validation=ROOT/'validation'
    if path.is_relative_to(validation) and path!=DEFAULT_OUTPUT:
        raise FileExistsError('refusing other/preserved validation evidence directory')
    if path.exists() and any(p.name not in STATIC for p in path.iterdir()):
        raise FileExistsError('runtime/unknown evidence exists; primary block cannot be rerun or replaced')
    return path


def protected_manifest():
    guard=g.protected_manifest()
    guard.update({str(p.resolve()):g.sha(p) for p in g.DEFAULT_OUTPUT.rglob('*') if p.is_file()})
    guard[str(Path(__file__).resolve())]=g.sha(__file__)
    guard[str(Path(ledger_io.__file__).resolve())]=g.sha(ledger_io.__file__)
    for directory in (HOST1,FORENSICS):
        guard.update({str(p.resolve()):g.sha(p) for p in directory.rglob('*') if p.is_file()})
    return guard


def protocol():
    return {'version':1,'primary_cases':25,'replicates_per_dose':5,'dose_counts':[0,1,2,3,4],
        'schedule':schedule(),'schedule_digest':digest(schedule()),'replacement_policy':'NO_PRIMARY_REPLACEMENTS; any later replacement is POST_HOC and excluded',
        'advance_policy':'zero requests for0; exactly one pause:true,multi_step:N request forN>0; one matched explicit pause ACK and two nonconsuming checkpoints per case',
        'PRE_gate':'accepted Host2 ZERO S0 reference plus pairwise comparisons to every included primary case, frozen bounds; reset/planner/sensor/command provenance also compared',
        'adequacy_rule':{'minimum_valid_per_dose':4,'minimum_total_valid':20,'invalids_never_count_as_physical_failure':True},
        'pattern_priority':['PATTERN_F_CAPTURE_INADEQUATE','PATTERN_E_BASELINE_UNSTABLE','PATTERN_A_THRESHOLD','PATTERN_C_NON_MONOTONIC','PATTERN_B_GRADED','PATTERN_D_NO_REPRODUCIBLE_TICK_EFFECT','PATTERN_UNRESOLVED'],
        'pattern_rules':{'F':'fewer than4 valid in any dose or fewer than20 total',
          'E':'any valid TICK_0 is not strict canonical failure; capture absence alone is not baseline instability',
          'A':'all valid zero cases fail canonically; each nonzero dose success fraction>=4/5. Deterministic-threshold flag requires25 valid,5/5 zero failure,20/20 nonzero success',
          'C':'adequate, stable observed zero baseline, not A, and empirical success fraction decreases at any adjacent dose',
          'B':'adequate, stable observed zero baseline, not A/C, nondecreasing success fractions with at least two distinct fractions',
          'D':'adequate and same physical categorical distribution at all five doses; no categorical dose effect demonstrated',
          'unresolved':'remaining shapes or outcome categories not fitting above'},
        'statistics':'Individual values/median/min/max; success denominator is valid cases, other physical outcomes retained. n=5 descriptive only; no significance claim.',
        'event_rules':{'unloading':'first post-T0 both drive Fn<=existing FORCE_ZERO_N',
          'caster_takeover':'first post-T0 caster fraction>=existing90percent of positive total load',
          'first_recovery':'first both drive Fn>existing FORCE_ZERO_N after unloading',
          'sustained_recovery':'unchanged strict classifier existing recovery window/tail',
          'material_translation':'first native forward displacement from production acquisition origin reaches unchanged production movement minimum; report separately from tiny first-positive displacement',
          'branch_comparison':'for each nonzero case compare exact relative rows with same replicate TICK_0 when both valid; first contact-topology difference and raw Fn deltas, never force+5ms'},
        'yaw_status':'YAW_CAUSAL_RELEVANCE_UNRESOLVED','root_mechanism_identified':False}


def freeze_files(output):
    output.mkdir(parents=True,exist_ok=True)
    for name,value in [('prospective_schedule.json',schedule()),('protocol.json',protocol())]:
        p=output/name
        if p.exists():
            if json.loads(p.read_text())!=value:raise InvalidCapture('prospective schedule/protocol changed')
        else:write_json(p,value)
    return {name:g.sha(output/name) for name in ('prospective_schedule.json','protocol.json')}


def load_frozen(output):
    expected={'prospective_schedule.json':schedule(),'protocol.json':protocol()}
    for name,value in expected.items():
        if json.loads((output/name).read_text())!=value:raise InvalidCapture('frozen order/protocol mismatch')
    return schedule()


def exact_stats(marker):
    if marker.get('stats_source') not in ('transport_snapshot','exact_time_transport_sample','fresh_explicit_pause_WorldStatistics'):
        raise InvalidCapture('raw transport statistics required; no reconstructed/fallback clock')
    data=marker.get('observed_snapshot') or {}
    st=data.get('sim_time');raw_i=data.get('iterations_normalized',data.get('iterations'))
    if not isinstance(st,dict) or isinstance(raw_i,bool):raise InvalidCapture('raw exact WorldStatistics unavailable')
    try:
        sec=int(st.get('sec',0));nsec=int(st.get('nsec',0));iteration=int(raw_i)
    except (ValueError,TypeError):raise InvalidCapture('noninteger raw WorldStatistics')
    for v in (st.get('sec',0),st.get('nsec',0),raw_i):
        if not isinstance(v,(int,str)) or isinstance(v,bool):raise InvalidCapture('floating raw statistics prohibited')
    if sec<0 or iteration<0 or not 0<=nsec<1_000_000_000 or data.get('paused') is not True:
        raise InvalidCapture('invalid exact paused statistics')
    ns=sec*1_000_000_000+nsec
    if marker.get('iteration')!=iteration or marker.get('sim_time_ns')!=ns:
        raise InvalidCapture('derived marker does not equal exact integer stats')
    return iteration,ns


def exact_treatment(record,n):
    it=record['one_tick_treatment'];start=exact_stats(it['boundary_marker'])
    for mark in (it['post_marker'],it['before_UP_publication_marker']):
        end=exact_stats(mark)
        if (end[0]-start[0],end[1]-start[1])!=(n,n*1_000_000):
            raise InvalidCapture('exact integer treatment duration/count mismatch')
    events=record['command_audit'];window=events[it['window_start_cursor']:it['window_end_cursor']]
    advances=[e for e in window if e.get('request_type','').split('.')[-1]=='WorldControl' and e.get('payload',{}).get('multi_step',0)]
    if len(advances)!=(1 if n else 0) or (n and advances[0]['payload']!={'pause':True,'multi_step':n}):
        raise InvalidCapture('nonzero dose must be one advancement request specifyingN; zero must make none')
    return {'raw_integer_stats_verified':True,'iterations':n,'elapsed_ns':n*1_000_000,'advancement_request_count':len(advances)}


def capture_case(case,scenario,directory,libraries,seed,namespace):
    """Accepted capture composition, with observation-only OS lifecycle ledger."""
    from aero_ai_studio.gazebo.process_manager import GazeboProcessManager
    Native=g.ab.native.NativeVelocityCapture
    old_launch,old_close,old_subscribe=GazeboProcessManager.launch,GazeboProcessManager.close,Native.subscribe
    events=[];instances=[]
    def launch(manager,*args,**kwargs):
        entry={'event':'launch','wall_monotonic_s':time.monotonic(),'partition':manager.partition}
        events.append(entry)
        try:
            result=old_launch(manager,*args,**kwargs)
            entry['status']=copy.deepcopy(manager.status())
            return result
        except Exception as exc:
            entry['error']=str(exc);raise
    def close(manager):
        entry={'event':'close','wall_monotonic_s':time.monotonic(),'partition':manager.partition}
        events.append(entry)
        try:return old_close(manager)
        except Exception as exc:
            entry['error']=str(exc);raise
        finally:
            process=manager.process
            entry.update(pid=process.pid if process else None,exit_code=process.poll() if process else None,
                         no_live_process=process is None or process.poll() is not None)
    def subscribe(native,*args,**kwargs):
        instances.append(native)
        return old_subscribe(native,*args,**kwargs)
    GazeboProcessManager.launch=launch;GazeboProcessManager.close=close;Native.subscribe=subscribe
    record=None
    try:
        with dose_plans():record=g.capture(case,scenario,directory,libraries,seed,namespace)
        return record
    finally:
        GazeboProcessManager.launch,GazeboProcessManager.close,Native.subscribe=old_launch,old_close,old_subscribe
        launches=[e for e in events if e['event']=='launch' and e.get('status',{}).get('pid')]
        closes=[e for e in events if e['event']=='close']
        observers=[{'topic':o.topic,'subscribed_after_close':o.subscribed,
                    'owner':'fresh Gazebo C++ plugin instances plus fresh Python capture object, no separate observer OS servers'} for o in instances]
        lifecycle={'case_id':case,'events':events,'observers':observers,
            'fresh_single_server_launch':len(launches)==1,
            'shutdown_proven':bool(closes) and all(e.get('no_live_process') is True and not e.get('error') for e in closes) and {e['partition'] for e in launches}<={e['partition'] for e in closes} and all(not o['subscribed_after_close'] for o in observers),
            'observer_lifecycle_complete':len(observers)==1 and not observers[0]['subscribed_after_close']}
        write_json(directory/'process_lifecycle.json',lifecycle)
        if record is not None:
            record['dose_process_lifecycle']=lifecycle
            write_json(directory/'case_result.json',record)


def pre_controls(record,check,reference,prior):
    failures=[];checks=[]
    state=record['one_tick_treatment']['before']
    for name,other in [('accepted_Host2',reference['S0'])]+[(p['case_id'],p['S0']) for p in prior]:
        eq=g.pre_equivalence(other,state,reference['limits'])
        checks.append({'reference':name,'classification':eq['classification'],'failures':eq['failures']})
        failures += [name+': '+v for v in eq['failures']]
    entry=record['terminal_entry_history']['production_plan']
    logical=record['one_tick_treatment']['logical_before']
    sensor=record['one_tick_treatment']['production_sensor_cursor_PRE']
    if entry!=reference['plan'] or logical!=reference['logical']:
        failures.append('executor/planner/logical command cursor differs')
    if any(sensor[k]!=reference['sensor'][k] for k in ('previous_timestamp','sequence')):
        failures.append('production sensor timestamp/cursor differs')
    if record['configured_reset_condition']!=reference['reset_configuration']:
        failures.append('configured reset differs')
    if check['reset_RPC_provenance']['signature']!=reference['reset_RPC_signature']:
        failures.append('reset pose RPC behavior differs')
    signature=[e['payload'] for e in g.command_suffix(record)]
    if signature!=reference['command_suffix']:
        failures.append('actual DOWN/braking/fresh UP command sequence differs')
    return {'classification':'CAPTURE_INVALID' if failures else 'PRE_TREATMENT_ARMS_EQUIVALENT',
            'failures':failures,'pairwise_checks':checks}


def load_reference():
    record=json.loads((g.DEFAULT_OUTPUT/g.CASES[0]/'case_result.json').read_text())
    signature=[e['payload'] for e in g.command_suffix(record)]
    del record;gc.collect()
    report=json.loads(REFERENCE.read_text())
    z=g.CASES[0]
    data=report['S0_equivalence']['control_executor_sensor'][z]
    return {'S0':report['event_states'][z]['S0'],'limits':g.y.tolerance_spec(),
            'logical':data['logical_state'],'plan':data['entry']['production_plan'],
            'sensor':data['sensor_cursor'],'reset_configuration':data['reset_configuration'],
            'reset_RPC_signature':report['capture_integrity']['independent_case_checks'][z]['reset_RPC_provenance']['signature'],
            'command_suffix':signature}


def flatten(v,prefix=''):
    if isinstance(v,dict):return {k:z for a,b in v.items() for k,z in flatten(b,prefix+'.'+a if prefix else a).items()}
    if isinstance(v,list):return {k:z for i,b in enumerate(v) for k,z in flatten(b,prefix+'.'+str(i)).items()}
    return {prefix:v} if type(v) in (int,float) else {}


def single_advance(adapter,count):
    from aero_ai_studio.gazebo.stepping import GazeboStepper
    if type(count) is not int or not 1<=count<=4:raise InvalidCapture('single advancement requires1..4')
    env=adapter.env
    probe=GazeboStepper(env.transport,env.stepper.world,physics_dt=.001,dt=.001,timeout=env.stepper.timeout)
    probe.STEP_RETRIES=0  # Diagnostic probe only; no second advancement request.
    probe.time=env.stepper.time
    probe.step_simulation(n_steps=count)
    v=copy.deepcopy(probe.last_verification)
    if v.get('valid') is not True or v.get('iteration_delta')!=count:
        raise InvalidCapture('diagnostic single-request advancement failed')
    env.stepper.time=probe.time;env.stepper.last_verification=v
    return v


def analyze_case(record,integrity,n):
    physical=g.history.classify_candidate(record,integrity)
    maps,t0,_=g.dm.terminal_alignment(record)
    start=g.dm.state_at(record,t0['iteration']-1,maps)
    origin=g.dm.state_at(record,t0['iteration'],maps)
    production_origin=record['events'][-1]['action_publication'].get('before_pose')
    pv=physical['production_movement_validator']
    pose_rows=pv.get('world_pose_history',[])
    ground=ET.parse(record['sdf_path']).find("world/model[@name='ground']/static")
    static=ground is not None and ground.text.strip().lower()=='true'
    if not static:raise InvalidCapture('contact sliding requires proven static ground')
    table=[]
    for i in range(t0['iteration']-5,t0['end_iteration']+1):
        st=g.dm.state_at(record,i,maps);dx=st['position_world_m'][0]-origin['position_world_m'][0];dy=st['position_world_m'][1]-origin['position_world_m'][1]
        st['native_forward_from_T0_m']=dx*math.cos(origin['yaw_rad'])+dy*math.sin(origin['yaw_rad'])
        dx=st['position_world_m'][0]-start['position_world_m'][0];dy=st['position_world_m'][1]-start['position_world_m'][1]
        st['native_forward_from_acquisition_origin_m']=dx*math.cos(start['yaw_rad'])+dy*math.sin(start['yaw_rad'])
        l,r=(st['wheel_phase_mod_2pi_rad'][side] for side in ('left','right'))
        st.update(differential_phase_rad=(l-r)/2,common_phase_rad=(l+r)/2)
        actual=[p for p in pose_rows if round(p['simulation_timestamp']*1e9)==st['sim_time_ns']]
        st['Pose_V_exact_time_samples']=actual
        st['Pose_V_forward_displacements_m']=[]
        if production_origin:
            for p in actual:
                st['Pose_V_forward_displacements_m'].append((p['world_x']-production_origin['x'])*math.cos(production_origin['yaw'])+(p['world_y']-production_origin['y'])*math.sin(production_origin['yaw']))
        st['Pose_V_note']='No nearest/interpolated substitution; repeated same-time phase samples retained, empty list means no exact sample.'
        slip={}
        for side in ('left','right'):
            raw=maps['support_rows'][i]['supports'][side+'_wheel'];link=st['native_wheel_links'][side]
            points=[p for contact in raw.get('contacts',[]) for p in contact.get('points',[])]
            slip[side]=[g.ab.native.relative_contact_velocity(p['position_world_m'],p['normal_world'],link['position_world_m'],link['linear_velocity_world_m_s'],link['angular_velocity_world_rad_s'],ground_static=True) for p in points]
        st['derived_native_contact_kinematics']=slip
        st['collision_assessment']=physical['collision']
        table.append({'delta_ms':i-t0['iteration'],**st})
    post=[r for r in table if r['delta_ms']>=0]
    def first(predicate,after=-1):return next((r['delta_ms'] for r in post if r['delta_ms']>after and predicate(r)),None)
    force=g.history.FORCE_ZERO_N
    unloaded=first(lambda r:all(r['supports'][s+'_wheel']['Fn_N']<=force for s in ('left','right')))
    events={'first_drive_unloading_ms':unloaded,
      'first_caster_takeover_ms':first(lambda r:r['total_Fn_N']>0 and sum(r['supports'][s]['Fn_N'] for s in ('front_caster','rear_caster'))>=.9*r['total_Fn_N']),
      'first_both_drive_recovery_ms':first(lambda r:all(r['supports'][s+'_wheel']['Fn_N']>force for s in ('left','right')),unloaded) if unloaded is not None else None,
      'first_sustained_drive_recovery_ms':physical['first_sustained_drive_recovery_delta_ms'],
      'first_native_forward_positive_ms':first(lambda r:r['native_forward_from_T0_m']>0),
      'first_material_translation_ms':first(lambda r:r['native_forward_from_acquisition_origin_m']>=physical['production_minimum_forward_translation_m'])}
    it=record['one_tick_treatment'];a,b=flatten(it['before']),flatten(it['after'])
    return {'case_id':record['candidate']['name'],'tick_count':n,'classification':physical['classification'],
      'native_displacement_m':physical['native_body_forward_translation_m'],
      'Pose_V_displacement_m':pv['body_forward_displacement'],'final_forward_velocity_m_s':table[-1]['longitudinal_velocity_m_s'],
      'support_recovery_ms':physical['first_sustained_drive_recovery_delta_ms'],'events':events,
      'production_movement_minimum_m':physical['production_minimum_forward_translation_m'],'collision':physical['collision'],
      'T0':t0,'S0':it['before'],'S1':it['after'],
      'S1_minus_S0':g.descriptive_delta(it['before'],it['after']),
      'all_saved_numeric_deltas':{k:b[k]-v for k,v in a.items() if k in b},
      'frozen_feature_deltas':g.y.deltas(it['before'],it['after']),
      'event_relative_trajectory':table,
      'sample_scope':'Exact advancing iteration/time/epoch joins; component producer phases may differ. Derived contact velocity is not a direct sensor. No sub-ms ordering claim.'}


def continuous(values):
    valid=[v for v in values if v is not None]
    return {'individual_values':values,'n_observed':len(valid),'median':statistics.median(valid) if valid else None,
            'min':min(valid) if valid else None,'max':max(valid) if valid else None,
            'missing_semantics':'None means event not reached/unavailable; not zero'}


def dose_table(results):
    table=[]
    for n in range(5):
        scheduled=[r for r in results if r['tick_count']==n]
        valid=[r for r in scheduled if r.get('case_valid')]
        success=sum(r['analysis']['classification']==SUCCESS for r in valid)
        failure=sum(r['analysis']['classification']==FAILURE for r in valid)
        row={'tick_count':n,'planned_replicates':5,'valid_replicates':len(valid),'invalid_replicates':5-len(valid),
             'not_executed_replicates':sum(r.get('status')=='NOT_EXECUTED' for r in scheduled),
             'failure_count':failure,'success_count':success,'other_count':len(valid)-success-failure,
             'success_rate':success/len(valid) if valid else None,
             'replicates':[{'replicate_id':r['replicate_id'],'case_id':r['case_id'],'valid':r.get('case_valid',False),
                  'classification':r['analysis']['classification'] if r.get('case_valid') else 'CAPTURE_INVALID',
                  'invalid_reasons':r.get('invalid_reasons',[])} for r in scheduled]}
        for key in ('native_displacement_m','Pose_V_displacement_m','final_forward_velocity_m_s','support_recovery_ms'):
            row[key]=continuous([r['analysis'][key] for r in valid])
            row[key]['replicate_ids']=[r['replicate_id'] for r in valid]
        row['event_time_distributions']={key:continuous([r['analysis']['events'][key] for r in valid]) for key in
            ('first_drive_unloading_ms','first_caster_takeover_ms','first_both_drive_recovery_ms','first_sustained_drive_recovery_ms','first_material_translation_ms')}
        table.append(row)
    return table


def classify_pattern(table):
    flags=[];rates=[r['success_rate'] for r in table]
    total=sum(r['valid_replicates'] for r in table)
    complete=total==25
    zero=table[0]
    unstable=zero['success_count']+zero['other_count']>0
    if unstable:flags.append('BASELINE_OUTCOME_VARIABILITY_OR_FAILURE_NONREPRODUCTION')
    if zero['valid_replicates']<5:flags.append('BASELINE_CAPTURE_INCOMPLETE_NOT_PHYSICAL_VARIABILITY')
    mixed=[r['tick_count'] for r in table if r['success_count'] and r['failure_count']]
    if mixed:flags.append('MIXED_OUTCOMES_WITHIN_IDENTICAL_TICK_COUNTS')
    strong=complete and zero['failure_count']==5 and sum(r['success_count'] for r in table[1:])==20
    if strong:flags.append('COMPLETE_DISCRETE_GE1_TICK_CONTEXTUAL_THRESHOLD')
    if total<20 or any(r['valid_replicates']<4 for r in table):primary='PATTERN_F_CAPTURE_INADEQUATE'
    elif unstable:primary='PATTERN_E_BASELINE_UNSTABLE'
    elif zero['failure_count']==zero['valid_replicates'] and all(r['success_rate']>=.8 for r in table[1:]):primary='PATTERN_A_THRESHOLD'
    elif any(b<a for a,b in zip(rates,rates[1:])):primary='PATTERN_C_NON_MONOTONIC'
    elif all(b>=a for a,b in zip(rates,rates[1:])) and len(set(rates))>1:primary='PATTERN_B_GRADED'
    elif len({(r['success_rate'],r['failure_count']/r['valid_replicates'],r['other_count']/r['valid_replicates']) for r in table})==1:primary='PATTERN_D_NO_REPRODUCIBLE_TICK_EFFECT'
    else:primary='PATTERN_UNRESOLVED'
    return {'primary_classification':primary,'descriptive_flags':flags,'strong_complete_threshold':strong,
            'baseline_reproduction':{'canonical_failure_out_of_5':zero['failure_count'],
                'valid':zero['valid_replicates'],'invalid':zero['invalid_replicates'],'success':zero['success_count'],'other':zero['other_count'],
                'all_5_canonical_failure':zero['failure_count']==5,
                'interpretation':'Probabilistic/descriptive, not deterministic, when valid baseline outcomes vary; missing captures are not physical successes/failures.'},
            'caution':'Empirical n<=5 fractions, no significance test or identified root mechanism. Nonmonotonic point estimates may reflect sampling variability.'}


def aggregate(results):
    table=dose_table(results);pattern=classify_pattern(table)
    included=[r for r in results if r.get('case_valid')]
    features=sorted({k for r in included for k in (r['analysis'].get('frozen_feature_deltas') or {})})
    micro={k:{str(n):continuous([(r['analysis']['frozen_feature_deltas'] or {}).get(k) for r in included if r['tick_count']==n]) for n in range(5)} for k in features}
    # Preserve dose summaries for every measured numeric checkpoint component,
    # including native link state and wrench components outside scalar gates.
    numeric_features=sorted({k for r in included for k in r['analysis'].get('all_saved_numeric_deltas',{})})
    numeric_micro={k:{str(n):continuous([r['analysis'].get('all_saved_numeric_deltas',{}).get(k)
        for r in included if r['tick_count']==n]) for n in range(5)} for k in numeric_features}
    for key,by_dose in micro.items():
        med=[by_dose[str(n)]['median'] for n in range(5)]
        by_dose['median_sequence']=med
        by_dose['descriptive_median_shape']=('INSUFFICIENT' if any(v is None for v in med) else
            'CONSTANT' if len(set(med))==1 else 'NONDECREASING' if all(b>=a for a,b in zip(med,med[1:])) else
            'NONINCREASING' if all(b<=a for a,b in zip(med,med[1:])) else 'NON_MONOTONIC')
    branches=[]
    for r in included:
        if r['tick_count']==0:continue
        control=next((z for z in included if z['tick_count']==0 and z['replicate_id']==r['replicate_id']),None)
        if control is None:
            branches.append({'case_id':r['case_id'],'comparison':'missing valid same-replicate zero'});continue
        a={v['delta_ms']:v for v in control['analysis']['event_relative_trajectory']};b={v['delta_ms']:v for v in r['analysis']['event_relative_trajectory']}
        rows=[]
        for dt in sorted(a.keys() & b.keys()):
            rows.append({'delta_ms':dt,'ZERO_iteration':a[dt]['iteration'],'dose_iteration':b[dt]['iteration'],
                'Fn_ZERO':{s:v['Fn_N'] for s,v in a[dt]['supports'].items()},'Fn_dose':{s:v['Fn_N'] for s,v in b[dt]['supports'].items()},
                'topology_differs':any(a[dt]['supports'][s]['state']!=b[dt]['supports'][s]['state'] for s in a[dt]['supports'])})
        first=next((v['delta_ms'] for v in rows if v['delta_ms']>=0 and v['topology_differs']),None)
        branches.append({'case_id':r['case_id'],'zero_case_id':control['case_id'],'zero_outcome':control['analysis']['classification'],
                         'first_contact_topology_divergence_ms':first,'full_support_comparison':rows,
                         'caution':'First nonzero Fn/depth/wrench differences need not be a material branch. Compare full trajectories; do not force+5ms.'})
    successful_branches=[b for b in branches if any(r['case_id']==b['case_id'] and
        r['analysis']['classification']==SUCCESS for r in included)]
    branch_distribution=continuous([b.get('first_contact_topology_divergence_ms') for b in successful_branches])
    branch_distribution.update(case_ids=[b['case_id'] for b in successful_branches],
        observed_at_plus5ms=sum(b.get('first_contact_topology_divergence_ms')==5 for b in successful_branches),
        interpretation='Exact first support-topology difference against same-replicate ZERO; no scalar-force materiality or mediator claim.')
    return {'dose_response_table':table,**pattern,'S1_microstate_vs_dose':micro,'support_branch_comparisons':branches,
            'successful_support_branch_divergence_distribution_ms':branch_distribution,
            'all_numeric_S1_minus_S0_by_dose':numeric_micro,
            'case_results':results,'yaw_causal_status':'YAW_CAUSAL_RELEVANCE_UNRESOLVED',
            'mediator_causal_claim':'NONE; dose/outcome correlations are not scalar mediator interventions',
            'hidden_state_note':'Mixed outcomes after frozen PRE equivalence support unresolved sensitivity, not identification of a solver cache.'}


GATES=('PROSPECTIVE_CASE_ORDER_FROZEN','TWENTY_FIVE_FRESH_CASES_DEFINED','FIVE_REPLICATES_PER_TICK_COUNT',
 'EXACT_TICK_ADVANCEMENT_READY','SINGLE_ADVANCEMENT_REQUEST_FOR_NONZERO_TREATMENTS','ZERO_ADVANCEMENT_REQUEST_FOR_TICK_0',
 'NO_EXTRA_COMMAND_DURING_TREATMENT','NO_POSE_RPC_DURING_TREATMENT','NO_WORLDPOSECMD_DURING_TREATMENT',
 'NO_CONSUMING_SENSOR_REFRESH_DURING_TREATMENT','CANONICAL_HISTORY_PRESERVED','PRE_EQUIVALENCE_GATE_ENABLED',
 'BASELINE_REPRODUCIBILITY_GATE_ENABLED','EVENT_RELATIVE_ANALYSIS_READY','EVIDENCE_PRESERVATION_PASS','PRODUCTION_SHA_UNCHANGED',
 'HOST1_PRESERVED','HOST1_FAILURE_CLASSIFIED','HOST1_RUNTIME_LAUNCH_STATUS_DETERMINED',
 'INCREMENTAL_LEDGER_SERIALIZATION_VALID','FUTURE_SCHEDULED_CASES_ALLOWED','FINALIZED_CASE_COMPLETENESS_VALIDATED',
 'CRASH_SAFE_LEDGER_WRITE_READY','NO_HOST1_CASE_REUSE','FRESH_PROCESS_PER_CASE','SHUTDOWN_GATE_ENABLED')


def self_check():
    rows=schedule()
    if len(rows)!=25 or len({r['case_id'] for r in rows})!=25:raise InvalidCapture('schedule is not25 unique cases')
    for n in range(5):
        if sum(r['tick_count']==n for r in rows)!=5:raise InvalidCapture('replicate count mismatch')
        if sorted((r['ordinal']-1)%5 for r in rows if r['tick_count']==n)!=list(range(5)):
            raise InvalidCapture('Latin execution positions not balanced')
    with dose_plans():
        for r in rows:
            p=plan(r['case_id']);n=r['tick_count']
            assert p['actions']==g.SUFFIX and p['canonical_indices']==list(range(8,25))
            g.verify_treatment(r['case_id'],{'iteration':3600,'sim_time_ns':3_600_000_000,'paused':True},
                {'iteration':3600+n,'sim_time_ns':3_600_000_000+n*1_000_000,'paused':True},42,42,0)
    # Real production planner remains unchanged.
    g.contract_self_check()


def preflight(output,artifact_dir=None):
    output=ensure_output(output);guard=protected_manifest()
    inventory=json.loads((FORENSICS/'inventory.json').read_text())
    g.history.verify_manifest({f['path']:f['sha256'] for f in inventory['files']})
    if json.loads((HOST1/'prospective_schedule.json').read_text())!=schedule():
        raise InvalidCapture('original Host1 frozen order changed')
    safety=process_safety()
    ledger_contract_self_check()
    self_check();frozen=freeze_files(output)
    template=initial_ledger();validate_ledger(template)
    write_json(output/'prospective_ledger_template.json',template,validate_ledger)
    g.production_sensor_order_contract()
    g.y.frozen_tolerance_digest(g.y.tolerance_spec())
    scenario,seed,_=g.history.source(artifact_dir or g.ab.DEFAULT_ARTIFACT)
    reference=load_reference()
    libraries,builds=g.ab._build_all(output/'observer_builds');g.verify_static_builds(builds)
    namespace=uuid4().hex;definitions=[]
    for r in schedule():
        directory=output/'preflight_sdfs'/r['case_id']
        prod=g.ab.GazeboWorldGenerator().generate(scenario,directory/'world',closed_loop=True,control_mode='PHYSICS')
        diag,info=g.ab._instrument_world(prod,directory/'observer_outputs',libraries,topic_identity=r['case_id']+'/'+namespace)
        diag,info=g.checkpoints.instrument(diag,info);diag,info=g.instrument_audit(diag,info)
        root=ET.parse(diag);value=root.findtext('world/physics/max_step_size')
        if g.sha(prod)!=g.EXPECTED_SHA or value!='0.001':
            raise InvalidCapture('production SDF/hash/step changed')
        definitions.append({**r,'diagnostic_sdf':str(diag),'native_topic':info['native']['topic'],'instrumentation':info})
    if len({d['native_topic'] for d in definitions})!=25:raise InvalidCapture('prospective topic identities collide')
    if list(output.rglob('*.ndjson')) or list(output.rglob('case_result.json')):raise InvalidCapture('preflight created runtime evidence')
    g.history.verify_manifest(guard)
    report={'status':'PREFLIGHT_PASS','gates':{k:True for k in GATES},
      'proof_scope':'Static build/load/composition and offline regression contracts; future case exactness/PRE equivalence/process closure must pass runtime gates.',
      'host1_forensics':str(FORENSICS/'inventory.json'),'process_safety':safety,
      'host1_classification':'PHASE_3H_AN_I_HOST1_ORCHESTRATION_OR_SERIALIZATION_FAILURE',
      'frozen_file_sha256':frozen,'schedule_digest':digest(schedule()),'protocol_digest':digest(protocol()),
      'schedule':schedule(),'case_definitions':definitions,'reference_source':str(REFERENCE),'reference_sha256':g.sha(REFERENCE),
      'reference_role':'Accepted Host2 ZERO S0/control provenance only; no old runtime outcome is used as a replicate.',
      'frozen_tolerances':reference['limits'],'observer_builds':builds,
      'scenario_seed':42,'reset_seed':seed,'reset_target':g.history.configured_reset_target(scenario),
      'observer_process_architecture':'Three C++ observer plugins belong to each fresh server process; fresh capture/subscription object per case, closed before next. Not25 retained subscriptions or separate long-lived observer servers.',
      'gazebo_launched':False,'runtime_evidence_created':False,
      'production_sha256_before':g.EXPECTED_SHA,'production_sha256_after':g.EXPECTED_SHA,'production_changed':False,
      'protected_source_sha256_before_after':guard,'runner_sha256':g.sha(__file__),'helper_sha256':g.sha(g.__file__),
      'yaw_causal_status':'YAW_CAUSAL_RELEVANCE_UNRESOLVED'}
    write_json(output/'tick_dose_preflight.json',report)
    return report


def run(output,artifact_dir=None):
    output=ensure_output(output)
    frozen=load_frozen(output)
    pf=json.loads((output/'tick_dose_preflight.json').read_text())
    if pf.get('status')!='PREFLIGHT_PASS' or pf['runner_sha256']!=g.sha(__file__) or pf['helper_sha256']!=g.sha(g.__file__):
        raise InvalidCapture('preflight/code version mismatch; no primary case launched')
    if any(g.sha(output/k)!=v for k,v in pf['frozen_file_sha256'].items()):
        raise InvalidCapture('frozen prospective files changed')
    # Compare with the preflight snapshot before any runtime case can launch.
    g.history.verify_manifest(pf['protected_source_sha256_before_after'])
    g.production_sensor_order_contract()
    process_safety()
    guard=protected_manifest();self_check()
    scenario,seed,_=g.history.source(artifact_dir or g.ab.DEFAULT_ARTIFACT)
    reference=load_reference();libraries,builds=g.ab._build_all(output/'observer_builds');g.verify_static_builds(builds)
    print('PROSPECTIVE_CASE_ORDER_FROZEN',flush=True)
    results=[];prior=[];partitions=set();topics=set();last_shutdown=True;reset_pose=None
    namespace=uuid4().hex
    ledger=initial_ledger();ledger_path=output/'prospective_case_ledger.json'
    write_json(ledger_path,ledger,validate_ledger)
    for index,slot in enumerate(frozen):
        c=slot['case_id'];n=slot['tick_count'];summary={**slot,'primary_prospective':True,'post_hoc':False,'case_valid':False}
        if not last_shutdown:
            summary.update(status='NOT_EXECUTED',invalid_reasons=['prior case shutdown not proven; no replacement'])
            results.append(summary)
            continue
        process_safety()
        current=ledger['slots'][index]
        current.update(state='STARTED',started_wall_monotonic_s=time.monotonic())
        current['transitions'].append('STARTED')
        write_json(ledger_path,ledger,validate_ledger)
        directory=output/c;directory.mkdir(parents=True)
        record=None;check=None
        try:
            record=capture_case(c,scenario,directory,libraries,seed,namespace)
            lifecycle=record['dose_process_lifecycle']
            current.update(state='CAPTURED',capture_outcome='CAPTURED',
                artifact_paths={'case_result':str(directory/'case_result.json')},
                process_lifecycle=lifecycle,runtime_identity=record.get('runtime_identity',{}))
            current['transitions'].append('CAPTURED')
            write_json(ledger_path,ledger,validate_ledger)
            last_shutdown=lifecycle['shutdown_proven'] and record.get('shutdown_completed') is True
            with dose_plans():check=g.validate(record,c,scenario,seed,reset_pose,partitions,topics)
            # Keep every observed identity, including an invalid case's identity.
            identity=record.get('runtime_identity',{})
            partitions.add(identity.get('partition'));topics.add(identity.get('topic'))
            summary.update(process_lifecycle=lifecycle,runtime_identity=identity,
                           case_result_path=str(directory/'case_result.json'))
            if not last_shutdown or not lifecycle['fresh_single_server_launch'] or not lifecycle['observer_lifecycle_complete'] or record.get('close_error'):
                check['case_valid']=False;check['invalid_reasons'].append('fresh single server / observer cleanup / shutdown not proven')
            if check['case_valid']:
                summary['exact_treatment']=exact_treatment(record,n)
                eq=pre_controls(record,check,reference,prior)
                summary['PRE_equivalence']=eq
                if eq['classification']!='PRE_TREATMENT_ARMS_EQUIVALENT':
                    check['case_valid']=False;check['invalid_reasons']+=eq['failures']
            if check['case_valid']:
                if prior and record['wall_start_monotonic_s']<prior[-1]['wall_end_after_shutdown_monotonic_s']:
                    raise InvalidCapture('next process started before previous accepted process shutdown')
                analysis=analyze_case(record,check,n)
                analysis=ledger_io.json_value(analysis)
                summary.update(case_valid=True,status='VALID',analysis=analysis)
                check['physical_classifier_attempted']=True
                reset_pose=reset_pose or record.get('canonical_reset_pose')
                prior.append({'case_id':c,'S0':analysis['S0'],'wall_end_after_shutdown_monotonic_s':record['wall_end_after_shutdown_monotonic_s']})
                write_json(directory/'case_analysis.json',analysis)
            else:summary.update(status='CAPTURE_INVALID',invalid_reasons=check['invalid_reasons'])
        except Exception as exc:
            summary.update(case_valid=False,status='CAPTURE_INVALID',invalid_reasons=[type(exc).__name__+': '+str(exc)],
                           diagnostic_traceback=traceback.format_exception(type(exc),exc,exc.__traceback__))
            check=check or {'case_valid':False,'physical_classifier_attempted':False,'invalid_reasons':[]}
            check['case_valid']=False;check['invalid_reasons']+=summary['invalid_reasons']
            lifecycle_path=directory/'process_lifecycle.json'
            lifecycle=json.loads(lifecycle_path.read_text()) if lifecycle_path.exists() else {}
            summary['process_lifecycle']=lifecycle
            last_shutdown=lifecycle.get('shutdown_proven') is True and (record is None or record.get('shutdown_completed') is True)
        finally:
            if check is not None:write_json(directory/'capture_integrity.json',check)
            del record;gc.collect()
        results.append(summary)
        if current['state']=='STARTED':
            current.update(state='CAPTURE_INVALID',capture_outcome='CAPTURE_INVALID',
                invalid_reasons=summary['invalid_reasons'],artifact_paths={})
            current['transitions'].append('CAPTURE_INVALID')
            write_json(ledger_path,ledger,validate_ledger)
        current.update(process_lifecycle=summary.get('process_lifecycle',{}),shutdown_proven=last_shutdown)
        if last_shutdown:
            current.update(state='SHUTDOWN_PROVEN');current['transitions'].append('SHUTDOWN_PROVEN')
            write_json(ledger_path,ledger,validate_ledger)
        current.update(state='FINALIZED',result=summary);current['transitions'].append('FINALIZED')
        write_json(ledger_path,ledger,validate_ledger)
        print(c+': '+(summary['analysis']['classification'] if summary['case_valid'] else 'CAPTURE_INVALID; '+'; '.join(summary.get('invalid_reasons',[]))),flush=True)
    ledger['block_state']='FINISHED' if all(s['state']=='FINALIZED' for s in ledger['slots']) else 'STOPPED_SHUTDOWN_UNPROVEN'
    write_json(ledger_path,ledger,validate_ledger)
    report=aggregate(results)
    g.history.verify_manifest(guard)
    if load_frozen(output)!=frozen:raise InvalidCapture('prospective schedule changed during run')
    report.update(status='CAPTURED' if all(r['case_valid'] for r in results) else 'CAPTURE_FAILED',
        completed_scheduled_slots=len(results),frozen_schedule_digest=digest(frozen),schedule=frozen,
        observer_builds=builds,protected_source_sha256_before_after=guard,
        production_changed=False,production_sha256=g.EXPECTED_SHA)
    write_json(output/'tick_dose_response_analysis.json',report)
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preflight-only',action='store_true');parser.add_argument('--host-run',action='store_true')
    parser.add_argument('--output',type=Path,default=DEFAULT_OUTPUT)
    parser.add_argument('--artifact-dir',type=Path,default=g.ab.DEFAULT_ARTIFACT)
    args=parser.parse_args(argv)
    if args.preflight_only==args.host_run:
        print('CAPTURE_FAILED: choose --preflight-only or explicit --host-run');return 1
    try:report=preflight(args.output,args.artifact_dir) if args.preflight_only else run(args.output,args.artifact_dir)
    except Exception as exc:
        print('CAPTURE_FAILED: '+type(exc).__name__+': '+str(exc));return 1
    if report['status']=='PREFLIGHT_PASS':
        for gate in GATES:print(gate)
    print(report['status']);print('evidence: '+str(args.output))
    if 'primary_classification' in report:
        print('pattern: '+report['primary_classification'])
        print('TICK_0 canonical failure = '+str(report['baseline_reproduction']['canonical_failure_out_of_5'])+' / 5')
        for row in report['dose_response_table']:
            print(f"TICK_{row['tick_count']}: valid={row['valid_replicates']}/5 invalid={row['invalid_replicates']} failure={row['failure_count']} success={row['success_count']} other={row['other_count']} success_rate={row['success_rate']}")
    print('YAW_CAUSAL_RELEVANCE_UNRESOLVED')
    return 0 if report['status'] in ('PREFLIGHT_PASS','CAPTURED') else 1


if __name__=='__main__':raise SystemExit(main())
