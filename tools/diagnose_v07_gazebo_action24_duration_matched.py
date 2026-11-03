#!/usr/bin/env python3
"""Two fresh diagnostic cases: neutral physics-time sham vs Action08 RIGHT.

Reuses H-AJ/H-AI launch, observers, reset validation and strict classification.
Preflight builds/checks static instrumentation only; runtime is Host-only.
"""
from __future__ import annotations

import argparse
import inspect
import json
import math
import traceback
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import xml.etree.ElementTree as ET

from tools import diagnose_v07_gazebo_action24_history_restoration as history
from aero_ai_studio.gazebo.stepping import GazeboStepper
from aero_ai_studio.gazebo.transport import stamp
from aero_ai_studio.simulation.action_mapping import gazebo_physics_twist

ab = history.ab
HOST1 = ab.ROOT / "validation/v071-host/gazebo-action24-duration-matched-phase3hal-host1"
DEFAULT_OUTPUT = ab.ROOT / "validation/v071-host/gazebo-action24-duration-matched-phase3hal-host2"
SUFFIX = history.CANONICAL[8:]
NEUTRAL = "neutral_sham"
CASES = ("CONTROL_SHAM", "RIGHT_HISTORY")
REFERENCE = history.DEFAULT_OUTPUT / "h14_h15_boundary_analysis.json"
PROTECTED = (HOST1, history.DEFAULT_PRIOR, history.DEFAULT_OUTPUT, ab.DEFAULT_OUTPUT,
             ab.ROOT / "validation/v071-host/gazebo-action24-history-ab-phase3hai-host1")


def invalid(message):
    raise history.InvalidCapture(message)


def required_events(record):
    events = record.get("events")
    if not isinstance(events,list):
        invalid("case events must be a list")
    return events


def unique_match(rows, predicate, label):
    if not isinstance(rows,list):
        invalid(label+": required list missing")
    matches = [row for row in rows if isinstance(row,dict) and predicate(row)]
    if len(matches) != 1:
        invalid(f"{label}: expected one record, found {len(matches)} (source length {len(rows)})")
    return next(iter(matches))


def terminal_event(record):
    events = required_events(record)
    return unique_match(events,lambda e:e.get("canonical_index")==24 and e.get("action")=="up",
        "terminal Action24 UP event")


def vector(value, length, label):
    if not isinstance(value,(list,tuple)) or len(value)!=length or not all(type(v) in (int,float) and math.isfinite(v) for v in value):
        invalid(label+f": expected {length} finite components")
    return tuple(value)


def failure_record(exc):
    result = dict(_original_failure(exc))
    result["traceback"] = traceback.format_exception(type(exc),exc,exc.__traceback__)
    return result


_original_failure = ab._failure


def execute_captured(adapter, action, phase):
    """The existing one-step production call, with total diagnostic extraction.

    A bare exception may have evidence=None. Never let evidence parsing mask
    that original exception (the older A/B helper did so on Host1).
    """
    start = float(adapter.env.stepper.time)
    before = getattr(adapter.env.controller,"publish_sequence",0)
    result,error = None,None
    try:
        result = adapter.step(action)
    except Exception as exc:
        error = failure_record(exc)
        error["diagnostic_stage"]=getattr(adapter,"_duration_matched_stage",phase)
    evidence = getattr(result,"execution_evidence",None) if result is not None else (error or {}).get("evidence")
    evidence = evidence if isinstance(evidence,dict) else {}
    phases = ab._find_phase_evidence(evidence)
    acquire = next((p for p in phases if isinstance(p,dict) and p.get("phase")=="ACQUIRE_LINEAR"),None)
    transition = adapter.env.telemetry.get("action_transition") or {}
    transition = dict(transition) if isinstance(transition,dict) else {}
    sequence = transition.get("action_publish_sequence")
    published = getattr(adapter.env.controller,"publish_sequence",0)>before
    last = getattr(adapter.env.controller,"last_published_command",None) or {}
    actual_up = (type(sequence) is int and sequence>before and transition.get("commanded_twist",{}).get("linear",{}).get("x")==.5) or (
        published and last.get("linear",{}).get("x")==.5)
    up_time = acquire.get("start_sim_time") if acquire else None
    if phase=="CLEAN_UP" and actual_up:
        up_time = transition.get("action_command_sim_time",start)
    return {"up_reached":action=="up" and actual_up and up_time is not None,
        "last_published_command":last,"action_publication":transition,"phase":phase,"action":action,
        "start_sim_time":start,"end_sim_time":float(adapter.env.stepper.time),
        "up_command_sim_time":up_time if action=="up" else None,"execution_evidence":evidence,
        "result_reason":getattr(result,"reason",None),"terminated":getattr(result,"terminated",None),
        "telemetry":dict(adapter.env.telemetry.get("gazebo_dqn_training") or {}),"exception":error}


def keyed_streams(record):
    try:
        maps = history.stream_maps(record)
    except history.InvalidCapture:
        raise
    except Exception as exc:
        invalid("stream structure/iteration validation failed: "+str(exc))
    identity = record.get("runtime_identity") or {}
    if not identity.get("partition") or not identity.get("topic"):
        invalid("runtime process partition/topic identity missing")
    for stream in ("support_rows","wrench_rows"):
        prior=-1
        for row in maps[stream].values():
            epoch=row.get("epoch")
            if type(epoch) is not int or epoch<prior:
                invalid(stream+": missing/nonmonotonic epoch identity")
            prior=epoch
    worlds = {row.get("world_entity_id") for row in maps["native_samples"].values()}
    if len(worlds)!=1 or any(type(v) is not int or v<=0 for v in worlds):
        invalid("native stream has missing/mixed process-local world identity")
    maps["_identity"] = {**identity,"world_entity_id":next(iter(worlds))}
    return maps


def aligned_sample(maps, iteration, label):
    if type(iteration) is not int:
        invalid(label+": required iteration is not an integer")
    found = {}
    for key in ("support_rows","wrench_rows","native_samples"):
        rows = maps.get(key,{})
        if iteration not in rows:
            invalid(f"{label}: missing {key} advancing iteration {iteration}")
        found[key] = rows[iteration]
    support,wrench,native = (found[k] for k in ("support_rows","wrench_rows","native_samples"))
    if any(row.get("iteration")!=iteration or row.get("paused") is not False for row in found.values()):
        invalid(label+": mismatched/nonadvancing iteration identity")
    ns = support.get("sim_time_ns")
    if type(ns) is not int or ns!=wrench.get("sim_time_ns") or ns!=round(native["simulation_time_s"]*1e9):
        invalid(label+": support/wrench/native simulation timestamps disagree")
    epoch = support.get("epoch")
    if type(epoch) is not int or epoch<0 or wrench.get("epoch")!=epoch:
        invalid(label+": support/wrench epoch mismatch or missing epoch")
    if native.get("world_entity_id")!=maps["_identity"]["world_entity_id"]:
        invalid(label+": native world/process identity mismatch")
    return support,wrench,native


