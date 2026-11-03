#!/usr/bin/env python3
"""Check whether pre-reset PHYSICS quiescence makes MODEL_ONLY safe."""
from __future__ import annotations

import argparse
import importlib
import json
import math
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from aero_ai_studio.core.storage import write_json
from aero_ai_studio.gazebo.diagnostics import gazebo_status
from aero_ai_studio.gazebo.environment import GazeboEnvironment
from aero_ai_studio.gazebo.entity_controller import summarize_world_pose_history
from aero_ai_studio.gazebo.transport import stamp
from aero_ai_studio.training.gazebo_dqn import dqn_validation_scenario
from aero_ai_studio.training.gazebo_physics import (
    BODY_STOPPED_EPSILON,
    PRE_RESET_QUIESCENCE_CHUNK_ITERATIONS,
    PRE_RESET_QUIESCENCE_MAX_CHUNKS,
    body_stopped_contract,
    reset_odometry_contract,
)
import diagnose_v07_gazebo_reset_strategies as reset_diagnostic

POSITION_TOLERANCE = 0.02
YAW_TOLERANCE = 0.02
SETTLE_CHUNK_ITERATIONS = PRE_RESET_QUIESCENCE_CHUNK_ITERATIONS
SETTLE_CHUNK_SECONDS = 0.1
MAX_QUIESCENCE_CHUNKS = PRE_RESET_QUIESCENCE_MAX_CHUNKS
MOTION_ACTIONS = 3


def _pose_delta(a, b):
    dx = float(b["x"]) - float(a["x"])
    dy = float(b["y"]) - float(a["y"])
    yaw = abs(math.atan2(math.sin(float(b["yaw"]) - float(a["yaw"])),
                         math.cos(float(b["yaw"]) - float(a["yaw"]))))
    return {"translation": math.hypot(dx, dy), "yaw_drift": yaw, "dx": dx, "dy": dy}


def diagnostic_verdict(evidence):
    motion = evidence.get("precondition_motion", {})
    if not motion.get("confirmed"):
        return "INCONCLUSIVE"
    quiescence = evidence.get("pre_reset_quiescence", {})
    if not quiescence.get("pass"):
        return "PRE_RESET_QUIESCENCE_FAILED"
    if not evidence.get("model_only", {}).get("rpc_accepted") or not evidence.get("model_only", {}).get("stats_contract", {}).get("pass"):
        return "MODEL_ONLY_RESET_FAILED"
    post = evidence.get("post_reset", {})
    if not post.get("contact_contract_pass"):
        return "CONTACT_FAILED"
    if not post.get("body_contract_pass"):
        return "MODEL_ONLY_POST_RESET_BODY_FAILED"
    if not all(post.get(key) is True for key in
               ("odometry_contract_pass", "sensor_fresh", "process_alive")):
        return "MODEL_ONLY_POST_RESET_CONTRACT_FAILED"
    return "SAFE_MODEL_ONLY_WITH_PRE_RESET_QUIESCENCE"


def _history(env, cursor, start, end):
    samples = env.controller.pose_history_after(cursor, start, end)
    return summarize_world_pose_history(samples, start, end)


def _motion_precondition(env):
    start_time = float(env.stepper.time)
    pose_start = env.controller.get_pose(start_time - .002, env.timeout)
    pose_cursor = env.transport.cursor(env.controller.pose_topic)
    odom_cursor = env.transport.cursor(env.odometry_topic)
    sensor_sequence_before = env.sensors.sequence
    commands = []
    for _ in range(MOTION_ACTIONS):
        env.controller.apply_action("up")
        commands.append(dict(env.controller.last_published_command))
        env.stepper.step_simulation()
    end_time = float(env.stepper.time)
    env._refresh()
    pose_end = dict(env.pose)
    body = _history(env, pose_cursor, start_time, end_time)
    odom = env.read_odometry_after_sequence(
        odom_cursor, end_time - .02, end_time + .002, timeout=.5)
    frame = env.sensors.frame
    displacement = _pose_delta(pose_start, pose_end)
    end_velocity = body.get("world_end_forward_velocity")
    confirmed = bool(
        displacement["translation"] > .01 and
        body.get("world_pose_history_fresh") and body.get("world_pose_history_dense_enough") and
        end_velocity is not None and abs(float(end_velocity)) > BODY_STOPPED_EPSILON and
        odom is not None and abs(float(odom.get("linear_x", 0.))) > BODY_STOPPED_EPSILON and
        frame is not None and frame.sequence > sensor_sequence_before and
        frame.source == "gazebo_lidar" and frame.age_ms <= 20.)
    return {
        "action": "up", "commands": commands, "action_count": MOTION_ACTIONS,
        "iterations_per_action": 100, "total_iterations": 300,
        "simulation_start": start_time, "simulation_end": end_time,
        "pose_start": pose_start, "pose_end": pose_end, **displacement,
        "world_pose_history": body, "body_forward_velocity": end_velocity,
        "body_angular_velocity": body.get("world_end_angular_velocity"),
        "odometry": odom,
        "sensor": None if frame is None else {"sequence": frame.sequence,
            "timestamp": frame.sensor_timestamp, "age_ms": frame.age_ms,
            "fresh": frame.source == "gazebo_lidar" and frame.age_ms <= 20.},
        "confirmed": confirmed,
        "failure_reason": None if confirmed else
            "Actual world-body motion, nonzero velocity, odometry, or fresh sensor was not established",
    }


