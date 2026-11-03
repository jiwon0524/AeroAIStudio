#!/usr/bin/env python3
"""Capture actual Gazebo body and wheel trajectories for ROTATION_TO_LINEAR."""
from __future__ import annotations

import argparse
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aero_ai_studio.core.storage import write_json
from aero_ai_studio.gazebo.entity_controller import summarize_world_pose_history
from aero_ai_studio.gazebo.environment import GazeboEnvironment
from aero_ai_studio.simulation.action_mapping import classify_physics_command_transition
from aero_ai_studio.training.gazebo_dqn import dqn_validation_scenario


ACTION_SEQUENCE = ["right", "right", "right", "down", "down", "down", "down"]
TARGET_TRANSITION = "ROTATION_TO_LINEAR"


def _sufficient(summary):
    return bool(summary and summary.get("world_pose_history_available") is True and
        summary.get("world_pose_history_fresh") is True and
        summary.get("world_pose_history_dense_enough") is True and
        int(summary.get("world_pose_sample_count", 0)) >= 3 and
        int(summary.get("world_velocity_sample_count", 0)) >= 2 and
        int(summary.get("world_angular_velocity_sample_count", 0)) >= 2)


def _signed_yaw_delta(before, after):
    delta=float(after["yaw"])-float(before["yaw"])
    return math.atan2(math.sin(delta), math.cos(delta))


def _action_collision(entry):
    result=entry.get("result") or {}
    validation=entry.get("pose_validation") or {}
    return bool("collision" in str(result.get("reason", "")) or
        entry.get("contact_event") is not None or
        validation.get("collision_may_block_motion") is True or
        validation.get("contact_blocked_world_motion") is True)


def _fixed_interval_ok(entry):
    step=entry.get("step_evidence") or {}
    actual_delta=float(entry.get("after_simulation_time",0.))-float(entry.get("before_simulation_time",0.))
    return bool(step.get("iteration_delta")==100 and
        step.get("expected_iteration_delta")==100 and abs(actual_delta-.1)<=.002)


def _trajectory_evidence(actions, history, summary, cursor, start_time, end_time):
    target_index=next((i for i,row in enumerate(actions)
        if (row.get("action_transition") or {}).get("command_mode_transition")==TARGET_TRANSITION),None)
    target=None if target_index is None else actions[target_index]
    if target is None:
        return {"target_transition_found":False,"target_transition_index":None,
                "world_pose_history":history,"world_pose_history_summary":summary,
                "world_pose_history_sufficient":False}
    transition=target.get("action_transition") or {}
    prior=actions[target_index-1] if target_index>0 else None
    prior_transition={} if prior is None else (prior.get("action_transition") or {})
    local_history=transition.get("world_pose_history") or []
    local_summary=transition.get("world_pose_history_summary")
    previous_command=transition.get("previous_action_twist")
    requested=transition.get("commanded_twist")
    detected=classify_physics_command_transition(previous_command,requested)

    body_linear=list(summary.get("world_forward_velocity_samples",())) if summary else []
    body_angular=list(summary.get("world_angular_velocity_samples",())) if summary else []
    target_time=transition.get("action_command_sim_time")
    requested_backward_time=next((float(sample["simulation_timestamp"])
        for sample in body_linear if target_time is not None and
        float(sample["simulation_timestamp"])>=float(target_time)-1e-9 and
        float(sample["forward_velocity"]) < -.02),None)

    odometry=[]
    for action in actions:
        t=action.get("action_transition") or {}
        odometry.extend(t.get("odometry_history") or [])
        for key in ("odometry_before","odometry_after"):
            sample=t.get(key)
            if sample:
                odometry.append({"timestamp":sample.get("timestamp"),
                    "linear_x":sample.get("linear_x"),"angular_z":sample.get("angular_z")})
    odometry=[row for row in odometry if row.get("timestamp") is not None]
    odometry.sort(key=lambda row:float(row["timestamp"]))
    dedup=[]
    for row in odometry:
        if dedup and abs(float(row["timestamp"])-float(dedup[-1]["timestamp"]))<1e-9:
            dedup[-1]=row
        else:
            dedup.append(row)

    post_actions=actions[target_index:]
    target_before=target.get("before_pose") or {}
    final_pose=(actions[-1].get("after_pose") or {}) if actions else {}
    yaw_after_transition=(_signed_yaw_delta(target_before,final_pose)
        if "yaw" in target_before and "yaw" in final_pose else None)
    forward_after_transition=None
    if all(k in target_before for k in ("x","y","yaw")) and all(k in final_pose for k in ("x","y")):
        dx=float(final_pose["x"])-float(target_before["x"])
        dy=float(final_pose["y"])-float(target_before["y"])
        forward_after_transition=dx*math.cos(float(target_before["yaw"]))+dy*math.sin(float(target_before["yaw"]))

    return {
        "target_transition_found":True,"target_transition_index":target_index,
        "target_transition_classification":detected,
        "target_transition_classification_matches":detected==TARGET_TRANSITION,
        "pose_cursor_sequence_before_rotation":cursor,
        "history_start_simulation_time":float(start_time),
        "history_end_simulation_time":float(end_time),
        "command_transition_timestamp":transition.get("action_command_sim_time"),
        "previous_action":None if prior is None else prior.get("action"),
        "previous_action_twist":previous_command,
        "requested_action":target.get("action"),"requested_twist":requested,
        "rotation_before_transition":{
            "action":None if prior is None else prior.get("action"),
            "body_history_summary":prior_transition.get("world_pose_history_summary"),
            "odometry_before":prior_transition.get("odometry_before"),
            "odometry_after":prior_transition.get("odometry_after")},
        "target_action_body_history":local_history,
        "target_action_body_history_summary":local_summary,
        "body_forward_velocity_history":body_linear,
        "body_angular_velocity_history":body_angular,
        "first_significant_requested_backward_body_velocity_time":requested_backward_time,
        "first_significant_requested_backward_velocity_mps":None if requested_backward_time is None else next(
            float(s["forward_velocity"]) for s in body_linear
            if abs(float(s["simulation_timestamp"])-requested_backward_time)<1e-9),
        "wheel_odometry_history":dedup,
        "world_body_forward_displacement_after_transition":forward_after_transition,
        "world_body_signed_yaw_delta_after_transition":yaw_after_transition,
        "post_transition_actions":[row.get("action") for row in post_actions],
        "world_pose_history":history,"world_pose_history_summary":summary,
        "world_pose_history_sufficient":_sufficient(summary) and _sufficient(local_summary),
        "timestamps_ordered":all(float(b["simulation_timestamp"])>=float(a["simulation_timestamp"])
            for a,b in zip(history,history[1:])),
    }