def at_sim_time(maps, ns, label):
    matches = [i for i,row in maps["support_rows"].items() if row["sim_time_ns"]==ns]
    if len(matches)!=1:
        invalid(f"{label}: exact support simulation timestamp {ns} ns missing/ambiguous ({len(matches)} matches)")
    iteration = next(iter(matches))
    aligned_sample(maps,iteration,label)
    return iteration


def command_active_t0(record, maps=None):
    maps = maps or keyed_streams(record)
    event = terminal_event(record)
    publication = event.get("action_publication") or {}
    time_s = publication.get("action_command_sim_time")
    sequence,before = publication.get("action_publish_sequence"),publication.get("command_publish_sequence_before")
    if (type(time_s) not in (int,float) or not math.isfinite(time_s) or
        type(sequence) is not int or type(before) is not int or sequence<=before or
        publication.get("commanded_twist",{}).get("linear",{}).get("x")!=.5):
        invalid("terminal UP actual publication/time evidence missing")
    pub_ns = round(time_s*1e9)
    pub_iteration = at_sim_time(maps,pub_ns,"UP publication boundary")
    t0 = pub_iteration+1
    s,_,_ = aligned_sample(maps,t0,"COMMAND_ACTIVE_T0")
    if s["sim_time_ns"]!=pub_ns+clock_spec()["physics_step_ns"]:
        invalid("COMMAND_ACTIVE_T0 is not the first 1 ms advancing post-publication iteration")
    end = event.get("end_sim_time")
    if type(end) not in (int,float) or not math.isfinite(end):
        invalid("terminal acquisition end time missing")
    end_iteration = at_sim_time(maps,round(end*1e9),"terminal UP acquisition end")
    moving = []
    for i,row in maps["wrench_rows"].items():
        if t0<=i<=end_iteration and all(type(row.get(side,{}).get("actual_velocity_rad_s")) in (int,float) and
            math.isfinite(row[side]["actual_velocity_rad_s"]) and row[side]["actual_velocity_rad_s"]>.01 for side in ("left","right")):
            moving.append(i)
    if not moving:
        invalid(f"FIRST_OBSERVED_WHEEL_ACTUATION missing in terminal iterations {t0}..{end_iteration}")
    first = min(moving)
    act,_,_ = aligned_sample(maps,first,"FIRST_OBSERVED_WHEEL_ACTUATION")
    return {"kind":"COMMAND_ACTIVE_T0","iteration":t0,"sim_time_ns":s["sim_time_ns"],"sim_time_s":s["sim_time_ns"]/1e9,
        "publication_iteration":pub_iteration,"publication_sim_time_s":time_s,"publication_sim_time_ns":pub_ns,
        "publication_to_T0_delta_iterations":1,"publication_to_T0_delta_ns":s["sim_time_ns"]-pub_ns,
        "first_observed_wheel_actuation":{"kind":"FIRST_OBSERVED_WHEEL_ACTUATION","iteration":first,
            "sim_time_ns":act["sim_time_ns"],"sim_time_s":act["sim_time_ns"]/1e9,
            "delta_ms":(act["sim_time_ns"]-s["sim_time_ns"])/1e6,"delta_iterations":first-t0},
        "end_iteration":end_iteration,"resolution_ms":1,"sub_ms_ordering_claimed":False,
        "stream_identity":maps["_identity"],"native_epoch_semantics":"native has no epoch field; join by current process/topic/world identity plus exact iteration/time and matching support/wrench epoch"}


def terminal_alignment(record):
    maps = keyed_streams(record)
    t0 = command_active_t0(record,maps)
    # Required diagnostic points are exact keys, never list offsets.
    for delta in (5,6,7):
        if t0["iteration"]+delta>t0["end_iteration"]:
            invalid(f"Action24 +{delta} ms exceeds captured acquisition window")
        aligned_sample(maps,t0["iteration"]+delta,f"Action24 +{delta} ms")
    indices = range(t0["iteration"]-5,t0["end_iteration"]+1)
    if len(indices)<21:
        invalid("terminal UP window insufficient for -5..+15 ms analysis")
    recovery_samples=t0["end_iteration"]-(t0["iteration"]+history.RECOVERY_WINDOW_START_MS)+1
    if recovery_samples<history.MIN_RECOVERY_WINDOW_MS:
        invalid("terminal recovery window insufficient: requires 50 advancing samples from +7 ms")
    for i in indices:
        s,_,_ = aligned_sample(maps,i,f"Action24 relative iteration {i-t0['iteration']}")
        if s["sim_time_ns"]!=t0["sim_time_ns"]+(i-t0["iteration"])*clock_spec()["physics_step_ns"]:
            invalid("terminal UP iteration/time grid inconsistent")
    return maps,t0,indices


def ensure_output(output):
    output = Path(output).resolve()
    for prior in PROTECTED:
        prior = prior.resolve()
        if output == prior or output.is_relative_to(prior) or prior.is_relative_to(output):
            raise FileExistsError("output overlaps preserved evidence: " + str(prior))


def write_json(path, value):
    ensure_output(path)
    history.write_json(path, value)


def plan(case, internal=False):
    if case not in CASES:
        raise ValueError("unknown matched-control case")
    first = NEUTRAL if case == "CONTROL_SHAM" else "right"
    return {"name":case, "prefix":[first, *history.CANONICAL[8:22]],
        "actions":[first, *SUFFIX], "canonical_indices":[8 if internal or first == "right" else None, *range(9,25)],
        "preparation_kind":"DURATION_MATCHED_NEUTRAL_SHAM" if first == NEUTRAL else "CANONICAL_ACTION08_RIGHT",
        "terminal_suffix":["23 DOWN", "production BRAKE_LINEAR", "production stopped contract", "24 UP +0.5"]}


