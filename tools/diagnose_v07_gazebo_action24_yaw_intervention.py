#!/usr/bin/env python3
"""Diagnostic-only, same-service pre-Action24 yaw intervention; Host runtime only.

The hook is after a completed braking WorldControl transaction, before the
executor creates acquisition baselines. Keep normal DOWN-to-UP planner history.
An explicit pause RPC and fresh exact stats synchronize the single diagnostic
tick; an acknowledged tick alone is not explicit paused-marker evidence.
"""
from __future__ import annotations

import argparse
import copy
import math
import threading
import time
import traceback
from pathlib import Path
from uuid import uuid4
import json
import xml.etree.ElementTree as ET

from tools import diagnose_v07_gazebo_action24_duration_matched as dm
from tools import gazebo_yaw_checkpoints as checkpoints
from aero_ai_studio.simulation.action_mapping import classify_physics_command_transition

history, ab = dm.history, dm.ab
InvalidCapture = history.InvalidCapture
CASES = ("RIGHT_YAW_SHAM", "RIGHT_YAW_MATCHED")
TARGETS = dict(zip(CASES, (0.282913297223, 0.378577077577)))
HOST1 = ab.ROOT / "validation/v071-host/gazebo-action24-yaw-intervention-phase3han-host1"
HOST2 = ab.ROOT / "validation/v071-host/gazebo-action24-yaw-intervention-phase3han-host2"
DEFAULT_OUTPUT = ab.ROOT / "validation/v071-host/gazebo-action24-yaw-intervention-phase3han-host3"
REFERENCE = dm.DEFAULT_OUTPUT / "duration_matched_final_analysis.json"
POST_STEPS = 1
STEP_NS = 1_000_000
PROTECTED = (*dm.PROTECTED, dm.DEFAULT_OUTPUT, HOST1, HOST2)


def plan(case):
    if case not in CASES:
        raise ValueError("unknown yaw arm")
    return {**history.candidate(15), "name":case, "yaw_target_rad":TARGETS[case],
            "post_service_advancing_iterations":POST_STEPS, "post_service_elapsed_ns":STEP_NS}


def ensure_output(path):
    path = Path(path).resolve()
    for prior in PROTECTED:
        prior = prior.resolve()
        if path == prior or path.is_relative_to(prior) or prior.is_relative_to(path):
            raise FileExistsError("output overlaps preserved evidence: " + str(prior))
    return path


def write_json(path, value):
    ensure_output(path)
    history.write_json(path, value)


def protected_manifest():
    paths = [p for p in (ab.ROOT/"src").rglob("*") if p.is_file() and p.suffix in (".py", ".sdf")]
    paths += [Path(dm.__file__), Path(history.__file__), Path(ab.__file__), Path(__file__), Path(checkpoints.__file__),
              ab.ROOT/"tools/gazebo_paused_physical_checkpoint.hh",ab.ROOT/"tools/gazebo_native_link_velocity_observer.cc",REFERENCE,
              ab.DEFAULT_ARTIFACT/"worlds/aero_ef81a06d3164/world.sdf"]
    for prior in PROTECTED:
        paths += [p for p in prior.rglob("*") if p.is_file() and p.suffix in (".json", ".ndjson", ".sdf", ".log")]
    paths += [p for prior in (HOST1,HOST2) for p in prior.rglob("*") if p.is_file()]
    return {str(p.resolve()):ab._sha(p) for p in set(paths)}


def wrapped(value):
    return math.atan2(math.sin(value), math.cos(value))


def rpy_quaternion(roll, pitch, yaw):
    cr, sr = math.cos(roll/2), math.sin(roll/2)
    cp, sp = math.cos(pitch/2), math.sin(pitch/2)
    cy, sy = math.cos(yaw/2), math.sin(yaw/2)
    return [sr*cp*cy-cr*sp*sy, cr*sp*cy+sr*cp*sy,
            cr*cp*sy-sr*sp*cy, cr*cp*cy+sr*sp*sy]


def pose_payload(state, case, model):
    """Pure math builder; runtime callers must use request_from_checkpoint."""
    if case not in CASES or model != "simple_agent":
        raise InvalidCapture("unexpected arm/model identity")
    xyz = dm.vector(state.get("position_world_m"), 3, "current measured XYZ")
    r, p = state["roll_rad"], state["pitch_rad"]
    if not all(math.isfinite(v) for v in (r,p)):
        raise InvalidCapture("nonfinite roll/pitch")
    q = rpy_quaternion(r,p,TARGETS[case])
    return {"name":model,"position":dict(zip(("x","y","z"),xyz)),
            "orientation":dict(zip(("x","y","z","w"),q))}


def rotate_inverse(q, vector):
    return dm.qmul(dm.qmul(dm.qinverse(q), [*vector,0.]), q)[:3]


def features(state):
    """Invariant candidates; yaw and rigid world wheel poses intentionally excluded.

    Axle phase is compared by wrapped LEFT/RIGHT differences, then D/C deltas.
    No direct joint position/phase setter is used anywhere in this runner.
    """
    out = {}
    def vec(prefix, value, size=3):
        for j,v in enumerate(dm.vector(value,size,prefix)):
            out[f"{prefix}.{j}"] = v
    vec("XYZ",state["position_world_m"])
    for key in ("roll_rad","pitch_rad"):
        out[key] = state[key]
    for key in ("linear_velocity_world_m_s","angular_velocity_world_rad_s"):
        vec(key,state[key])
    for side in ("left","right"):
        joint = state["joint_transmitted_wrench"][side]
        for key in ("actual_velocity_rad_s","force_norm_N","torque_norm_N_m"):
            out[f"{side}.{key}"] = joint[key]
        for key in ("force_xyz_N","torque_xyz_N_m"):
            vec(side+"."+key,joint[key])
        out[side+".phase_rad"] = state["wheel_phase_mod_2pi_rad"][side]
        link = state["native_wheel_links"][side]
        relative_q = dm.qmul(dm.qinverse(state["orientation_world_xyzw"]),link["orientation_world_xyzw"])
        if relative_q[3] < 0:
            relative_q = [-v for v in relative_q]
        vec(side+".body_relative_quaternion",relative_q,4)
        relative = [v-u for u,v in zip(state["position_world_m"],link["position_world_m"])]
        vec(side+".body_relative_position_m",rotate_inverse(state["orientation_world_xyzw"],relative))
        for key in ("linear_velocity_world_m_s","angular_velocity_world_rad_s"):
            vec(side+".native_"+key,link[key])
    for name,support in state["supports"].items():
        out[name+".Fn_N"] = support["Fn_N"]
        depths = support["depths_m"]
        if not isinstance(depths,list) or not all(math.isfinite(x) for x in depths):
            raise InvalidCapture("invalid contact depths: "+name)
        for j,v in enumerate(sorted(depths)):
            out[f"{name}.sorted_depth_m.{j}"] = v
    out["total_Fn_N"] = state["total_Fn_N"]
    if not all(type(x) in (int,float) and math.isfinite(x) for x in out.values()):
        raise InvalidCapture("nonfinite isolation observable")
    return out


def deltas(before, after):
    a,b = features(before),features(after)
    if a.keys() != b.keys():
        return None  # Different contact cardinality is an isolation failure, not interpolation.
    result = {k:b[k]-v for k,v in a.items()}
    for side in ("left","right"):
        result[side+".phase_rad"] = wrapped(result[side+".phase_rad"])
    l,r = result["left.phase_rad"],result["right.phase_rad"]
    result.update(differential_phase_rad=(l-r)/2, common_phase_rad=(l+r)/2)
    return result


