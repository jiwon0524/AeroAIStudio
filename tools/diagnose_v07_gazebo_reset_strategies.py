#!/usr/bin/env python3
"""Compare installed Gazebo WorldReset modes on isolated PHYSICS processes."""
from __future__ import annotations

import argparse
import math
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aero_ai_studio.core.storage import write_json
from aero_ai_studio.gazebo.diagnostics import gazebo_status
from aero_ai_studio.gazebo.environment import GazeboEnvironment
from aero_ai_studio.gazebo.entity_controller import summarize_world_pose_history
from aero_ai_studio.gazebo.transport import stamp
from aero_ai_studio.training.gazebo_dqn import dqn_validation_scenario
from aero_ai_studio.training.gazebo_physics import reset_odometry_contract

RESET_MODES = ("all", "model_only", "time_only")
CONTACT_TYPE = "gz.msgs.Contacts"
MOTION_STEPS = 3
CONTACT_READINESS_TIMEOUT = 1.0  # diagnostic observation bound; not a production timeout
CONTACT_POLL_INTERVAL = 0.05
STATS_TIMEOUT = 2.0
POSITION_TOLERANCE = 0.02
YAW_TOLERANCE = 0.02
BODY_VELOCITY_EPSILON = 0.02


def supported_reset_modes(world_reset_descriptor):
    """Read supported boolean reset switches from the installed protobuf descriptor."""
    fields = {field.name: field for field in world_reset_descriptor.fields}
    modes = {}
    for name in RESET_MODES:
        field = fields.get(name)
        if field is None:
            continue
        modes[name] = {
            "supported": field.type == field.TYPE_BOOL,
            "protobuf_type": "bool" if field.type == field.TYPE_BOOL else str(field.type),
            "has_presence": bool(field.has_presence),
            "default": field.default_value,
        }
    return modes


def reset_mode_payload(mode, supported):
    if mode not in RESET_MODES or mode not in supported or not supported[mode].get("supported"):
        raise ValueError(f"Unsupported installed WorldReset mode: {mode}")
    return {"pause": True, "reset": {mode: True}}


def strategy_stats_contract(mode, before, after, sequence_before, sequence_after, *, tolerance=.002):
    """Validate stats per requested reset semantics, keeping clock-only separate."""
    after = after if isinstance(after, dict) else {}
    before_time = stamp(before or {})
    after_time = stamp(after)
    seq_new = (sequence_before is not None and sequence_after is not None and
               int(sequence_after) > int(sequence_before))
    paused = after.get("paused") is True
    if mode == "all":
        from aero_ai_studio.gazebo.stepping import world_reset_stats_contract
        contract = world_reset_stats_contract(after, sequence_before, sequence_after,
                                              time_tolerance=tolerance)
        return {"mode": mode, "clock_semantics": "reset_world_and_time_epoch",
                "before_simulation_time": before_time, **contract}
    if mode == "time_only":
        time_ok = abs(after_time) <= tolerance
        conditions = {"stats_sequence_new": seq_new, "paused": paused,
                      "simulation_time_reset": time_ok}
        expected = "reset_simulation_time_without_asserting_model_reset"
    elif mode == "model_only":
        time_ok = abs(after_time - before_time) <= tolerance
        conditions = {"stats_sequence_new": seq_new, "paused": paused,
                      "simulation_time_preserved": time_ok}
        expected = "preserve_simulation_time_epoch"
    else:
        raise ValueError(f"Unsupported reset mode: {mode}")
    failures = [key for key, passed in conditions.items() if not passed]
    return {"mode": mode, "clock_semantics": expected,
            "before_simulation_time": before_time, "simulation_time": after_time,
            "paused_value": after.get("paused"),
            "iterations_raw_present": after.get("iterations_raw_present", "iterations" in after),
            "iterations_normalized": after.get("iterations_normalized", after.get("iterations")),
            "stats_sequence_before": sequence_before,
            "stats_sequence_after": sequence_after, **conditions,
            "pass": not failures,
            "failure_reason": None if not failures else ",".join(failures)}


