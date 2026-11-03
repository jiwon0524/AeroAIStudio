#!/usr/bin/env python3
"""Diagnostic-only sequential restoration of the canonical Action24 history.

One Host invocation runs H0..H22 until the first valid persistent failure.
No monotonicity assumption, binary search, production changes or extra stops.
"""
from __future__ import annotations

import argparse
import json
import math
import time
from uuid import uuid4
from aero_ai_studio.gazebo.entity_controller import VELOCITY_DIRECTION_EPSILON
from pathlib import Path
import xml.etree.ElementTree as ET

from tools import diagnose_v07_gazebo_action24_history_ab as ab
from tools.analyze_v07_gazebo_action24_continuous_support import project_force

CANONICAL = tuple("up down up up up down up right left up down left down left right left up up right left left up down up".split())
DEFAULT_PRIOR = ab.ROOT / "validation/v071-host/gazebo-action24-history-restoration-phase3haj-host1"
DEFAULT_OUTPUT = ab.ROOT / "validation/v071-host/gazebo-action24-history-restoration-phase3haj-host2"
# Diagnostic pattern definitions only; never passed to production validation.
FORCE_ZERO_N = 1e-8
RECOVERY_WINDOW_START_MS = 7
MIN_RECOVERY_WINDOW_MS = 50


class InvalidCapture(RuntimeError):
    pass


def write_json(path, value):
    path = Path(path)
    if path.resolve().is_relative_to(DEFAULT_PRIOR.resolve()):
        raise FileExistsError("refusing to modify preserved Host1 evidence")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)
    if json.loads(path.read_text()) != value:
        raise InvalidCapture("incomplete result serialization: " + str(path))


def candidate(k):
    if type(k) is not int or not 0 <= k <= 22:
        raise ValueError("history restoration index must be 0..22")
    start = 23 - k
    return {"name": f"H{k:02d}_from{start:02d}", "restored_preceding_action_count": k,
        "canonical_start_index": start, "prefix": list(CANONICAL[start - 1:22]),
        "actions": list(CANONICAL[start - 1:]),
        "canonical_indices": list(range(start, 25)),
        "terminal_suffix": ["23 DOWN", "production BRAKE_LINEAR", "production stopped contract", "24 UP +0.5"]}


def source(artifact_dir):
    replay = ab.extract_reversal_replay(Path(artifact_dir))
    # The canonical Action24 is in completed episode 1, not the later failed
    # episode returned under failed_episode_saved_prefix.
    actions = (replay.get("completed_episode_actions") or [[]])[0]
    if tuple(actions[:24]) != CANONICAL:
        raise ValueError("saved Stage1 episode-1 actions 1..24 differ from canonical sequence")
    scenario = ab.ScenarioSpec.from_dict(replay["scenario"])
    # Canonical Stage1 episode 1 resets with training_seed + 1 (saved H-AG
    # reset provenance confirms 43). H0 re-establishes the baseline at that
    # same reset seed; accepted H-AI host2 used scenario.seed (42).
    return scenario, int(replay["training_seed"]) + 1, replay


# The production pose refresh accepts samples up to 2 ms old. Production's
# stopped linear/yaw speed epsilon is 0.02. For two independent measurements,
# the conservative relative sampling envelope is 2 * 0.002 * 0.02 = 80 um / urad.
# Full native 3-D speed bounds below make that envelope applicable to Z/tilt,
# rather than assuming the planar stopped contract constrains those axes.
RESET_POSE_MAX_AGE_S = .002
RESET_STOPPED_SPEED = VELOCITY_DIRECTION_EPSILON
RESET_POSITION_ENVELOPE_M = 2 * RESET_POSE_MAX_AGE_S * RESET_STOPPED_SPEED
RESET_ORIENTATION_ENVELOPE_RAD = RESET_POSITION_ENVELOPE_M
RESET_ROUNDING_SLACK = 1e-15


def ensure_new_output(output, prior=None):
    output = Path(output).resolve()
    for protected in (DEFAULT_PRIOR, prior):
        if protected is None:
            continue
        protected = Path(protected).resolve()
        if output == protected or output.is_relative_to(protected) or protected.is_relative_to(output):
            raise FileExistsError("output overlaps preserved source evidence: " + str(protected))


def configured_reset_target(scenario):
    return {"name":"simple_agent", "position":{"x":scenario.start[0]+.5,
        "y":scenario.start[1]+.5,"z":.16},
        "orientation":{"x":0.,"y":0.,"z":0.,"w":1.}}


def quaternion_distance(a, b):
    def q(value):
        result = [value.get(k, 1. if k == "w" else 0.) for k in ("x","y","z","w")]
        if not all(type(v) in (int,float) and math.isfinite(v) for v in result):
            raise InvalidCapture("nonfinite measured reset orientation")
        length = math.sqrt(sum(v*v for v in result))
        if abs(length-1.) > 1e-9:
            raise InvalidCapture("invalid measured reset quaternion")
        return [v/length for v in result]
    a,b = q(a),q(b)
    if sum(x*y for x,y in zip(a,b)) < 0:
        b = [-v for v in b]
    return 4*math.atan2(math.dist(a,b), math.sqrt(sum((x+y)**2 for x,y in zip(a,b))))