def tolerance_spec():
    """Fixed before Host execution, from accepted stopped, no-service measurements.

    Maximum one-step variation across each valid H-AL arm at iterations3598..3601.
    A 64-ULP allowance handles deterministic float/quaternion arithmetic only.
    Two independent arms permit the sum (2x) of the one-step envelopes.
    This is an empirical diagnostic gate, not a new production/sensor tolerance.
    """
    reference = json.loads(REFERENCE.read_text())
    if reference["capture_integrity"]["classification"] != "BOTH_CAPTURES_VALID":
        raise InvalidCapture("accepted tolerance reference is not valid")
    rows = reference["full_terminal_relative_table_minus5_through_acquisition_end"]
    limits, scales = {},{}
    for case in dm.CASES:
        selected = {r["delta_ms"]:r[case] for r in rows if -3<=r["delta_ms"]<=0}
        if set(selected) != {-3,-2,-1,0}:
            raise InvalidCapture("reference stopped one-step calibration missing")
        for dt in (-3,-2,-1):
            changes = deltas(selected[dt],selected[dt+1])
            if changes is None:
                raise InvalidCapture("reference contact cardinality changed in stopped calibration")
            for key,value in changes.items():
                limits[key] = max(limits.get(key,0.),abs(value))
            for st in (selected[dt],selected[dt+1]):
                for key,value in features(st).items():
                    scales[key] = max(scales.get(key,1.),abs(value),1.)
    limits = {key:value+64*math.ulp(scales.get(key,1.)) for key,value in limits.items()}
    yaw_drift = max(abs(wrapped(r[case]["yaw_rad"]-TARGETS[CASES[j]]))
                    for j,case in enumerate(("RIGHT_HISTORY","CONTROL_SHAM"))
                    for r in rows if -3<=r["delta_ms"]<=0)
    # Target rounding is included above. No observed intervention data can enlarge this.
    return {"per_arm_limits":limits,"pair_difference_of_changes_limits":{k:2*v for k,v in limits.items()},
            "yaw_target_tolerance_rad":yaw_drift+64*math.ulp(1.),
            "wheel_stopped_linear_equivalent_m_s":history.RESET_STOPPED_SPEED,
            "source":str(REFERENCE),"source_sha256":ab._sha(REFERENCE),
            "calibration_iterations":[3598,3599,3600,3601],
            "justification":"Maximum measured one-iteration natural stopped drift, independently across the two accepted no-service arms, plus 64 ULP arithmetic slack. Pair limits sum two one-step envelopes. Production stopped speed0.02m/s additionally caps absolute velocities. No adaptive relaxation; a conservative empirical gate, not a guaranteed physical noise bound."}


def stopped_chunk(row):
    if (row.get("phase") != "BRAKE_LINEAR" or row.get("iterations_contract_pass") is not True or
        row.get("world_pose_history_contract",{}).get("pass") is not True or
        row.get("body_stopped_contract",{}).get("pass") is not True or row.get("collision_events")):
        raise InvalidCapture("intervention requires completed production BRAKE_LINEAR/stopped contract")


def track_production_steps(adapter):
    """Diagnostic instance wrapper; delegate every production step unchanged."""
    stepper = adapter.env.stepper
    original = stepper.step_simulation
    tracker = {"active_depth":0,"completed_steps":[]}
    adapter._yaw_step_tracker = tracker
    def tracked(*args, **kwargs):
        tracker["active_depth"] += 1
        start = stepper.time
        try:
            return original(*args, **kwargs)
        finally:
            tracker["active_depth"] -= 1
            tracker["completed_steps"].append({"start_sim_time":start,"end_sim_time":stepper.time,
                "verification":copy.deepcopy(stepper.last_verification)})
    stepper.step_simulation = tracked


def completed_brake_checkpoint(adapter, row):
    stopped_chunk(row)
    tracker = getattr(adapter,"_yaw_step_tracker",{})
    completed = tracker.get("completed_steps")
    if tracker.get("active_depth") != 0 or not isinstance(completed,list) or not completed:
        raise InvalidCapture("unsafe checkpoint: production physics transaction active or not observed complete")
    last = next(reversed(completed))
    verification = row.get("step_evidence",{})
    if (verification.get("valid") is not True or last["verification"] != verification or
        adapter.env.stepper.last_verification != verification or
        round(last["end_sim_time"]*1e9) != round(row["simulation_end"]*1e9) or
        round(adapter.env.stepper.time*1e9) != round(row["simulation_end"]*1e9)):
        raise InvalidCapture("braking WorldControl transaction did not finish before intervention")
    return {"active_physics_transactions":0,"completed_brake_step":copy.deepcopy(last),
            "location":"completed braking chunk callback; acquisition baseline/cursor not yet constructed"}


def synchronize_paused(adapter, expected_iteration, expected_ns, evidence):
    """One explicit public pause RPC, then a fresh exact paused stats sample.

    Waiting is transport I/O only. No physics tick, resume, reset, pose retry,
    timestamp tolerance, fabricated pause flag, or use of a cached verification.
    """
    env = adapter.env
    if round(env.stepper.time*1e9) != expected_ns:
        raise InvalidCapture("pause synchronization owner clock differs from expected exact time")
    transport,topic = env.transport,env.stepper.topic
    cursor = transport.cursor(topic)
    if type(cursor) is not int or cursor < 0:
        raise InvalidCapture("pause synchronization requires a WorldStatistics receive cursor")
    evidence.update(expected_iteration=expected_iteration,expected_sim_time_ns=expected_ns,
        sequence_before_pause=cursor,before_snapshot=env.stepper._snapshot(),observed_stats=[],
        physics_advanced_by_synchronization=False,request={"pause":True})
    rpc_cursor = len(transport.request_history)
    evidence["response"] = env.stepper.control({"pause":True})
    evidence["RPC_history"] = copy.deepcopy(transport.request_history[rpc_cursor:])
    if evidence["response"].get("data") is not True:
        raise InvalidCapture("explicit post-service pause rejected")
    deadline = time.monotonic()+env.stepper.timeout
    while True:
        remaining = deadline-time.monotonic()
        if remaining <= 0:
            raise InvalidCapture(f"fresh explicit paused WorldStatistics missing at iteration {expected_iteration}, {expected_ns} ns")
        messages = transport.messages_after(topic,cursor,timeout=remaining)
        if not messages:
            raise InvalidCapture(f"fresh explicit paused WorldStatistics missing at iteration {expected_iteration}, {expected_ns} ns")
        for sequence,data in messages:
            if type(sequence) is not int or sequence <= cursor:
                raise InvalidCapture("nonadvancing receive sequence in paused synchronization")
            cursor = sequence
            iteration = data.get("iterations_normalized",data.get("iterations"))
            ns = round(dm.stamp(data)*1e9)
            evidence["observed_stats"].append({"sequence":sequence,"data":copy.deepcopy(data)})
            if type(iteration) is not int or iteration != expected_iteration or ns != expected_ns:
                raise InvalidCapture("paused synchronization observed unexpected iteration/time; no corrective stepping allowed")
            if data.get("paused") is not True:
                continue  # A transient advancing sample is not a paused marker.
            marker = {"iteration":iteration,"sim_time_ns":ns,"sim_time_s":dm.stamp(data),
                "stats_receive_sequence":sequence,"paused":True,
                "stats_source":"fresh_explicit_pause_WorldStatistics",
                "observed_snapshot":copy.deepcopy(data)}
            evidence.update(valid=True,marker=marker,sequence_after_pause=sequence)
            return marker


def prove_pose_application(state, case):
    try:
        features(state)  # Require complete finite physical observation, not just yaw.
        yaw = state.get("yaw_rad")
        if type(yaw) not in (int,float) or not math.isfinite(yaw) or case not in CASES:
            raise InvalidCapture("missing/nonfinite observed post-service yaw or arm identity")
    except (KeyError,TypeError,ValueError) as exc:
        raise InvalidCapture("complete post-service pose observation missing: "+str(exc)) from exc
    error = abs(wrapped(state["yaw_rad"]-TARGETS[case]))
    limit = tolerance_spec()["yaw_target_tolerance_rad"]
    if error > limit:
        raise InvalidCapture(f"post-service native yaw application not proven: error {error} > fixed tolerance {limit}")
    return {"valid":True,"measured_yaw_rad":state["yaw_rad"],"target_yaw_rad":TARGETS[case],
            "absolute_error_rad":error,"fixed_tolerance_rad":limit}


def canonical_transition(previous):
    requested = dm.gazebo_physics_twist("up")
    kind = classify_physics_command_transition(previous,requested)
    if previous != dm.gazebo_physics_twist("down") or kind != "LINEAR_REVERSAL":
        raise InvalidCapture("terminal production adapter.step(UP) must enter with actual DOWN command and LINEAR_REVERSAL")
    return {"previous_command":copy.deepcopy(previous),"requested_command":requested,
            "transition_type":kind,"entry_path":"normal production adapter.step(up)"}


