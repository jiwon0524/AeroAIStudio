#!/usr/bin/env python3
"""Capture actual Gazebo body trajectory for forward-to-turn transitions."""
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
    report["endpoint_evidence_captured"] = bool(actions) and all(
        item.get("before_pose") is not None and item.get("after_pose") is not None and
        item.get("action_transition") is not None for item in actions)
    target = next((item for item in actions
                   if item.get("action_transition", {}).get("command_mode_transition") ==
                   "LINEAR_TO_ROTATION"), None)
    transition = None if target is None else target.get("action_transition") or {}
    summary = None if transition is None else transition.get("world_pose_history_summary")
    history = [] if transition is None else transition.get("world_pose_history", [])
    report["target_transition_found"] = target is not None
    report["world_pose_history_captured"] = bool(history)
    report["world_pose_history_sufficient"] = bool(
        summary and summary.get("world_pose_history_fresh") is True and
        summary.get("world_pose_history_dense_enough") is True and
        summary.get("world_pose_sample_count", 0) >= 3 and
        summary.get("world_velocity_sample_count", 0) >= 2 and
        summary.get("world_angular_velocity_sample_count", 0) >= 2)
    report["world_pose_history_sample_count"] = (
        0 if summary is None else int(summary.get("world_pose_sample_count", 0)))
    report["world_pose_history_max_gap"] = (
        None if summary is None else summary.get("world_pose_history_max_gap"))
    if not report["world_pose_history_sufficient"]:
        report["status"] = "CAPTURED_WITH_INSUFFICIENT_POSE_HISTORY"
    elif target.get("pose_validation", {}).get("valid") is False:
        report["status"] = "CAPTURED_WITH_VALIDATOR_FAILURE"
    else:
        report["status"] = "CAPTURED"
    return report


def run_diagnostic(output: Path, *, gui: bool = False):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": "0.7.1",
        "diagnostic": "Gazebo PHYSICS forward-to-rotation body trajectory",
        "status": "NOT_STARTED",
        "control_mode": "PHYSICS",
        "action_sequence": ["up", "right"],
        "target_transition": "LINEAR_TO_ROTATION",
        "action_semantics": "existing action -> one Twist publish -> 100 Gazebo physics iterations -> endpoint",
        "physics_interval_semantics_changed": False,
        "intermediate_zero_twist": False,
        "agent_action_uses_set_pose": False,
        "pose_topic_history_mode": "passive buffered Pose_V history",
        "actions": [],
    }
    env = None
    try:
        env = GazeboEnvironment(dqn_validation_scenario(), max_steps=2,
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
                "simulation_timestamp_field": "Pose_V.header.stamp",
                "per_pose_header_required": False})
        for index, action in enumerate(report["action_sequence"]):
            entry = {"index": index, "action": action,
                "before_pose": dict(env.pose),
                "before_simulation_time": float(env.stepper.time)}
            try:
                result = env.step(action)
                entry["result"] = {"reward": result.reward,
                    "terminated": result.terminated, "truncated": result.truncated,
                    "reason": result.reason}
            except Exception as error:
                entry["exception"] = {"type": type(error).__name__, "message": str(error)}
            entry["action_transition"] = env.telemetry.get("action_transition")
            entry["pose_validation"] = env.telemetry.get("pose_validation")
            entry["after_pose"] = dict(env.pose) if env.pose is not None else None
            entry["after_simulation_time"] = float(env.stepper.time)
            report["actions"].append(entry)
            if "exception" in entry:
                report["last_action_exception"] = entry["exception"]
                break
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
        if report.get("status") != "INFRASTRUCTURE_FAILURE":
            finalize_capture_status(report)
        report["evidence_file"] = str(output / "motion_transition_diagnostic.json")
        write_json(output / "motion_transition_diagnostic.json", report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--gui", action="store_true")
    args = parser.parse_args(argv)
    report = run_diagnostic(args.output, gui=args.gui)
    print("motion transition diagnostic: " + report["status"])
    print("target transition/body history sufficient: " +
        f"{report.get('target_transition_found')}/{report.get('world_pose_history_sufficient')}")
    print("world pose samples: " + str(report.get("world_pose_history_sample_count", 0)))
    print("evidence: " + report["evidence_file"])
    return 0 if report.get("world_pose_history_sufficient") else 1


if __name__ == "__main__":
    raise SystemExit(main())