def _quiesce(env, *, max_chunks=MAX_QUIESCENCE_CHUNKS):
    env.controller.stop_agent()
    zero_command = dict(env.controller.last_published_command or {})
    start_time = float(env.stepper.time)
    start_pose = env.controller.get_pose(start_time - .002, env.timeout)
    odom_cursor = env.transport.cursor(env.odometry_topic)
    chunks = []
    stopped = False
    final_summary = None
    for index in range(max_chunks):
        chunk_start = float(env.stepper.time)
        chunk_pose_cursor = env.transport.cursor(env.controller.pose_topic)
        odom_before = env.transport.cursor(env.odometry_topic)
        env.stepper.step_simulation()
        env._refresh()
        chunk_end = float(env.stepper.time)
        # Judge the current bounded chunk only. Earlier moving samples are kept
        # in the report but must not prevent a later stopped chunk from passing.
        summary = _history(env, chunk_pose_cursor, chunk_start, chunk_end)
        contract = body_stopped_contract(summary)
        odom = env.read_odometry_after_sequence(
            odom_before, chunk_end - .02, chunk_end + .002, timeout=.5)
        odom_contract = reset_odometry_contract(
            odom, reset_epoch_sim_time=start_time,
            settle_start_sim_time=chunk_start, settle_end_sim_time=chunk_end,
            sequence_before_reset=odom_cursor, sequence_after_reset=odom_cursor,
            sequence_before_settle=odom_before)
        chunk = {"index": index + 1, "iterations": SETTLE_CHUNK_ITERATIONS,
                 "simulation_start": chunk_start, "simulation_end": chunk_end,
                 "body_history": summary, "body_stopped_contract": contract,
                 "odometry": odom, "odometry_contract": odom_contract,
                 "pose": dict(env.pose)}
        chunks.append(chunk)
        final_summary = summary
        if contract["pass"]:
            stopped = True
            break
    end_pose = dict(env.pose)
    return {
        "zero_twist_sent": True, "zero_twist": zero_command,
        "zero_twist_publish_sequence": getattr(env.controller, "publish_sequence", None),
        "fixed_physics_stepper_used": True, "wall_clock_sleep_used_for_settling": False,
        "chunk_iterations": SETTLE_CHUNK_ITERATIONS,
        "max_chunks": max_chunks, "settle_chunks": chunks,
        "total_iterations": sum(c["iterations"] for c in chunks),
        "simulation_time_spent": float(env.stepper.time) - start_time,
        "start_pose": start_pose, "end_pose": end_pose,
        "displacement_during_quiescence": _pose_delta(start_pose, end_pose),
        "final_body_history": final_summary,
        "final_body_stopped_contract": chunks[-1]["body_stopped_contract"] if chunks else None,
        "final_odometry": chunks[-1]["odometry"] if chunks else None,
        "final_odometry_contract": chunks[-1]["odometry_contract"] if chunks else None,
        "world_body_stopped": stopped,
        "pass": stopped,
        "failure_reason": None if stopped else "PRE_RESET_QUIESCENCE_FAILED: body did not stop within bounded physics budget",
    }