def exact_one_step(adapter):
    env = adapter.env
    from aero_ai_studio.gazebo.stepping import GazeboStepper
    probe = GazeboStepper(env.transport,env.stepper.world,physics_dt=.001,dt=.001,timeout=env.stepper.timeout)
    probe.time = env.stepper.time
    probe.step_simulation()
    evidence = dict(probe.last_verification)
    if evidence.get("valid") is not True or evidence.get("iteration_delta") != POST_STEPS:
        raise InvalidCapture("pose observability step did not advance exactly one iteration")
    env.stepper.time = probe.time
    env.stepper.last_verification = evidence
    return evidence


def request_from_checkpoint(checkpoint, case):
    """Only an atomic current model checkpoint may define a runtime request."""
    if not isinstance(checkpoint,dict) or checkpoint.get("classification")!="PRE_RPC_CHECKPOINT_COHERENT":
        raise InvalidCapture("PRE_RPC_CHECKPOINT_COHERENT required; advancing request origin rejected")
    _,model = checkpoints.validate(checkpoint,checkpoint["marker"],"PRE_RPC")
    current_yaw = model["yaw_rad"]
    yaw_gap = wrapped(TARGETS[case]-current_yaw)
    if case == "RIGHT_YAW_SHAM" and abs(yaw_gap)>tolerance_spec()["yaw_target_tolerance_rad"]:
        raise InvalidCapture("SHAM_TARGET_NOT_CURRENT_YAW")
    payload = pose_payload(model,case,"simple_agent")
    angles = checkpoints.rpy([payload["orientation"][k] for k in ("x","y","z","w")])
    deltas = {key:payload["position"][key]-model["position_world_m"][j] for j,key in enumerate(("x","y","z"))}
    deltas.update(roll=angles[0]-model["roll_rad"],pitch=angles[1]-model["pitch_rad"])
    limits = {key:checkpoints.precision() if key in ("roll","pitch") else checkpoints.precision(model["position_world_m"][("x","y","z").index(key)]) for key in deltas}
    if any(abs(value)>limits[key] for key,value in deltas.items()):
        raise InvalidCapture("requested XYZ/roll/pitch differ from current coherent model origin")
    return payload,{"valid":True,"origin_checkpoint_id":checkpoint["raw"]["checkpoint_id"],
        "origin_postupdate_count":checkpoint["raw"]["postupdate_count"],"non_yaw_construction_deltas":deltas,
        "construction_precision_limits":limits,"current_model_pose":model,"intended_yaw_delta_rad":yaw_gap,
        "SHAM_current_yaw_guard_limit_rad":tolerance_spec()["yaw_target_tolerance_rad"] if case=="RIGHT_YAW_SHAM" else None}


def perform_intervention(adapter, case, output, native_capture, row, evidence):
    stopped_chunk(row)
    if evidence:
        raise InvalidCapture("repeated intervention forbidden")
    env = adapter.env
    checkpoint = completed_brake_checkpoint(adapter,row)
    request_mark = dm.physics_mark(adapter)
    if round(row["simulation_end"]*1e9) != request_mark["sim_time_ns"]:
        raise InvalidCapture("stopped completion and intervention boundary differ")
    pre = checkpoints.acquire(adapter,native_capture,request_mark,"PRE_RPC")
    before = pre["state"]
    evidence.update(request_marker=request_mark,before=before,pre_checkpoint=pre,
        stopped_chunk=copy.deepcopy(row),completed_brake_checkpoint=checkpoint)
    payload,origin_assertion = request_from_checkpoint(pre,case)
    evidence.update(request_marker=request_mark,before=before,requested_pose=payload,
        stopped_chunk=copy.deepcopy(row),pose_service=f"/world/{env.stepper.world}/set_pose",
        pose_service_call_count=1,post_service_steps_requested=POST_STEPS,
        completed_brake_checkpoint=checkpoint,pre_checkpoint=pre,request_origin_assertion=origin_assertion)
    checkpoints.not_superseded(native_capture,pre)
    cursor = len(env.transport.request_history)
    response = env.transport.request(evidence["pose_service"],"Pose","Boolean",payload,max_attempts=1)
    evidence["pose_service_RPC_history"] = copy.deepcopy(env.transport.request_history[cursor:])
    evidence["service_response"] = response
    evidence["service_completion_marker"] = dm.physics_mark(adapter)
    if response.get("data") is not True:
        raise InvalidCapture("yaw pose service rejected")
    if evidence["service_completion_marker"]["iteration"] != request_mark["iteration"] or evidence["service_completion_marker"]["sim_time_ns"] != request_mark["sim_time_ns"]:
        raise InvalidCapture("physics advanced during paused pose service")
    evidence["post_service_step_verification"] = exact_one_step(adapter)
    # Host1's step verification can be valid with paused_after=None. Never
    # mistake that for the explicit paused=True boundary needed by this diagnostic.
    synchronization = {}
    evidence["post_service_pause_synchronization"] = synchronization
    after_mark = synchronize_paused(adapter,request_mark["iteration"]+POST_STEPS,
        request_mark["sim_time_ns"]+STEP_NS,synchronization)
    evidence["first_advancing_post_service_marker"] = after_mark
    evidence["before_Action24_publication_marker"] = after_mark
    evidence["advancing_iterations"] = after_mark["iteration"]-request_mark["iteration"]
    evidence["elapsed_ns"] = after_mark["sim_time_ns"]-request_mark["sim_time_ns"]
    evidence["post_checkpoint"] = checkpoints.acquire(adapter,native_capture,after_mark,"POST_RPC")
    evidence["after"] = evidence["post_checkpoint"]["state"]
    evidence["pose_application_proof"] = prove_pose_application(evidence["after"],case)
    # Refresh through the normal public path, never overwrite a newer pose with
    # an older checkpoint. Both fresh production views must still match it.
    env._refresh()
    fresh_pose = env.controller.get_pose(env.stepper.time,env.timeout)
    model = evidence["post_checkpoint"]["model_state"]
    if not checkpoints.same_pose(model,checkpoints.pose_v_view(env.pose)) or not checkpoints.same_pose(model,checkpoints.pose_v_view(fresh_pose)):
        raise InvalidCapture("POST checkpoint superseded or stale production refresh; no snapshot substitution")
    evidence["production_pose_after_service"] = dict(fresh_pose)
    if abs(wrapped(fresh_pose["yaw"]-evidence["after"]["yaw_rad"])) > tolerance_spec()["yaw_target_tolerance_rad"]:
        raise InvalidCapture("fresh production Pose_V and native post-service yaw disagree")
    checkpoints.not_superseded(native_capture,evidence["post_checkpoint"])
    evidence["pre_acquire_checkpoint_ready"] = True