def reset_validity(record, scenario, seed, reference_pose=None):
    reasons = []
    configured, measured = {}, {}
    try:
        metadata = json.loads(Path(record["sdf_path"]).with_name("metadata.json").read_text())
        evidence = record["reset_evidence"]
        target = evidence["set_pose_response"]
        expected = configured_reset_target(scenario)
        configured = {"scenario":metadata["scenario"],"scenario_seed":metadata["scenario"]["seed"],
            "reset_seed":record.get("seed"),"target":target.get("payload"),
            "model_identity":metadata.get("agent_entity"),"control_mode":metadata.get("control_mode"),
            "production_sdf_sha256":ab._sha(Path(record["sdf_path"]).with_name("world.sdf")),
            "reset_path":evidence.get("reset_method")}
        if metadata["scenario"] != json.loads(json.dumps(scenario.to_dict())) or metadata["scenario"].get("seed") != 42:
            reasons.append("canonical scenario/scenario seed mismatch")
        if seed != 43 or record.get("seed") != seed or evidence.get("seed") != seed or evidence.get("reset_trace",{}).get("seed") != seed:
            reasons.append("canonical reset seed mismatch")
        if target.get("payload") != expected or evidence.get("reset_trace",{}).get("requested_pose") != expected:
            reasons.append("configured canonical reset target differs")
        if metadata.get("agent_entity") != "simple_agent" or metadata.get("control_mode") != "PHYSICS" or configured["production_sdf_sha256"] != ab.PRODUCTION_HASH:
            reasons.append("canonical model/configuration mismatch")
        if (not record.get("reset_completed") or evidence.get("normal_reset_pass") is not True or
            evidence.get("restart_fallback_used") is not False or evidence.get("reset_method") != "fresh_process_initialization" or
            target.get("accepted") is not True or target.get("response",{}).get("data") is not True):
            reasons.append("production fresh-process reset did not complete normally")
        if not (evidence.get("body_residual_velocity_stopped") is True and evidence.get("odometry_fresh_and_stopped") is True):
            reasons.append("production stopped contract failed")
        pose = record["canonical_reset_pose"]
        trace = evidence["reset_trace"]
        end_time = trace["post_settle_simulation_time"]
        if pose != evidence["pose_after_settle"] or pose != trace["post_settle_body_pose"]:
            reasons.append("measured reset pose provenance disagrees")
        position = [pose[k] for k in ("x","y","z")]
        if not all(type(v) in (int,float) and math.isfinite(v) for v in position):
            raise InvalidCapture("nonfinite measured reset position")
        quaternion_distance(pose["orientation"],expected["orientation"])
        if math.hypot(pose["x"]-expected["position"]["x"],pose["y"]-expected["position"]["y"]) > .02:
            reasons.append("measured reset exceeds production XY reset tolerance")
        # Use the saved reset trace, not record.reset_sim_time: the latter is
        # recorded by the inherited A/B wrapper after prefix execution.
        native = next(r for r in record["native_samples"] if r.get("paused") is False and
            round(r["simulation_time_s"]*1e9) == round(end_time*1e9))
        body = next(l for l in native["links"] if l["expected_scoped_name"] == "simple_agent::body")
        linear = body["linear_velocity_world_m_s"]
        angular = body["angular_velocity_world_rad_s"]
        end_ns = round(end_time*1e9)
        window = [r for r in record["native_samples"] if r.get("paused") is False and
            end_ns-round(RESET_POSE_MAX_AGE_S*1e9) <= round(r["simulation_time_s"]*1e9) <= end_ns]
        expected_times = list(range(end_ns-2_000_000,end_ns+1,1_000_000))
        if [round(r["simulation_time_s"]*1e9) for r in window] != expected_times:
            reasons.append("native reset sampling-envelope window incomplete")
        for sample in window:
            sample_body = next(l for l in sample["links"] if l["expected_scoped_name"] == "simple_agent::body")
            v = sample_body["linear_velocity_world_m_s"]
            w = sample_body["angular_velocity_world_rad_s"]
            if not all(type(x) in (int,float) and math.isfinite(x) for x in v+w):
                raise InvalidCapture("invalid native reset velocity")
            if math.sqrt(sum(x*x for x in v)) > RESET_STOPPED_SPEED or math.sqrt(sum(x*x for x in w)) > RESET_STOPPED_SPEED:
                reasons.append("native 3D reset motion exceeds sampling-envelope speed bound")
                break
        support = next(r for r in record["support_rows"] if r.get("kind") == "support_iteration" and r.get("paused") is False and r["iteration"] == native["iteration"])
        support_state = {}
        for key,value in support["supports"].items():
            fn = 0.
            for contact in value.get("contacts",[]):
                for point in contact.get("points",[]):
                    projected = project_force(point.get("body_1_force_world_n"),point.get("normal_world"))
                    if projected is None:
                        raise InvalidCapture("invalid reset support force")
                    fn += projected["Fn_N"]
            support_state[key] = {"state":value["state"],"Fn_N":fn}
        if set(support_state) != set(ab.support.SUPPORTS) or not all(v["state"] == "VALID_CONTACTS" and v["Fn_N"] > 0 for v in support_state.values()):
            reasons.append("canonical reset ground support not established")
        measured = {"post_reset_pose":trace["post_set_pose_body_pose"],
            "post_reset_sim_time_s":trace["post_set_pose_simulation_time"],
            "post_settle_pose":pose,"post_settle_nominal_sim_time_s":end_time,
            "actual_pose_message_timestamp_s":None,
            "timestamp_note":"Production refresh permits pose samples up to 2 ms old; actual selected Pose_V timestamp was not retained in legacy reset pose fields.",
            "native_iteration":native["iteration"],"native_sim_time_s":native["simulation_time_s"],
            "native_speed_bound_checked_at_sim_times_s":[r["simulation_time_s"] for r in window],
            "native_position_world_m":body["position_world_m"],"native_linear_velocity_world_m_s":linear,
            "native_angular_velocity_world_rad_s":angular,"support_state":support_state,
            "position_envelope_m":RESET_POSITION_ENVELOPE_M,"orientation_envelope_rad":RESET_ORIENTATION_ENVELOPE_RAD}
        if reference_pose is not None:
            deviation = math.dist(position,[reference_pose[k] for k in ("x","y","z")])
            angle = quaternion_distance(pose["orientation"],reference_pose["orientation"])
            measured.update(reference_position_difference_m={k:pose[k]-reference_pose[k] for k in ("x","y","z")},
                reference_position_distance_m=deviation,reference_orientation_distance_rad=angle)
            if deviation > RESET_POSITION_ENVELOPE_M+RESET_ROUNDING_SLACK:
                reasons.append("measured settled reset position outside sampling envelope")
            if angle > RESET_ORIENTATION_ENVELOPE_RAD+RESET_ROUNDING_SLACK:
                reasons.append("measured settled reset orientation outside sampling envelope")
    except (KeyError,TypeError,ValueError,OSError,StopIteration,InvalidCapture) as exc:
        reasons.append("reset evidence incomplete: "+str(exc))
    return {"reset_valid":not reasons,"invalid_reasons":reasons,
        "configured_reset_condition":configured,"measured_reset_state":measured,
        "tolerance_basis":"2 independent pose endpoints * production 2 ms refresh age * 0.02 stopped-speed bound; native full 3D speed independently checked; production XY/reset/stopped checks remain unchanged"}