def readiness_snapshot(env):
    try:
        publishers, subscribers = env.transport.node.topic_info(env.contact_topic)
        types = sorted({getattr(publisher, "msg_type_name", "") for publisher in publishers
                        if getattr(publisher, "msg_type_name", "")})
        return {"topic": env.contact_topic, "topic_visible": bool(publishers or subscribers),
                "publisher_visible": bool(publishers), "schema_visible": bool(publishers) and types == [CONTACT_TYPE],
                "message_type": types[0] if len(types) == 1 else types or None,
                "expected_schema": CONTACT_TYPE, "error": None}
    except Exception as error:
        return {"topic": env.contact_topic, "topic_visible": False,
                "publisher_visible": False, "schema_visible": False,
                "message_type": None, "expected_schema": CONTACT_TYPE,
                "error": {"type": type(error).__name__, "message": str(error)}}


def wait_contact_readiness(env, phase, *, timeout=CONTACT_READINESS_TIMEOUT,
                           poll_interval=CONTACT_POLL_INTERVAL, monotonic=time.monotonic,
                           sleep=time.sleep):
    started = monotonic()
    deadline = started + timeout
    attempts = []
    initial_ready = None
    while True:
        process_status = env.manager.status()
        row = readiness_snapshot(env)
        row.update(attempt=len(attempts) + 1, wall_elapsed_seconds=max(0., monotonic() - started),
                   phase=phase, process_alive=process_status.get("status") == "Running",
                   process_pid=process_status.get("pid"))
        attempts.append(row)
        if initial_ready is None:
            initial_ready = bool(row["publisher_visible"] and row["schema_visible"])
        if not row["process_alive"]:
            break
        if row["publisher_visible"] and row["schema_visible"]:
            break
        remaining = deadline - monotonic()
        if remaining <= 0:
            break
        sleep(min(poll_interval, remaining))
    final = attempts[-1]
    passed = bool(final["process_alive"] and final["publisher_visible"] and final["schema_visible"])
    return {
        "required": True, "phase": phase, "topic": env.contact_topic,
        "expected_schema": CONTACT_TYPE, "timeout_seconds": timeout,
        "polling_interval_seconds": poll_interval, "attempts": len(attempts),
        "initial_ready": initial_ready,
        "recovered": bool(not initial_ready and passed),
        "recovery_wall_seconds": final["wall_elapsed_seconds"] if passed and not initial_ready else (0.0 if passed else None),
        "final_publisher_visible": final["publisher_visible"],
        "final_schema_valid": final["schema_visible"],
        "final_message_type": final["message_type"],
        "process_alive": final["process_alive"],
        "process_pid": final["process_pid"],
        "pass": passed,
        "failure_reason": None if passed else (
            "Gazebo process exited during contact publisher readiness" if not final["process_alive"] else
            "Contact publisher/schema readiness timeout"),
        "timeline": attempts,
    }


def strategy_verdict(evidence):
    if not evidence.get("pre_reset_motion", {}).get("confirmed"):
        return "INCONCLUSIVE"
    if not evidence.get("reset_rpc", {}).get("accepted"):
        return "UNSAFE"
    if not evidence.get("stats_reset_contract", {}).get("pass"):
        return "UNSAFE"
    checks = ("process_alive", "body_velocity_cleared", "body_pose_stable",
              "odometry_stopped", "sensor_fresh", "contact_publisher_healthy")
    return "SAFE_FOR_PERSISTENT_EPISODE_RESET" if all(evidence.get(key) is True for key in checks) else "UNSAFE"


def _stats_after_sequence(env, sequence_before, mode, before_sample, timeout=STATS_TIMEOUT):
    deadline = time.monotonic() + timeout
    last_sample = None
    last_sequence = None
    contract = None
    while True:
        snap = env.transport.snapshot(env.stepper.topic)
        sample = snap.get("data")
        sequence = snap.get("sequence")
        if sample is not None and sequence is not None and sequence > sequence_before:
            last_sample, last_sequence = sample, sequence
            contract = strategy_stats_contract(mode, before_sample, sample, sequence_before, sequence)
            if contract.get("pass"):
                break
        if time.monotonic() >= deadline:
            break
        time.sleep(.01)
    return last_sample, last_sequence, contract or strategy_stats_contract(
        mode, before_sample, {}, sequence_before, last_sequence)


