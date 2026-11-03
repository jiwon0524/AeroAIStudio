#!/usr/bin/env python3
"""AN-G: fresh zero/one pre-acquisition tick pair; canonical reset allowed.

Pose RPC, WorldPoseCmd and Twist are forbidden only in the treatment window.
No production controller, reset, threshold or physics semantics are modified.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import copy
import math
import traceback
import xml.etree.ElementTree as ET
from uuid import uuid4
from tools import diagnose_v07_gazebo_action24_yaw_intervention as y

dm, history, ab, checkpoints = y.dm, y.history, y.ab, y.checkpoints
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOST1 = ROOT / "validation/v071-host/gazebo-action24-one-tick-control-phase3hang-host1"
DEFAULT_OUTPUT = ROOT / "validation/v071-host/gazebo-action24-one-tick-control-phase3hang-host2"
EXPECTED_SHA = "92def637ff4da2be1348502d345a30721cc845c34704f0b125d4ff1a26fdcc55"
CASES = ("ZERO_TICK_CONTROL", "ONE_TICK_TREATMENT")
SUFFIX = "right left up down left down left right left up up right left left up down up".split()


InvalidCapture = history.InvalidCapture


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def plan(case):
    if case not in CASES:
        raise ValueError("unknown arm")
    steps = CASES.index(case)
    return {**history.candidate(15), "name": case,
            "scenario_seed": 42, "reset_seed": 43,
            "extra_pre_acquisition_iterations": steps,
            "extra_pre_acquisition_sim_time_ns": steps * 1_000_000,
            "treatment_window_pose_rpc_count_required": 0,
            "treatment_command_publications_required": 0,
            "previous_logical_action": "down", "transition_type": "LINEAR_REVERSAL",
            "phases": ["BRAKE_LINEAR", "stopped", "experiment checkpoint", "ACQUIRE_LINEAR"],
            "runtime_implementation_ready": True}


def tick_count(case):
    """Diagnostic extension point; legacy two-arm plans remain zero/one."""
    count=plan(case)['extra_pre_acquisition_iterations']
    if type(count) is not int or not 0<=count<=4:
        raise InvalidCapture('diagnostic tick count must be an integer0..4')
    return count


def advance_ticks(adapter,count):
    """One WorldControl request for N physics iterations; never N requests."""
    if type(count) is not int or not 1<=count<=4:
        raise InvalidCapture('advance_ticks requires1..4; zero must never step')
    if count==1:
        return y.exact_one_step(adapter)
    from aero_ai_studio.gazebo.stepping import GazeboStepper
    env=adapter.env
    probe=GazeboStepper(env.transport,env.stepper.world,physics_dt=.001,dt=.001,timeout=env.stepper.timeout)
    probe.time=env.stepper.time
    probe.step_simulation(n_steps=count)
    evidence=copy.deepcopy(probe.last_verification)
    if (evidence.get('valid') is not True or evidence.get('iteration_delta')!=count or
        round((evidence['after_sim_time']-evidence['before_sim_time'])*1e9)!=count*1_000_000):
        raise InvalidCapture('single N-step request progression differs from exact requested ticks')
    env.stepper.time=probe.time
    env.stepper.last_verification=evidence
    return evidence


def method(path, owner, name):
    tree = ast.parse(Path(path).read_text())
    matches = [node for cls in tree.body if isinstance(cls, ast.ClassDef) and cls.name == owner
               for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == name]
    if len(matches) != 1:
        raise InvalidCapture(f"source audit cannot resolve {owner}.{name}")
    return matches[0]


def calls(node, attribute):
    return [n for n in ast.walk(node) if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute) and n.func.attr == attribute]


def reset_rpc_audit():
    training = ROOT / "src/aero_ai_studio/training/gazebo_physics.py"
    environment = ROOT / "src/aero_ai_studio/gazebo/environment.py"
    controller = ROOT / "src/aero_ai_studio/gazebo/entity_controller.py"
    reset_once = method(training, "GazeboPhysicsTrainingEnvironment", "_reset_once")
    reset = method(environment, "GazeboEnvironment", "_reset")
    setter = method(controller, "GazeboEntityController", "reset_agent_pose")
    reset_calls = calls(reset_once, "reset")
    setter_calls = calls(reset, "reset_agent_pose")
    rpc_calls = [n for n in calls(setter, "request") if n.args
                 and "set_pose" in ast.unparse(n.args[0])]
    # Fail closed if the inspected call chain changes. Do not infer a new safe path.
    if not reset_calls or not setter_calls or len(rpc_calls) != 1:
        raise InvalidCapture("canonical reset/RPC source chain changed; manual audit required")
    unconditional = [n for statement in reset.body if isinstance(statement, ast.Expr)
                     for n in calls(statement, "reset_agent_pose")]
    if len(unconditional) != 1:
        raise InvalidCapture("unconditional canonical agent pose reset not proven")
    entries = [(training, reset_calls[0], "production _reset_once -> env.reset(seed)"),
               (environment, unconditional[0], "production canonical reset -> controller.reset_agent_pose"),
               (controller, rpc_calls[0], "controller -> /world/<world>/set_pose RPC")]
    return {"classification": "CANONICAL_RESET_REQUIRES_POSE_RPC",
            "whole_arm_NO_POSE_RPC_possible_without_reset_change": False,
            "call_chain": [{"file": str(path), "line": n.lineno,
                            "expression": ast.unparse(n), "meaning": text,
                            "source_sha256": sha(path)} for path, n, text in entries],
            "scope": "Canonical reset pose RPC allowed; treatment window has zero pose RPC."}


def verify_treatment(case, before, after, publications_before, publications_after, pose_rpc_count):
    """Pure prospective contract; no simulator execution or synthetic evidence."""
    expected = plan(case)
    if pose_rpc_count != 0:
        raise InvalidCapture("pose RPC forbidden in treatment window")
    if publications_after != publications_before:
        raise InvalidCapture("NO_ADDITIONAL_COMMAND_PUBLICATION_BEFORE_TREATMENT_TICK violated")
    if after["iteration"] - before["iteration"] != expected["extra_pre_acquisition_iterations"]:
        raise InvalidCapture("wrong extra pre-acquisition iteration count")
    if after["sim_time_ns"] - before["sim_time_ns"] != expected["extra_pre_acquisition_sim_time_ns"]:
        raise InvalidCapture("wrong extra pre-acquisition simulation duration")
    if before.get("paused") is not True or after.get("paused") is not True:
        raise InvalidCapture("explicit paused boundary missing")


def outcome_interpretation(zero, one):
    failure = "CANONICAL_ACTION24_FAILURE_REPRODUCED"
    success = "SUPPORT_RECOVERY_AND_TRANSLATION_SUCCESS"
    pair = (zero, one)
    pattern = {(failure, success): "ONE_PRE_ACQUISITION_TICK_SUFFICIENT_TO_CHANGE_OUTCOME_IN_THIS_CONTEXT",
               (failure, failure): "ONE_TICK_ALONE_INSUFFICIENT",
               (success, success): "COMMON_DIAGNOSTIC_TREATMENT_OR_REPRODUCIBILITY_CONFOUND",
               (success, failure): "UNEXPECTED_DIRECTIONAL_TICK_EFFECT"}.get(pair, "RESULT_UNRESOLVED")
    return {"pattern": pattern, "causal_interpretation_allowed": zero == failure and one in (failure, success),
            "baseline_gate": "ZERO_TICK_BASELINE_REPRODUCTION_FAILED" if zero != failure else "PASS",
            "yaw_causal_status": "YAW_CAUSAL_RELEVANCE_UNRESOLVED"}



STATIC_NAMES = {'observer_builds', 'preflight_sdfs', 'one_tick_control_preflight.json',
                'host1_zero_tick_sensor_forensics.json'}


def ensure_output(path):
    path = Path(path).resolve()
    validation = ROOT/'validation'
    if path.is_relative_to(validation) and path != DEFAULT_OUTPUT:
        raise FileExistsError('refusing other evidence directory')
    if path.exists() and any(p.name not in STATIC_NAMES for p in path.iterdir()):
        raise FileExistsError('runtime/unknown evidence already exists; refusing overwrite')
    return path


def protected_manifest():
    # Existing evidence is hashed anew, never rewritten. The observer source is
    # intentionally extended, so old source digests are not treated as raw data.
    guard = y.protected_manifest()
    for directory in (y.DEFAULT_OUTPUT,HOST1):
        guard.update({str(p.resolve()):sha(p) for p in directory.rglob('*') if p.is_file()})
    guard[str(Path(__file__).resolve())] = sha(__file__)
    return guard


def instrument_audit(diagnostic, info):
    tree = ET.parse(diagnostic)
    plugin = tree.find("world/plugin[@name='aero_diagnostic::NativeLinkVelocityObserver']")
    if plugin is None:
        raise InvalidCapture('native observer missing')
    ET.SubElement(plugin, 'audit_world_pose_commands').text = 'true'
    tree.write(diagnostic, encoding='utf-8', xml_declaration=True)
    info['diagnostic_sdf_sha256'] = sha(diagnostic)
    info['native']['diagnostic_sdf_sha256'] = sha(diagnostic)
    info['world_pose_command_audit'] = 'const component reads at PreUpdate/PostUpdate; cumulative observations, not distinct command IDs'
    return diagnostic, info


def logical_state(adapter):
    env = adapter.env
    return {'controller_command':copy.deepcopy(env.controller.last_command),
            'publish_sequence':env.controller.publish_sequence,
            'env_previous_action':copy.deepcopy(getattr(env,'previous_action',None)),
            'adapter_previous_action':copy.deepcopy(getattr(adapter,'previous_action',None))}


def pose_command_counter(native):
    value = native.get('world_pose_command_audit') or {}
    if (value.get('enabled') is not True or
        type(value.get('component_observations_total')) is not int or
        type(value.get('read_callbacks_total')) is not int or
        value.get('active_component_count') != 0):
        raise InvalidCapture('missing command monitor or active WorldPoseCmd at treatment boundary')
    return value


def audit_window(events, start, end):
    if not (type(start) is int and type(end) is int and 0 <= start <= end <= len(events)):
        raise InvalidCapture('invalid treatment command-audit boundaries')
    selected = events[start:end]
    pose = [e for e in selected if e['kind']=='RPC' and is_pose_service(e['service'])]
    twists = [e for e in selected if e['kind']=='TWIST']
    if pose:
        raise InvalidCapture('NO_POSE_RPC_DURING_TREATMENT violated (same-pose also forbidden)')
    if twists:
        raise InvalidCapture('NO_EXTRA_COMMAND_PUBLICATION_DURING_TREATMENT violated')
    return {'treatment_window_pose_rpc_count':len(pose),
            'treatment_window_additional_twist_publications':len(twists),
            'start_audit_cursor_inclusive':start, 'end_audit_cursor_exclusive':end}


def is_pose_service(service):
    return service.endswith(('/set_pose', '/set_pose/blocking', '/set_pose_vector', '/set_pose_vector/blocking'))


def sensor_cursor(adapter):
    """Read cached production bookkeeping only; never ask for a LaserScan."""
    env=adapter.env
    provider=getattr(env,'sensors',None)
    return {'previous_timestamp':getattr(provider,'previous_timestamp',None),
            'sequence':getattr(provider,'sequence',None),
            'cached_observation_identity':id(getattr(env,'observation',None)),
            'cached_production_pose':copy.deepcopy(getattr(env,'pose',None))}


def window_rpc_policy(case,events,start,end):
    selected=events[start:end]
    controls=[e['payload'] for e in selected if e.get('request_type','').split('.')[-1]=='WorldControl']
    count=tick_count(case)
    expected=([{'pause':True,'multi_step':count}] if count else [])+[{'pause':True}]
    if controls!=expected:
        raise InvalidCapture('treatment WorldControl sequence differs; reset/resume/extra steps forbidden')
    checkpoints_rpc=[e for e in selected if e.get('service','').endswith('/checkpoint')]
    if len(checkpoints_rpc)!=2 or any(e.get('request_type')!='Empty' or e.get('payload')!={} for e in checkpoints_rpc):
        raise InvalidCapture('both arms require exactly two observation-only checkpoint requests')
    allowed=len(controls)+len(checkpoints_rpc)
    if len(selected)!=allowed:
        raise InvalidCapture('unexpected treatment operation')
    if any(e.get('response',{}).get('data') is not True or len(e.get('transport_evidence',{}).get('attempts',[]))!=1 for e in selected):
        raise InvalidCapture('treatment RPC completion/single-attempt evidence missing')


def perform_treatment(adapter, case, native_capture, row, evidence, audit):
    if evidence:
        raise InvalidCapture('treatment callback repeated')
    y.stopped_chunk(row)
    completed = y.completed_brake_checkpoint(adapter,row)
    mark = dm.physics_mark(adapter)
    audit['phase'] = 'treatment'
    evidence.update(window_start_cursor=len(audit['events']), boundary_marker=mark,
                    completed_brake_checkpoint=completed, stopped_chunk=copy.deepcopy(row),
                    logical_before=logical_state(adapter),production_sensor_cursor_PRE=sensor_cursor(adapter))
    pre = checkpoints.acquire(adapter,native_capture,mark,'PRE_RPC')
    evidence.update(pre_checkpoint=pre,before=pre['state'])
    pose_command_counter(pre['raw']['native'])
    audit['live_native'] = native_capture
    count=tick_count(case)
    if count:
        evidence['extra_step_verification'] = advance_ticks(adapter,count)
    # Both arms use the same pause ACK and two observation-only checkpoint RPCs.
    # ZERO never calls exact_one_step. Waiting for observations is not stepping.
    sync = {}
    expected_it = mark['iteration'] + count
    expected_ns = mark['sim_time_ns'] + count*1_000_000
    after = y.synchronize_paused(adapter,expected_it,expected_ns,sync)
    post = checkpoints.acquire(adapter,native_capture,after,'POST_RPC')
    # Evidence-only paused pose read. _refresh() also consumes a new LiDAR
    # frame, which ZERO cannot supply while paused. Do not touch the production
    # observation/cursor/pose; its ordinary acquisition refresh follows physics.
    fresh = adapter.env.controller.get_pose(adapter.env.stepper.time,adapter.env.timeout)
    if not checkpoints.same_pose(post['model_state'],checkpoints.pose_v_view(fresh)):
        raise InvalidCapture('POST current model and production Pose_V disagree')
    checkpoints.not_superseded(native_capture,post)
    evidence.update(post_checkpoint=post,after=post['state'],post_marker=after,
                    pause_synchronization=sync,production_pose_POST=fresh,
                    logical_after=logical_state(adapter),window_open_until_fresh_UP=True,
                    production_sensor_cursor_POST=sensor_cursor(adapter),
                    diagnostic_checkpoint_sensor_semantics='same-time paused ECM/Pose_V evidence, not a new advancing LaserScan')
    if evidence['production_sensor_cursor_PRE']!=evidence['production_sensor_cursor_POST']:
        raise InvalidCapture('diagnostic consumed or rewrote production observation/sensor cursor')
    if evidence['logical_before'] != evidence['logical_after']:
        raise InvalidCapture('treatment mutated command/action/planner history')
    check = audit_window(audit['events'],evidence['window_start_cursor'],len(audit['events']))
    verify_treatment(case,mark,after,evidence['logical_before']['publish_sequence'],
                     evidence['logical_after']['publish_sequence'],check['treatment_window_pose_rpc_count'])


def capture(case, scenario, output, libraries, seed, namespace):
    """Compose the accepted completed-brake callback lifecycle, no pose action."""
    from aero_ai_studio.gazebo.transport import HarmonicTransport
    from aero_ai_studio.training.gazebo_physics import GazeboPhysicsTrainingEnvironment
    from aero_ai_studio.gazebo.sensor_provider import RangeSensorProvider
    audit = {'phase':'initialization','events':[],'sensor_reads':[]}
    evidence = {}
    old_plan,old_hook,old_track = y.plan,y.perform_intervention,y.track_production_steps
    old_instrument = checkpoints.instrument
    old_request,old_publish = HarmonicTransport.request,HarmonicTransport.publish
    old_reset = GazeboPhysicsTrainingEnvironment.reset
    old_execute = dm.execute_captured
    old_sensor_read = RangeSensorProvider.get_range_observation
    def stamp(transport):
        with transport.condition:
            stats = [v for k,v in transport.samples.items() if k.endswith('/stats')]
            data = copy.deepcopy(stats[-1]) if stats else {}
        return {'iteration':data.get('iterations_normalized',data.get('iterations')),
                'sim_time_ns':round(dm.stamp(data)*1e9) if data else None,
                'paused':data.get('paused'), 'partition':transport.partition}
    def request(transport,service,request_type,response_type,payload,**kwargs):
        item = {'ordinal':len(audit['events']),'kind':'RPC','phase':audit['phase'],
                'service':service,'request_type':request_type,'response_type':response_type,
                'payload':copy.deepcopy(payload),'marker':stamp(transport)}
        audit['events'].append(item)
        if audit['phase']=='treatment' and is_pose_service(service):
            raise InvalidCapture('pose RPC blocked inside treatment window')
        try:
            result = old_request(transport,service,request_type,response_type,payload,**kwargs)
            item['response']=copy.deepcopy(result)
            item['transport_evidence']=copy.deepcopy(transport.request_history[-1])
            return result
        except Exception as exc:
            item['error']=str(exc)
            raise
    def publish(transport,topic,message_type,payload):
        if message_type.split('.')[-1] != 'Twist':
            return old_publish(transport,topic,message_type,payload)
        if audit['phase']=='treatment':
            # The ONLY permissible next publication is normal production UP,
            # after treatment/POST are complete. It is outside the window.
            if payload != dm.gazebo_physics_twist('up') or not evidence.get('post_checkpoint'):
                raise InvalidCapture('unexpected Twist during treatment')
            adapter = audit['adapter']
            fence = dm.physics_mark(adapter)
            latest = copy.deepcopy(audit['live_native'].samples[-1])
            if latest.get('paused') is not True or latest.get('iteration')!=fence['iteration'] or round(latest['simulation_time_s']*1e9)!=fence['sim_time_ns']:
                raise InvalidCapture('fresh current paused native command audit missing before UP')
            evidence.update(window_end_cursor=len(audit['events']),before_UP_publication_marker=fence,
                            before_UP_native=latest,logical_at_publication=logical_state(adapter))
            evidence['extra_pre_acquisition_iterations']=fence['iteration']-evidence['boundary_marker']['iteration']
            evidence['extra_pre_acquisition_sim_time_ns']=fence['sim_time_ns']-evidence['boundary_marker']['sim_time_ns']
            evidence.update(audit_window(audit['events'],evidence['window_start_cursor'],len(audit['events'])))
            verify_treatment(case,evidence['boundary_marker'],fence,
                evidence['logical_before']['publish_sequence'],adapter.env.controller.publish_sequence,0)
            for cp in (evidence['pre_checkpoint'],evidence['post_checkpoint']):
                pose_command_counter(cp['raw']['native'])
            baseline = pose_command_counter(evidence['pre_checkpoint']['raw']['native'])
            finish = pose_command_counter(latest)
            if finish['component_observations_total']!=baseline['component_observations_total']:
                raise InvalidCapture('WorldPoseCmd observed during treatment')
            evidence['treatment_window_world_pose_cmd_count']=0
            audit['phase']='production_acquisition'
        item={'ordinal':len(audit['events']),'kind':'TWIST','phase':audit['phase'],
              'topic':topic,'payload':copy.deepcopy(payload),'marker':stamp(transport),
              'twist_publication_sequence':1+sum(e['kind']=='TWIST' for e in audit['events'])}
        audit['events'].append(item)
        result=old_publish(transport,topic,message_type,payload)
        item['published']=True
        return result
    def reset(adapter,selected_seed=None):
        audit['phase']='canonical_reset'
        return old_reset(adapter,selected_seed)
    def track(adapter):
        old_track(adapter)
        audit['adapter']=adapter
        audit['reset_completion_marker']=dm.physics_mark(adapter)
        audit['reset_completion_cursor']=len(audit['events'])
        audit['phase']='canonical_history_and_production_braking'
    def hook(adapter,selected,output_dir,native,row,it):
        audit['adapter']=adapter
        try:
            perform_treatment(adapter,selected,native,row,it,audit)
            evidence.update(it)
        except Exception:
            evidence.update(it)
            raise
    def instrument(path,info):
        path,info=old_instrument(path,info)
        return instrument_audit(path,info)
    def execute(adapter,action,phase):
        result=old_execute(adapter,action,phase)
        if phase=='BRAKE_LINEAR_THEN_UP':
            audit['phase']='after_experiment'
        return result
    def sensor_read(provider,pose,min_time=0,simulation_time=None):
        if audit['phase']=='treatment':
            raise InvalidCapture('diagnostic must not request a fresh LaserScan before production UP')
        item={'phase':audit['phase'],'command_audit_cursor':len(audit['events']),
              'simulation_time':simulation_time,'min_time_argument':min_time,
              'previous_timestamp':provider.previous_timestamp,'sequence_before':provider.sequence}
        audit['sensor_reads'].append(item)
        try:
            result=old_sensor_read(provider,pose,min_time,simulation_time=simulation_time)
            item.update(sample_timestamp=provider.previous_timestamp,sequence_after=provider.sequence)
            return result
        except Exception as exc:
            item['error']=str(exc)
            raise
    y.plan=plan
    y.perform_intervention=hook
    y.track_production_steps=track
    checkpoints.instrument=instrument
    HarmonicTransport.request=request
    HarmonicTransport.publish=publish
    GazeboPhysicsTrainingEnvironment.reset=reset
    dm.execute_captured=execute
    RangeSensorProvider.get_range_observation=sensor_read
    try:
        record=y.capture(case,scenario,output,libraries,seed,namespace)
    finally:
        y.plan,y.perform_intervention,y.track_production_steps=old_plan,old_hook,old_track
        checkpoints.instrument=old_instrument
        HarmonicTransport.request,HarmonicTransport.publish=old_request,old_publish
        GazeboPhysicsTrainingEnvironment.reset=old_reset
        dm.execute_captured=old_execute
        RangeSensorProvider.get_range_observation=old_sensor_read
    # The generic accepted harness calls its callback payload yaw_intervention;
    # rename it here. No yaw payload/service or yaw analysis function is used.
    raw=record.pop('yaw_intervention',{})
    raw.update(evidence)
    record['one_tick_treatment']=raw
    record['command_audit']=copy.deepcopy(audit['events'])
    record['production_sensor_reads']=copy.deepcopy(audit['sensor_reads'])
    record['reset_completion_marker']=audit.get('reset_completion_marker')
    record['reset_completion_cursor']=audit.get('reset_completion_cursor')
    poses=[e for e in record['command_audit'] if e['kind']=='RPC' and is_pose_service(e['service'])]
    record['pose_RPC_counts']={phase+'_pose_rpc_count':sum(e['phase']==phase for e in poses)
                              for phase in ('initialization','canonical_reset','treatment','after_experiment')}
    record['initialization_pose_rpc_count']=record['pose_RPC_counts']['initialization_pose_rpc_count']
    record['reset_pose_rpc_count']=record['pose_RPC_counts']['canonical_reset_pose_rpc_count']
    record['treatment_window_pose_rpc_count']=raw.get('treatment_window_pose_rpc_count')
    record['one_tick_treatment']['checkpoint_roles']={'PRE_RPC':'PRE_TREATMENT','POST_RPC':'POST_TREATMENT',
        'note':'Legacy checkpoint labels denote observation stages; their RPC type is Empty, never a pose request.'}
    output.mkdir(parents=True,exist_ok=True)
    with (output/'command_audit.ndjson').open('w') as stream:
        for item in record['command_audit']:
            stream.write(json.dumps(item,allow_nan=False)+'\n')
    history.write_json(output/'case_result.json',record)
    return record


def reset_provenance(record):
    logs=record['command_audit']
    cursor=record['reset_completion_cursor']
    reset_mark=record['reset_completion_marker']
    poses=[e for e in logs if e['kind']=='RPC' and is_pose_service(e['service'])]
    expected=record['configured_reset_condition']['target']
    reset=[e for e in poses if e['phase']=='canonical_reset']
    initialization=[e for e in poses if e['phase']=='initialization']
    if not reset or any(e['ordinal']>=cursor or e['marker']['sim_time_ns'] is None or e['marker']['iteration'] is None or
                        e['marker']['sim_time_ns']>reset_mark['sim_time_ns'] or
                        e.get('response',{}).get('data') is not True for e in initialization+reset):
        raise InvalidCapture('canonical reset pose RPC completion/provenance unavailable')
    if not any(e['payload']==expected for e in reset):
        raise InvalidCapture('canonical configured reset target not found in actual RPC log')
    if any(e['phase'] not in ('initialization','canonical_reset','after_experiment') for e in poses):
        raise InvalidCapture('pose RPC outside allowed production reset/initialization')
    first=dm.unique_match(record['events'],lambda e:e.get('canonical_index')==8,'Action08')
    if round(first['start_sim_time']*1e9)<reset_mark['sim_time_ns']:
        raise InvalidCapture('canonical history precedes reset completion')
    pre=record['one_tick_treatment']['boundary_marker']
    return {'initialization_pose_rpc_count':len(initialization),'reset_pose_rpc_count':len(reset),
            'pose_operations':poses,'reset_completion_marker':reset_mark,
            'reset_epoch':{'odometry':record['reset_evidence'].get('odometry_epoch'),
                           'support_epochs':sorted({r['epoch'] for r in record['support_rows'] if 'epoch' in r}),
                           'wrench_epochs':sorted({r['epoch'] for r in record['wrench_rows'] if 'epoch' in r}),
                           'process_partition':record['runtime_identity']['partition']},
            'full_reset_evidence':record['reset_evidence'],
            'treatment_PRE_marker':pre,'reset_completion_to_PRE_ns':pre['sim_time_ns']-reset_mark['sim_time_ns'],
            'signature':[{'phase':e['phase'],'payload':e['payload'],'request_type':e['request_type'],
                          'service_suffix':e['service'].split('/world/')[-1].split('/',1)[-1],
                          'RPC_attempt_count':len(e['transport_evidence']['attempts'])} for e in initialization+reset]}


def validate_pause(sync,marker):
    y.pause_sync_validity({'post_service_pause_synchronization':sync,
                          'before_Action24_publication_marker':marker})


def validate_acquisition_sensor_order(record):
    it=record['one_tick_treatment']
    before,after=(it[k] for k in ('production_sensor_cursor_PRE','production_sensor_cursor_POST'))
    if before!=after or type(before['previous_timestamp']) not in (int,float) or type(before['sequence']) is not int:
        raise InvalidCapture('diagnostic altered or lacks production sensor cursor')
    reads=record.get('production_sensor_reads')
    if not isinstance(reads,list) or any(r['phase']=='treatment' for r in reads):
        raise InvalidCapture('pre-UP diagnostic sensor read present or read audit missing')
    acquisition=[r for r in reads if r['phase']=='production_acquisition']
    if not acquisition:
        raise InvalidCapture('normal acquisition fresh sensor observation missing')
    publication=it['before_UP_publication_marker']['sim_time_ns']/1e9
    for r in acquisition:
        if (r.get('error') or r['command_audit_cursor']<=it['window_end_cursor'] or
            r.get('simulation_time') is None or r['simulation_time']<=publication or
            r.get('sample_timestamp',-1)<=before['previous_timestamp'] or
            r.get('sequence_after',-1)<=r['sequence_before']):
            raise InvalidCapture('fresh production acquisition sample not after UP/physics advancement')
    return {'ZERO_PRE_UP_FRESH_SAMPLE_NOT_REQUIRED_BY_DIAGNOSTIC':True,
            'PRODUCTION_SENSOR_FRESHNESS_UNCHANGED':True,'first_acquisition_sensor_read':acquisition[0]}


def validate(record,case,scenario,seed,reference,partitions,topics):
    check={'case_valid':False,'invalid_reasons':[],'physical_classifier_attempted':False}
    try:
        dm.terminal_event(record)  # guard inherited positional selection
        check.update(history.validate_candidate(record,plan(case),partitions,topics))
        reset=history.reset_validity(record,scenario,seed,reference)
        check['reset_validation']=reset
        check['invalid_reasons']+=reset['invalid_reasons']
        events=dm.required_events(record)
        for e in events:
            p=e.get('action_publication') or {}
            if p.get('commanded_twist')!=dm.gazebo_physics_twist(e['action']) or p.get('action_publish_sequence',-1)<=p.get('command_publish_sequence_before',-1):
                raise InvalidCapture('canonical actual fresh command publication missing')
            if e.get('canonical_index')!=24 and (e.get('exception') or e.get('terminated')):
                raise InvalidCapture('canonical history did not complete')
        maps,t0,_=dm.terminal_alignment(record)
        it=record['one_tick_treatment']
        if it.get('diagnostic_error'):
            raise InvalidCapture(str(it['diagnostic_error']))
        y.stopped_chunk(it['stopped_chunk'])
        entry=record['terminal_entry_history']
        expected=y.canonical_transition(entry['previous_command'])
        if any(entry.get(k)!=v for k,v in expected.items()):
            raise InvalidCapture('previous logical DOWN / normal adapter entry not preserved')
        selected=entry['production_plan']
        if (selected['request']['previous_command']!=dm.gazebo_physics_twist('down') or
            selected['request']['transition_type']!='LINEAR_REVERSAL' or
            [p['kind'] for p in selected['phases']]!=['BRAKE_LINEAR','ACQUIRE_LINEAR']):
            raise InvalidCapture('production LINEAR_REVERSAL plan changed')
        completed=it['completed_brake_checkpoint']
        if completed['active_physics_transactions']!=0 or record['production_step_trace']['active_depth']!=0 or completed['completed_brake_step']['verification']!=it['stopped_chunk']['step_evidence']:
            raise InvalidCapture('physics transaction still active or completed brake proof missing')
        if round(it['stopped_chunk']['simulation_end']*1e9)!=it['boundary_marker']['sim_time_ns']:
            raise InvalidCapture('treatment PRE not at successful brake boundary')
        for cp,mark,label in ((it['pre_checkpoint'],it['boundary_marker'],'PRE_RPC'),(it['post_checkpoint'],it['post_marker'],'POST_RPC')):
            state,_=checkpoints.validate(cp,mark,label)
            if state!=it['before' if label=='PRE_RPC' else 'after'] or cp['raw'] not in record['paused_checkpoints']:
                raise InvalidCapture('coherent checkpoint not serialized')
            same=dm.unique_match(record['native_samples'],lambda r:r.get('postupdate_count')==cp['raw']['postupdate_count'],'same-callback native')
            if any(same.get(k)!=v for k,v in cp['raw']['native'].items()):
                raise InvalidCapture('checkpoint native/raw stream mismatch')
            pose_command_counter(cp['raw']['native'])
        if len(record['paused_checkpoints'])!=2 or ab._finite_json_rows(Path(record['case_result_path']).parent/'paused_checkpoints.ndjson')!=record['paused_checkpoints']:
            raise InvalidCapture('complete paused checkpoint raw serialization missing')
        if it['post_checkpoint']['raw']['postupdate_count']<=it['pre_checkpoint']['raw']['postupdate_count']:
            raise InvalidCapture('PRE/POST phase provenance not ordered')
        validate_pause(it['pause_synchronization'],it['post_marker'])
        if (it['logical_before']!=it['logical_after'] or
            it['logical_after']['publish_sequence']!=it['logical_at_publication']['publish_sequence'] or
            it['logical_at_publication']['controller_command']!=dm.gazebo_physics_twist('up')):
            raise InvalidCapture('command/logical state changed inside treatment')
        window=audit_window(record['command_audit'],it['window_start_cursor'],it['window_end_cursor'])
        window_rpc_policy(case,record['command_audit'],it['window_start_cursor'],it['window_end_cursor'])
        fence=it['before_UP_publication_marker']
        verify_treatment(case,it['boundary_marker'],fence,it['logical_before']['publish_sequence'],it['logical_at_publication']['publish_sequence'],window['treatment_window_pose_rpc_count'])
        verify_treatment(case,it['boundary_marker'],it['post_marker'],0,0,0)
        count=tick_count(case)
        if count:
            v=it['extra_step_verification']
            if v.get('valid') is not True or v.get('iteration_delta')!=count or round((v['after_sim_time']-v['before_sim_time'])*1e9)!=count*1_000_000:
                raise InvalidCapture('N-tick progression not proven')
        elif 'extra_step_verification' in it:
            raise InvalidCapture('ZERO arm invoked diagnostic step')
        start=pose_command_counter(it['pre_checkpoint']['raw']['native'])
        end=pose_command_counter(it['before_UP_native'])
        if start['component_observations_total']!=end['component_observations_total'] or end['read_callbacks_total']<=start['read_callbacks_total']:
            raise InvalidCapture('NO_WORLDPOSECMD_DURING_TREATMENT not proven')
        # Assert the whole callback stream, not just endpoint counters.
        first_phase=it['pre_checkpoint']['raw']['postupdate_count']
        last_phase=it['before_UP_native']['postupdate_count']
        samples=[r for r in record['native_samples'] if first_phase<=r['postupdate_count']<=last_phase]
        if not samples or any(pose_command_counter(r)['component_observations_total']!=start['component_observations_total'] for r in samples):
            raise InvalidCapture('WorldPoseCmd present inside treatment native stream')
        if t0['publication_iteration']!=fence['iteration'] or t0['publication_sim_time_ns']!=fence['sim_time_ns']:
            raise InvalidCapture('additional progression between treatment fence and UP publication')
        fresh=record['command_audit'][it['window_end_cursor']]
        if fresh['kind']!='TWIST' or fresh['phase']!='production_acquisition' or fresh['payload']!=dm.gazebo_physics_twist('up') or not fresh.get('published'):
            raise InvalidCapture('fresh normal UP transport publication missing')
        for i in range(it['boundary_marker']['iteration']-5,t0['end_iteration']+1):
            dm.aligned_sample(maps,i,'treatment and terminal continuous coverage')
        directory=Path(record['case_result_path']).parent
        if ab._finite_json_rows(directory/'command_audit.ndjson')!=record['command_audit']:
            raise InvalidCapture('complete command audit raw serialization mismatch')
        for key,name in (('support_rows','continuous_support_iterations.ndjson'),('wrench_rows','joint_transmitted_wrench.ndjson')):
            if ab._finite_json_rows(directory/name)!=record[key]:
                raise InvalidCapture('raw/serialized mandatory stream mismatch: '+key)
        provenance=reset_provenance(record)
        check['sensor_order']=validate_acquisition_sensor_order(record)
        check.update(keyed_T0=t0,reset_RPC_provenance=provenance,treatment_window=window,
            TREATMENT_WINDOW_WORLD_POSE_CMD_COUNT=0,PREVIOUS_LOGICAL_ACTION_DOWN_PRESERVED=True,LINEAR_REVERSAL_PRESERVED=True)
        check.update(NO_POSE_RPC_DURING_TREATMENT=True,NO_WORLDPOSECMD_DURING_TREATMENT=True,
                     NO_EXTRA_COMMAND_PUBLICATION_DURING_TREATMENT=True,
                     extra_pre_acquisition_iterations=fence['iteration']-it['boundary_marker']['iteration'],
                     extra_pre_acquisition_sim_time_ns=fence['sim_time_ns']-it['boundary_marker']['sim_time_ns'])
        check['EXACT_TICK_ADVANCEMENT']=True
        check['ZERO_TICK_EXACT' if count==0 else 'ONE_TICK_EXACT' if count==1 else f'TICK_{count}_EXACT']=True
        check['case_valid']=not check['invalid_reasons']
    except Exception as exc:
        check['case_valid']=False
        check.setdefault('invalid_reasons',[]).append(type(exc).__name__+': '+str(exc))
        check['validation_traceback']=traceback.format_exception(type(exc),exc,exc.__traceback__)
    return check


def pre_equivalence(a,b,limits):
    delta=y.deltas(a,b)
    failures=[]
    if delta is None:
        return {'classification':'PRE_TREATMENT_ARMS_DIFFERENT','failures':['contact cardinality differs']}
    rows={k:{'delta':v,'frozen_limit':limits['pair_difference_of_changes_limits'][k],
             'pass':abs(v)<=limits['pair_difference_of_changes_limits'][k]} for k,v in delta.items()}
    yaw=y.wrapped(b['yaw_rad']-a['yaw_rad'])
    rows['yaw_rad']={'delta':yaw,'frozen_limit':2*limits['yaw_target_tolerance_rad'],'pass':abs(yaw)<=2*limits['yaw_target_tolerance_rad']}
    failures += [k for k,v in rows.items() if not v['pass']]
    for k,v in a['supports'].items():
        if v['state']!=b['supports'][k]['state']:failures.append(k+'.state')
    for name,state in (('ZERO',a),('ONE',b)):
        if any(math.sqrt(sum(x*x for x in state[key]))>limits['wheel_stopped_linear_equivalent_m_s'] for key in ('linear_velocity_world_m_s','angular_velocity_world_rad_s')):
            failures.append(name+'.not_stopped')
        if any(abs(state['joint_transmitted_wrench'][s]['actual_velocity_rad_s'])*.1>limits['wheel_stopped_linear_equivalent_m_s'] for s in ('left','right')):
            failures.append(name+'.wheel_not_stopped')
    return {'classification':'PRE_TREATMENT_ARMS_DIFFERENT' if failures else 'PRE_TREATMENT_ARMS_EQUIVALENT',
            'failures':failures,'checks':rows,'ZERO':a,'ONE':b}


def descriptive_delta(a,b):
    # Cardinalities can change due to the actual tick. Retain entire arrays;
    # never drop the description or impose a POST isolation equality gate.
    af,bf=y.features(a),y.features(b)
    phases={label:{**state['wheel_phase_mod_2pi_rad'],
                   'differential_phase_rad':(state['wheel_phase_mod_2pi_rad']['left']-state['wheel_phase_mod_2pi_rad']['right'])/2,
                   'common_phase_rad':(state['wheel_phase_mod_2pi_rad']['left']+state['wheel_phase_mod_2pi_rad']['right'])/2}
            for label,state in (('ZERO',a),('ONE',b))}
    phase_delta={s:y.wrapped(b['wheel_phase_mod_2pi_rad'][s]-a['wheel_phase_mod_2pi_rad'][s]) for s in ('left','right')}
    phase_delta.update(differential_phase_rad=(phase_delta['left']-phase_delta['right'])/2,
                       common_phase_rad=(phase_delta['left']+phase_delta['right'])/2)
    return {'ZERO':a,'ONE':b,'shared_scalar_deltas':{k:bf[k]-v for k,v in af.items() if k in bf},
            'ZERO_only_scalar_fields':sorted(af.keys()-bf.keys()),'ONE_only_scalar_fields':sorted(bf.keys()-af.keys()),
            'support_states':{k:{'ZERO':v['state'],'ONE':b['supports'][k]['state']} for k,v in a['supports'].items()},
            'phase_measurements':phases,'phase_deltas':phase_delta,
            'description_only_not_an_isolation_gate':True}


def command_suffix(record):
    down=dm.unique_match(record['events'],lambda e:e.get('canonical_index')==23,'Action23')
    ns=round(down['action_publication']['action_command_sim_time']*1e9)
    end=record['one_tick_treatment']['window_end_cursor']
    logs=record['command_audit']
    candidates=[i for i,e in enumerate(logs[:end]) if e['kind']=='TWIST' and e.get('published') and
                e['payload']==dm.gazebo_physics_twist('down') and e['marker']['sim_time_ns']==ns]
    if len(candidates)!=1:raise InvalidCapture('actual final DOWN publication ambiguous/missing')
    result=copy.deepcopy([e for e in logs[candidates[0]:end+1] if e['kind']=='TWIST'])
    for i,e in enumerate(result):
        e['terminal_sequence_phase']=('Action23_final_DOWN' if i==0 else
             'production_acquisition' if e['ordinal']==end else 'production_braking')
    return result


def pair_identity_gate(a,b):
    if (a['configured_reset_condition']!=b['configured_reset_condition'] or
        any(not a['runtime_identity'].get(k) or not b['runtime_identity'].get(k) or
            a['runtime_identity'][k]==b['runtime_identity'][k] for k in ('partition','topic')) or
        not a.get('shutdown_completed') or not b.get('shutdown_completed') or
        a['wall_end_after_shutdown_monotonic_s']>b['wall_start_monotonic_s']):
        raise InvalidCapture('case configuration/fresh-process/shutdown isolation failed')


def earliest_differences(rows):
    result={}
    for row in rows:
        if row['delta_ms']<0:continue
        a,b=(row[c] for c in CASES)
        flags={
            'support_Fn':any(a['supports'][k]['Fn_N']!=b['supports'][k]['Fn_N'] for k in a['supports']),
            'contact_topology':any(a['supports'][k]['state']!=b['supports'][k]['state'] for k in a['supports']),
            'contact_depth':any(a['supports'][k]['depths_m']!=b['supports'][k]['depths_m'] for k in a['supports']),
            'joint_wrench':any(a['joint_transmitted_wrench'][s][k]!=b['joint_transmitted_wrench'][s][k]
                               for s in ('left','right') for k in ('force_xyz_N','torque_xyz_N_m')),
            'body_forward_translation':a['native_forward_displacement_from_T0_m']!=b['native_forward_displacement_from_T0_m']}
        for key,yes in flags.items():
            if yes and key not in result:result[key]={'delta_ms':row['delta_ms'],'ZERO_iteration':a['iteration'],'ONE_iteration':b['iteration']}
    return {'first_exact_nonzero_difference':result,
            'interpretation':'Exact numerical differences are not automatically material branches. Inspect full support/wrench trajectories and unchanged recovery classifier. No sub-ms order is asserted.'}


def analyze(records,checks,limits):
    if not all(checks.get(c,{}).get('case_valid') for c in CASES):
        raise InvalidCapture('invalid telemetry cannot be physically classified')
    a,b=(records[c] for c in CASES)
    pair_identity_gate(a,b)
    if checks[CASES[0]]['reset_RPC_provenance']['signature']!=checks[CASES[1]]['reset_RPC_provenance']['signature']:
        raise InvalidCapture('RESET_POSE_RPC_BEHAVIOR_EQUIVALENT failed')
    sequences={c:command_suffix(records[c]) for c in CASES}
    if [e['payload'] for e in sequences[CASES[0]]]!=[e['payload'] for e in sequences[CASES[1]]]:
        raise InvalidCapture('actual DOWN/braking/UP Twist sequences differ')
    if a['terminal_entry_history']['production_plan']!=b['terminal_entry_history']['production_plan']:
        raise InvalidCapture('executor/planner state differs between arms')
    eq=pre_equivalence(a['one_tick_treatment']['before'],b['one_tick_treatment']['before'],limits)
    report={'status':'CAPTURED','capture_integrity':checks,'PRE_equivalence':eq,
            'RESET_POSE_RPC_BEHAVIOR_EQUIVALENT':True,'command_suffixes':sequences,
            'post_treatment_description':descriptive_delta(a['one_tick_treatment']['after'],b['one_tick_treatment']['after']),
            'frozen_tolerances':limits,'yaw_causal_status':'YAW_CAUSAL_RELEVANCE_UNRESOLVED',
            'diagnostic_asymmetry':'Same two checkpoints and explicit pause per arm; ONE additionally issues exactly one WorldControl multi_step=1. Callback counts/delivery need not match; advancing iteration counts must.'}
    if eq['classification']!='PRE_TREATMENT_ARMS_EQUIVALENT':
        report.update(status='PRE_TREATMENT_EQUIVALENCE_FAILED',interpretation='CAUSAL_INTERPRETATION_BLOCKED',physical_classification_created=False)
        return report
    physical={c:history.classify_candidate(records[c],checks[c]) for c in CASES}
    result=outcome_interpretation(*(physical[c]['classification'] for c in CASES))
    tables={}
    for c in CASES:
        checks[c]['physical_classifier_attempted']=True
        maps,t0,_=dm.terminal_alignment(records[c]);origin=dm.state_at(records[c],t0['iteration'],maps)
        validator=physical[c]['production_movement_validator'];times=validator.get('odometry_sample_timestamps',[])
        tables[c]=[]
        for i in range(t0['iteration']-5,t0['end_iteration']+1):
            state=dm.state_at(records[c],i,maps)
            phases=state['wheel_phase_mod_2pi_rad'];state['differential_phase_rad']=(phases['left']-phases['right'])/2;state['common_phase_rad']=(phases['left']+phases['right'])/2
            dx,dy=(state['position_world_m'][j]-origin['position_world_m'][j] for j in (0,1))
            state['native_forward_displacement_from_T0_m']=dx*math.cos(origin['yaw_rad'])+dy*math.sin(origin['yaw_rad'])
            found=[j for j,t in enumerate(times) if round(t*1e9)==state['sim_time_ns']]
            state['odometry']={'exact_sample_available':bool(found),'source':'production native DiffDrive; 10ms samples, no interpolation'}
            if len(found)==1:
                j=found[0];state['odometry'].update(linear_x=validator['odometry_sample_linear_x'][j],angular_z=validator['odometry_sample_angular_z'][j])
            state['collision_assessment_for_acquisition']=physical[c]['collision']
            tables[c].append({'delta_ms':i-t0['iteration'],**state})
    aligned=[{'delta_ms':dt,**{c:dm.unique_match(tables[c],lambda row:row['delta_ms']==dt,'exact relative sample') for c in CASES}} for dt in range(-5,100)]
    # Raw deltas at every iteration. Differentiate tiny nonzero changes from a
    # contact-state/support-recovery branch; no new physical threshold is fitted.
    divergence=[]
    for row in aligned:
        diff=descriptive_delta(row[CASES[0]],row[CASES[1]])
        divergence.append({'delta_ms':row['delta_ms'],**diff})
    report.update(Action24=physical,case_outcomes={c:physical[c]['classification'] for c in CASES},
        T0={c:dm.command_active_t0(records[c]) for c in CASES},relative_iteration_table=aligned,
        trajectory_comparison=divergence,baseline_reproduction_gate=result['baseline_gate'],
        outcome_pattern=result['pattern'],causal_interpretation_allowed=result['causal_interpretation_allowed'],
        interpretation=result['pattern'] if result['baseline_gate']=='PASS' else result['baseline_gate'],
        physical_classification_created=True,
        hidden_state_caution='Any contextual tick sufficiency does not identify contact/solver state. No sub-ms order claimed. Yaw causal status remains unresolved.')
    report['earliest_observable_differences']=earliest_differences(aligned)
    if result['baseline_gate']!='PASS':report['status']='ZERO_TICK_BASELINE_REPRODUCTION_FAILED'
    return report



def audit_host1_sensor_failure():
    """Read-only infrastructure audit. Never call a physical outcome classifier."""
    result={'classification':'PHASE_3H_AN_G_HOST1_ZERO_TICK_CAPTURE_INFRASTRUCTURE_FAILURE',
            'pair_valid':False,'physical_interpretation_created':False,
            'ONE_classification':'ONE_TICK_CURRENTLY_CONFOUNDED_WITH_SENSOR_FRESHNESS_GATE',
            'yaw_causal_status':'YAW_CAUSAL_RELEVANCE_UNRESOLVED','cases':{}}
    for c in CASES:
        path=HOST1/c/'case_result.json'
        r=json.loads(path.read_text());it=r['one_tick_treatment'];event=dm.terminal_event(r)
        rawcp=r['paused_checkpoints']
        if len(rawcp)!=2:raise InvalidCapture('Host1 PRE/POST checkpoint evidence differs')
        saved=json.loads((path.parent/'capture_integrity.json').read_text())
        counts={key:len({row['iteration'] for row in r[key] if row.get('paused') is False and
                        (key=='native_samples' or row.get('kind')==('support_iteration' if key=='support_rows' else 'joint_wrench_sample'))})
                for key in ('support_rows','wrench_rows','native_samples')}
        twists=[e for e in r['command_audit'] if e['kind']=='TWIST']
        action23=dm.unique_match(r['events'],lambda e:e.get('canonical_index')==23,'Host1 Action23')
        err=it.get('diagnostic_error') or {}
        proof={'case_result':str(path),'sha256':sha(path),'saved_runtime_case_valid':saved['case_valid'],
               'stream_unique_advancing_iterations':counts,'last_valid_advancing_iteration':max(row['iteration'] for row in r['native_samples'] if row.get('paused') is False),
               'final_sim_time_s':r['final_sim_time'],'shutdown_completed':r['shutdown_completed'],
               'Action23':{'start':action23['start_sim_time'],'end':action23['end_sim_time']},
               'stopped_boundary':it['boundary_marker'],'stopped_pass':it['stopped_chunk']['body_stopped_contract']['pass'],
               'PRE_checkpoint':{'iteration':rawcp[0]['iteration'],'time_ns':rawcp[0]['sim_time_ns'],'phase':rawcp[0]['postupdate_count']},
               'POST_checkpoint':{'iteration':rawcp[1]['iteration'],'time_ns':rawcp[1]['sim_time_ns'],'phase':rawcp[1]['postupdate_count'],
                                  'stored_in_treatment_object':'post_checkpoint' in it},
               'fresh_UP_reached':event['up_reached'],'terminal_publication':event.get('action_publication'),
               'last_Twist_publications':twists[-5:],'diagnostic_error':err}
        if c==CASES[0]:
            message='No fresh Gazebo sample: /aero/aero_ef81a06d3164/scan, expected sim time >= 3.600000001'
            trace=''.join(err.get('traceback',[]))
            if (saved['case_valid'] or err.get('message')!=message or 'adapter.env._refresh()' not in trace or
                event['up_reached'] or r['final_sim_time']!=3.6 or rawcp[1]['iteration']!=3600):
                raise InvalidCapture('Host1 ZERO evidence does not match diagnosed refresh regression')
            proof.update(classification='INFRASTRUCTURE_FAILURE_NOT_PHYSICAL_FAILURE',
                last_consumed_scan_timestamp_s=3.6,
                scan_timestamp_provenance='Derived from saved exact requested bound and unchanged provider max(min_time, previous_timestamp+1e-9): min_time=3.598; previous_timestamp=3.6. A raw final scan packet was not separately saved.',
                requested_scan_minimum_s=3.600000001,
                stale_terminal_telemetry_note='ZERO terminal telemetry retains Action23 sensor frame3.4; it is not the failed callback current scan. Do not use it as final scan timestamp.',
                no_fresh_UP_publication=not any(e['payload']==dm.gazebo_physics_twist('up') and e['marker']['sim_time_ns']>=3_400_000_000 for e in twists))
        else:
            if not saved['case_valid'] or not event['up_reached'] or rawcp[1]['iteration']!=3601:
                raise InvalidCapture('Host1 ONE infrastructure evidence changed')
            dm.terminal_alignment(r)  # synchronized coverage only; no physical verdict
            before=event['telemetry']['sensor_before'];after=event['telemetry']['sensor_after']
            if before['timestamp']!=3.601:raise InvalidCapture('ONE pre-acquisition scan evidence changed')
            proof.update(classification='RUNTIME_CAPTURE_VALID_NO_PHYSICAL_INTERPRETATION',
                scan_before_UP=before,scan_after_acquisition=after,
                last_stopped_consumed_scan_timestamp_s=3.6,
                scan_before_diagnostic_refresh_source='production final braking read, same3600 boundary; one new tick supplies3.601',
                treatment_tick_iterations=it['extra_pre_acquisition_iterations'],
                treatment_tick_ns=it['extra_pre_acquisition_sim_time_ns'])
        result['cases'][c]=proof
        del r
    baseline=dm.DEFAULT_OUTPUT/'RIGHT_HISTORY/case_result.json'
    r=json.loads(baseline.read_text());event=dm.terminal_event(r)
    phases=ab._find_phase_evidence(event['execution_evidence'])
    brake=dm.unique_match(phases,lambda p:p.get('phase')=='BRAKE_LINEAR','H-AL brake')
    acquire=dm.unique_match(phases,lambda p:p.get('phase')=='ACQUIRE_LINEAR','H-AL acquisition')
    if (event.get('exception',{}).get('type')!='PhysicalControlFailure' or
        event['action_publication'].get('action_command_sim_time')!=3.6 or
        brake['chunks'][-1]['task_outcome']['sensor_contract']['timestamp']!=3.6):
        raise InvalidCapture('accepted H-AL canonical ordering evidence differs')
    result['canonical_H_AL']={'source':str(baseline),'sha256':sha(baseline),
        'production_sha256':r['observer_sdf']['production_sdf_sha256_before'],
        'Action23_end_s':r['events'][-2]['end_sim_time'],
        'brake_chunks':[{'start_s':c['simulation_start'],'end_s':c['simulation_end'],
                         'stopped_pass':c['body_stopped_contract']['pass'],'sensor_contract':c.get('task_outcome',{}).get('sensor_contract')} for c in brake['chunks']],
        'acquisition_start_s':acquire['start_sim_time'],
        'fresh_UP_publication':event['action_publication'],
        'sensor_before_acquisition':brake['chunks'][-1].get('task_outcome',{}).get('sensor_contract'),
        'sensor_after_acquisition':{'status':'exact scan packet timestamp not separately preserved',
            'source_proof':'PhysicalControlFailure occurs in movement validation after production env._step completed _refresh; no pre-UP consuming refresh exists in this baseline.',
            'minimum_from_unchanged_provider_at_3_7s':3.698},
        'stale_terminal_telemetry_not_acquisition':{
            'sensor_before':event['telemetry']['sensor_before'],'sensor_after':event['telemetry']['sensor_after'],
            'note':'These retained Action23 frames (3.3/3.4) must not be labelled Action24 acquisition sensor frames.'},
        'physical_result':'accepted canonical failure; not reclassified in this audit'}
    result['root_cause']={'old_diagnostic_source_function':'perform_treatment',
        'Host1_traceback_line':240,'expression':'adapter.env._refresh()',
        'production_refresh_source':'src/aero_ai_studio/gazebo/environment.py:237',
        'lower_bound_origin':'src/aero_ai_studio/gazebo/sensor_provider.py:33: minimum=max(min_time,previous_timestamp+1e-9)',
        'numeric_evaluation':'max(3.600-0.002, 3.600+1e-9) = 3.600000001',
        'first_logical_order_difference':'H-AL returns from stopped callback to normal acquisition/publication. Host1 diagnostic calls a consuming sensor refresh before callback return; ZERO is paused with no future sample.',
        'not_a_marker_or_checkpoint_time_failure':True,
        'checkpoint_read_freshness':'PRE/POST Pose_V and native may be freshly delivered at same paused time; neither establishes advancing LiDAR freshness.'}
    result['repair']={'change':'Remove diagnostic env._refresh; retain evidence-only get_pose and coherent checkpoint corroboration.',
        'unchanged_production_cache':'Leave env.pose, env.observation, provider previous_timestamp/sequence unchanged during treatment.',
        'diagnostic_sensor_read_guard':'Any get_range_observation call during treatment is rejected before invoking provider.',
        'normal_acquisition_order':'fresh production UP -> ordinary physics advancement -> unchanged production _refresh/get_range_observation',
        'extra_ZERO_iterations':0,'extra_ZERO_ns':0}
    return result

PREFLIGHT_GATES = ('CANONICAL_RESET_POSE_RPC_ALLOWED','RESET_POSE_RPC_BEHAVIOR_EQUIVALENT',
    'NO_POSE_RPC_DURING_TREATMENT','NO_WORLDPOSECMD_DURING_TREATMENT',
    'ZERO_TICK_EXACT','ONE_TICK_EXACT','NO_EXTRA_COMMAND_PUBLICATION_DURING_TREATMENT',
    'PREVIOUS_LOGICAL_ACTION_DOWN_PRESERVED','LINEAR_REVERSAL_PRESERVED',
    'EVENT_RELATIVE_ALIGNMENT_READY','BASELINE_REPRODUCTION_GATE_ENABLED',
    'ZERO_PRE_UP_FRESH_SAMPLE_NOT_REQUIRED_BY_DIAGNOSTIC',
    'CANONICAL_FRESH_UP_PUBLICATION_REACHABLE','PRODUCTION_SENSOR_FRESHNESS_UNCHANGED',
    'NO_EXTRA_COMMAND_DURING_TREATMENT','HOST1_PRESERVED')


def production_sensor_order_contract():
    environment=ROOT/'src/aero_ai_studio/gazebo/environment.py'
    step=method(environment,'GazeboEnvironment','_step')
    positions={name:min(n.lineno for n in calls(step,name))
               for name in ('apply_action','step_simulation','_refresh')}
    if not positions['apply_action']<positions['step_simulation']<positions['_refresh']:
        raise InvalidCapture('production publication/advancement/sensor ordering changed')
    cached=method(environment,'GazeboEnvironment','get_agent_observation')
    if calls(cached,'get_range_observation') or calls(cached,'_refresh'):
        raise InvalidCapture('production before-observation is no longer cached')
    node=next(n for n in ast.parse(Path(__file__).read_text()).body
              if isinstance(n,ast.FunctionDef) and n.name=='perform_treatment')
    if calls(node,'_refresh') or calls(node,'get_range_observation'):
        raise InvalidCapture('diagnostic still requests pre-UP fresh sensor')
    saved=json.loads((HOST1/'one_tick_control_preflight.json').read_text())['protected_source_sha256_before_after']
    protected={p:h for p,h in saved.items() if '/src/' in p and Path(p).suffix=='.py'}
    for p,h in protected.items():
        if sha(p)!=h:raise InvalidCapture('production sensor/control source changed: '+p)
    return {'production_step_call_lines':positions,'cached_before_observation':True,
            'diagnostic_consuming_refresh_calls':0,'production_source_sha256':protected}


def verify_static_builds(builds):
    for name in ('support','wrench'):
        b=builds[name]
        if b.get('plugin_info_exit_code')!=0 or b.get('ldd_exit_code')!=0 or b.get('unresolved_dependencies'):
            raise InvalidCapture('observer static load/dependency check failed: '+name)
    b=builds['native']['static_inspection']
    if b.get('registration_status')!='PASS' or b.get('dependencies_status')!='PASS':
        raise InvalidCapture('native observer static load/dependency check failed')


def contract_self_check():
    def mark(i):return {'iteration':i,'sim_time_ns':i*1_000_000,'paused':True}
    for c in CASES:
        verify_treatment(c,mark(3600),mark(3600+CASES.index(c)),10,10,0)
    logs=[{'kind':'RPC','service':'/world/x/set_pose','phase':'canonical_reset'},
          {'kind':'RPC','service':'/checkpoint','phase':'treatment'},
          {'kind':'TWIST','payload':dm.gazebo_physics_twist('up'),'phase':'production_acquisition'}]
    assert audit_window(logs,1,2)['treatment_window_pose_rpc_count']==0
    for item in ({'kind':'RPC','service':'/world/x/set_pose'}, {'kind':'TWIST'}):
        try:audit_window([item],0,1)
        except InvalidCapture:pass
        else:raise InvalidCapture('negative treatment regression not enforced')
    from aero_ai_studio.simulation.control_execution import ControlExecutionRequest,plan_control_execution
    selected=plan_control_execution(ControlExecutionRequest('up',dm.gazebo_physics_twist('down'),dm.gazebo_physics_twist('up'),'LINEAR_REVERSAL')).to_dict()
    assert [p['kind'] for p in selected['phases']]==['BRAKE_LINEAR','ACQUIRE_LINEAR']
    assert outcome_interpretation('SUPPORT_RECOVERY_AND_TRANSLATION_SUCCESS','SUPPORT_RECOVERY_AND_TRANSLATION_SUCCESS')['baseline_gate']=='ZERO_TICK_BASELINE_REPRODUCTION_FAILED'
    return selected


def preflight(output,artifact_dir=None):
    output=ensure_output(output)
    artifact_dir=artifact_dir or ab.DEFAULT_ARTIFACT
    guard=protected_manifest()
    scenario,seed,_=history.source(artifact_dir)
    clock=dm.clock_spec()
    selected=contract_self_check()
    source_order=production_sensor_order_contract()
    host1_audit=audit_host1_sensor_failure()
    limits=y.tolerance_spec()
    digest=y.frozen_tolerance_digest(limits)
    libraries,builds=ab._build_all(output/'observer_builds')
    verify_static_builds(builds)
    namespace=uuid4().hex
    definitions=[]
    for c in CASES:
        directory=output/'preflight_sdfs'/c
        prod=ab.GazeboWorldGenerator().generate(scenario,directory/'world',closed_loop=True,control_mode='PHYSICS')
        diag,info=ab._instrument_world(prod,directory/'observer_outputs',libraries,topic_identity=c+'/'+namespace)
        diag,info=checkpoints.instrument(diag,info)
        diag,info=instrument_audit(diag,info)
        root=ET.parse(diag)
        if sha(prod)!=EXPECTED_SHA or round(float(root.findtext('world/physics/max_step_size'))*1e9)!=1_000_000:
            raise InvalidCapture('production hash or fixed physics step changed')
        if root.findtext("world/plugin[@name='aero_diagnostic::NativeLinkVelocityObserver']/audit_world_pose_commands")!='true':
            raise InvalidCapture('read-only WorldPoseCmd monitoring not composed')
        definitions.append({'plan':plan(c),'diagnostic_sdf':str(diag),'instrumentation':info})
    if len({d['instrumentation']['native']['topic'] for d in definitions})!=2:
        raise InvalidCapture('fresh topic identities collide')
    if list(output.rglob('*.ndjson')) or list(output.rglob('case_result.json')):
        raise InvalidCapture('preflight created runtime evidence')
    history.verify_manifest(guard)
    report={'status':'PREFLIGHT_PASS','runtime_execution_enabled':True,
        'gates':{gate:True for gate in PREFLIGHT_GATES},'proof_scope':'Static composition and positive/negative offline contract tests; actual arm validity and equivalence remain mandatory Host gates.',
        'reset_rpc_audit':reset_rpc_audit(),'scope':'Canonical production initialization/reset pose RPC allowed; zero pose RPC/WorldPoseCmd/Twist only in treatment window.',
        'treatment_window':{'start':'successful stopped boundary before coherent PRE collection','end':'normal production fresh UP publication exclusive; no physics advancement after POST allowed except the configured extra tick'},
        'cases':definitions,'scenario_seed':42,'reset_seed':seed,'configured_reset_target':history.configured_reset_target(scenario),
        'clock':clock,'production_DOWN_UP_plan':selected,'frozen_tolerances':limits,'frozen_tolerance_digest':digest,
        'observer_builds':builds,'gazebo_launched':False,'runtime_evidence_created':False,
        'host1_infrastructure_audit':host1_audit,'production_sensor_order_contract':source_order,
        'diagnostic_asymmetry':'Same PRE/POST observation-only checkpoint RPCs and explicit pause ACK. ONE additionally has one WorldControl multi_step=1. No wall-clock waiting is physics treatment.',
        'WorldPoseCmd_proof':'Opt-in native observer reads const WorldPoseCmd on all entities at PreUpdate/PostUpdate. Active count zero and cumulative count unchanged from PRE through fresh UP required. Observations are not distinct command IDs.',
        'production_sha256_before':EXPECTED_SHA,'production_sha256_after':EXPECTED_SHA,'production_changed':False,
        'protected_source_sha256_before_after':guard,'runner_sha256':sha(__file__)}
    history.write_json(output/'one_tick_control_preflight.json',report)
    history.write_json(output/'host1_zero_tick_sensor_forensics.json',host1_audit)
    return report


def run(output,artifact_dir=None):
    output=ensure_output(output)
    artifact_dir=artifact_dir or ab.DEFAULT_ARTIFACT
    guard=protected_manifest()
    scenario,seed,_=history.source(artifact_dir)
    contract_self_check()
    dm.clock_spec()
    limits=y.tolerance_spec();y.frozen_tolerance_digest(limits)
    libraries,builds=ab._build_all(output/'observer_builds')
    verify_static_builds(builds)
    records,checks,parts,topics={},{},set(),set()
    namespace,reference=uuid4().hex,None
    for c in CASES:
        if c!=CASES[0] and not records.get(CASES[0],{}).get('shutdown_completed'):
            checks[c]={'case_valid':False,'invalid_reasons':['previous process shutdown not proven']}
            break
        directory=output/c
        directory.mkdir(parents=True)
        try:
            record=capture(c,scenario,directory,libraries,seed,namespace)
            records[c]=record
            checks[c]=validate(record,c,scenario,seed,reference,parts,topics)
            reference=reference or record.get('canonical_reset_pose')
            parts.add(record['runtime_identity']['partition']);topics.add(record['runtime_identity']['topic'])
        except Exception as exc:
            checks[c]={'case_valid':False,'invalid_reasons':[type(exc).__name__+': '+str(exc)],'physical_classifier_attempted':False,
                       'traceback':traceback.format_exception(type(exc),exc,exc.__traceback__)}
        history.write_json(directory/'capture_integrity.json',checks[c])
        print(c+': '+('RUNTIME_CAPTURE_VALID' if checks[c]['case_valid'] else 'CAPTURE_INVALID'),flush=True)
    try:
        history.verify_manifest(guard)
        report=analyze(records,checks,limits)
    except Exception as exc:
        report={'status':'CAPTURE_FAILED','capture_integrity':checks,'interpretation':'CAPTURE_INVALID',
                'diagnostic_error':type(exc).__name__+': '+str(exc),'physical_classification_created':False}
    report.update(yaw_causal_status='YAW_CAUSAL_RELEVANCE_UNRESOLVED',observer_builds=builds,
                  production_changed=False,protected_source_sha256_before_after=guard,runner_sha256=sha(__file__))
    history.write_json(output/'one_tick_control_analysis.json',report)
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preflight-only',action='store_true')
    parser.add_argument('--host-run',action='store_true',help='explicit Host runtime opt-in; never use inside Codex')
    parser.add_argument('--output',type=Path,default=DEFAULT_OUTPUT)
    parser.add_argument('--artifact-dir',type=Path,default=ab.DEFAULT_ARTIFACT)
    args=parser.parse_args(argv)
    if args.preflight_only==args.host_run:
        print('CAPTURE_FAILED: select --preflight-only or explicit --host-run');return 1
    try:
        report=preflight(args.output,args.artifact_dir) if args.preflight_only else run(args.output,args.artifact_dir)
    except Exception as exc:
        print('CAPTURE_FAILED: '+type(exc).__name__+': '+str(exc));return 1
    if report['status']=='PREFLIGHT_PASS':
        for gate in PREFLIGHT_GATES:print(gate)
    if report.get('PRE_equivalence'):print(report['PRE_equivalence']['classification'])
    for c,label in report.get('case_outcomes',{}).items():print(c+': '+label)
    print(report['status']);print('evidence: '+str(args.output))
    if report.get('outcome_pattern'):print('outcome pattern: '+report['outcome_pattern'])
    if report.get('interpretation'):print('interpretation: '+report['interpretation'])
    if report.get('diagnostic_error'):print(report['diagnostic_error'])
    if report['status']=='CAPTURE_FAILED':
        for c,check in report.get('capture_integrity',{}).items():
            print(c+': '+'; '.join(check.get('invalid_reasons',[])))
    print('YAW_CAUSAL_RELEVANCE_UNRESOLVED')
    return 0 if report['status'] in ('PREFLIGHT_PASS','CAPTURED') else 1


if __name__=='__main__':
    raise SystemExit(main())
