#!/usr/bin/env python3
"""Capture actual Gazebo body-pose and wheel-odometry evidence around reversal."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aero_ai_studio.core.storage import write_json
from aero_ai_studio.gazebo.environment import GazeboEnvironment
from aero_ai_studio.training.gazebo_dqn import dqn_validation_scenario


def finalize_capture_status(report):
    actions = report.get("actions", [])
    endpoint_captured = bool(actions) and all(
        entry.get("before_pose") is not None and entry.get("after_pose") is not None and
        entry.get("action_transition") is not None for entry in actions)
    histories = [entry.get("action_transition", {}).get("world_pose_history", [])
                 for entry in actions]
    history_captured = bool(histories) and all(bool(samples) for samples in histories)
    summaries = [entry.get("action_transition", {}).get("world_pose_history_summary")
                 for entry in actions]
    history_sufficient = bool(summaries) and all(
        summary is not None and summary.get("world_pose_history_dense_enough") is True
        for summary in summaries)
    report["endpoint_evidence_captured"] = endpoint_captured
    report["world_pose_history_captured"] = history_captured
    report["world_pose_history_sufficient"] = history_sufficient
    report["world_pose_history_sample_counts"] = [
        0 if summary is None else int(summary.get("world_pose_sample_count", 0))
        for summary in summaries]
    if report.get("status") == "INFRASTRUCTURE_FAILURE":
        return report
    if any("exception" in entry for entry in actions):
        report["status"] = "ACTION_VALIDATION_FAILURE" if any(
            entry.get("pose_validation") is not None for entry in actions if "exception" in entry
        ) else "INFRASTRUCTURE_FAILURE"
    elif endpoint_captured and history_captured and history_sufficient:
        report["status"] = "CAPTURED"
    else:
        report["status"] = "CAPTURED_WITH_INSUFFICIENT_POSE_HISTORY"
    return report


def run_diagnostic(output: Path, *, gui: bool = False):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": "0.7.1",
        "diagnostic": "Gazebo PHYSICS longitudinal reversal pose history",
        "status": "NOT_STARTED",
        "endpoint_evidence_captured": False,
        "world_pose_history_captured": False,
        "world_pose_history_sufficient": False,
        "control_mode": "PHYSICS",
        "action_sequence": ["up", "down", "up"],
        "action_semantics": "existing discrete action -> Twist -> 100-iteration GazeboStepper",
        "physics_interval_semantics_changed": False,
        "agent_action_uses_set_pose": False,
        "actions": [],
    }
    env = None
    try:
        env = GazeboEnvironment(dqn_validation_scenario(), max_steps=3,
            root=output / "worlds", gui=gui, control_mode="PHYSICS",
            max_sensor_age_ms=20, allow_geometric_fallback=False,
            capture_world_pose_history=True)
        launch = env.launch()
        if not launch.get("available", True):
            raise RuntimeError("Gazebo launch unavailable: " + str(launch))
        if env.injected or env.control_mode != "PHYSICS":
            raise RuntimeError("Diagnostic requires actual Gazebo PHYSICS transport")
        env.reset(seed=42)
        report.update(status="RUNNING", actual_world=env.world_name,
                      process=env.manager.status(), partition=env.manager.partition,
                      reset_initialization=dict(env.initialization_checks),
                      pose_topic_contract={
                          "topic": env.controller.pose_topic,
                          "message_type": "gz.msgs.Pose_V",
                          "publisher": "gz-sim 8 SceneBroadcaster",
                          "publisher_max_messages_per_second": 60,
                          "simulation_timestamp_field": "Pose_V.header.stamp",
                          "per_pose_header_required": False})
        for index, action in enumerate(report["action_sequence"]):
            entry = {"index": index, "action": action,
                     "before_pose": dict(env.pose),
                     "before_simulation_time": float(env.stepper.time)}
            try:
                result = env.step(action)
                entry["result"] = {"reward": result.reward, "terminated": result.terminated,
                                   "truncated": result.truncated, "reason": result.reason}
            except Exception as error:
                entry["exception"] = {"type": type(error).__name__, "message": str(error)}
            entry["action_transition"] = env.telemetry.get("action_transition")
            entry["pose_validation"] = env.telemetry.get("pose_validation")
            entry["after_pose"] = dict(env.pose) if env.pose is not None else None
            entry["after_simulation_time"] = float(env.stepper.time)
            report["actions"].append(entry)
            if "exception" in entry:
                report["status"] = "ACTION_VALIDATION_FAILURE" if entry.get("pose_validation") else "INFRASTRUCTURE_FAILURE"
                report["error"] = entry["exception"]
                break
        else:
            report["status"] = "ACTIONS_COMPLETE"
        report["final_process"] = env.manager.status()
    except Exception as error:
        report.update(status="INFRASTRUCTURE_FAILURE",
                      error={"type": type(error).__name__, "message": str(error)})
    finally:
        if env is not None:
            try:
                env.close()
                report["shutdown"] = "PASS"
            except Exception as error:
                report["shutdown"] = "FAIL"
                report["shutdown_error"] = str(error)
        finalize_capture_status(report)
        report["evidence_file"] = str(output / "reversal_diagnostic.json")
        write_json(output / "reversal_diagnostic.json", report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--gui", action="store_true")
    args = parser.parse_args(argv)
    report = run_diagnostic(args.output, gui=args.gui)
    print(f"reversal diagnostic: {report['status']}")
    print("endpoint evidence: " + str(report.get("endpoint_evidence_captured")))
    print("interval pose history captured/sufficient: " +
          f"{report.get('world_pose_history_captured')}/{report.get('world_pose_history_sufficient')}")
    print(f"evidence: {report['evidence_file']}")
    return 0 if report["status"] == "CAPTURED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