def run_diagnostic(output: Path, *, gui=False, env_factory=GazeboEnvironment,
                   max_chunks=MAX_QUIESCENCE_CHUNKS, contact_timeout=1.0,
                   contact_poll_interval=.05):
    max_chunks = int(max_chunks)
    if max_chunks < 1 or max_chunks > MAX_QUIESCENCE_CHUNKS:
        raise ValueError(f"max_chunks must be in [1, {MAX_QUIESCENCE_CHUNKS}]")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    report = {"schema_version": "0.7.1",
        "diagnostic": "MODEL_ONLY reset after strict pre-reset PHYSICS quiescence",
        "status": "INCONCLUSIVE", "control_mode": "PHYSICS",
        "gazebo_version": gazebo_status(probe=True).get("detail"),
        "process_restart_used": False, "precondition_motion": {"confirmed": False},
        "pre_reset_quiescence": {}, "model_only": {}, "post_reset": {},
        "baseline_comparison": {
            "model_only_without_pre_reset_quiescence": {
                "max_abs_forward_velocity_mps": .5036052580812407,
                "post_reset_translation_m": .058125657904757766,
                "contact_publisher_healthy": True},
            "current_run": "pending"}}
    env = None
    try:
        schema_mod = importlib.import_module("gz.msgs10.world_reset_pb2")
        supported = reset_diagnostic.supported_reset_modes(schema_mod.WorldReset.DESCRIPTOR)
        report["supported_reset_modes"] = supported
        if "model_only" not in supported or not supported["model_only"].get("supported"):
            raise RuntimeError("Installed WorldReset schema does not support model_only")
        env = env_factory(dqn_validation_scenario(), max_steps=4, root=output / "world",
            gui=gui, control_mode="PHYSICS", max_sensor_age_ms=20,
            allow_geometric_fallback=False, capture_world_pose_history=True)
        launch = env.launch()
        if not launch.get("available", True) or env.injected or env.control_mode != "PHYSICS":
            raise RuntimeError("Diagnostic requires an actual Gazebo PHYSICS environment")
        env.prepare()
        env.prepare_contacts()
        env.reset(seed=42)
        process = env.manager.status()
        report["process"] = {"pid": process.get("pid"), "partition": env.manager.partition,
                             "world": env.world_name, "status": process.get("status"),
                             "fresh_process": True}
        initial_contact = reset_diagnostic.readiness_snapshot(env)
        report["initial_contact"] = initial_contact
        if not initial_contact.get("publisher_visible") or not initial_contact.get("schema_visible"):
            raise RuntimeError("Initial Contact publisher/schema unavailable")

        motion = _motion_precondition(env)
        report["precondition_motion"] = motion
        if not motion["confirmed"]:
            report["verdict"] = "INCONCLUSIVE"
            report["reason"] = motion["failure_reason"]
            return _write_report(output, report)

        quiescence = _quiesce(env, max_chunks=max_chunks)
        report["pre_reset_quiescence"] = quiescence
        if not quiescence["pass"]:
            report["verdict"] = "PRE_RESET_QUIESCENCE_FAILED"
            report["reason"] = quiescence["failure_reason"]
            return _write_report(output, report)

        # Only a body-history-confirmed stop permits MODEL_ONLY to be invoked.
        env.stepper.pause()
        stats_before_snapshot = env.transport.snapshot(env.stepper.topic)
        stats_before = stats_before_snapshot.get("data")
        sequence_before = stats_before_snapshot.get("sequence")
        odom_sequence_before_reset = env.transport.cursor(env.odometry_topic)
        if stats_before is None or sequence_before is None:
            raise RuntimeError("Missing pre-reset WorldStatistics baseline")
        payload = reset_diagnostic.reset_mode_payload("model_only", supported)
        try:
            response = env.stepper.control(payload)
            accepted = response.get("data") is True
        except Exception as error:
            report["model_only"] = {"request": payload, "rpc_accepted": False,
                "error": {"type": type(error).__name__, "message": str(error)}}
            report["verdict"] = "MODEL_ONLY_RESET_FAILED"
            report["reason"] = "MODEL_ONLY reset RPC failed"
            return _write_report(output, report)
        stats_after, sequence_after, stats_contract = reset_diagnostic._stats_after_sequence(
            env, sequence_before, "model_only", stats_before)
        reset_time = stamp(stats_after or {})
        env.stepper.time = reset_time
        env.contacts.reset(reset_time)
        contact_sequence_epoch = env.transport.cursor(env.contact_topic)
        odom_sequence_after_reset = env.transport.cursor(env.odometry_topic)
        after_reset_contact = reset_diagnostic.wait_contact_readiness(
            env, "after_model_only", timeout=contact_timeout,
            poll_interval=contact_poll_interval)
        report["model_only"] = {
            "request": payload, "rpc_response": response, "rpc_accepted": accepted,
            "stats_before": stats_before, "stats_after": stats_after,
            "stats_sequence_before": sequence_before,
            "stats_sequence_after": sequence_after,
            "stats_contract": stats_contract,
            "contact_readiness": {k: v for k, v in after_reset_contact.items() if k != "timeline"},
            "contact_readiness_timeline": after_reset_contact.get("timeline", []),
            "contact_epoch": {"epoch": env.contacts.epoch, "floor_sim_time": env.contacts.floor,
                              "receive_sequence_baseline": contact_sequence_epoch}}
        if not accepted or not stats_contract.get("pass"):
            report["verdict"] = "MODEL_ONLY_RESET_FAILED"
            report["reason"] = "MODEL_ONLY RPC or strategy-specific stats contract failed"
            return _write_report(output, report)

        start_x, start_y = env.scenario.start[0] + .5, env.scenario.start[1] + .5
        pose_cursor = env.transport.cursor(env.controller.pose_topic)
        sensor_sequence_before = env.sensors.sequence
        env.controller.reset_agent_pose(start_x, start_y, .16, 0.)
        set_pose = dict(env.controller.last_pose_request)
        progression_start = float(env.stepper.time)
        env.stepper.step_simulation()
        env._refresh()
        pose_after_progress = dict(env.pose)
        progression_contact = reset_diagnostic.wait_contact_readiness(
            env, "after_100_iterations", timeout=contact_timeout,
            poll_interval=contact_poll_interval)
        settle_start = float(env.stepper.time)
        pose_before_settle = dict(env.pose)
        odom_sequence_before_settle = env.transport.cursor(env.odometry_topic)
        env.stepper.step_simulation()
        env._refresh()
        pose_after_settle = dict(env.pose)
        settle_end = float(env.stepper.time)
        settle_contact = reset_diagnostic.wait_contact_readiness(
            env, "after_settle", timeout=contact_timeout,
            poll_interval=contact_poll_interval)
        history = _history(env, pose_cursor, progression_start, settle_end)
        progress_pose_error = _pose_delta({"x": start_x, "y": start_y, "yaw": 0.}, pose_after_progress)
        settle_pose_motion = _pose_delta(pose_before_settle, pose_after_settle)
        final_pose_error = _pose_delta({"x": start_x, "y": start_y, "yaw": 0.}, pose_after_settle)
        body_contract = body_stopped_contract(history)
        body_pose_stable = bool(
            progress_pose_error["translation"] <= POSITION_TOLERANCE and
            progress_pose_error["yaw_drift"] <= YAW_TOLERANCE and
            settle_pose_motion["translation"] <= POSITION_TOLERANCE and
            settle_pose_motion["yaw_drift"] <= YAW_TOLERANCE and
            final_pose_error["translation"] <= POSITION_TOLERANCE and
            final_pose_error["yaw_drift"] <= YAW_TOLERANCE)
        odom = env.read_odometry_after_sequence(
            odom_sequence_before_settle, settle_end - .02, settle_end + .002, timeout=.5)
        odom_contract = reset_odometry_contract(
            odom, reset_epoch_sim_time=reset_time,
            settle_start_sim_time=settle_start, settle_end_sim_time=settle_end,
            sequence_before_reset=odom_sequence_before_reset,
            sequence_after_reset=odom_sequence_after_reset,
            sequence_before_settle=odom_sequence_before_settle)
        frame = env.sensors.frame
        sensor_fresh = bool(frame is not None and frame.sequence > sensor_sequence_before and
                            frame.source == "gazebo_lidar" and frame.age_ms <= 20.)
        contact_pass = all(phase.get("pass") for phase in
                           (after_reset_contact, progression_contact, settle_contact))
        # Poll only after publisher/schema readiness; no event is required for readiness.
        contact_events = env.contacts.poll(settle_end, timeout=.01) if contact_pass else []
        contact_state = dict(env.contacts.state)
        process_status = env.manager.status()
        body_pass = bool(body_contract["pass"] and body_pose_stable)
        post = {
            "set_pose": set_pose,
            "pose_after_progress": pose_after_progress,
            "pose_after_settle": pose_after_settle,
            "pose_error_after_progress": progress_pose_error,
            "settle_motion": settle_pose_motion,
            "final_start_pose_error": final_pose_error,
            "world_pose_history": history,
            "body_stopped_contract": body_contract,
            "body_velocity_cleared": body_contract["pass"],
            "body_pose_stable": body_pose_stable,
            "body_contract_pass": body_pass,
            "odometry": odom, "odometry_contract": odom_contract,
            "odometry_contract_pass": bool(odom_contract["pass"]),
            "sensor": None if frame is None else {"sequence": frame.sequence,
                "timestamp": frame.sensor_timestamp, "age_ms": frame.age_ms,
                "fresh": sensor_fresh},
            "sensor_fresh": sensor_fresh,
            "contact_phases": {
                "after_model_only": {k: v for k, v in after_reset_contact.items() if k != "timeline"},
                "after_100_iterations": {k: v for k, v in progression_contact.items() if k != "timeline"},
                "after_settle": {k: v for k, v in settle_contact.items() if k != "timeline"}},
            "contact_timelines": {
                "after_model_only": after_reset_contact.get("timeline", []),
                "after_100_iterations": progression_contact.get("timeline", []),
                "after_settle": settle_contact.get("timeline", [])},
            "contact_contract_pass": contact_pass,
            "contact_epoch": {"epoch": env.contacts.epoch, "floor_sim_time": env.contacts.floor,
                "receive_sequence_baseline": contact_sequence_epoch,
                "state_after_poll": contact_state, "events_after_reset": contact_events,
                "event_packet_count_since_epoch": contact_state.get("received_frames", 0),
                "event_silence_is_not_publisher_health": True,
                "pre_reset_sequence_excluded_by_baseline": True},
            "process_alive": process_status.get("status") == "Running",
            "process": process_status}
        report["post_reset"] = post
        report["baseline_comparison"]["current_run"] = {
            "pre_reset_max_forward_velocity_mps": quiescence["final_body_stopped_contract"]["max_abs_forward_velocity"],
            "post_reset_max_forward_velocity_mps": body_contract["max_abs_forward_velocity"],
            "post_reset_translation_m": final_pose_error["translation"],
            "contact_publisher_healthy": contact_pass}
        report["verdict"] = diagnostic_verdict(report)
        report["reason"] = None if report["verdict"] == "SAFE_MODEL_ONLY_WITH_PRE_RESET_QUIESCENCE" else report["verdict"]
    except Exception as error:
        report["error"] = {"type": type(error).__name__, "message": str(error)}
        report["verdict"] = "INCONCLUSIVE"
        report["reason"] = str(error)
    finally:
        if env is not None:
            pid = env.manager.status().get("pid")
            try:
                env.close()
                report["shutdown"] = "PASS"
                report["process_exited"] = env.manager.status().get("status") == "Stopped"
            except Exception as error:
                report["shutdown"] = "FAIL"
                report["shutdown_error"] = str(error)
            report.setdefault("process", {})["pid"] = pid
            _write_report(output, report)
    return _write_report(output, report)


def _write_report(output, report):
    report["process_restart_used"] = False
    evidence_path = Path(output) / "model_only_quiescence_diagnostic.json"
    report["evidence_file"] = str(evidence_path)
    write_json(evidence_path, report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--gui", action="store_true")
    parser.add_argument("--max-quiescence-chunks", type=int, default=MAX_QUIESCENCE_CHUNKS)
    args = parser.parse_args(argv)
    if not 1 <= args.max_quiescence_chunks <= MAX_QUIESCENCE_CHUNKS:
        parser.error(f"--max-quiescence-chunks must be in [1, {MAX_QUIESCENCE_CHUNKS}]")
    report = run_diagnostic(args.output, gui=args.gui, max_chunks=args.max_quiescence_chunks)
    print("MODEL_ONLY quiescence diagnostic: " + report.get("verdict", "INCONCLUSIVE"))
    print("evidence: " + report["evidence_file"])
    return 0 if report.get("verdict") == "SAFE_MODEL_ONLY_WITH_PRE_RESET_QUIESCENCE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