def _pose_metrics(before, after):
    dx, dy = float(after["x"]) - float(before["x"]), float(after["y"]) - float(before["y"])
    yaw = abs(math.atan2(math.sin(float(after["yaw"]) - float(before["yaw"])),
                         math.cos(float(after["yaw"]) - float(before["yaw"]))))
    return {"translation": (dx * dx + dy * dy) ** .5, "yaw_delta": yaw,
            "dx": dx, "dy": dy}


def run_strategy(mode, root, *, gui=False, env_factory=GazeboEnvironment,
                 supported=None, contact_timeout=CONTACT_READINESS_TIMEOUT,
                 contact_poll_interval=CONTACT_POLL_INTERVAL):
    """Execute one candidate on a new environment/process; never reuse across modes."""
    evidence = {"mode": mode, "fresh_process_required": True,
                "process_isolated_for_strategy": True,
                "pre_reset_motion": {"confirmed": False},
                "reset_rpc": {"accepted": False}, "reset_stats": {},
                "phases": {}, "verdict": "INCONCLUSIVE"}
    env = None
    try:
        env = env_factory(dqn_validation_scenario(), max_steps=4, root=root,
            gui=gui, control_mode="PHYSICS", max_sensor_age_ms=20,
            allow_geometric_fallback=False, capture_world_pose_history=True)
        launch = env.launch()
        if not launch.get("available", True) or env.injected or env.control_mode != "PHYSICS":
            raise RuntimeError("Reset strategy diagnostic requires actual Gazebo PHYSICS")
        env.prepare()
        env.prepare_contacts()
        env.reset(seed=42)
        process_before = env.manager.status()
        evidence["process"] = {"pid": process_before.get("pid"),
                               "partition": env.manager.partition,
                               "world": env.world_name,
                               "status": process_before.get("status")}
        evidence["initial_contact"] = readiness_snapshot(env)
        if not evidence["initial_contact"].get("schema_visible"):
            raise RuntimeError("Initial Contacts publisher/schema unavailable")

        # Establish the same actual physical action response in every fresh process.
        move_start = env.stepper.time
        pose_start = env.controller.get_pose(move_start - .002, env.timeout)
        pose_cursor = env.transport.cursor(env.controller.pose_topic)
        odom_cursor = env.transport.cursor(env.odometry_topic)
        sensor_sequence_before_motion = env.sensors.sequence
        motion_commands = []
        for _ in range(MOTION_STEPS):
            env.controller.apply_action("up")
            motion_commands.append(dict(env.controller.last_published_command))
            env.stepper.step_simulation()
        move_end = env.stepper.time
        pose_end = env.controller.get_pose(move_end - .002, env.timeout)
        pre_motion_pose = _pose_metrics(pose_start, pose_end)
        pose_history = env.controller.pose_history_after(pose_cursor, move_start, move_end)
        pre_history = summarize_world_pose_history(pose_history, move_start, move_end)
        odometry_before_reset = env.read_odometry_after_sequence(
            odom_cursor, move_end - .02, move_end + .002, timeout=.5)
        env._refresh()
        pre_sensor = env.sensors.frame
        pre_motion_confirmed = bool(
            pre_motion_pose["translation"] > .01 and odometry_before_reset is not None and
            abs(odometry_before_reset["linear_x"]) > BODY_VELOCITY_EPSILON and
            pre_history.get("world_pose_history_fresh") and
            pre_history.get("world_pose_history_dense_enough") and
            pre_history.get("world_end_forward_velocity") is not None and
            abs(float(pre_history["world_end_forward_velocity"])) > BODY_VELOCITY_EPSILON and
            pre_sensor is not None and pre_sensor.sequence > sensor_sequence_before_motion)
        evidence["pre_reset_motion"] = {
            "action": "up", "command_trace": motion_commands,
            "action_count": MOTION_STEPS,
            "iterations_per_action": 100,
            "total_iterations": MOTION_STEPS * 100,
            "simulation_start": move_start,
            "simulation_end": move_end, "pose_before": pose_start, "pose_after": pose_end,
            **pre_motion_pose, "world_pose_history": pre_history,
            "wheel_odometry": odometry_before_reset,
            "sensor_fresh": bool(pre_sensor and pre_sensor.age_ms <= 20.),
            "confirmed": pre_motion_confirmed,
            "failure_reason": None if pre_motion_confirmed else "Actual body, wheel odometry, or sensor motion precondition was not established",
        }
        if not pre_motion_confirmed:
            evidence["verdict"] = "INCONCLUSIVE"
            return evidence

        env.controller.stop_agent()
        env.stepper.pause()
        before_snapshot = env.transport.snapshot(env.stepper.topic)
        before_stats = before_snapshot.get("data")
        before_sequence = before_snapshot.get("sequence")
        if before_stats is None or before_sequence is None:
            raise RuntimeError("Missing pre-reset WorldStatistics sample/sequence")
        payload = reset_mode_payload(mode, supported or {})
        evidence["reset_request"] = {"service": f"/world/{env.world_name}/control",
                                     "request_type": "gz.msgs.WorldControl",
                                     "response_type": "gz.msgs.Boolean", "payload": payload}
        try:
            response = env.stepper.control(payload)
            accepted = response.get("data") is True
            evidence["reset_rpc"] = {"accepted": accepted, "response": response}
        except Exception as error:
            evidence["reset_rpc"] = {"accepted": False,
                                     "error": {"type": type(error).__name__, "message": str(error)}}
            evidence["verdict"] = "UNSAFE"
            return evidence
        if not evidence["reset_rpc"]["accepted"]:
            evidence["verdict"] = "UNSAFE"
            return evidence
        after_stats, after_sequence, stats_contract = _stats_after_sequence(
            env, before_sequence, mode, before_stats)
        evidence["reset_stats"] = {"sequence_before": before_sequence,
            "sequence_after": after_sequence,
            "before_simulation_time": stamp(before_stats or {}),
            "after_simulation_time": None if after_stats is None else stamp(after_stats),
            "before_iterations": (before_stats or {}).get("iterations_normalized", (before_stats or {}).get("iterations")),
            "after_iterations": None if after_stats is None else after_stats.get("iterations_normalized", after_stats.get("iterations")),
            "paused": None if after_stats is None else after_stats.get("paused"),
            "contract": stats_contract}
        evidence["stats_reset_contract"] = stats_contract
        if not stats_contract.get("pass"):
            evidence["verdict"] = "UNSAFE"
            return evidence
        reset_time = stamp(after_stats)
        env.stepper.time = reset_time
        if reset_time < move_end - .002:
            env.sensors.reset_epoch()
        if hasattr(env, "contacts"):
            env.contacts.reset(reset_time)
        contact_sequence_at_reset = env.transport.cursor(env.contact_topic)

        evidence["phases"]["after_reset"] = wait_contact_readiness(
            env, "after_reset", timeout=contact_timeout,
            poll_interval=contact_poll_interval)
        target_x, target_y = env.scenario.start[0] + .5, env.scenario.start[1] + .5
        env.controller.reset_agent_pose(target_x, target_y, .16, 0.)
        evidence["set_pose"] = dict(env.controller.last_pose_request)
        pose_history_cursor = env.transport.cursor(env.controller.pose_topic)
        progression_start = env.stepper.time
        sensor_sequence_before = env.sensors.sequence
        odom_sequence_after_reset = env.transport.cursor(env.odometry_topic)
        env.stepper.step_simulation()
        env._refresh()
        pose_after_progress = dict(env.pose)
        evidence["phases"]["after_100_iterations"] = wait_contact_readiness(
            env, "after_100_iterations", timeout=contact_timeout,
            poll_interval=contact_poll_interval)

        settle_start = env.stepper.time
        pose_before_settle = dict(env.pose)
        odom_sequence_before_settle = env.transport.cursor(env.odometry_topic)
        env.stepper.step_simulation()
        env._refresh()
        pose_after_settle = dict(env.pose)
        settle_end = env.stepper.time
        evidence["phases"]["after_settle"] = wait_contact_readiness(
            env, "after_settle", timeout=contact_timeout,
            poll_interval=contact_poll_interval)

        full_history = env.controller.pose_history_after(pose_history_cursor, progression_start, settle_end)
        body = summarize_world_pose_history(full_history, progression_start, settle_end)
        set_pose_error = _pose_metrics({"x": target_x, "y": target_y, "yaw": 0.}, pose_after_progress)
        settle_motion = _pose_metrics(pose_before_settle, pose_after_settle)
        final_start_error = _pose_metrics({"x": target_x, "y": target_y, "yaw": 0.}, pose_after_settle)
        max_forward = max((abs(float(row["forward_velocity"])) for row in body.get("world_forward_velocity_samples", [])), default=float("inf"))
        max_angular = max((abs(float(row["angular_velocity"])) for row in body.get("world_angular_velocity_samples", [])), default=float("inf"))
        body_velocity_cleared = bool(body.get("world_pose_history_fresh") and
            body.get("world_pose_history_dense_enough") and
            max_forward <= BODY_VELOCITY_EPSILON and max_angular <= BODY_VELOCITY_EPSILON)
        body_pose_stable = bool(set_pose_error["translation"] <= POSITION_TOLERANCE and
            set_pose_error["yaw_delta"] <= YAW_TOLERANCE and
            settle_motion["translation"] <= POSITION_TOLERANCE and
            settle_motion["yaw_delta"] <= YAW_TOLERANCE and
            final_start_error["translation"] <= POSITION_TOLERANCE and
            final_start_error["yaw_delta"] <= YAW_TOLERANCE)
        odometry = env.read_odometry_after_sequence(
            odom_sequence_before_settle, settle_end - .02, settle_end + .002, timeout=.5)
        odometry_contract = reset_odometry_contract(odometry,
            reset_epoch_sim_time=reset_time, settle_start_sim_time=settle_start,
            settle_end_sim_time=settle_end, sequence_before_reset=odom_cursor,
            sequence_after_reset=odom_sequence_after_reset,
            sequence_before_settle=odom_sequence_before_settle)
        frame = env.sensors.frame
        sensor_fresh = bool(frame is not None and frame.sequence > sensor_sequence_before and
                            frame.source == "gazebo_lidar" and frame.age_ms <= 20.)
        contacts = env.transport.cursor(env.contact_topic)
        contact_phases = evidence["phases"]
        contact_healthy = all(contact_phases[name].get("pass") for name in
                              ("after_reset", "after_100_iterations", "after_settle"))
        process_status = env.manager.status()
        evidence.update(
            process_alive=process_status.get("status") == "Running",
            set_pose_accepted=evidence["set_pose"].get("accepted") is True,
            reset_progression={"start_simulation_time": progression_start,
                               "after_100_iterations_simulation_time": settle_start,
                               "after_settle_simulation_time": settle_end,
                               "iterations_each_step": 100},
            body={"pose_after_progress": pose_after_progress,
                  "pose_after_settle": pose_after_settle,
                  "pose_error_after_progress": set_pose_error,
                  "settle_motion": settle_motion,
                  "final_start_pose_error": final_start_error,
                  "history": body,"max_abs_forward_velocity": max_forward,
                  "max_abs_angular_velocity": max_angular,
                  "velocity_threshold": BODY_VELOCITY_EPSILON},
            odometry={"sample": odometry, "contract": odometry_contract},
            odometry_stopped=odometry_contract["pass"],
            sensor={"sequence_before": sensor_sequence_before,
                    "sequence_after": None if frame is None else frame.sequence,
                    "timestamp": None if frame is None else frame.sensor_timestamp,
                    "age_ms": None if frame is None else frame.age_ms,
                    "fresh": sensor_fresh},
            sensor_fresh=sensor_fresh,
            contact={"publisher_schema_healthy": contact_healthy,
                     "sequence_before_reset": contact_sequence_at_reset,
                     "sequence_after_settle": contacts,
                     "event_packet_count": max(0, contacts - contact_sequence_at_reset),
                     "event_absence_is_not_publisher_absence": True,
                     "phase_contracts": {name: {k: v for k, v in value.items() if k != "timeline"}
                                         for name, value in contact_phases.items()}},
            contact_publisher_healthy=contact_healthy)
        evidence["body_velocity_cleared"] = body_velocity_cleared
        evidence["body_pose_stable"] = body_pose_stable
        evidence["process_alive"] = process_status.get("status") == "Running"
        evidence["verdict"] = strategy_verdict(evidence)
    except Exception as error:
        evidence["error"] = {"type": type(error).__name__, "message": str(error)}
        evidence["verdict"] = "INCONCLUSIVE" if not evidence.get("pre_reset_motion", {}).get("confirmed") else "UNSAFE"
    finally:
        if env is not None:
            pid = env.manager.status().get("pid")
            try:
                env.close()
                evidence["shutdown"] = "PASS"
                evidence["process_exited"] = env.manager.status().get("status") == "Stopped"
            except Exception as error:
                evidence["shutdown"] = "FAIL"
                evidence["shutdown_error"] = str(error)
            evidence.setdefault("process", {})["pid"] = pid
    return evidence