def capture(case, scenario, output, libraries, seed, namespace):
    from aero_ai_studio.training import gazebo_physics
    base = gazebo_physics.GazeboPhysicsTrainingEnvironment
    old_executor = gazebo_physics.GazeboLinearReversalControlExecutor
    old_native = ab.native.NativeVelocityCapture
    old_execute, old_failure = ab._execute_captured,ab._failure
    old_instrument = ab._instrument_world
    intervention, reset_state, live, terminal_entry = {},{},{},{}
    class Capture(checkpoints.CaptureMixin,old_native):
        def __init__(self,*args,**kwargs):
            super().__init__(*args,**kwargs)
            live["native"] = self
            self.checkpoint_output = output/"paused_checkpoints.ndjson"
    class Environment(base):
        def reset(self,selected_seed=None):
            result = super().reset(selected_seed)
            reset_state.update(reset_completed=True,reset_evidence=copy.deepcopy(self.last_reset_evidence),
                               canonical_reset_pose=dict(self.env.pose))
            track_production_steps(self)
            live["adapter"] = self
            return result
    class Executor(old_executor):
        def execute_plan(self, execution_plan, *, on_braking_chunk=None):
            if not getattr(self.training_environment,"_yaw_terminal",False):
                return super().execute_plan(execution_plan,on_braking_chunk=on_braking_chunk)
            selected = execution_plan.to_dict()
            if (selected["request"]["transition_type"] != "LINEAR_REVERSAL" or
                [p["kind"] for p in selected["phases"]] != ["BRAKE_LINEAR","ACQUIRE_LINEAR"]):
                raise InvalidCapture("production terminal planner did not select canonical reversal phases")
            terminal_entry["production_plan"] = selected
            def callback(row):
                outcome = on_braking_chunk(row) if on_braking_chunk else {}
                if (row.get("body_stopped_contract",{}).get("pass") is True and
                    not any(outcome.get(k) for k in ("collision","terminated","truncated"))):
                    try:
                        perform_intervention(self.training_environment,case,output,live["native"],row,intervention)
                    except Exception as exc:
                        intervention["diagnostic_error"] = dm.failure_record(exc)
                        raise
                return outcome
            return super().execute_plan(execution_plan,on_braking_chunk=callback)
    def execute(adapter,action,phase):
        terminal = phase=="BRAKE_LINEAR_THEN_UP"
        adapter._yaw_terminal = terminal
        try:
            if terminal:
                terminal_entry.update(canonical_transition(adapter.env.controller.last_command))
                terminal_entry["sim_time_before_adapter_step"] = adapter.env.stepper.time
            event = dm.execute_captured(adapter,action,phase)
            if terminal and intervention.get("before_Action24_publication_marker"):
                # Actual controller publication, never phase/list-position-derived T0.
                pub = event.get("action_publication",{}).get("action_command_sim_time")
                event["up_command_sim_time"] = pub
                event["up_reached"] = pub is not None and event.get("up_reached",False)
            return event
        finally:
            adapter._yaw_terminal = False
    def instrument(production,directory,libs,topic_identity=None):
        diagnostic,info = old_instrument(production,directory,libs,topic_identity=topic_identity)
        return checkpoints.instrument(diagnostic,info)
    ab._instrument_world = instrument
    gazebo_physics.GazeboPhysicsTrainingEnvironment = Environment
    gazebo_physics.GazeboLinearReversalControlExecutor = Executor
    ab.native.NativeVelocityCapture = Capture
    ab._execute_captured,ab._failure = execute,dm.failure_record
    try:
        record = history.capture_candidate(plan(case),scenario,output,libraries,seed,runtime_namespace=namespace)
    finally:
        gazebo_physics.GazeboPhysicsTrainingEnvironment = base
        gazebo_physics.GazeboLinearReversalControlExecutor = old_executor
        ab.native.NativeVelocityCapture = old_native
        ab._execute_captured,ab._failure = old_execute,old_failure
        ab._instrument_world = old_instrument
    record.update(reset_state)
    record["yaw_intervention"] = intervention
    record["paused_checkpoints"] = copy.deepcopy(getattr(live.get("native"),"checkpoints",[]))
    record["terminal_entry_history"] = terminal_entry
    record["production_step_trace"] = copy.deepcopy(getattr(live.get("adapter"),"_yaw_step_tracker",{}))
    write_json(output/"case_result.json",record)
    return record


def intervention_timing_validity(it, t0):
    req,done,after = (it[k] for k in ("request_marker","service_completion_marker","before_Action24_publication_marker"))
    if (req["iteration"]!=done["iteration"] or req["sim_time_ns"]!=done["sim_time_ns"] or
        after["iteration"]-done["iteration"]!=POST_STEPS or after["sim_time_ns"]-done["sim_time_ns"]!=STEP_NS or
        it.get("advancing_iterations")!=POST_STEPS or it.get("elapsed_ns")!=STEP_NS or
        t0["publication_iteration"]!=after["iteration"] or t0["publication_sim_time_ns"]!=after["sim_time_ns"] or
        it.get("first_advancing_post_service_marker")!=after):
        raise InvalidCapture("pose completion -> one-step -> Action24 publication timing invalid")
    return req,done,after


def pause_sync_validity(it):
    sync = it.get("post_service_pause_synchronization") or {}
    mark = it.get("before_Action24_publication_marker") or {}
    rpc = sync.get("RPC_history")
    if (sync.get("valid") is not True or sync.get("request")!={"pause":True} or
        sync.get("response",{}).get("data") is not True or sync.get("marker")!=mark or
        mark.get("paused") is not True or mark.get("stats_source")!="fresh_explicit_pause_WorldStatistics" or
        sync.get("physics_advanced_by_synchronization") is not False or
        sync.get("expected_iteration")!=mark.get("iteration") or
        sync.get("expected_sim_time_ns")!=mark.get("sim_time_ns") or
        not isinstance(rpc,list) or len(rpc)!=1 or rpc[0].get("payload")!={"pause":True} or
        len(rpc[0].get("attempts",[]))!=1):
        raise InvalidCapture("fresh explicit paused marker/RPC proof missing or invalid")
    previous = sync.get("sequence_before_pause")
    if type(previous) is not int:
        raise InvalidCapture("pause proof receive cursor missing")
    observations = sync.get("observed_stats")
    if not isinstance(observations,list) or not observations:
        raise InvalidCapture("fresh paused WorldStatistics observation missing")
    for item in observations:
        seq,data = item["sequence"],item["data"]
        if (type(seq) is not int or seq<=previous or
            data.get("iterations_normalized",data.get("iterations"))!=mark["iteration"] or
            round(dm.stamp(data)*1e9)!=mark["sim_time_ns"]):
            raise InvalidCapture("pause proof iteration/time/sequence mismatch")
        previous = seq
    observed = dm.unique_match(observations,lambda item:item["sequence"]==mark["stats_receive_sequence"],"actual paused marker observation")
    if (observed["data"].get("paused") is not True or observed["data"]!=mark["observed_snapshot"] or
        previous!=sync.get("sequence_after_pause") or previous!=mark["stats_receive_sequence"]):
        raise InvalidCapture("explicit paused=True marker not proven by fresh received sample")