def finalize_capture_status(report):
    actions=report.get("actions",[])
    report["endpoint_evidence_captured"]=bool(actions) and all(
        row.get("before_pose") is not None and row.get("after_pose") is not None and
        row.get("action_transition") is not None for row in actions)
    target=next((row for row in actions if
        (row.get("action_transition") or {}).get("command_mode_transition")==TARGET_TRANSITION),None)
    report["target_transition_found"]=target is not None
    report["world_pose_history_captured"]=bool(report.get("trajectory",{}).get("world_pose_history"))
    report["world_pose_history_sufficient"]=bool(
        report.get("trajectory",{}).get("world_pose_history_sufficient"))
    report["fixed_physics_intervals_valid"]=bool(actions) and all(_fixed_interval_ok(row) for row in actions)
    report["collision_free_sample"]=not any(_action_collision(row) for row in actions)
    if target is None:
        report["status"]="TARGET_TRANSITION_NOT_FOUND"
    elif not report["fixed_physics_intervals_valid"]:
        report["status"]="INVALID_PHYSICS_INTERVAL_EVIDENCE"
    elif not report["collision_free_sample"]:
        report["status"]="COLLISION_SAMPLE_REJECTED"
    elif not report["world_pose_history_sufficient"]:
        report["status"]="CAPTURED_WITH_INSUFFICIENT_POSE_HISTORY"
    elif (target.get("pose_validation") or {}).get("valid") is False:
        report["status"]="CAPTURED_WITH_VALIDATOR_FAILURE"
    else:
        report["status"]="CAPTURED"
    return report