def clock_spec():
    parameters = inspect.signature(GazeboStepper.__init__).parameters
    dt = parameters["dt"].default
    physics_dt = parameters["physics_dt"].default
    ticks = round(dt / physics_dt)
    if dt != .1 or physics_dt != .001 or ticks != 100:
        raise history.InvalidCapture("production clock differs from accepted Action08 one-chunk duration")
    return {"simulation_duration_ns":round(dt*1e9), "advancing_iterations":ticks,
        "physics_step_ns":round(physics_dt*1e9),
        "rule":"exact equal integer physics iterations and integer nanoseconds; no wall-clock matching"}


def protected_manifest():
    paths = [p for p in (ab.ROOT/"src").rglob("*") if p.is_file() and p.suffix in (".py", ".sdf")]
    paths += [ab.DEFAULT_ARTIFACT/"worlds/aero_ef81a06d3164/world.sdf",Path(ab.__file__),Path(history.__file__),REFERENCE]
    paths += [p for p in HOST1.rglob("*") if p.is_file()]
    return {str(p.resolve()):ab._sha(p) for p in paths}


def physics_mark(adapter):
    stepper = adapter.env.stepper
    now_ns = round(stepper.time*1e9)
    snapshot = stepper._snapshot()
    observed = snapshot.get("data") or {}
    candidates = [("transport_snapshot",observed,snapshot.get("sequence"))]
    verified = stepper.last_verification or {}
    if verified.get("valid") is True:
        after = verified.get("after_sim_time")
        if type(after) in (int,float) and math.isfinite(after) and round(after*1e9)==now_ns:
            candidates.append(("verified_stepper_WorldStatistics",{
                "iterations":verified.get("iterations_after"),"paused":verified.get("paused_after"),
                "sim_time":{"sec":now_ns//1_000_000_000,"nsec":now_ns%1_000_000_000}},
                verified.get("stats_sequence_after")))
    def valid(data):
        i=data.get("iterations_normalized",data.get("iterations"))
        return type(i) is int and i>=0 and data.get("paused") is True and round(stamp(data)*1e9)==now_ns
    if not any(valid(data) for _,data,_ in candidates):
        transport = getattr(stepper,"transport",None)
        if transport is not None:
            try:
                data = transport.sample(stepper.topic,stepper.time,stepper.timeout)
                candidates.append(("exact_time_transport_sample",data,None))
            except Exception as exc:
                invalid("preparation exact-time WorldStatistics unavailable: "+str(exc))
    for source,data,sequence in candidates:
        if valid(data):
            iteration=data.get("iterations_normalized",data.get("iterations"))
            return {"iteration":iteration,"sim_time_ns":now_ns,"sim_time_s":stamp(data),
                "stats_receive_sequence":sequence,"paused":True,"stats_source":source,
                "observed_snapshot":observed,"verified_stepper_evidence":dict(verified)}
    invalid(f"paused WorldStatistics for exact current simulation time {now_ns} ns missing; no physics advanced by marker")


def finish_preparation(adapter, start, kind):
    end = physics_mark(adapter)
    verification = dict(adapter.env.stepper.last_verification)
    spec = clock_spec()
    ticks = end["iteration"]-start["iteration"]
    elapsed_ns = end["sim_time_ns"]-start["sim_time_ns"]
    if (ticks != spec["advancing_iterations"] or elapsed_ns != spec["simulation_duration_ns"] or
        verification.get("valid") is not True or verification.get("iteration_delta") != ticks):
        raise history.InvalidCapture("preparation did not advance exactly one production Action08 chunk")
    return {"kind":kind,"start":start,"end":end,"advancing_iterations":ticks,
        "simulation_duration_ns":elapsed_ns,"simulation_duration_s":elapsed_ns/1e9,
        "step_verification":verification}


def neutral_advance(adapter):
    """No reset, set_pose, contact reset, agent decision, or wall-clock wait."""
    env = adapter.env
    spec = clock_spec()
    if round(env.stepper.dt*1e9) != spec["simulation_duration_ns"] or round(env.stepper.physics_dt*1e9) != spec["physics_step_ns"]:
        raise history.InvalidCapture("SHAM stepper duration differs from production Action08 duration")
    before = physics_mark(adapter)
    sequence = env.controller.publish_sequence
    env.controller.stop_agent()
    publication = dict(env.controller.last_published_command)
    if publication != {"linear":{"x":0.},"angular":{"z":0.}}:
        raise history.InvalidCapture("SHAM did not publish a neutral Twist")
    env.stepper.step_simulation()
    env._refresh()
    result = finish_preparation(adapter,before,"DURATION_MATCHED_NEUTRAL_SHAM")
    result["action_publication"] = {"action":NEUTRAL,"commanded_twist":publication,
        "action_publish_sequence":env.controller.publish_sequence,
        "command_publish_sequence_before":sequence,"action_command_sim_time":before["sim_time_s"]}
    result["semantics"] = {"physics_advanced":True,"directional_action_executed":False,
        "reset_called":False,"reposition_called":False,"contact_reset_called":False,
        "wall_clock_wait_used":False,"path":"controller.stop_agent -> stepper.step_simulation -> environment._refresh"}
    return result


def capture(case, scenario, output, libraries, seed, namespace):
    ensure_output(output)
    from aero_ai_studio.training import gazebo_physics
    original = gazebo_physics.GazeboPhysicsTrainingEnvironment
    preparation = {}
    reset_state = {}
    old_execute,old_failure = ab._execute_captured,ab._failure

    class MatchedEnvironment(original):
        def reset(self, selected_seed=None):
            result=super().reset(selected_seed)
            reset_state.update(reset_completed=True,reset_evidence=dict(self.last_reset_evidence),
                canonical_reset_pose=dict(self.env.pose),initial_reset_sim_time_s=float(self.env.stepper.time))
            return result

        def step(self, action):
            if action == NEUTRAL:
                if case != "CONTROL_SHAM" or preparation:
                    raise history.InvalidCapture("unexpected/repeated SHAM intervention")
                self._duration_matched_stage="SHAM prelude: neutral physics advancement"
                preparation.update(neutral_advance(self))
                return SimpleNamespace(execution_evidence={"neutral_physics_preparation":preparation},
                    reason="neutral_physics_advanced",terminated=False)
            if not preparation:
                if case != "RIGHT_HISTORY" or action != "right":
                    raise history.InvalidCapture("RIGHT case must execute Action08 RIGHT first")
                self._duration_matched_stage="RIGHT prelude: start WorldStatistics"
                before = physics_mark(self)
                self._duration_matched_stage="RIGHT prelude: production step(right)"
                result = super().step(action)
                self._duration_matched_stage="RIGHT prelude: end WorldStatistics"
                preparation.update(finish_preparation(self,before,"CANONICAL_ACTION08_RIGHT"))
                return result
            self._duration_matched_stage="canonical suffix: production step("+action+")"
            return super().step(action)

    gazebo_physics.GazeboPhysicsTrainingEnvironment = MatchedEnvironment
    ab._execute_captured,ab._failure = execute_captured,failure_record
    try:
        record = history.capture_candidate(plan(case,internal=True),scenario,output,libraries,seed,
            runtime_namespace=namespace)
    finally:
        gazebo_physics.GazeboPhysicsTrainingEnvironment = original
        ab._execute_captured,ab._failure = old_execute,old_failure
    record.update(reset_state)
    reset_audit=history.reset_validity(record,scenario,seed)
    record["configured_reset_condition"]=reset_audit["configured_reset_condition"]
    record["measured_reset_state"]=reset_audit["measured_reset_state"]
    record["preparation"] = preparation
    record["candidate"] = plan(case)
    if case == "CONTROL_SHAM" and any(e.get("action")==NEUTRAL for e in record.get("events",[])):
        first = unique_match(required_events(record),lambda e:e.get("action")==NEUTRAL,"SHAM preparation event")
        first.update(canonical_index=None,intervention_slot=8,phase="DURATION_MATCHED_NEUTRAL_SHAM",
            canonical_action_executed=False,action_publication=preparation.get("action_publication",{}))
    write_json(output/"case_result.json",record)
    return record


def qmul(a,b):
    x,y,z,w=vector(a,4,"quaternion A");X,Y,Z,W=vector(b,4,"quaternion B")
    return [w*X+x*W+y*Z-z*Y,w*Y-x*Z+y*W+z*X,w*Z+x*Y-y*X+z*W,w*W-x*X-y*Y-z*Z]


def qinverse(a):
    x,y,z,w=vector(a,4,"inverse quaternion")
    return [-x,-y,-z,w]


def state_at(record, iteration, maps=None):
    maps = maps or keyed_streams(record)
    support,wrench,native = aligned_sample(maps,iteration,"physical boundary")
    return component_state(support,wrench,native)


def component_state(support, wrench, native):
    """Normalize component reads; this pure function never selects update phase.

    Advancing callers validate keyed streams first. Paused checkpoint callers
    must validate their atomic same-callback provenance before calling this.
    Paused input flags are preserved; no sample is relabelled as advancing.
    """
    iteration = support.get("iteration")
    ns = support["sim_time_ns"]
    if ns != wrench["sim_time_ns"] or ns != round(native["simulation_time_s"]*1e9):
        raise history.InvalidCapture("boundary streams do not join at exact iteration/time")
    if not native.get("all_link_native_velocities_available"):
        raise history.InvalidCapture("boundary native velocities unavailable")
    raw_links=native.get("links")
    if not isinstance(raw_links,list) or len(raw_links)!=3 or not all(isinstance(l,dict) and isinstance(l.get("expected_scoped_name"),str) for l in raw_links):
        invalid(f"physical boundary iteration {iteration}: three required native links missing")
    links={l["expected_scoped_name"].rsplit("::",1).pop():l for l in raw_links}
    if set(links)!={"body","left_wheel","right_wheel"}:
        invalid(f"physical boundary iteration {iteration}: required native link names missing/duplicated")
    for name,link in links.items():
        for key,n in (("position_world_m",3),("orientation_world_xyzw",4),("linear_velocity_world_m_s",3),("angular_velocity_world_rad_s",3)):
            vector(link.get(key),n,"native "+name+" "+key)
    body = links["body"];q = list(vector(body["orientation_world_xyzw"],4,"body orientation"));x,y,z,w = q
    vx,vy,vz=vector(body["linear_velocity_world_m_s"],3,"body linear velocity")
    vector(body["angular_velocity_world_rad_s"],3,"body angular velocity")
    vector(body["position_world_m"],3,"body position")
    roll = math.atan2(2*(w*x+y*z),1-2*(x*x+y*y))
    pitch = math.asin(max(-1.,min(1.,2*(w*y-z*x))))
    yaw = math.atan2(2*(w*z+x*y),1-2*(y*y+z*z))
    supports = {}
    for key,value in support["supports"].items():
        if not value.get("component_available") or value["state"] not in ("VALID_CONTACTS","VALID_EMPTY_CONTACT_SET"):
            raise history.InvalidCapture("boundary support component unavailable")
        points = [p for c in value.get("contacts",[]) if c["pair_classification"] == "SUPPORT_GROUND" for p in c["points"]]
        fn = 0.
        for point in points:
            force = history.project_force(point.get("body_1_force_world_n"),point.get("normal_world"))
            if force is None:
                raise history.InvalidCapture("invalid boundary contact force")
            fn += force["Fn_N"]
        supports[key] = {"state":value["state"],"Fn_N":fn,"depths_m":[p["depth_m"] for p in points]}
    phases,joints = {},{}
    for side in ("left","right"):
        wheel = links[side+"_wheel"]
        relative = qmul(qinverse(q),wheel["orientation_world_xyzw"])
        spin = qmul(relative,qinverse([math.sqrt(.5),0,0,math.sqrt(.5)]))
        _,spin_y,_,spin_w=spin  # qmul guarantees four validated components.
        phases[side] = math.atan2(math.sin(2*math.atan2(spin_y,spin_w)),math.cos(2*math.atan2(spin_y,spin_w)))
        raw = wrench[side]
        if raw.get("state") != "VALID_WRENCH" or not raw.get("actual_velocity_available"):
            raise history.InvalidCapture("boundary joint observer unavailable")
        if type(raw.get("actual_velocity_rad_s")) not in (int,float) or not math.isfinite(raw["actual_velocity_rad_s"]):
            invalid("boundary wheel velocity invalid: "+side)
        vector(raw.get("force_xyz_N"),3,"boundary "+side+" force")
        vector(raw.get("torque_xyz_N_m"),3,"boundary "+side+" torque")
        joints[side] = {k:raw[k] for k in ("actual_velocity_rad_s","force_xyz_N","torque_xyz_N_m")}
        for src,dst in (("force_xyz_N","force_norm_N"),("torque_xyz_N_m","torque_norm_N_m")):
            joints[side][dst] = math.sqrt(sum(v*v for v in raw[src]))
    state = {"iteration":iteration,"sim_time_ns":ns,"position_world_m":body["position_world_m"],
        "orientation_world_xyzw":q,"roll_rad":roll,"pitch_rad":pitch,"yaw_rad":yaw,
        "linear_velocity_world_m_s":body["linear_velocity_world_m_s"],"angular_velocity_world_rad_s":body["angular_velocity_world_rad_s"],
        "longitudinal_velocity_m_s":vx*math.cos(yaw)+vy*math.sin(yaw),
        "vertical_velocity_m_s":vz,"supports":supports,
        "total_Fn_N":sum(v["Fn_N"] for v in supports.values()),"joint_transmitted_wrench":joints,
        "wheel_phase_mod_2pi_rad":phases,"native_wheel_links":{side:{k:links[side+"_wheel"][k] for k in
            ("position_world_m","orientation_world_xyzw","linear_velocity_world_m_s","angular_velocity_world_rad_s")} for side in ("left","right")}}
    json.dumps(state,allow_nan=False)
    return state


def numerical_difference(a,b):
    """RIGHT minus SHAM, preserving vectors and reporting all numeric fields."""
    def flatten(value,path=""):
        out = {}
        if isinstance(value,dict):
            for k,v in value.items():out.update(flatten(v,path+"."+k if path else k))
        elif isinstance(value,list):
            for i,v in enumerate(value):out.update(flatten(v,f"{path}[{i}]"))
        elif type(value) in (int,float):out[path]=value
        return out
    av,bv = flatten(a),flatten(b)
    delta = {k:bv[k]-av[k] for k in sorted(av.keys()&bv.keys()) if k not in ("iteration","sim_time_ns")}
    return {"SHAM":a,"RIGHT":b,"RIGHT_minus_SHAM":delta,
        "support_states_equal":all(a["supports"][k]["state"]==b["supports"][k]["state"] for k in a["supports"])}


def preparation_validity(record, case):
    p = record.get("preparation",{})
    spec = clock_spec()
    if not p or p.get("advancing_iterations") != spec["advancing_iterations"] or p.get("simulation_duration_ns") != spec["simulation_duration_ns"]:
        raise history.InvalidCapture(case+": preparation duration/iteration evidence invalid")
    if p["end"]["iteration"]-p["start"]["iteration"] != p["advancing_iterations"] or p["end"]["sim_time_ns"]-p["start"]["sim_time_ns"] != p["simulation_duration_ns"]:
        raise history.InvalidCapture("preparation boundary/count mismatch")
    expected = NEUTRAL if case == "CONTROL_SHAM" else "right"
    first = unique_match(required_events(record),lambda e:e.get("action")==expected and e.get("canonical_index")== (None if case=="CONTROL_SHAM" else 8),"preparation event")
    if first["action"] != expected or first.get("exception") or first.get("terminated"):
        raise history.InvalidCapture("preparation action did not complete")
    publication = first["action_publication"]
    twist = {"linear":{"x":0.},"angular":{"z":0.}} if case == "CONTROL_SHAM" else gazebo_physics_twist("right")
    if publication.get("commanded_twist") != twist or publication.get("action_publish_sequence",-1) <= publication.get("command_publish_sequence_before",-1):
        raise history.InvalidCapture("preparation actual publication incorrect")
    if round(first["start_sim_time"]*1e9) != p["start"]["sim_time_ns"] or round(first["end_sim_time"]*1e9) != p["end"]["sim_time_ns"]:
        raise history.InvalidCapture("preparation event timing mismatch")
    maps = keyed_streams(record)
    for i in range(p["start"]["iteration"],p["end"]["iteration"]+1):
        s = state_at(record,i,maps)
        lvx,lvy,_=vector(s["linear_velocity_world_m_s"],3,"SHAM linear velocity")
        _,_,wz=vector(s["angular_velocity_world_rad_s"],3,"SHAM angular velocity")
        if case == "CONTROL_SHAM" and (math.hypot(lvx,lvy) > history.RESET_STOPPED_SPEED or
            abs(wz) > history.RESET_STOPPED_SPEED or
            any(abs(s["joint_transmitted_wrench"][side]["actual_velocity_rad_s"])*.1 > history.RESET_STOPPED_SPEED for side in ("left","right"))):
            raise history.InvalidCapture("SHAM did not remain within existing stopped-speed contract")
    action09 = unique_match(required_events(record),lambda e:e.get("canonical_index")==9 and e.get("action")=="left","canonical Action09 event")
    if round(action09["start_sim_time"]*1e9) != p["end"]["sim_time_ns"]:
        raise history.InvalidCapture("unrecorded physics interval before Action09")
    return True


def validate(record,case,scenario,seed,reference_pose,partitions,topics):
    integrity={"case_valid":False,"invalid_reasons":[],"physical_classifier_attempted":False}
    try:
        integrity.update(ab.validate_case(record))
        terminal_event(record)  # Guard before inherited validator's events[-1].
        events=required_events(record)
        expected=plan(case)
        if ([e.get("canonical_index") for e in events]!=expected["canonical_indices"] or
            [e.get("action") for e in events]!=expected["actions"]):
            invalid("required complete preparation and canonical Actions09-24 sequence missing")
        maps,t0,_=terminal_alignment(record)
        integrity.update(history.validate_candidate(record,expected,partitions,topics))
        integrity["keyed_terminal_alignment"]={"valid":True,"T0":t0,"stream_identity":maps["_identity"]}
        reset=history.reset_validity(record,scenario,seed,reference_pose)
        integrity["reset_validation"]=reset
        integrity["invalid_reasons"].extend(reset["invalid_reasons"])
        preparation_validity(record,case)
        for index in range(9,25):
            event=unique_match(events,lambda e:e.get("canonical_index")==index,f"canonical Action{index:02d}")
            p=event.get("action_publication") or {}
            if p.get("commanded_twist")!=gazebo_physics_twist(event["action"]) or p.get("action")!=event["action"] or p.get("action_publish_sequence",-1)<=p.get("command_publish_sequence_before",-1):
                invalid("canonical suffix actual publication/order invalid")
        integrity["case_valid"]=not integrity["invalid_reasons"]
    except Exception as exc:
        integrity["case_valid"]=False
        integrity.setdefault("invalid_reasons",[]).append(str(exc) if isinstance(exc,history.InvalidCapture) else "malformed capture evidence: "+type(exc).__name__+": "+str(exc))
        integrity["validation_traceback"]=traceback.format_exception(type(exc),exc,exc.__traceback__)
    return integrity


def pair_controls(records):
    a,b = (records[k] for k in CASES)
    identities=[record.get("runtime_identity",{}) for record in (a,b)]
    if not all(i.get("partition") and i.get("topic") for i in identities) or len({i["partition"] for i in identities})!=2 or len({i["topic"] for i in identities})!=2:
        invalid("matched cases do not have fresh distinct process/topic identities")
    pa,pb = a["preparation"],b["preparation"]
    for key in ("advancing_iterations","simulation_duration_ns"):
        if pa[key] != pb[key]:raise history.InvalidCapture("SHAM/RIGHT duration mismatch: "+key)
    if pa["start"]["sim_time_ns"] != pb["start"]["sim_time_ns"] or pa["end"]["sim_time_ns"] != pb["end"]["sim_time_ns"]:
        raise history.InvalidCapture("SHAM/RIGHT initial simulation epochs differ")
    aa = state_at(a,pa["start"]["iteration"]);bb = state_at(b,pb["start"]["iteration"])
    comparison = numerical_difference(aa,bb)
    qa,qb = (dict(zip(("x","y","z","w"),v["orientation_world_xyzw"])) for v in (aa,bb))
    position_gap = math.dist(aa["position_world_m"],bb["position_world_m"])
    orientation_gap = history.quaternion_distance(qa,qb)
    phase_gap = {side:math.atan2(math.sin(bb["wheel_phase_mod_2pi_rad"][side]-aa["wheel_phase_mod_2pi_rad"][side]),
        math.cos(bb["wheel_phase_mod_2pi_rad"][side]-aa["wheel_phase_mod_2pi_rad"][side])) for side in ("left","right")}
    if (a["configured_reset_condition"] != b["configured_reset_condition"] or
        position_gap > history.RESET_POSITION_ENVELOPE_M+history.RESET_ROUNDING_SLACK or
        orientation_gap > history.RESET_ORIENTATION_ENVELOPE_RAD+history.RESET_ROUNDING_SLACK or
        any(abs(v)>history.RESET_ORIENTATION_ENVELOPE_RAD+history.RESET_ROUNDING_SLACK for v in phase_gap.values()) or not comparison["support_states_equal"]):
        raise history.InvalidCapture("initial physical conditions materially differ")
    comparison.update(classification="INITIAL_STATE_EQUIVALENT" if all(v==0 for v in comparison["RIGHT_minus_SHAM"].values()) else "INITIAL_STATE_DIFFERENT_WITHIN_VALID_RESET_ENVELOPE",
        position_distance_m=position_gap,orientation_distance_rad=orientation_gap,wrapped_phase_difference_rad=phase_gap)
    return {"duration_equality_verified":True,"initial_comparison":comparison,
        "SHAM":pa,"RIGHT":pb,"precision":"exact integer iterations and nanoseconds"}


def case_outcome(case,classification):
    if classification == "SUPPORT_RECOVERY_AND_TRANSLATION_SUCCESS":
        return "DURATION_MATCHED_SHAM_SUCCESS" if case == "CONTROL_SHAM" else "RIGHT_HISTORY_SUCCESS"
    if classification == "CANONICAL_ACTION24_FAILURE_REPRODUCED":
        return "DURATION_MATCHED_SHAM_CANONICAL_FAILURE" if case == "CONTROL_SHAM" else "RIGHT_HISTORY_CANONICAL_FAILURE"
    return "OTHER_PHYSICAL_OUTCOME"


def interpretation(sham,right):
    return {("DURATION_MATCHED_SHAM_SUCCESS","RIGHT_HISTORY_CANONICAL_FAILURE"):
                "ACTION08_RIGHT_HISTORY_REQUIRED_BEYOND_ELAPSED_TIME_CONTROL",
            ("DURATION_MATCHED_SHAM_CANONICAL_FAILURE","RIGHT_HISTORY_CANONICAL_FAILURE"):
                "EXTRA_ELAPSED_PHYSICS_TIME_SUFFICIENT_TO_REPRODUCE_FAILURE",
            ("DURATION_MATCHED_SHAM_SUCCESS","RIGHT_HISTORY_SUCCESS"):
                "H15_FAILURE_NOT_REPRODUCED_IN_MATCHED_CONTROL"}.get((sham,right),"MATCHED_CONTROL_RESULT_UNRESOLVED")


def analyze(records,integrities):
    if not all(integrities.get(k,{}).get("case_valid") for k in CASES):
        raise history.InvalidCapture("invalid telemetry cannot be physically classified")
    alignments={case:terminal_alignment(records[case]) for case in CASES}
    map_cache={case:maps for case,(maps,_,_) in alignments.items()}
    controls = pair_controls(records)
    physical,states,labels = {},{},{}
    for case in CASES:
        record = records[case]
        integrities[case]["physical_classifier_attempted"]=True
        physical[case] = history.classify_candidate(record,integrities[case])
        labels[case] = case_outcome(case,physical[case]["classification"])
        maps,t0_record,indices = alignments[case]
        physical[case]["T0"]=t0_record
        t0 = t0_record["iteration"]
        states[case] = {"A_before_preparation":state_at(record,record["preparation"]["start"]["iteration"],maps),
            "B_after_preparation_before_Action09":state_at(record,record["preparation"]["end"]["iteration"],maps),
            "C_before_terminal_Action24":state_at(record,t0-1,maps)}
        table = [{**state_at(record,i,maps),"delta_ms":i-t0} for i in indices]
        physical[case]["full_terminal_UP_table"] = table
        physical[case]["relative_iteration_table"] = [r for r in table if r["delta_ms"]<=15]
    paired = []
    for delta in range(-5, min(max(r["delta_ms"] for r in physical[c]["full_terminal_UP_table"]) for c in CASES)+1):
        a,b = (state_at(records[c],physical[c]["T0"]["iteration"]+delta,map_cache[c]) for c in CASES)
        paired.append({"delta_ms":delta,**numerical_difference(a,b)})
    boundaries = {name:numerical_difference(states["CONTROL_SHAM"][name],states["RIGHT_HISTORY"][name]) for name in states["CONTROL_SHAM"]}
    return {"status":"CAPTURED","capture_integrity":integrities,"pair_controls":controls,
        "accepted_H14_H15_bifurcation_reference":{"delta_ms":5,"H14_right_Fn_N":14.082903188300154,"H14_front_Fn_N":0.,
            "H15_right_Fn_N":0.000147934563,"H15_front_Fn_N":29.97257408520229,"source":str(REFERENCE)},
        "case_outcomes":labels,"interpretation":interpretation(labels["CONTROL_SHAM"],labels["RIGHT_HISTORY"]),
        "boundary_comparisons":boundaries,"Action24":physical,"paired_terminal_table":paired,
        "detail_0_to_15_ms":[r for r in paired if 0<=r["delta_ms"]<=15],
        "support_recovery_5_6_7_ms":[r for r in paired if r["delta_ms"] in (5,6,7)],
        "scope":"single matched pair at fixed scenario/reset; no universal causality claim",
        "wheel_phase_causality_claimed":False,"physical_classification_created":True,
        "wheel_phase_caution":"Derived phase is correlated only; drive collision geometry is rotationally symmetric cylinders, and original failure tolerates different common-mode absolute phase.",
        "initial_state_uncertainty":"All initial numeric differences are recorded; within-envelope equivalence is not bit-identical state equality."}


def audit_host1():
    """Read-only diagnostic audit. Never invoke a physical classifier."""
    if not (HOST1/"duration_matched_analysis.json").is_file():
        return {"status":"SOURCE_NOT_AVAILABLE","physical_classification_attempted":False}
    original=json.loads((HOST1/"duration_matched_analysis.json").read_text())
    scenario,seed,_=history.source(ab.DEFAULT_ARTIFACT)
    cases={};reproduced=None
    for case in CASES:
        directory=HOST1/case
        record=json.loads((directory/"case_result.json").read_text())
        events=required_events(record)
        counts={}
        for key,kind in (("support_rows","support_iteration"),("wrench_rows","joint_wrench_sample"),("native_samples",None)):
            raw=record.get(key,[])
            advancing=[row for row in raw if row.get("paused") is False and (kind is None or row.get("kind")==kind)]
            counts[key]={"total_records":len(raw),"advancing_samples":len(advancing),
                "first_iteration":min((row["iteration"] for row in advancing),default=None),
                "last_iteration":max((row["iteration"] for row in advancing),default=None)}
        raw_equal=all(ab._finite_json_rows(directory/name)==record[key] for key,name in
            (("support_rows","continuous_support_iterations.ndjson"),("wrench_rows","joint_transmitted_wrench.ndjson")))
        check=validate(record,case,scenario,seed,None,set(),set())
        if case=="RIGHT_HISTORY":
            try:
                history.validate_candidate(record,plan(case))
            except IndexError as exc:
                reproduced={"source_file":str(Path(history.__file__).resolve()),"function":"validate_candidate",
                    "line":434,"expression":'record.get("events", [{}])[-1]',"requested_index":-1,
                    "actual_list_length":len(events),"reproduced_offline_traceback":traceback.format_exception(type(exc),exc,exc.__traceback__),
                    "explanation":"dict.get default applies only to an absent key, not to the present empty events list"}
        sdf=Path(record["sdf_path"])
        metadata=json.loads(sdf.with_name("metadata.json").read_text())
        cases[case]={"gazebo_launched":record.get("gazebo_launched"),"runtime_sdf_exists":sdf.is_file(),
            "production_sdf_sha256":ab._sha(sdf.with_name("world.sdf")),"scenario_seed":metadata["scenario"]["seed"],
            "reset_seed":record.get("seed"),"persisted_reset_completed":record.get("reset_completed"),
            "base_reset_returned_inferred_from_capture_site":"canonical_reset_pose" in record,
            "recorded_reset_target":record.get("reset_evidence",{}).get("set_pose_response"),
            "canonical_configured_target":history.configured_reset_target(scenario),
            "canonical_reset_pose":record.get("canonical_reset_pose"),"prelude":record.get("preparation"),
            "executed_event_count":len(events),"executed_actions":[{"canonical_index":e.get("canonical_index"),"action":e.get("action")} for e in events],
            "terminal_UP_recorded":any(e.get("canonical_index")==24 and e.get("up_reached") for e in events),
            "stream_counts":counts,"raw_ndjson_matches_case_json":raw_equal,
            "complete_failed_or_completed_case_JSON_written":record.get("case_result_written"),
            "shutdown_completed":record.get("shutdown_completed"),"saved_infrastructure_failure":record.get("infrastructure_failure"),
            "new_diagnostic_validation":check,"physical_classifier_attempted":False,
            "process_log_contains_python_traceback":"Traceback" in sdf.with_name("gazebo.log").read_text()}
    return {"status":"DIAGNOSTIC_CAPTURE_FAILURE","original_Host1_status_preserved":original["status"],
        "physical_classification_attempted":False,"matched_control_interpretation_created":False,"cases":cases,
        "IndexError_reproduction":reproduced,
        "preceding_masked_exception":{"saved_error":"AttributeError: 'NoneType' object has no attribute 'get'",
            "masking_expression":'evidence.get("execution_phases")',"source_file":str(Path(ab.__file__).resolve()),"line":343,
            "structural_cause":"older _execute_captured permits exception.evidence=None, then treats it as a dictionary",
            "original_prelude_exception":"NOT_RETAINED; exact initial trigger cannot be determined from saved Host1 evidence",
            "repair":"None-safe extraction plus original full tracebacks, explicit stage, and immediate base-reset evidence persistence"},
        "duration_match_verified":False,"duration_audit":"SHAM records 200->300, 0.200->0.300 s, 100 iterations/100000000 ns. RIGHT prelude markers are absent; its streams end at reset iteration 200/0.200 s. No matched-duration physical result is inferred.",
        "why_CONTROL_SHAM_outcome_not_printed":"runtime completed, but overall all-cases-valid gate raised before any physical classifier, and CLI prints outcomes only for overall CAPTURED"}


def preflight(artifact_dir, output):
    output = Path(output).resolve();ensure_output(output)
    if (output/"duration_matched_analysis.json").exists() or any(output.glob("*/case_result.json")):
        raise FileExistsError("refusing to overwrite runtime evidence")
    guard = protected_manifest();scenario,seed,_ = history.source(artifact_dir)
    source_audit=audit_host1()
    spec = clock_spec()
    accepted = unique_match(json.loads(REFERENCE.read_text())["executed_histories"]["H15"],lambda e:e.get("canonical_index")==8 and e.get("action")=="right","accepted Action08 reference")
    if accepted["action"] != "right" or round((accepted["end_sim_time_s"]-accepted["start_sim_time_s"])*1e9) != spec["simulation_duration_ns"]:
        raise history.InvalidCapture("accepted Action08 RIGHT duration differs from production one-chunk duration")
    libraries,builds = ab._build_all(output/"observer_builds")
    namespace = uuid4().hex;checks = []
    for case in CASES:
        directory = output/"preflight_sdfs"/case
        production = ab.GazeboWorldGenerator().generate(scenario,directory/"world",closed_loop=True,control_mode="PHYSICS")
        diagnostic,info = ab._instrument_world(production,directory/"observer_outputs",libraries,topic_identity=case+"/"+namespace)
        if round(float(ET.parse(diagnostic).findtext("world/physics/max_step_size"))*1e9) != spec["physics_step_ns"]:
            raise history.InvalidCapture("diagnostic SDF physics step differs from matching precision")
        checks.append({"case":case,"plan":plan(case),"runtime_topic":info["native"]["topic"],"sdf_integrity":info,"diagnostic_sdf":str(diagnostic)})
    if len({v["runtime_topic"] for v in checks}) != 2 or list(output.rglob("*.ndjson")) or list(output.rglob("case_result.json")):
        raise history.InvalidCapture("preflight identity collision or runtime evidence created")
    history.verify_manifest(guard)
    report = {"status":"PREFLIGHT_PASS","gazebo_launched":False,"runtime_evidence_created":False,
        "scenario_seed":42,"reset_seed":seed,"configured_reset_target":history.configured_reset_target(scenario),
        "clock_spec":spec,"cases":checks,"observer_builds":builds,"protected_source_sha256_before_after":guard,
        "runner_sha256":ab._sha(__file__),"wheel_phase_intervention_implemented":False,
        "host1_diagnostic_audit":source_audit}
    write_json(output/"duration_matched_preflight.json",report)
    return report


def run(artifact_dir, output):
    output = Path(output).resolve();ensure_output(output)
    allowed = {"observer_builds","preflight_sdfs","duration_matched_preflight.json"}
    if output.exists() and any(p.name not in allowed for p in output.iterdir()):
        raise FileExistsError("refusing to overwrite runtime or unknown output entries")
    guard = protected_manifest();scenario,seed,_ = history.source(artifact_dir)
    libraries,builds = ab._build_all(output/"observer_builds")
    records,integrities,partitions,topics = {},{},{},{}
    namespace = uuid4().hex;reference = None;previous_end = None
    for case in CASES:
        if records and not records.get("CONTROL_SHAM",{}).get("shutdown_completed"):
            integrities[case] = {"case_valid":False,"invalid_reasons":["SHAM shutdown not confirmed; RIGHT not launched"]}
            break
        directory = output/case;directory.mkdir(parents=True)
        try:
            record = capture(case,scenario,directory,libraries,seed,namespace)
            records[case] = record
            integrity = validate(record,case,scenario,seed,reference,partitions,topics)
            if previous_end is not None and record["wall_start_monotonic_s"]<previous_end:
                integrity["invalid_reasons"].append("fresh-case lifecycle overlaps previous process")
                integrity["case_valid"] = False
            integrities[case] = integrity
            if reference is None:reference=record.get("canonical_reset_pose")
            identity=record.get("runtime_identity",{})
            if identity.get("partition"):partitions[identity["partition"]]=case
            if identity.get("topic"):topics[identity["topic"]]=case
            previous_end=record.get("wall_end_after_shutdown_monotonic_s")
            write_json(directory/"capture_integrity.json",integrity)
        except Exception as exc:
            records.setdefault(case,{"shutdown_completed":False})
            integrities[case] = {"case_valid":False,"invalid_reasons":[type(exc).__name__+": "+str(exc)],
                "physical_classifier_attempted":False,"capture_traceback":traceback.format_exception(type(exc),exc,exc.__traceback__)}
    try:
        history.verify_manifest(guard)
        report = analyze(records,integrities)
    except Exception as exc:
        report = {"status":"CAPTURE_FAILED","capture_integrity":integrities,
            "diagnostic_error":type(exc).__name__+": "+str(exc),"physical_classification_created":False}
    report["case_capture_errors"]={case:{"infrastructure_failure":record.get("infrastructure_failure"),
        "event_error_tracebacks":[e.get("exception") for e in record.get("events",[]) if e.get("exception")]}
        for case,record in records.items() if not integrities.get(case,{}).get("case_valid")}
    report.update(observer_builds=builds,production_modified=False,protected_source_sha256_before_after=guard,
        runner_sha256=ab._sha(__file__),case_result_paths={case:str(output/case/"case_result.json") for case in records},
        wheel_phase_intervention_implemented=False)
    write_json(output/"duration_matched_analysis.json",report)
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir",type=Path,default=ab.DEFAULT_ARTIFACT)
    parser.add_argument("--output",type=Path,default=DEFAULT_OUTPUT)
    parser.add_argument("--preflight-only",action="store_true")
    args=parser.parse_args(argv)
    try:
        report=preflight(args.artifact_dir,args.output) if args.preflight_only else run(args.artifact_dir,args.output)
    except Exception as exc:
        print("CAPTURE_FAILED: "+type(exc).__name__+": "+str(exc));return 1
    if report["status"]=="CAPTURED":
        for case,label in report["case_outcomes"].items():print(case+": "+label)
    print(report["status"]);print("evidence: "+str(args.output))
    if report["status"]=="CAPTURE_FAILED":
        for name in CASES:
            check=report.get("capture_integrity",{}).get(name,{})
            print(name+" runtime: "+("VALID" if check.get("case_valid") else "INVALID")+
                ("; physical classifier attempted, no matched result" if check.get("physical_classifier_attempted") else "; physical classification not attempted"))
        for case,integrity in report.get("capture_integrity",{}).items():
            if not integrity["case_valid"]:print(case+": "+"; ".join(integrity["invalid_reasons"]))
        print(report["diagnostic_error"]);return 1
    if report["status"]=="CAPTURED":print("interpretation: "+report["interpretation"])
    return 0


if __name__=="__main__":
    raise SystemExit(main())