def validate(record, case, scenario, seed, reference, partitions, topics):
    result = {"case_valid":False,"invalid_reasons":[],"physical_classifier_attempted":False}
    try:
        events = dm.required_events(record)
        terminal = dm.terminal_event(record)  # Guard inherited validator's positional access.
        if len(events) != 17:
            raise InvalidCapture("all canonical Actions08-24 required")
        result.update(history.validate_candidate(record,plan(case),partitions,topics))
        reset = history.reset_validity(record,scenario,seed,reference)
        result["reset_validation"] = reset
        result["invalid_reasons"].extend(reset["invalid_reasons"])
        for event in events:
            pub = event.get("action_publication") or {}
            if (pub.get("commanded_twist") != dm.gazebo_physics_twist(event["action"]) or
                pub.get("action_publish_sequence",-1)<=pub.get("command_publish_sequence_before",-1) or
                (event is not terminal and (event.get("exception") or event.get("terminated")))):
                raise InvalidCapture("canonical action publication/completion invalid")
        maps,t0,indices = dm.terminal_alignment(record)
        it = record.get("yaw_intervention") or {}
        if it.get("diagnostic_error") or it.get("pose_service_call_count") != 1 or it.get("service_response",{}).get("data") is not True:
            raise InvalidCapture("single completed pose service missing or failed: "+str(it.get("diagnostic_error")))
        stopped_chunk(it["stopped_chunk"])
        rpc = it.get("pose_service_RPC_history")
        if (not isinstance(rpc,list) or len(rpc)!=1 or len(rpc[0].get("attempts",[]))!=1 or
            rpc[0].get("payload")!=it["requested_pose"] or rpc[0].get("service")!=it["pose_service"]):
            raise InvalidCapture("exactly one pose-service RPC attempt required")
        req,done,after = intervention_timing_validity(it,t0)
        pause_sync_validity(it)
        if it.get("pose_application_proof")!=prove_pose_application(it["after"],case) or it.get("pre_acquire_checkpoint_ready") is not True:
            raise InvalidCapture("pose application not proven before production acquisition")
        checkpoint = it.get("completed_brake_checkpoint") or {}
        if (checkpoint.get("active_physics_transactions")!=0 or
            checkpoint.get("completed_brake_step",{}).get("verification")!=it["stopped_chunk"].get("step_evidence") or
            record.get("production_step_trace",{}).get("active_depth")!=0):
            raise InvalidCapture("completed production physics checkpoint not proven")
        entry = record.get("terminal_entry_history") or {}
        expected_entry = canonical_transition(entry.get("previous_command"))
        if any(entry.get(k)!=v for k,v in expected_entry.items()):
            raise InvalidCapture("terminal DOWN history / normal adapter entry not preserved")
        selected = entry.get("production_plan") or {}
        if (selected.get("request",{}).get("transition_type")!="LINEAR_REVERSAL" or
            selected.get("request",{}).get("previous_command")!=dm.gazebo_physics_twist("down") or
            selected.get("request",{}).get("requested_command")!=dm.gazebo_physics_twist("up") or
            [p.get("kind") for p in selected.get("phases",[])]!=["BRAKE_LINEAR","ACQUIRE_LINEAR"]):
            raise InvalidCapture("actual production planner selection differs from canonical DOWN-to-UP")
        if (it["post_service_step_verification"].get("valid") is not True or
            it["post_service_step_verification"].get("iteration_delta")!=POST_STEPS):
            raise InvalidCapture("post-service WorldStatistics progression invalid")
        expected_payload,expected_assertion = request_from_checkpoint(it["pre_checkpoint"],case)
        if it["requested_pose"]!=expected_payload or it.get("request_origin_assertion")!=expected_assertion:
            raise InvalidCapture("current checkpoint request-origin proof missing/changed")
        raw_checkpoints = record.get("paused_checkpoints")
        if not isinstance(raw_checkpoints,list) or len(raw_checkpoints)!=2 or [cp.get("checkpoint_id") for cp in raw_checkpoints]!=[1,2]:
            raise InvalidCapture("exactly two paused component checkpoint records required")
        raw_path = Path(record["case_result_path"]).parent/"paused_checkpoints.ndjson"
        if ab._finite_json_rows(raw_path)!=raw_checkpoints:
            raise InvalidCapture("paused raw checkpoint serialization mismatch")
        for label,mark,stage in (("before",req,"PRE_RPC"),("after",after,"POST_RPC")):
            cp = it["pre_checkpoint" if stage=="PRE_RPC" else "post_checkpoint"]
            state,_ = checkpoints.validate(cp,mark,stage)
            if cp["latest_native_corroboration"] not in record["native_samples"]:
                raise InvalidCapture("current native corroboration absent from captured native stream")
            ordinary = dm.unique_match(record["native_samples"],lambda sample:sample.get("postupdate_count")==cp["raw"]["postupdate_count"],"atomic checkpoint native callback")
            if any(ordinary.get(key)!=value for key,value in cp["raw"]["native"].items()):
                raise InvalidCapture("checkpoint native payload differs from same-callback heartbeat")
            if state!=it[label] or cp["raw"] not in raw_checkpoints or cp["raw"].get("capture_topic")!=record["runtime_identity"]["topic"]:
                raise InvalidCapture("paused coherent checkpoint identity/state mismatch")
        if not checkpoints.same_pose(it["post_checkpoint"]["model_state"],checkpoints.pose_v_view(it["production_pose_after_service"])):
            raise InvalidCapture("production POST pose differs from coherent current model")
        if it["post_checkpoint"]["raw"]["postupdate_count"]<=it["pre_checkpoint"]["raw"]["postupdate_count"]:
            raise InvalidCapture("PRE/POST checkpoint phase order invalid")
        for i in range(req["iteration"]-5,t0["end_iteration"]+1):
            dm.aligned_sample(maps,i,"intervention/terminal coverage")
        result["keyed_T0"] = t0
        result["case_valid"] = not result["invalid_reasons"]
    except Exception as exc:
        result["case_valid"] = False
        result["invalid_reasons"].append(type(exc).__name__+": "+str(exc))
        result["validation_traceback"] = traceback.format_exception(type(exc),exc,exc.__traceback__)
    return result


def field_provenance(record, field):
    category = ("support" if any(field.startswith(name) for name in ("left_wheel","right_wheel","front_caster","rear_caster","total_Fn")) else
                "wrench" if any(name in field for name in ("force_","torque_","actual_velocity")) else "native")
    result = {}
    for stage in ("pre","post"):
        raw = record["yaw_intervention"].get(stage+"_checkpoint",{}).get("raw",{})
        result[stage] = {"category":category,"checkpoint_id":raw.get("checkpoint_id"),
            "postupdate_count":raw.get("postupdate_count"),"source":raw.get("field_sources",{}).get(category),
            "measurement_age_limitation":raw.get("measurement_age_limitation")}
    return result


def isolation(records, tolerances):
    failures,observed = [],{}
    changes = {}
    for case in CASES:
        it = records[case]["yaw_intervention"]
        before,after = it["before"],it["after"]
        change = deltas(before,after)
        changes[case] = change
        yaw_error = abs(wrapped(after["yaw_rad"]-TARGETS[case]))
        if abs(wrapped(before["yaw_rad"]-TARGETS[CASES[0]]))>tolerances["yaw_target_tolerance_rad"]:
            failures.append(case+": pre-intervention RIGHT baseline yaw differs from accepted target")
        checks = {"yaw_target_error_rad":{"before":before["yaw_rad"],"after":after["yaw_rad"],
            "delta":wrapped(after["yaw_rad"]-before["yaw_rad"]),"observed":yaw_error,"limit":tolerances["yaw_target_tolerance_rad"],
            "ratio":yaw_error/tolerances["yaw_target_tolerance_rad"],"pass":yaw_error<=tolerances["yaw_target_tolerance_rad"],
            "comparison_basis":"POST minus intended yaw target; intended yaw delta is not collateral", "source_provenance":field_provenance(records[case],"yaw_rad")}}
        if change is None:
            failures.append(case+": contact cardinality changed")
        else:
            values_before,values_after = features(before),features(after)
            for target,st in ((values_before,before),(values_after,after)):
                left,right = (st["wheel_phase_mod_2pi_rad"][s] for s in ("left","right"))
                target.update(differential_phase_rad=(left-right)/2,common_phase_rad=(left+right)/2)
            for key,value in change.items():
                limit = tolerances["per_arm_limits"][key]
                checks[key] = {"before":values_before[key],"after":values_after[key],"delta":value,
                    "absolute_delta":abs(value),"limit":limit,"ratio":abs(value)/limit,"pass":abs(value)<=limit,
                    "source_provenance":field_provenance(records[case],key)}

        for key,s in before["supports"].items():
            if s["state"]!=after["supports"][key]["state"]:
                failures.append(case+": support state changed: "+key)
        for state_label,state in (("before",before),("after",after)):
            speed = tolerances["wheel_stopped_linear_equivalent_m_s"]
            for key in ("linear_velocity_world_m_s","angular_velocity_world_rad_s"):
                if math.sqrt(sum(v*v for v in state[key]))>speed:
                    failures.append(case+": native 3D stopped bound exceeded: "+state_label+" "+key)
            if any(abs(state["joint_transmitted_wrench"][side]["actual_velocity_rad_s"])*.1>speed for side in ("left","right")):
                failures.append(case+": wheel no longer stopped: "+state_label)
        observed[case] = {"checks":checks,"before":before,"after":after,"requested_pose":it["requested_pose"],
            "categorical_checks":{key:{"before":value["state"],"after":after["supports"][key]["state"],
                "delta":None,"limit":"exact state equality","ratio":0 if value["state"]==after["supports"][key]["state"] else None,
                "pass":value["state"]==after["supports"][key]["state"],"source_provenance":field_provenance(records[case],key)}
                for key,value in before["supports"].items()}}

        failures += [case+": "+k for k,v in checks.items() if not v["pass"]]
    a,b = (records[c]["yaw_intervention"] for c in CASES)
    pair_limits = tolerances["pair_difference_of_changes_limits"]
    before_delta,after_delta = deltas(a["before"],b["before"]),deltas(a["after"],b["after"])
    # Also demand the two RIGHT-history arms start and finish comparable apart from yaw.
    for label,delta in (("between-arm before",before_delta),("between-arm after",after_delta)):
        if delta is None:
            failures.append(label+": contact cardinality differs")
        else:
            failures += [label+": "+k for k,v in delta.items() if abs(v)>pair_limits[k]]
    change_differences = None
    if all(changes[c] is not None for c in CASES):
        change_differences = {k:changes[CASES[1]][k]-v for k,v in changes[CASES[0]].items()}
        failures += ["between-arm collateral change: "+k for k,v in change_differences.items() if abs(v)>pair_limits[k]]
    for label in ("before","after"):
        if any(a[label]["supports"][k]["state"]!=b[label]["supports"][k]["state"] for k in a[label]["supports"]):
            failures.append("between-arm "+label+": support states differ")
    yaw_gap = wrapped(b["after"]["yaw_rad"]-a["after"]["yaw_rad"])
    if abs(wrapped(yaw_gap-(TARGETS[CASES[1]]-TARGETS[CASES[0]])))>2*tolerances["yaw_target_tolerance_rad"]:
        failures.append("intended between-arm yaw difference not achieved")
    return {"classification":"INTERVENTION_ISOLATION_FAILED" if failures else "YAW_INTERVENTION_ISOLATED",
            "failures":failures,"observed":observed,"between_arm_before_deltas":before_delta,
            "between_arm_after_deltas":after_delta,"difference_of_collateral_changes":change_differences,
            "observed_yaw_gap_rad":yaw_gap,"tolerances":tolerances,
            "limitation":"Measured isolation only; no contact-cache invariance proof. No tolerance is changed after seeing intervention results."}