def run_diagnostic(output:Path,*,gui=False,env_factory=None):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    if env_factory is None:
        env_factory=GazeboEnvironment
    report={"schema_version":"0.7.1",
        "diagnostic":"Gazebo PHYSICS rotation-to-backward-linear actual body trajectory",
        "status":"NOT_STARTED","control_mode":"PHYSICS",
        "action_sequence":list(ACTION_SEQUENCE),"target_transition":TARGET_TRANSITION,
        "target_requested_action":"down",
        "target_requested_twist":{"linear":{"x":-.5},"angular":{"z":0.}},
        "rotation_command_twist":{"linear":{"x":0.},"angular":{"z":-.8}},
        "physics_interval_iterations":100,"physics_interval_seconds":.1,
        "command_mode":"existing GazeboEnvironment.step PHYSICS path",
        "dqn_used":False,"training_used":False,"production_validator_changed":False,
        "actions":[]}
    env=None
    try:
        env=env_factory(dqn_validation_scenario(),max_steps=len(ACTION_SEQUENCE),
            root=output/"worlds",gui=gui,control_mode="PHYSICS",max_sensor_age_ms=20,
            allow_geometric_fallback=False,capture_world_pose_history=True)
        launch=env.launch()
        if not launch.get("available",True) or env.injected or env.control_mode!="PHYSICS":
            raise RuntimeError("Diagnostic requires actual Gazebo PHYSICS transport")
        env.reset(seed=42)
        process=env.manager.status()
        pose_topic=env.controller.pose_topic
        cursor=env.transport.cursor(pose_topic)
        start_time=float(env.stepper.time)
        report.update(status="RUNNING",actual_world=env.world_name,
            process=process,partition=env.manager.partition,
            reset_initialization=dict(env.initialization_checks),
            pose_topic_contract={"topic":pose_topic,"message_type":"gz.msgs.Pose_V",
                "timestamp_source":"Pose_V.header.stamp simulation time; contained Pose.header.stamp fallback",
                "history_mode":"buffered actual Gazebo Pose_V frames; no interpolation"},
            pose_cursor_sequence_before_rotation=cursor,
            rotation_start_simulation_time=start_time)
        for index,action in enumerate(ACTION_SEQUENCE):
            before_pose=dict(env.pose);before_time=float(env.stepper.time)
            entry={"index":index,"action":action,"before_pose":before_pose,
                "before_simulation_time":before_time}
            try:
                result=env.step(action)
                entry["result"]={"reward":result.reward,"terminated":result.terminated,
                    "truncated":result.truncated,"reason":result.reason}
            except Exception as error:
                validation=env.telemetry.get("pose_validation")
                entry["exception"]={"type":type(error).__name__,"message":str(error)}
                entry["exception_kind"]=("validator_failure" if isinstance(validation,dict) and
                    validation.get("valid") is False else "infrastructure_failure")
            transition=env.telemetry.get("action_transition")
            entry["action_transition"]=transition
            entry["pose_validation"]=env.telemetry.get("pose_validation")
            entry["after_pose"]=dict(env.pose) if env.pose is not None else None
            entry["after_simulation_time"]=float(env.stepper.time)
            entry["step_evidence"]=dict(getattr(env.stepper,"last_verification",{}))
            entry["fixed_physics_interval_valid"]=_fixed_interval_ok(entry)
            entry["contact_event"]=(None if getattr(env,"collision_event",None) is None else
                env.collision_event.to_dict())
            entry["commanded_twist"]=None if transition is None else transition.get("commanded_twist")
            entry["world_forward_displacement"]=None
            entry["signed_yaw_delta"]=None
            if entry["after_pose"] is not None:
                dx=entry["after_pose"]["x"]-before_pose["x"]
                dy=entry["after_pose"]["y"]-before_pose["y"]
                entry["world_forward_displacement"]=dx*math.cos(before_pose["yaw"])+dy*math.sin(before_pose["yaw"])
                entry["signed_yaw_delta"]=_signed_yaw_delta(before_pose,entry["after_pose"])
            report["actions"].append(entry)
            if entry.get("exception_kind")=="infrastructure_failure":
                report["error"]=entry["exception"]
                break
            if entry.get("result",{}).get("terminated") or _action_collision(entry):
                break
            # A strict validator failure is recorded but does not erase the actual
            # sample. Continue only the bounded diagnostic sequence on the same process.

        end_time=float(env.stepper.time)
        history=env.controller.pose_history_after(cursor,start_time,end_time)
        summary=summarize_world_pose_history(history,start_time,end_time)
        report["trajectory"]=_trajectory_evidence(report["actions"],history,summary,
            cursor,start_time,end_time)
        report["final_process"]=env.manager.status()
        report["process_alive_at_end"]=bool(report["final_process"].get("available",True))
    except Exception as error:
        report.update(status="INFRASTRUCTURE_FAILURE",
            error={"type":type(error).__name__,"message":str(error)})
    finally:
        if env is not None:
            try:
                env.close();report["shutdown"]="PASS"
            except Exception as error:
                report["shutdown"]="FAIL";report["shutdown_error"]=str(error)
        if report.get("status")!="INFRASTRUCTURE_FAILURE":
            finalize_capture_status(report)
        report["evidence_file"]=str(output/"rotation_to_linear_diagnostic.json")
        write_json(output/"rotation_to_linear_diagnostic.json",report)
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--gui",action="store_true")
    args=parser.parse_args(argv)
    report=run_diagnostic(args.output,gui=args.gui)
    print("rotation-to-linear diagnostic: "+str(report.get("status")))
    print("target transition/body history sufficient: "+
        f"{report.get('target_transition_found')}/{report.get('world_pose_history_sufficient')}")
    print("evidence: "+report["evidence_file"])
    return 0 if (report.get("target_transition_found") and report.get("world_pose_history_sufficient")
        and report.get("collision_free_sample") and report.get("fixed_physics_intervals_valid")) else 1


if __name__=="__main__":
    raise SystemExit(main())
