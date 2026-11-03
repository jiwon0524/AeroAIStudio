#!/usr/bin/env python3
"""Capture current production telemetry around Stage1 composition action 24."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aero_ai_studio.core.storage import write_json
from aero_ai_studio.scenario.models import ScenarioSpec
from aero_ai_studio.simulation.action_mapping import (
    classify_physics_command_transition, gazebo_physics_twist)
from aero_ai_studio.simulation.base import PhysicalControlFailure
from aero_ai_studio.training.gazebo_physics import GazeboPhysicsTrainingEnvironment
from tools.verify_v07_gazebo_control_executor_linear_reversal import extract_reversal_replay
from tools.verify_v07_gazebo_up_to_down_production_integration import (
    _strict_json_value, find_nonfinite_paths)


def validate_sources(replay, retry):
    actions = (replay.get("completed_episode_actions") or [[]])[0]
    failed = retry.get("failed_prefix_action") or {}
    checks = {
        "stage1_action24_is_up": len(actions) >= 24 and actions[23] == "up",
        "stage1_action23_is_down": len(actions) >= 23 and actions[22] == "down",
        "retry2_failed_at_action24": failed.get("index_1_based") == 24 and
            failed.get("action") == "up" and
            failed.get("type") == "PhysicalControlFailure",
        "retry2_prefix_count_is_23": retry.get("prefix_replayed_count") == 23,
        "retry2_did_not_call_target138":
            retry.get("production_environment_step_used_for_target") is False and
            retry.get("target_action_index_in_episode_1_based") == 138,
    }
    if not all(checks.values()):
        raise ValueError(f"Artifacts do not prove exact action-24 replay failure: {checks}")
    return {"checks": checks, "source_action_count": len(actions),
        "source_actions_19_to_29": [
            {"global_action_index": index, "action": actions[index - 1]}
            for index in range(19, 30)],
        "expected_prefix_count": 23, "failed_action_index": 24,
        "failed_action": "up", "previous_action": "down",
        "retry2_failure": failed}


def _runtime_snapshot(adapter):
    env = adapter.env
    training = dict(env.telemetry.get("gazebo_dqn_training") or {})
    transition = dict(env.telemetry.get("action_transition") or {})
    process_status = adapter.manager.status() if getattr(adapter, "manager", None) else {}
    return {
        "simulation_time": float(env.stepper.time),
        "simulation_iteration_evidence": dict(
            getattr(env.stepper, "last_verification", {}) or {}),
        "environment_step_count": getattr(env, "steps", None),
        "pose": dict(getattr(env, "pose", {}) or {}),
        "last_command": dict(getattr(env.controller, "last_command", {}) or {}),
        "last_published_command": dict(
            getattr(env.controller, "last_published_command", {}) or {}),
        "publish_sequence": getattr(env.controller, "publish_sequence", None),
        "action_transition": transition,
        "pose_validation": dict(env.telemetry.get("pose_validation") or {}),
        "production_training_telemetry": training,
        "sensor_frame": (env.sensors.frame.to_dict()
            if getattr(getattr(env, "sensors", None), "frame", None) else None),
        "contact_state": dict(getattr(getattr(env, "contacts", None), "state", {}) or {}),
        "contact_schema": getattr(getattr(env, "contacts", None), "schema", None),
        "collision_event": (None if getattr(env, "collision_event", None) is None else
            env.collision_event.to_dict()),
        "process": process_status,
        "partition": process_status.get("partition"),
        "pid": process_status.get("pid"),
    }


def run_diagnostic(artifact_dir, failure_evidence, output, *, gui=False,
                   env_factory=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    report = {"schema_version": "0.7.1",
        "verifier": "diagnostic-only current-production action-24 macro composition",
        "status": "ARTIFACT_EXTRACTION", "verdict": "ACTION24_DIAGNOSTIC_FAILED",
        "production_behavior_modified": False, "dqn_used": False, "training_used": False,
        "target_episode": 1, "target_action_index_in_episode_1_based": 24,
        "target_global_action_index_1_based": 24, "expected_prefix_count": 23,
        "prefix_replayed_count": 0, "target_production_step_call_started": False,
        "target_production_step_returned": False, "shutdown": "NOT_ATTEMPTED",
        "acceptance": None, "error": None}
    adapter = None
    stage = "ARTIFACT_EXTRACTION"
    try:
        replay = extract_reversal_replay(Path(artifact_dir))
        retry = json.loads(Path(failure_evidence).read_text(encoding="utf-8"))
        report["source_reconstruction"] = validate_sources(replay, retry)
        report["replay_source"] = {"run_id": replay.get("run_id"),
            "artifact_dir": replay.get("artifact_dir"),
            "episode_1_action_count": len(replay["completed_episode_actions"][0])}

        stage = "ENVIRONMENT_STARTUP"
        report.update(status=stage, failure_stage=stage,
                      last_completed_stage="ARTIFACT_EXTRACTION")
        adapter = (env_factory or GazeboPhysicsTrainingEnvironment)(
            ScenarioSpec.from_dict(replay["scenario"]), replay["max_steps"],
            root=output / "worlds", gui=gui, max_sensor_age_ms=20)
        stage = "INITIAL_RESET"
        report.update(status=stage, failure_stage=stage,
                      last_completed_stage="ENVIRONMENT_STARTUP")
        adapter.reset(int(replay["training_seed"]) + 1)
        report["reset_provenance"] = dict(adapter.last_reset_evidence)
        if adapter.injected or adapter.control_mode != "PHYSICS":
            raise RuntimeError("Diagnostic requires native Gazebo PHYSICS mode")
        if adapter.process is None or adapter.process.poll() is not None:
            raise RuntimeError("Gazebo process is not alive after fresh initialization")
        report["process_start"] = adapter.manager.status()
        report["last_completed_stage"] = stage

        actions = replay["completed_episode_actions"][0]
        prefix = actions[:23]
        if len(prefix) != 23:
            raise ValueError("Saved Stage1 episode has no complete action-1..23 prefix")
        stage = "REPLAYING_ACTIONS_1_TO_23"
        report.update(status=stage, failure_stage=stage)
        rows = []
        for index, action in enumerate(prefix, 1):
            start = float(adapter.env.stepper.time)
            before_command = dict(adapter.env.controller.last_command or {})
            try:
                result = adapter.step(action)
            except Exception as error:
                report["failed_prefix_action"] = {"global_action_index": index,
                    "action": action, "previous_command": before_command,
                    "type": type(error).__name__, "message": str(error),
                    "runtime": _runtime_snapshot(adapter)}
                raise
            rows.append({"global_action_index": index, "action": action,
                "previous_command": before_command,
                "simulation_start": start,
                "simulation_end": float(adapter.env.stepper.time),
                "elapsed_execution_time": result.elapsed_execution_time,
                "elapsed_discount_units": result.elapsed_discount_units,
                "reason": result.reason, "terminated": result.terminated,
                "truncated": result.truncated,
                "production_training_telemetry": dict(
                    adapter.env.telemetry.get("gazebo_dqn_training") or {})})
            report["prefix_replayed_count"] = len(rows)
            if result.terminated or result.truncated:
                raise RuntimeError(f"Production prefix terminated at action {index}")
        report["prefix_actions"] = rows
        report["last_completed_stage"] = stage

        env = adapter.env
        previous = dict(env.controller.last_command or {})
        requested = gazebo_physics_twist("up")
        transition_type = classify_physics_command_transition(previous, requested)
        report["target_pre_state"] = {
            "global_action_index": 24, "previous_action": "down",
            "requested_action": "up", "previous_command": previous,
            "requested_command": requested, "transition_type": transition_type,
            "route_condition_matches_down_to_up": previous == gazebo_physics_twist("down") and
                transition_type == "LINEAR_REVERSAL",
            "simulation_time": float(env.stepper.time), "pose": dict(env.pose),
            "world_pose_history_summary": (env.telemetry.get("action_transition") or {}).get(
                "world_pose_history_summary"),
            "wheel_odometry_corroboration": (env.telemetry.get("action_transition") or {}).get(
                "odometry_history"),
            "sensor_before": (env.telemetry.get("gazebo_dqn_training") or {}).get("sensor_after"),
            "contact_state": dict(getattr(env.contacts, "state", {}) or {}),
        }
        if previous != gazebo_physics_twist("down") or transition_type != "LINEAR_REVERSAL":
            raise RuntimeError("Replayed action 23 did not establish the expected DOWN→UP request")

        stage = "EXECUTING_PRODUCTION_ACTION_24"
        report.update(status=stage, failure_stage=stage,
                      last_completed_stage="REPLAYING_ACTIONS_1_TO_23")
        report["target_production_step_call_started"] = True
        try:
            # Keep the target on the real production adapter route.
            result = adapter.step("up")
        except Exception as error:
            report["target_exception"] = {
                "type": type(error).__name__, "message": str(error),
                "physical_failure": error.to_dict() if isinstance(
                    error, PhysicalControlFailure) else None,
                "runtime_after_failure": _runtime_snapshot(adapter)}
            report["failure_category"] = ("physical_control_failure" if isinstance(
                error, PhysicalControlFailure) else "infrastructure_or_unknown")
            report["status"] = "FAILED"
            report["failure_stage"] = stage
        else:
            report["target_production_step_returned"] = True
            report["target_result"] = {"reason": result.reason,
                "reward": result.reward, "terminated": result.terminated,
                "truncated": result.truncated,
                "elapsed_execution_time": result.elapsed_execution_time,
                "elapsed_discount_units": result.elapsed_discount_units,
                "execution_evidence": result.execution_evidence,
                "runtime_after_step": _runtime_snapshot(adapter)}
            report["status"] = "TARGET_STEP_RETURNED"
            report["failure_stage"] = None
            report["last_completed_stage"] = stage
    except Exception as error:
        report.update(status="FAILED", failure_stage=stage,
            error={"type": type(error).__name__, "message": str(error)})
        if isinstance(error, PhysicalControlFailure):
            report["failure_category"] = "physical_control_failure"
    finally:
        if adapter is not None:
            try:
                report["final_process_status"] = adapter.manager.status()
                report["shutdown"] = "PASS"
                adapter.close()
            except Exception as error:
                report["shutdown"] = "FAIL"
                report["shutdown_error"] = {"type": type(error).__name__,
                    "message": str(error)}
        report["evidence_file"] = str(output / "macro_composition_action24.json")
        paths = find_nonfinite_paths(report)
        report["nonfinite_field_paths"] = paths
        report["json_evidence_audit"] = {"status": "PASS" if not paths else "FAIL",
            "nonfinite_field_paths": paths}
        prepared = _strict_json_value(report)
        write_json(output / "macro_composition_action24.json", prepared)
        report.clear()
        report.update(prepared)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--failure-evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--gui", action="store_true")
    args = parser.parse_args(argv)
    report = run_diagnostic(args.artifact_dir, args.failure_evidence,
        args.output, gui=args.gui)
    print("Gazebo action-24 production composition diagnostic: " + report["status"])
    print("evidence: " + report["evidence_file"])
    return 0 if report.get("target_production_step_returned") else 1


if __name__ == "__main__":
    raise SystemExit(main())