def evidence_manifest(directory):
    return {str(p.resolve()):ab._sha(p) for p in sorted(Path(directory).rglob("*")) if p.is_file()}


def verify_manifest(manifest):
    if any(not Path(p).is_file() or ab._sha(p) != digest for p,digest in manifest.items()):
        raise InvalidCapture("preserved source evidence changed")


def audit_preserved_candidate(directory, plan, scenario, seed, reference_pose, partitions, topics):
    saved = json.loads((directory/"capture_integrity.json").read_text())
    if not saved.get("case_valid"):
        raise InvalidCapture("original capture was invalid; candidate requires a fresh run")
    record = json.loads((directory/"case_result.json").read_text())
    integrity = validate_candidate(record,plan,partitions,topics)
    reset = reset_validity(record,scenario,seed,reference_pose)
    if not integrity["case_valid"] or not reset["reset_valid"]:
        raise InvalidCapture("preserved candidate failed independent audit: "+"; ".join(integrity["invalid_reasons"]+reset["invalid_reasons"]))
    physical = classify_candidate(record,integrity)
    saved_physical = json.loads((directory/"candidate_analysis.json").read_text())
    if physical["classification"] != saved_physical.get("classification"):
        raise InvalidCapture("preserved physical classification does not reproduce offline")
    if physical["classification"] == "CANONICAL_ACTION24_FAILURE_REPRODUCED":
        raise InvalidCapture("source already contains a reproduced canonical failure; do not search past it")
    compact = {k:v for k,v in physical.items() if k not in ("production_movement_validator","relative_iteration_table","full_terminal_UP_table")}
    compact["production_body_forward_displacement_m"] = physical["production_movement_validator"]["body_forward_displacement"]
    compact["production_movement_valid"] = physical["production_movement_validator"]["valid"]
    compact["final_supports"] = physical["full_terminal_UP_table"][-1]["supports"]
    return {"candidate":plan,"case_result_path":str(directory/"case_result.json"),
        "physical_classification":physical["classification"],"capture_integrity":integrity,
        "reset_audit":reset,"physical_audit":compact,"runtime_identity":record["runtime_identity"],
        "shutdown_end_monotonic_s":record["wall_end_after_shutdown_monotonic_s"]}


def prepare_resume(prior, artifact_dir):
    prior = Path(prior).resolve()
    scenario,seed,_ = source(artifact_dir)
    report = json.loads((prior/"history_restoration_capture.json").read_text())
    if report.get("canonical_actions") != list(CANONICAL) or report.get("reset_seed") != seed:
        raise InvalidCapture("resume source canonical sequence/reset seed mismatch")
    manifest = evidence_manifest(prior)
    h0 = json.loads((prior/candidate(0)["name"]/"case_result.json").read_text())
    reference = h0["canonical_reset_pose"]
    preserved,partitions,topics = [],set(),set()
    resume_index,reason = 0,"no accepted contiguous source candidates"
    for k in range(23):
        plan = candidate(k)
        directory = prior/plan["name"]
        if not directory.is_dir():
            resume_index,reason=k,"candidate not captured in source"
            break
        try:
            summary = audit_preserved_candidate(directory,plan,scenario,seed,reference,partitions,topics)
        except (InvalidCapture,KeyError,ValueError,OSError) as exc:
            resume_index,reason=k,str(exc)
            break
        preserved.append(summary)
        partitions.add(summary["runtime_identity"]["partition"]);topics.add(summary["runtime_identity"]["topic"])
    else:
        resume_index,reason=23,"all source candidates already captured"
    # Even originally invalid cases must not leak transport identities into a
    # fresh Host2 run. They are never promoted to valid/preserved results.
    for path in prior.glob("H*/case_result.json"):
        identity = json.loads(path.read_text()).get("runtime_identity",{})
        if identity.get("partition"):partitions.add(identity["partition"])
        if identity.get("topic"):topics.add(identity["topic"])
    unresolved_reset = None
    if resume_index < 23:
        path = prior/candidate(resume_index)["name"]/"case_result.json"
        if path.is_file():
            unresolved = json.loads(path.read_text())
            unresolved_reset = {"original_capture_status_preserved":"INVALID_OR_UNRESOLVED",
                "promoted_to_valid_capture":False,"new_reset_rule_audit_only":reset_validity(unresolved,scenario,seed,reference)}
    verify_manifest(manifest)
    return {"status":"OFFLINE_SOURCE_AUDIT","source_directory":str(prior),
        "resume_index":resume_index,"resume_candidate":candidate(resume_index)["name"] if resume_index<23 else None,
        "resume_reason":reason,"unresolved_source_reset_audit":unresolved_reset,"preserved_candidates":preserved,"reset_reference_pose":reference,
        "prior_partitions":sorted(partitions),"prior_topics":sorted(topics),
        "source_evidence_sha256":manifest,"runtime_evidence_created":False}