def case_outcome(case, physical):
    return case+{"SUPPORT_RECOVERY_AND_TRANSLATION_SUCCESS":"_SUCCESS",
                 "CANONICAL_ACTION24_FAILURE_REPRODUCED":"_CANONICAL_FAILURE"}.get(physical,"_OTHER_PHYSICAL_OUTCOME")


def interpretation(isolation_label, labels):
    if isolation_label != "YAW_INTERVENTION_ISOLATED":
        return isolation_label
    return {("RIGHT_YAW_SHAM_CANONICAL_FAILURE","RIGHT_YAW_MATCHED_SUCCESS"):
            "YAW_NORMALIZATION_RESCUES_ACTION24_IN_RIGHT_HISTORY_CONTEXT",
            ("RIGHT_YAW_SHAM_CANONICAL_FAILURE","RIGHT_YAW_MATCHED_CANONICAL_FAILURE"):
            "YAW_NORMALIZATION_ALONE_INSUFFICIENT",
            ("RIGHT_YAW_SHAM_SUCCESS","RIGHT_YAW_MATCHED_SUCCESS"):
            "POSE_SERVICE_ITSELF_DISRUPTS_FAILURE_REPRODUCTION"}.get(tuple(labels.get(c) for c in CASES),"YAW_INTERVENTION_RESULT_UNRESOLVED")


def analyze(records, integrities, tolerances):
    if not all(integrities.get(c,{}).get("case_valid") for c in CASES):
        raise InvalidCapture("both captures must be valid before isolation or physical classification")
    a,b = (records[c] for c in CASES)
    if (a["configured_reset_condition"]!=b["configured_reset_condition"] or
        any(not a["runtime_identity"].get(k) or a["runtime_identity"].get(k)==b["runtime_identity"].get(k) for k in ("partition","topic")) or
        a["wall_end_after_shutdown_monotonic_s"]>b["wall_start_monotonic_s"]):
        raise InvalidCapture("fresh-process/configuration isolation failed")
    iso = isolation(records,tolerances)
    physical,labels,tables = {},{},{}
    for c in CASES:
        maps,t0,indices = dm.terminal_alignment(records[c])
        tables[c] = [{"delta_ms":i-t0["iteration"],**dm.state_at(records[c],i,maps)} for i in indices]
        if iso["classification"]=="YAW_INTERVENTION_ISOLATED":
            physical[c] = history.classify_candidate(records[c],integrities[c])
            integrities[c]["physical_classifier_attempted"] = True
            labels[c] = case_outcome(c,physical[c]["classification"])
        else:
            physical[c] = {"physical_classification_created":False,"reason":"isolation failed; raw terminal telemetry preserved"}
    return {"status":"CAPTURED" if iso["classification"]=="YAW_INTERVENTION_ISOLATED" else "INTERVENTION_ISOLATION_FAILED",
            "capture_integrity":integrities,"isolation":iso,
            "checkpoints":{c:{stage:records[c]["yaw_intervention"].get(stage+"_checkpoint") for stage in ("pre","post")} for c in CASES},
            "materiality_note":"Every formal tolerance failure remains isolation failure, including numerically tiny failures; no physical-materiality override.",
            "case_outcomes":labels,"Action24":physical,"terminal_tables":tables,
            "T0":{c:dm.command_active_t0(records[c]) for c in CASES},
            "detail_0_through_15_ms":[{"delta_ms":dt,**{c:dm.unique_match(tables[c],lambda row:row["delta_ms"]==dt,"relative iteration") for c in CASES}} for dt in range(16)],
            "interpretation":interpretation(iso["classification"],labels),
            "physical_classification_created":iso["classification"]=="YAW_INTERVENTION_ISOLATED",
            "caution":"A rescue supports yaw-associated intervention sensitivity, not a unique root cause. Both failing means yaw normalization alone is insufficient."}