def run_diagnostic(output: Path, *, gui=False, env_factory=GazeboEnvironment,
                   contact_timeout=CONTACT_READINESS_TIMEOUT,
                   contact_poll_interval=CONTACT_POLL_INTERVAL):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    report = {"schema_version": "0.7.1",
        "diagnostic": "Gazebo installed WorldReset strategy comparison",
        "status": "COMPLETED", "control_mode": "PHYSICS",
        "gazebo_version": gazebo_status(probe=True).get("detail"),
        "supported_reset_modes": {}, "strategies": {},
        "reset_all_recreates_world_systems_hypothesis":
            "ALL includes all world reset state and may recreate systems; this lifecycle effect is evaluated empirically per fresh process.",
        "contact_system_sdf": {"world_plugin_filename": "gz-sim-contact-system",
            "world_plugin_name": "gz::sim::systems::Contact",
            "sensor_type": "contact", "sensor_name": "body_contacts",
            "sensor_topic_source": "contact/topic", "event_driven": True},
        "recommended_strategy": None, "recommendation_reason": None}
    try:
        # Resolve the installed descriptor without creating a transport node.
        import importlib
        reset_descriptor = importlib.import_module("gz.msgs10.world_reset_pb2").WorldReset.DESCRIPTOR
        schema = supported_reset_modes(reset_descriptor)
        report["supported_reset_modes"] = schema
        candidates = [mode for mode in ("all", "model_only", "time_only")
                      if mode in schema and schema[mode]["supported"]]
        if not candidates:
            raise RuntimeError("Installed WorldReset schema has no supported candidate reset mode")
        previous_process_exited = True
        for mode in candidates:
            if not previous_process_exited:
                report["strategies"][mode] = {
                    "mode": mode, "verdict": "INCONCLUSIVE",
                    "fresh_process_required": True,
                    "error": {"type": "LifecycleIsolationError",
                              "message": "Prior strategy process did not exit; candidate was not launched."}}
                continue
            result = run_strategy(mode, output / "worlds" / mode,
                gui=gui, env_factory=env_factory, supported=schema,
                contact_timeout=contact_timeout,
                contact_poll_interval=contact_poll_interval)
            report["strategies"][mode] = result
            previous_process_exited = result.get("process_exited") is True
        safe = [mode for mode, result in report["strategies"].items()
                if result.get("verdict") == "SAFE_FOR_PERSISTENT_EPISODE_RESET"]
        if safe:
            report["recommended_strategy"] = safe[0]
            report["recommendation_reason"] = "First candidate satisfying body, pose, odometry, sensor, contact-schema, and process contracts in its own fresh process."
        else:
            report["recommendation_reason"] = "No tested reset strategy met every persistent-reset safety contract."
    except Exception as error:
        report["status"] = "INCONCLUSIVE"
        report["error"] = {"type": type(error).__name__, "message": str(error)}
    report["evidence_file"] = str(output / "reset_strategy_diagnostic.json")
    write_json(output / "reset_strategy_diagnostic.json", report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--gui", action="store_true")
    args = parser.parse_args(argv)
    report = run_diagnostic(args.output, gui=args.gui)
    print("reset strategy diagnostic: " + report["status"])
    for mode, result in report.get("strategies", {}).items():
        print(f"{mode}: {result.get('verdict')}")
    print("recommended strategy: " + str(report.get("recommended_strategy")))
    print("evidence: " + report["evidence_file"])
    return 0 if report.get("status") == "COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