def stream_maps(record):
    streams = {}
    for key, kind in (("support_rows", "support_iteration"),
                      ("wrench_rows", "joint_wrench_sample"), ("native_samples", None)):
        data = [r for r in record.get(key, []) if r.get("paused") is False and
                (kind is None or r.get("kind") == kind)]
        previous = None
        values = {}
        for row in data:
            i = row.get("iteration")
            stamp = row.get("simulation_time_s") if kind is None else row.get("sim_time_ns")
            if type(i) is not int or type(stamp) not in (int, float) or not math.isfinite(stamp) or stamp < 0:
                raise InvalidCapture(key + ": invalid iteration/time")
            ns = round(stamp * 1e9) if kind is None else stamp
            if previous is not None and (i <= previous[0] or ns <= previous[1] or ns-previous[1] != (i-previous[0])*1_000_000):
                raise InvalidCapture(key + ": repeated, nonadvancing or inconsistent iteration/time sample")
            previous = i, ns
            values[i] = row
        if not values:
            raise InvalidCapture(key + ": zero advancing samples")
        streams[key] = values
    return streams


def command_active_t0(record, streams=None):
    maps = streams or stream_maps(record)
    event = record["events"][-1]
    publication = event.get("action_publication", {})
    if (event.get("action") != "up" or publication.get("commanded_twist", {}).get("linear", {}).get("x") != .5 or
        publication.get("action_publish_sequence", -1) <= publication.get("command_publish_sequence_before", -1)):
        raise InvalidCapture("terminal UP has no fresh +0.5 command publication")
    stamp = publication.get("action_command_sim_time")
    if type(stamp) not in (int, float) or not math.isfinite(stamp):
        raise InvalidCapture("terminal UP command time missing")
    ns = round(stamp * 1e9)
    support = maps["support_rows"]
    after = [i for i, row in support.items() if row["sim_time_ns"] > ns]
    if not after:
        raise InvalidCapture("no advancing iteration after terminal UP publication")
    t0 = min(after)
    if t0 - 1 not in support or support[t0 - 1]["sim_time_ns"] != ns:
        raise InvalidCapture("UP publication boundary not bracketed at 1 ms resolution")
    actuation = next((i for i, row in maps["wrench_rows"].items() if i >= t0 and
                      all(row[side].get("actual_velocity_rad_s", 0) > .01 for side in ("left", "right"))), None)
    return {"kind": "COMMAND_ACTIVE_T0", "iteration": t0, "sim_time_ns": support[t0]["sim_time_ns"],
        "publication_sim_time_s": stamp,
        "first_observed_wheel_actuation": {"kind": "FIRST_OBSERVED_WHEEL_ACTUATION", "iteration": actuation,
            "delta_ms": actuation - t0 if actuation is not None else None},
        "resolution_ms": 1, "sub_ms_ordering_claimed": False}