def audit_host1():
    """Read-only setup/ordering audit; never invoke any physical classifier."""
    cases = {}
    expected_error = "paused WorldStatistics for exact current simulation time 3601000000 ns missing; no physics advanced by marker"
    for case in CASES:
        path = HOST1/case/"case_result.json"
        record = json.loads(path.read_text())
        intervention = record["yaw_intervention"]
        row = intervention["stopped_chunk"]
        step = intervention["post_service_step_verification"]
        event = dm.terminal_event(record)
        error = intervention.get("diagnostic_error") or {}
        if (error.get("message")!=expected_error or step.get("valid") is not True or
            step.get("iterations_after")!=3601 or step.get("after_sim_time")!=3.601 or
            step.get("paused_after") is not None or intervention.get("first_advancing_post_service_marker") is not None):
            raise InvalidCapture("Host1 evidence differs from exact diagnosed marker regression")
        counts = {}
        for key,kind,filename in (("support_rows","support_iteration","continuous_support_iterations.ndjson"),
                                 ("wrench_rows","joint_wrench_sample","joint_transmitted_wrench.ndjson"),
                                 ("native_samples",None,None)):
            raw = record[key]
            if filename and ab._finite_json_rows(path.parent/filename)!=raw:
                raise InvalidCapture("Host1 raw telemetry and case serialization disagree")
            advancing = [r for r in raw if r.get("paused") is False and (kind is None or r.get("kind")==kind)]
            counts[key] = {"all_rows":len(raw),"advancing_samples":len(advancing),
                "unique_advancing_iterations":len({r["iteration"] for r in advancing}),
                "last_iteration":max(r["iteration"] for r in advancing)}
        action23 = dm.unique_match(record["events"],lambda e:e.get("canonical_index")==23,"Host1 Action23")
        last_native = dm.state_at(record,3601)
        cases[case] = {"classification":"DIAGNOSTIC_CAPTURE_FAILURE","last_iteration":3601,"last_sim_time_ns":3601000000,
            "last_completed_canonical_action":23,"Action23_completed":not action23.get("exception") and not action23.get("terminated"),
            "Action23_interval_s":[action23["start_sim_time"],action23["end_sim_time"]],
            "terminal_UP_adapter_entered":True,"terminal_UP_adapter_start_s":event["start_sim_time"],
            "BRAKE_LINEAR_began":True,"stopped_passed":row["body_stopped_contract"]["pass"],
            "final_braking_chunk_s":[row["simulation_start"],row["simulation_end"]],
            "final_braking_chunk_evidence":row["step_evidence"],"braking_chunk_index":row["index"],
            "pose_service_called":intervention["pose_service_call_count"],"pose_service_response":intervention["service_response"],
            "pose_service_RPC_history":intervention["pose_service_RPC_history"],
            "request_marker":intervention["request_marker"],"service_completion_marker":intervention["service_completion_marker"],
            "diagnostic_step_evidence":step,"paused_marker_constructed_after_step":False,
            "post_step_pause_observation":"paused field missing in accepted step sample; explicit paused=True was not recorded",
            "last_native_yaw_rad_diagnostic_only":last_native["yaw_rad"],
            "last_native_yaw_minus_requested_rad":wrapped(last_native["yaw_rad"]-TARGETS[case]),
            "ACQUIRE_LINEAR_began":False,"fresh_UP_publication":False,
            "terminal_action_publication_record":event.get("action_publication"),
            "stream_counts":counts,"shutdown_completed":record.get("shutdown_completed"),
            "complete_failed_case_serialization":record.get("case_result_written"),
            "exception":error,"physical_classification_created":False}
        del record
    # Accepted working infrastructure, using its saved actual production phases.
    working_path = dm.DEFAULT_OUTPUT/"RIGHT_HISTORY"/"case_result.json"
    working = json.loads(working_path.read_text())
    terminal = dm.terminal_event(working)
    phases = ab._find_phase_evidence(terminal["execution_evidence"])
    brake = dm.unique_match(phases,lambda p:p.get("phase")=="BRAKE_LINEAR","working H-AL terminal brake")
    acquire = dm.unique_match(phases,lambda p:p.get("phase")=="ACQUIRE_LINEAR","working H-AL terminal acquire")
    return {"classification":"PHASE_3H_AN_HOST1_DIAGNOSTIC_CAPTURE_FAILURE","physical_interpretation_created":False,
        "cases":cases,"working_H_AL_source":str(working_path),"working_H_AL_source_sha256":ab._sha(working_path),
        "working_H_AL_timeline":{"Action23_complete_s":3.4,"UP_adapter_entered_s":terminal["start_sim_time"],
            "brake_start_s":brake["start_sim_time"],"brake_end_s":brake["end_sim_time"],
            "brake_chunks":[{"start":r["simulation_start"],"end":r["simulation_end"],
                "stopped":r["body_stopped_contract"]["pass"],"stats":r["step_evidence"]} for r in brake["chunks"]],
            "ACQUIRE_LINEAR_start_s":acquire["start_sim_time"],
            "actual_UP_publication_s":terminal["action_publication"]["action_command_sim_time"]},
        "first_ordering_difference":"After the successful final braking chunk/task callback at3.600s, H-AN issues its diagnostic pose service and one tick; H-AL returns directly to production brake completion/acquisition baselines and UP publication at3.600s.",
        "exact_failure":{"Host1_source_function":"perform_intervention","Host1_source_line":248,
            "expression":"after_mark = dm.physics_mark(adapter)",
            "marker_function":"diagnose_v07_gazebo_action24_duration_matched.physics_mark",
            "marker_raise_line":301,"requested_time_ns":3601000000,
            "creation":"diagnostic dictionary only after an actual stats candidate satisfies exact time and paused is True",
            "consumption":"snapshot and transport.sample read latest non-destructively; sample waits for timestamp only, not pause flag",
            "stepper_contract":"GazeboStepper._verify_progress line201 accepts absent paused when require_iterations=False; it retained paused_after=None",
            "point_of_failure":"diagnostic one-shot marker rejects the accepted, transient/missing-pause stats, without waiting for a fresh explicit paused sample",
            "no_production_marker_was_consumed_or_skipped":True,
            "later_paused_message_or_different_timestamp":"NOT_PRESERVED; do not infer later emission or a timestamp mismatch"},
        "architecture_finding":{"production_step_return_line":696,"completed_callback_line":772,
            "acquisition_baseline_lines":[835,839],"acquisition_call_line":849,
            "pending_WorldControl_transaction_at_callback":False,
            "why_checkpoint_safe":"step_simulation returned and chunk iteration/Pose_V/stopped checks completed before callback. Acquisition start pose, clock and cursor are constructed only after callback. No reserved marker/clock remains pending; added interval is explicitly synchronized before returning.",
            "why_not_between_adapter_calls":"Action23 completes with the actual DOWN command latched. External stop_agent would replace it with zero, so next adapter.step(up) selects OTHER/direct instead of LINEAR_REVERSAL. Moving the hook that way would change the experiment.",
            "pause_and_observe_without_stepping":"Possible for a stats pause acknowledgement; complete synchronized support/wrench/native evidence still needs an advancing sample. Host1 raw native data already observes each requested yaw at3601 after one tick (diagnostic pose proof only). Retain that minimum single tick, then explicitly pause with no additional ticks."}}


def audit_host2_checkpoint_defect():
    source = HOST2/"yaw_intervention_isolation_forensics.json"
    report = json.loads(source.read_text())
    cases = {}
    for case in CASES:
        evidence = report["sample_alignment_audit"]["cases"][case]["PRE_update_phase_staleness"]
        stale = evidence["saved_advancing_PRE"]
        current = evidence["production_pre_RPC_pose"]
        current_model = checkpoints.pose_v_view(current)
        roll,pitch,yaw = checkpoints.rpy(current_model["orientation_world_xyzw"])
        current_model.update(roll_rad=roll,pitch_rad=pitch,yaw_rad=yaw)
        old_request = pose_payload(stale,case,"simple_agent")
        corrected_construction = pose_payload(current_model,case,"simple_agent")
        differences = {k:old_request["position"][k]-current[k] for k in ("x","y","z")}
        differences.update(roll=stale["roll_rad"]-roll,pitch=stale["pitch_rad"]-pitch)
        if stale["iteration"]!=3600 or stale["sim_time_ns"]!=3600000000 or max(abs(v) for v in differences.values())<1e-7:
            raise InvalidCapture("accepted Host2 stale checkpoint defect did not reproduce")
        if any(corrected_construction["position"][key]!=current[key] for key in ("x","y","z")):
            raise InvalidCapture("current model origin construction regression")
        cases[case] = {"same_iteration":3600,"same_sim_time_ns":3600000000,
            "stale_request_minus_current_pose":differences,"current_model_construction":corrected_construction,
            "construction_only_not_runtime_checkpoint":True}
    return {"classification":"HOST2_UPDATE_PHASE_DEFECT_REPRODUCED_OFFLINE","source":str(source),
            "source_sha256":ab._sha(source),"cases":cases,
            "Host2_had_no_paused_support_wrench_checkpoint":True,
            "Host2_noncausal_physical_outcomes_used_for_tuning":False,
            "repair":"one const-ECM callback reads model/native/wheel/contact/wrench with shared phase id; current model defines request"}


def frozen_tolerance_digest(limits):
    import hashlib
    saved = json.loads((HOST2/"yaw_intervention_preflight.json").read_text())["tolerances"]
    actual_bytes = json.dumps(limits,sort_keys=True,allow_nan=False).encode()
    expected_bytes = json.dumps(saved,sort_keys=True,allow_nan=False).encode()
    if limits!=saved or actual_bytes!=expected_bytes:
        raise InvalidCapture("Host2 predeclared isolation tolerances changed")
    return hashlib.sha256(actual_bytes).hexdigest()


def preflight(artifact_dir, output):
    output = ensure_output(output)
    allowed = {"observer_builds","preflight_sdfs","yaw_intervention_preflight.json"}
    if output.exists() and any(p.name not in allowed for p in output.iterdir()):
        raise FileExistsError("refusing existing runtime/unknown evidence")
    guard = protected_manifest()
    scenario,seed,_ = history.source(artifact_dir)
    limits = tolerance_spec()
    frozen_digest = frozen_tolerance_digest(limits)
    host1_audit = audit_host1()
    host2_audit = audit_host2_checkpoint_defect()
    saved_limits = json.loads((HOST1/"yaw_intervention_preflight.json").read_text())["tolerances"]
    if limits != saved_limits:
        raise InvalidCapture("predetermined H-AN isolation tolerances changed")
    from aero_ai_studio.simulation.control_execution import ControlExecutionRequest, plan_control_execution
    entry = canonical_transition(dm.gazebo_physics_twist("down"))
    production_plan = plan_control_execution(ControlExecutionRequest("up",entry["previous_command"],
        entry["requested_command"],entry["transition_type"])).to_dict()
    if [p["kind"] for p in production_plan["phases"]] != ["BRAKE_LINEAR","ACQUIRE_LINEAR"]:
        raise InvalidCapture("production DOWN-to-UP plan changed")
    dm.clock_spec()
    libraries,builds = ab._build_all(output/"observer_builds")
    namespace = uuid4().hex
    cases = []
    for c in CASES:
        directory = output/"preflight_sdfs"/c
        prod = ab.GazeboWorldGenerator().generate(scenario,directory/"world",closed_loop=True,control_mode="PHYSICS")
        diag,info = ab._instrument_world(prod,directory/"observer_outputs",libraries,topic_identity=c+"/"+namespace)
        diag,info = checkpoints.instrument(diag,info)
        if round(float(ET.parse(diag).findtext("world/physics/max_step_size"))*1e9)!=STEP_NS:
            raise InvalidCapture("runtime SDF physics step differs from fixed one-step intervention")
        if ab._sha(prod)!=ab.PRODUCTION_HASH:
            raise InvalidCapture("production SDF hash changed")
        cases.append({"plan":plan(c),"diagnostic_sdf":str(diag),"instrumentation":info})
    if len({x["instrumentation"]["native"]["topic"] for x in cases})!=2:
        raise InvalidCapture("preflight topic identities collide")
    if list(output.rglob("*.ndjson")) or list(output.rglob("case_result.json")):
        raise InvalidCapture("preflight created runtime evidence")
    history.verify_manifest(guard)
    report = {"status":"PREFLIGHT_PASS","gazebo_launched":False,"runtime_evidence_created":False,
              "scenario_seed":42,"reset_seed":seed,"configured_reset_target":history.configured_reset_target(scenario),
              "cases":cases,"observer_builds":builds,"tolerances":limits,
              "host1_marker_failure_audit":host1_audit,
              "host2_checkpoint_defect_audit":host2_audit,
              "checkpoint_contract":{"PRE":"PRE_RPC_CHECKPOINT_COHERENT","POST":"POST_RPC_CHECKPOINT_COHERENT",
                  "collection_phase":checkpoints.PHASE,"atomic_read_scope":"one current const-ECM callback, not simultaneous new producer measurements",
                  "contact_wrench_age":"held component results, producer stamp retained when available; no fresh paused solve claimed",
                  "production_Pose_V":"fresh receive sequence at exact time, matches atomic current model pose at construction precision",
                  "stale_advancing_fallback_allowed":False,"RPC_request_origin":"atomic current model XYZ/roll/pitch",
                  "SHAM_fixed_yaw_guard":"SHAM_TARGET_NOT_CURRENT_YAW on existing predeclared yaw-bound failure",
                  "numerical_construction_precision":"64 ULP, separate from unchanged physical isolation limits"},
              "checkpoint_sources_sha256":{str(path):ab._sha(path) for path in (Path(checkpoints.__file__),ab.ROOT/"tools/gazebo_paused_physical_checkpoint.hh",ab.ROOT/"tools/gazebo_native_link_velocity_observer.cc")},
              "isolation_gates_unchanged":True,"frozen_tolerance_canonical_sha256":frozen_digest,
              "normal_production_DOWN_UP_plan":production_plan,
              "no_inflight_physics_transaction_at_intervention_required":True,
              "pause_synchronization":{"request":{"pause":True},"extra_physics_iterations":0,
                  "fresh_receive_sequence_required":True,"explicit_paused_True_required":True,
                  "exact_iteration_and_nanoseconds_required":True,"corrective_stepping_allowed":False},
              "synchronization_architecture":"completed production braking transaction -> atomic coherent PRE -> current-model pose RPC -> one tick -> explicit pause and fresh marker -> atomic coherent POST -> unchanged production acquisition",
              "post_service_advancing_iterations":POST_STEPS,"post_service_elapsed_ns":STEP_NS,
              "same_pose_service_path":True,"wheel_phase_intervention_implemented":False,
              "protected_source_sha256_before_after":guard,"runner_sha256":ab._sha(__file__)}
    write_json(output/"yaw_intervention_preflight.json",report)
    return report


def run(artifact_dir, output):
    output = ensure_output(output)
    allowed = {"observer_builds","preflight_sdfs","yaw_intervention_preflight.json"}
    if output.exists() and any(p.name not in allowed for p in output.iterdir()):
        raise FileExistsError("refusing to overwrite runtime/unknown evidence")
    guard = protected_manifest()
    scenario,seed,_ = history.source(artifact_dir)
    dm.clock_spec()
    tolerances = tolerance_spec()  # Freeze before either arm; never fit to this run.
    frozen_tolerance_digest(tolerances)
    libraries,builds = ab._build_all(output/"observer_builds")
    records,integrities,partitions,topics = {},{},set(),set()
    namespace,reference = uuid4().hex,None
    for c in CASES:
        if records and not records.get(CASES[0],{}).get("shutdown_completed"):
            integrities[c] = {"case_valid":False,"invalid_reasons":["previous process shutdown not proven"]}
            break
        output.joinpath(c).mkdir(parents=True)
        try:
            r = capture(c,scenario,output/c,libraries,seed,namespace)
            records[c] = r
            integrities[c] = validate(r,c,scenario,seed,reference,partitions,topics)
            reference = reference or r.get("canonical_reset_pose")
            identity = r.get("runtime_identity",{})
            partitions.add(identity.get("partition"));topics.add(identity.get("topic"))
            write_json(output/c/"capture_integrity.json",integrities[c])
        except Exception as exc:
            records.setdefault(c,{"shutdown_completed":False})
            integrities[c] = {"case_valid":False,"invalid_reasons":[type(exc).__name__+": "+str(exc)],
                              "physical_classifier_attempted":False,"traceback":traceback.format_exception(type(exc),exc,exc.__traceback__)}
    try:
        history.verify_manifest(guard)
        report = analyze(records,integrities,tolerances)
    except Exception as exc:
        report = {"status":"CAPTURE_FAILED","capture_integrity":integrities,"isolation":{"classification":"CAPTURE_INVALID"},
                  "interpretation":"CAPTURE_INVALID","physical_classification_created":False,
                  "diagnostic_error":type(exc).__name__+": "+str(exc)}
    report.update(production_changed=False,protected_source_sha256_before_after=guard,
                  observer_builds=builds,runner_sha256=ab._sha(__file__),wheel_phase_intervention_implemented=False)
    write_json(output/"yaw_intervention_analysis.json",report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir",type=Path,default=ab.DEFAULT_ARTIFACT)
    parser.add_argument("--output",type=Path,default=DEFAULT_OUTPUT)
    parser.add_argument("--preflight-only",action="store_true")
    args = parser.parse_args(argv)
    try:
        report = preflight(args.artifact_dir,args.output) if args.preflight_only else run(args.artifact_dir,args.output)
    except Exception as exc:
        print("CAPTURE_FAILED: "+type(exc).__name__+": "+str(exc));return 1
    if report["status"] in ("CAPTURED","INTERVENTION_ISOLATION_FAILED"):
        for case,stages in report.get("checkpoints",{}).items():
            print(case+": RUNTIME_CAPTURE_VALID")
            for cp in stages.values():
                if cp:print(case+": "+cp["classification"])
    if report["status"]=="CAPTURED":
        print(report["isolation"]["classification"])
        for case,label in report["case_outcomes"].items():
            print(case+": "+label)
    print(report["status"])
    print("evidence: "+str(args.output))
    if report.get("interpretation"):
        print("interpretation: "+report["interpretation"])
    if report["status"]=="CAPTURE_FAILED":
        for case,check in report.get("capture_integrity",{}).items():
            print(case+" runtime: "+("VALID" if check.get("case_valid") else "INVALID")+
                  ("; "+"; ".join(check.get("invalid_reasons",[])) if check.get("invalid_reasons") else ""))
        print(report["diagnostic_error"])
        return 1
    if report["status"]=="INTERVENTION_ISOLATION_FAILED":
        failures = report["isolation"]["failures"]
        for prefix in ("RIGHT_YAW_SHAM:","RIGHT_YAW_MATCHED:","between-arm after:","between-arm collateral change:","between-arm before:"):
            print(prefix+" failure count = "+str(sum(name.startswith(prefix) for name in failures)))
        print("Full failed field names and values: "+str(args.output/"yaw_intervention_analysis.json"))
        print("YAW_CAUSAL_RELEVANCE_UNRESOLVED")
        return 2
    return 0


if __name__=="__main__":
    raise SystemExit(main())