def terminal_table(record, maps=None):
    maps = maps or stream_maps(record)
    t0 = command_active_t0(record, maps)
    start = t0["iteration"]
    end_ns = round(record["events"][-1]["end_sim_time"] * 1e9)
    support, wrench, native = (maps[k] for k in ("support_rows", "wrench_rows", "native_samples"))
    indices = [i for i, row in support.items() if start - 5 <= i and row["sim_time_ns"] <= end_ns]
    if (len(indices) < 6 or support[max(indices)]["sim_time_ns"] != end_ns or
        indices != list(range(start-5,max(indices)+1))):
        raise InvalidCapture("terminal UP observation window incomplete")
    result = []
    for i in indices:
        if i not in wrench or i not in native:
            raise InvalidCapture("terminal UP streams do not overlap at iteration " + str(i))
        sr, wr, nr = support[i], wrench[i], native[i]
        if sr["sim_time_ns"] != wr["sim_time_ns"] or sr["sim_time_ns"] != round(nr["simulation_time_s"] * 1e9):
            raise InvalidCapture("terminal stream simulation times disagree")
        supports = {}
        for key in ab.support.SUPPORTS:
            item = sr["supports"][key]
            if not item.get("component_available") or item["state"] not in ("VALID_CONTACTS", "VALID_EMPTY_CONTACT_SET"):
                raise InvalidCapture("support component unavailable: " + key)
            fn, depths = 0., []
            for contact in item.get("contacts", []):
                if contact["pair_classification"] != "SUPPORT_GROUND":
                    raise InvalidCapture("non-ground contact in terminal support stream")
                for point in contact.get("points", []):
                    projection = project_force(point.get("body_1_force_world_n"), point.get("normal_world"))
                    if projection is None:
                        raise InvalidCapture("invalid support force/normal")
                    fn += projection["Fn_N"]
                    if type(point.get("depth_m")) not in (int,float) or not math.isfinite(point["depth_m"]):
                        raise InvalidCapture("invalid contact depth")
                    depths.append(point["depth_m"])
            supports[key] = {"state": item["state"], "Fn_N": fn, "depth_m": depths}
        links = {l["expected_scoped_name"].split("::")[-1]: l for l in nr["links"]}
        if set(links) != {"body", "left_wheel", "right_wheel"} or not nr.get("all_link_native_velocities_available"):
            raise InvalidCapture("native link velocity incomplete")
        body = links["body"]
        for link in links.values():
            for key in ("position_world_m", "linear_velocity_world_m_s", "angular_velocity_world_rad_s"):
                if len(link[key]) != 3 or not all(type(v) in (int, float) and math.isfinite(v) for v in link[key]):
                    raise InvalidCapture("invalid native link vector: " + key)
        for link in links.values():
            q = link["orientation_world_xyzw"]
            if len(q) != 4 or not all(type(v) in (int,float) and math.isfinite(v) for v in q) or sum(v*v for v in q) < .5:
                raise InvalidCapture("invalid native orientation")
        x, y, z, w = body["orientation_world_xyzw"]
        roll = math.atan2(2 * (w*x+y*z), 1-2*(x*x+y*y))
        pitch = math.asin(max(-1., min(1., 2*(w*y-z*x))))
        yaw = math.atan2(2*(w*z+x*y), 1-2*(y*y+z*z))
        joints = {}
        for side in ("left", "right"):
            value = wr[side]
            if value.get("state") != "VALID_WRENCH" or not value.get("actual_velocity_available"):
                raise InvalidCapture("joint velocity/wrench unavailable: " + side)
            joints[side] = {k: value[k] for k in ("actual_velocity_rad_s", "force_xyz_N", "torque_xyz_N_m")}
            for key, out in (("force_xyz_N", "force_norm_N"), ("torque_xyz_N_m", "torque_norm_N_m")):
                if len(value[key]) != 3 or not all(math.isfinite(v) for v in value[key]):
                    raise InvalidCapture("nonfinite transmitted wrench")
                joints[side][out] = math.sqrt(sum(v*v for v in value[key]))
            if not math.isfinite(value["actual_velocity_rad_s"]):
                raise InvalidCapture("nonfinite wheel velocity")
        result.append({"delta_ms": i-start, "iteration": i, "sim_time_ns": sr["sim_time_ns"],
            "supports": supports, "total_Fn_N": sum(v["Fn_N"] for v in supports.values()),
            "joint_transmitted_wrench": joints, "chassis_position_world_m": body["position_world_m"],
            "chassis_orientation_world_xyzw": body["orientation_world_xyzw"],
            "roll_rad": roll, "pitch_rad": pitch, "yaw_rad": yaw,
            "longitudinal_velocity_m_s": body["linear_velocity_world_m_s"][0]*math.cos(yaw)+body["linear_velocity_world_m_s"][1]*math.sin(yaw),
            "vertical_velocity_m_s": body["linear_velocity_world_m_s"][2],
            "native_wheel_links": {side: {key: links[side+"_wheel"][key] for key in
                ("position_world_m", "orientation_world_xyzw", "linear_velocity_world_m_s", "angular_velocity_world_rad_s")} for side in ("left", "right")}})
    # Reject invalid quaternion/depth values before any physical classification.
    json.dumps(result, allow_nan=False)
    return t0, result


def validate_candidate(record, plan, seen_partitions=(), seen_topics=()):
    integrity = ab.validate_case(record)
    reasons = list(integrity["invalid_reasons"])
    identity = record.get("runtime_identity", {})
    if not identity.get("partition") or identity["partition"] in seen_partitions:
        reasons.append("missing or stale process partition")
    suffix = "/"+plan["name"]+("/"+record["runtime_namespace"] if record.get("runtime_namespace") else "")
    if not identity.get("topic") or identity["topic"] in seen_topics or not identity["topic"].endswith(suffix):
        reasons.append("missing, stale or wrong candidate native topic")
    if (not record.get("prefix_completed") or [e.get("canonical_index") for e in record.get("events", [])] != plan["canonical_indices"] or
        [e.get("action") for e in record.get("events", [])] != plan["actions"]):
        reasons.append("intended canonical history did not complete up to terminal UP")
    phases = ab._find_phase_evidence(record.get("events", [{}])[-1].get("execution_evidence", {}))
    brake = next((p for p in phases if p.get("phase") == "BRAKE_LINEAR"), {})
    acquire = next((p for p in phases if p.get("phase") == "ACQUIRE_LINEAR"), {})
    if not (brake.get("completion_result") is True and acquire.get("start_sim_time") is not None and
            brake.get("end_sim_time") == acquire.get("start_sim_time")):
        reasons.append("terminal production BRAKE_LINEAR/stopped/ACQUIRE_LINEAR ordering not proven")
    sdf = record.get("sdf_path")
    try:
        if not sdf or ab._sha(Path(sdf).with_name("world.sdf")) != ab.PRODUCTION_HASH:
            reasons.append("runtime production SDF hash mismatch")
        if ab._sha(sdf) != record["observer_sdf"]["diagnostic_sdf_sha256"]:
            reasons.append("runtime diagnostic SDF hash mismatch")
        root = ET.parse(sdf).getroot()
        for plugin_name in ("ContinuousSupportObserver", "JointTransmittedWrenchObserver", "NativeLinkVelocityObserver"):
            plugin = root.find(f"world/plugin[@name='aero_diagnostic::{plugin_name}']")
            if plugin is None or not Path(plugin.get("filename", "")).is_file():
                reasons.append("runtime observer plugin/library missing: " + plugin_name)
        if root.findtext("world/plugin[@name='aero_diagnostic::NativeLinkVelocityObserver']/topic") != identity.get("topic"):
            reasons.append("runtime SDF topic differs from current subscription")
        if not record.get("case_result_path") or json.loads(Path(record["case_result_path"]).read_text()) != record:
            reasons.append("complete candidate serialization readback failed")
        t0, table = terminal_table(record)
        if not t0["first_observed_wheel_actuation"]["iteration"]:
            reasons.append("positive terminal UP wheel actuation never observed")
    except (KeyError, ValueError, TypeError, OSError, InvalidCapture) as exc:
        reasons.append(str(exc))
    return {**integrity, "case_valid": not reasons, "invalid_reasons": reasons}


def find_movement_validator(event):
    def search(value):
        if isinstance(value, dict):
            if (type(value.get("valid")) is bool and "body_forward_displacement" in value and
                    value.get("expected_distance", 0) > 0 and abs(value.get("expected_yaw", 0)) < 1e-9):
                return value
            for child in value.values():
                found = search(child)
                if found is not None:
                    return found
        elif isinstance(value, list):
            for child in value:
                found = search(child)
                if found is not None:
                    return found
        return None
    # Failure evidence is authoritative; previous successful DOWN telemetry
    # may still be retained in gazebo_dqn_training when terminal UP throws.
    for value in (event.get("exception"), event.get("execution_evidence"), event.get("telemetry")):
        found = search(value)
        if found is not None:
            return found
    raise InvalidCapture("terminal production physical movement validator missing")


def classify_candidate(record, integrity):
    if not integrity.get("case_valid"):
        raise InvalidCapture("invalid telemetry cannot receive a physical classification")
    t0, table = terminal_table(record)
    validator = find_movement_validator(record["events"][-1])
    tail = [r for r in table if r["delta_ms"] >= RECOVERY_WINDOW_START_MS]
    if len(tail) < MIN_RECOVERY_WINDOW_MS:
        raise InvalidCapture("insufficient terminal recovery observation duration")
    before = next(r for r in table if r["delta_ms"] == -1)
    final = table[-1]
    yaw = before["yaw_rad"]
    delta = [b-a for a,b in zip(before["chassis_position_world_m"], final["chassis_position_world_m"])]
    forward = delta[0]*math.cos(yaw)+delta[1]*math.sin(yaw)
    minimum = max(.01, abs(validator["expected_distance"])*.25)
    wheel_positive = all(all(r["joint_transmitted_wrench"][side]["actual_velocity_rad_s"] > .01 for side in ("left", "right")) for r in tail)
    persistent_zero = all(all(r["supports"][side+"_wheel"]["Fn_N"] <= FORCE_ZERO_N for side in ("left", "right")) for r in tail)
    left_empty = all(r["supports"]["left_wheel"]["state"] == "VALID_EMPTY_CONTACT_SET" for r in tail)
    caster_borne = all(r["total_Fn_N"] > 0 and
        (r["supports"]["front_caster"]["Fn_N"]+r["supports"]["rear_caster"]["Fn_N"]) >= .9*r["total_Fn_N"] for r in tail)
    recovery_tail = tail[-20:]
    recovered = all(all(r["supports"][side+"_wheel"]["Fn_N"] > FORCE_ZERO_N for side in ("left", "right")) for r in recovery_tail)
    first_sustained_recovery = next((r["delta_ms"] for j,r in enumerate(tail)
        if all(all(x["supports"][side+"_wheel"]["Fn_N"] > FORCE_ZERO_N for side in ("left", "right")) for x in tail[j:])), None)
    collision = validator.get("collision_may_block_motion") is True or record["events"][-1].get("result_reason") == "collision"
    movement_failed = (validator["valid"] is False and validator.get("world_direction_raw_ok") is False and
                       validator["body_forward_displacement"] < minimum-1e-9 and forward < minimum-1e-9)
    success = validator["valid"] is True and validator["body_forward_displacement"] >= minimum-1e-9 and forward >= minimum-1e-9
    if wheel_positive and movement_failed and persistent_zero and left_empty and caster_borne and not collision:
        classification = "CANONICAL_ACTION24_FAILURE_REPRODUCED"
    elif wheel_positive and success and recovered and not collision:
        classification = "SUPPORT_RECOVERY_AND_TRANSLATION_SUCCESS"
    else:
        classification = "OTHER_PHYSICAL_OUTCOME"
    return {"classification": classification, "T0": t0,
        "production_movement_validator": validator, "production_minimum_forward_translation_m": minimum,
        "native_body_forward_translation_m": forward, "wheel_rotation_positive": wheel_positive,
        "persistent_drive_Fn_zero": persistent_zero, "persistent_left_empty_contact_set": left_empty,
        "caster_borne_support": caster_borne, "sustained_drive_support_recovered": recovered,
        "first_sustained_drive_recovery_delta_ms": first_sustained_recovery,
        "success_support_tail_samples": 20,
        "collision": collision, "recovery_window_ms": [tail[0]["delta_ms"],tail[-1]["delta_ms"]],
        "diagnostic_pattern_definition": {"force_zero_tolerance_N": FORCE_ZERO_N,
            "window_start_ms": RECOVERY_WINDOW_START_MS, "minimum_window_samples": MIN_RECOVERY_WINDOW_MS,
            "reference_pattern": "accepted H-AG Host2: persistent LEFT empty contact set, RIGHT zero Fn, caster-borne load, wheel rotation without required physical translation",
            "production_thresholds_modified": False},
        "relative_iteration_table": [r for r in table if -5 <= r["delta_ms"] <= 15],
        "full_terminal_UP_table": table}


def capture_candidate(plan, scenario, output, libraries, seed, runtime_namespace=None):
    ensure_new_output(output)
    from aero_ai_studio.training import gazebo_physics
    original = gazebo_physics.GazeboPhysicsTrainingEnvironment
    original_instrument = ab._instrument_world
    runtime_namespace = runtime_namespace or uuid4().hex
    def instrument(production, directory, libs, topic_identity=None):
        return original_instrument(production,directory,libs,topic_identity=plan["name"]+"/"+runtime_namespace)
    prefix_events = []
    state = {"prefix_completed": False}

    class PrefixEnvironment(original):
        def reset(self, selected_seed=None):
            observation = super().reset(selected_seed)
            state["canonical_reset_pose"] = dict(self.env.pose)
            for index, action in zip(plan["canonical_indices"], plan["prefix"]):
                event = ab._execute_captured(self, action, f"CANONICAL_ACTION_{index:02d}")
                event["canonical_index"] = index
                prefix_events.append(event)
                if event.get("exception") or event.get("terminated"):
                    raise InvalidCapture(f"canonical prefix action {index} {action} did not complete: {event.get('exception') or event.get('result_reason')}")
            state["prefix_completed"] = True
            return observation

    started = time.monotonic()
    gazebo_physics.GazeboPhysicsTrainingEnvironment = PrefixEnvironment
    ab._instrument_world = instrument
    try:
        record = ab._run_case(plan["name"], True, scenario, output/"world", output, libraries, seed)
    finally:
        gazebo_physics.GazeboPhysicsTrainingEnvironment = original
        ab._instrument_world = original_instrument
    for index, event in zip((23,24), record["events"]):
        event["canonical_index"] = index
    record.update(state)
    record["events"] = prefix_events + record["events"]
    record["candidate"] = plan
    record["runtime_namespace"] = runtime_namespace
    reset = reset_validity(record,scenario,seed)
    record["configured_reset_condition"] = reset["configured_reset_condition"]
    record["measured_reset_state"] = reset["measured_reset_state"]
    record["case_result_path"] = str(output/"case_result.json")
    record["wall_start_monotonic_s"] = started
    record["wall_end_after_shutdown_monotonic_s"] = time.monotonic()
    write_json(output/"case_result.json", record)
    return record


def preflight(artifact_dir, output, resume_from=None):
    output = Path(output).resolve()
    ensure_new_output(output,resume_from)
    resume = prepare_resume(resume_from,artifact_dir) if resume_from else None
    start = resume["resume_index"] if resume else 0
    namespace = uuid4().hex
    if (output/"history_restoration_capture.json").exists() or any(output.glob("H*/case_result.json")):
        raise FileExistsError("refusing to preflight over runtime evidence")
    scenario, seed, _ = source(artifact_dir)
    libraries, builds = ab._build_all(output/"observer_builds")
    sdf_checks = []
    for k in range(start,23):
        plan = candidate(k)
        directory = output/"preflight_sdfs"/plan["name"]
        production = ab.GazeboWorldGenerator().generate(scenario, directory/"world", closed_loop=True, control_mode="PHYSICS")
        diagnostic, info = ab._instrument_world(production, directory/"observer_outputs", libraries, topic_identity=plan["name"]+"/"+namespace)
        sdf_checks.append({"candidate":plan,"runtime_topic":info["native"]["topic"],
            "diagnostic_sdf":str(diagnostic),"sdf_integrity":info})
    if len({s["runtime_topic"] for s in sdf_checks}) != 23-start:
        raise InvalidCapture("preflight candidate topic identities collide")
    if list(output.rglob("*.ndjson")) or list(output.rglob("case_result.json")):
        raise InvalidCapture("preflight unexpectedly created runtime evidence")
    report = {"status":"PREFLIGHT_PASS","gazebo_launched":False,"runtime_evidence_created":False,
        "scenario_seed":scenario.seed,"reset_seed":seed,"canonical_actions":list(CANONICAL),
        "source_action_history":"saved completed Stage1 episode 1 actions 1..24",
        "seed_policy":"canonical Stage1 episode-1 reset seed = training_seed + 1 for every fresh-process candidate; H0 is rechecked; accepted H-AI host2 reset seed was 42",
        "search":"sequential from audited resume point through H22; stop first reproduced failure; no monotonicity or global-minimum claim",
        "diagnostic_runner_sha256":ab._sha(__file__),"reused_ab_runner_sha256":ab._sha(ab.__file__),
        "resume_index":start,"resume_candidate":candidate(start)["name"] if start<23 else None,
        "runtime_namespace":namespace,"configured_reset_target":configured_reset_target(scenario),
        "reset_position_envelope_m":RESET_POSITION_ENVELOPE_M,"reset_orientation_envelope_rad":RESET_ORIENTATION_ENVELOPE_RAD,
        "observer_builds":builds,"candidates":sdf_checks,"production_sdf_sha256_expected":ab.PRODUCTION_HASH}
    if resume:
        verify_manifest(resume["source_evidence_sha256"])
        write_json(output/"resume_audit.json",resume)
    write_json(output/"history_restoration_preflight.json",report)
    return report


def run(artifact_dir, output, resume_from=None):
    output = Path(output).resolve()
    ensure_new_output(output,resume_from)
    allowed = {"observer_builds","preflight_sdfs","history_restoration_preflight.json","resume_audit.json"}
    if output.exists() and any(p.name not in allowed for p in output.iterdir()):
        raise FileExistsError("refusing to overwrite runtime or unknown output entries")
    scenario, seed, _ = source(artifact_dir)
    libraries, builds = ab._build_all(output/"observer_builds")
    resume = prepare_resume(resume_from,artifact_dir) if resume_from else None
    start = resume["resume_index"] if resume else 0
    summaries = []
    partitions = set(resume["prior_partitions"]) if resume else set()
    topics = set(resume["prior_topics"]) if resume else set()
    report = {"status":"CAPTURE_FAILED","candidates":summaries,"canonical_actions":list(CANONICAL),
        "reset_seed":seed,"diagnostic_runner_sha256":ab._sha(__file__),
        "reused_ab_runner_sha256":ab._sha(ab.__file__),"observer_builds":builds,"shortest_tested_reproducing_history":None,
        "global_minimum_claimed":False,"monotonicity_assumed":False,"production_modified":False}
    report.update(resume_index=start,resume_candidate=candidate(start)["name"] if start<23 else None,
        preserved_candidates=resume["preserved_candidates"] if resume else [],
        resume_source=resume["source_directory"] if resume else None,runtime_namespace=uuid4().hex)
    if resume:
        write_json(output/"resume_audit.json",resume)
    print("resume: "+str(report["resume_candidate"])+"; preserved candidates: "+str(start),flush=True)
    prior_end = None
    reset_reference = resume["reset_reference_pose"] if resume else None
    for k in range(start,23):
        plan = candidate(k)
        directory = output/plan["name"]
        directory.mkdir(parents=True)
        try:
            record = capture_candidate(plan, scenario, directory, libraries, seed, runtime_namespace=report["runtime_namespace"])
            integrity = validate_candidate(record, plan, partitions, topics)
            reset = reset_validity(record,scenario,seed,reset_reference)
            integrity["reset_validation"] = reset
            if not reset["reset_valid"]:
                integrity["case_valid"] = False
                integrity["invalid_reasons"].extend(reset["invalid_reasons"])
            elif reset_reference is None:
                reset_reference = record["canonical_reset_pose"]
            if prior_end is not None and record["wall_start_monotonic_s"] < prior_end:
                integrity["case_valid"] = False
                integrity["invalid_reasons"].append("previous process shutdown did not precede current candidate")
            summary = {"candidate":plan,"case_result_path":str(directory/"case_result.json"),"capture_integrity":integrity}
            summaries.append(summary)
            write_json(directory/"capture_integrity.json",integrity)
            if not integrity["case_valid"]:
                raise InvalidCapture("; ".join(integrity["invalid_reasons"]))
            identity = record["runtime_identity"]
            partitions.add(identity["partition"]);topics.add(identity["topic"])
            prior_end = record["wall_end_after_shutdown_monotonic_s"]
            physical = classify_candidate(record, integrity)
            write_json(directory/"candidate_analysis.json",physical)
            summary["physical_classification"] = physical["classification"]
            print(plan["name"]+": "+physical["classification"],flush=True)
            if physical["classification"] == "CANONICAL_ACTION24_FAILURE_REPRODUCED":
                report["shortest_tested_reproducing_history"] = plan
                report["search_status"] = "FIRST_REPRODUCING_CANDIDATE_FOUND"
                break
        except Exception as exc:
            report["diagnostic_error"] = {"candidate":plan["name"],"type":type(exc).__name__,"message":str(exc)}
            write_json(output/"history_restoration_capture.json",report)
            return report
        write_json(output/"history_restoration_capture.json",report)
    if resume:
        verify_manifest(resume["source_evidence_sha256"])
    report["status"] = "CAPTURED"
    report.setdefault("search_status","ALL_23_CANDIDATES_CAPTURED_NO_MATCHING_FAILURE")
    write_json(output/"history_restoration_capture.json",report)
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir",type=Path,default=ab.DEFAULT_ARTIFACT)
    parser.add_argument("--output",type=Path,default=DEFAULT_OUTPUT)
    parser.add_argument("--preflight-only",action="store_true")
    parser.add_argument("--resume-from",type=Path,help="read-only source; independently audit accepted contiguous candidates and resume earliest unresolved candidate")
    args=parser.parse_args(argv)
    try:
        kwargs = {"resume_from":args.resume_from} if args.resume_from else {}
        report=preflight(args.artifact_dir,args.output,**kwargs) if args.preflight_only else run(args.artifact_dir,args.output,**kwargs)
    except Exception as exc:
        print("CAPTURE_FAILED: "+type(exc).__name__+": "+str(exc));return 1
    print(report["status"])
    if args.preflight_only:
        print("resume: "+str(report.get("resume_candidate")))
    print("evidence: "+str(args.output))
    if report["status"]=="CAPTURE_FAILED":
        print(json.dumps(report.get("diagnostic_error")));return 1
    if not args.preflight_only:
        print("search: "+report["search_status"])
        if report["shortest_tested_reproducing_history"]:
            plan=report["shortest_tested_reproducing_history"]
            print("shortest tested: "+plan["name"]+" "+" -> ".join(a.upper() for a in plan["actions"]))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
