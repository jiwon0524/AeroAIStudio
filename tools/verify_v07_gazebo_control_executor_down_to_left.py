#!/usr/bin/env python3
"""DQN-free actual-host feedback executor check for saved DOWN-to-LEFT failure."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aero_ai_studio.core.storage import write_json
from aero_ai_studio.gazebo.control_executor import GazeboDownToLeftControlExecutor
from aero_ai_studio.gazebo.physics_feedback import BODY_STOPPED_EPSILON
from aero_ai_studio.scenario.models import ScenarioSpec
from aero_ai_studio.simulation.action_mapping import (
    classify_physics_command_transition, gazebo_physics_twist)
from aero_ai_studio.simulation.control_execution import ControlExecutionRequest, ControlExecutionStatus
from aero_ai_studio.simulation.base import PhysicalControlFailure
from aero_ai_studio.training.gazebo_physics import GazeboPhysicsTrainingEnvironment
from aero_ai_studio.training.temporal import NOMINAL_DISCOUNT_TIME_UNIT_SECONDS
from tools.verify_v07_gazebo_control_executor_linear_reversal import (
    _task_outcome_callback, extract_reversal_replay)

PREFIX = ["up", "down", "up", "up", "up", "down", "up", "right", "left",
          "up", "down", "left", "down"]


def _strict_json_evidence(value, path="$", nonfinite=None):
    if nonfinite is None:
        nonfinite = []
    if isinstance(value, float) and not math.isfinite(value):
        nonfinite.append(path)
        return None
    if isinstance(value, dict):
        return {str(key): _strict_json_evidence(item, f"{path}.{key}", nonfinite)
                for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_strict_json_evidence(item, f"{path}[{index}]", nonfinite)
                for index, item in enumerate(value)]
    return value


def validate_saved_failure_source(replay, failure_report):
    actions = replay["completed_episode_actions"][0]
    if actions[:13] != PREFIX or len(actions) < 14 or actions[13] != "left":
        raise ValueError("Saved Stage1 episode does not contain exact DOWN-to-LEFT action-14 prefix")
    episodes = failure_report.get("episode_replays") or []
    recorded = (episodes[0].get("actions") or []) if episodes else []
    failed = failure_report.get("failed_replay_action") or {}
    if ([row.get("action") for row in recorded] != PREFIX or
            failed.get("episode") != 1 or failed.get("episode_action_index_1_based") != 14 or
            failed.get("global_action_index_1_based") != 14 or failed.get("action") != "left" or
            failed.get("type") != "PhysicalControlFailure"):
        raise ValueError("Composition retry evidence does not prove exact action-14 failure")
    return {"episode": 1, "target_action_index_in_episode_1_based": 14,
        "target_global_action_index_1_based": 14, "expected_prefix_count": 13,
        "saved_prefix": PREFIX, "failure_evidence": failed, "prefix_source_match": True}


def _acceptance(execution, process_status):
    evidence = execution.execution_evidence or {}
    phases = evidence.get("phase_evidence") or []
    brake = next((row for row in phases if row.get("phase") == "BRAKE_LINEAR"), {})
    acquire = next((row for row in phases if row.get("phase") == "ACQUIRE_ANGULAR"), {})
    chunks = brake.get("chunks") or []
    history_contract = acquire.get("world_pose_history_contract") or {}
    history = acquire.get("world_pose_history") or {}
    samples = history.get("world_angular_velocity_samples") or []
    values = []
    for row in samples:
        try:
            timestamp, velocity = float(row["simulation_timestamp"]), float(row["angular_velocity"])
        except (KeyError, TypeError, ValueError, OverflowError):
            values = []
            break
        if not math.isfinite(timestamp) or not math.isfinite(velocity):
            values = []
            break
        values.append((timestamp, velocity))
    ordered = bool(values and all(b[0] > a[0] for a, b in zip(values, values[1:])))
    epsilon = BODY_STOPPED_EPSILON
    first_index = next((i for i, (_, v) in enumerate(values) if v > epsilon), None)
    no_reverse = bool(first_index is not None and all(v >= -epsilon for _, v in values[first_index:]))
    end_angular = values[-1][1] if values else None
    first_response = None if first_index is None else {
        "simulation_timestamp": values[first_index][0], "angular_velocity": values[first_index][1]}
    stopped = chunks[-1].get("body_stopped_contract", {}) if chunks else {}
    validator = acquire.get("production_pose_validation") or {}
    checks = {
        "exact_down_to_left_transition": execution.transition_type == "LINEAR_TO_ROTATION",
        "brake_then_acquire": [row.get("phase") for row in phases] ==
            ["BRAKE_LINEAR", "ACQUIRE_ANGULAR"],
        "initial_backward_body_motion": evidence.get("initial_backward_body_motion_established") is True,
        "neutral_before_left": len(execution.executed_commands) >= 2 and
            execution.executed_commands[0] == {"linear": {"x": 0.0}, "angular": {"z": 0.0}} and
            execution.executed_commands[-1] == gazebo_physics_twist("left"),
        "bounded_world_body_stop": stopped.get("pass") is True and
            stopped.get("world_body_is_authority") is True and bool(chunks),
        "fresh_dense_acquisition_pose_history": history_contract.get("pass") is True,
        "left_body_angular_acquisition": ordered and first_index is not None and no_reverse and
            end_angular is not None and end_angular > epsilon,
        "production_pose_validator": validator.get("valid") is True,
        "sensor_contract": acquire.get("sensor_contract_pass") is True,
        "contact_contract": acquire.get("contact_contract_pass") is True,
        "collision_free": acquire.get("collision") is False and bool(chunks) and all(
            isinstance(row.get("collision_events"), list) and not row["collision_events"]
            for row in chunks),
        "publish_order": acquire.get("command_published_after_braking") is True and
            isinstance(acquire.get("brake_completion_publish_sequence"), int) and
            isinstance(acquire.get("acquire_command_publish_sequence"), int) and
            acquire["acquire_command_publish_sequence"] > acquire["brake_completion_publish_sequence"],
        "process_healthy": process_status.get("status") == "Running" and
            process_status.get("available") is True,
        "execution_status_executed": execution.status is ControlExecutionStatus.EXECUTED,
        "elapsed_finite_positive": execution.elapsed_simulation_time is not None and
            math.isfinite(execution.elapsed_simulation_time) and execution.elapsed_simulation_time > 0.,
    }
    elapsed = execution.elapsed_simulation_time
    return {"checks": checks, "all_pass": all(checks.values()),
        "first_requested_angular_response": first_response,
        "final_body_angular_velocity": end_angular,
        "no_opposite_response_after_established": no_reverse,
        "control_chunk_count": len(chunks) + (1 if acquire else 0),
        "elapsed_execution_time": elapsed,
        "elapsed_discount_units": None if elapsed is None else
            elapsed / NOMINAL_DISCOUNT_TIME_UNIT_SECONDS}


def run_verifier(artifact_dir, failure_evidence_path, output, *, gui=False, env_factory=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    report = {"schema_version": "0.7.1", "verifier": "experimental DOWN-to-LEFT L2R",
        "status": "INITIALIZING", "verdict": "DOWN_TO_LEFT_L2R_EXECUTOR_FAILED",
        "failure_stage": "ARTIFACT_EXTRACTION", "last_completed_stage": None,
        "dqn_used": False, "training_used": False, "production_routing_activated": False,
        "target_episode": 1, "target_action_index_in_episode_1_based": 14,
        "target_global_action_index_1_based": 14, "prefix_actions": PREFIX,
        "prefix_replayed_count": 0, "execution": None, "acceptance": None,
        "error": None, "shutdown": "NOT_ATTEMPTED"}
    adapter = None
    try:
        replay = extract_reversal_replay(Path(artifact_dir))
        failure = json.loads(Path(failure_evidence_path).read_text(encoding="utf-8"))
        report["source_reconstruction"] = validate_saved_failure_source(replay, failure)
        report["replay_source"] = {"run_id": replay["run_id"],
            "saved_run_status": replay.get("saved_run_status"),
            "episode_action_count": len(replay["completed_episode_actions"][0])}
        report["last_completed_stage"] = "ARTIFACT_EXTRACTION"
        report.update(status="ENVIRONMENT_STARTUP", failure_stage="ENVIRONMENT_STARTUP")
        factory = env_factory or GazeboPhysicsTrainingEnvironment
        adapter = factory(ScenarioSpec.from_dict(replay["scenario"]), replay["max_steps"],
            root=output / "worlds", gui=gui, max_sensor_age_ms=20)
        report.update(status="INITIAL_RESET", failure_stage="INITIAL_RESET",
                      last_completed_stage="ENVIRONMENT_STARTUP")
        adapter.reset(int(replay["training_seed"]) + 1)
        report["reset_evidence"] = dict(adapter.last_reset_evidence)
        if adapter.injected or adapter.control_mode != "PHYSICS":
            raise RuntimeError("Verifier requires actual Gazebo transport in PHYSICS mode")
        if adapter.process is None or adapter.process.poll() is not None:
            raise RuntimeError("Gazebo process is not alive after fresh initialization")
        report["initial_pid"] = adapter.process.pid
        report["last_completed_stage"] = "INITIAL_RESET"
        report.update(status="REPLAYING_TARGET_PREFIX", failure_stage="REPLAYING_TARGET_PREFIX")
        rows = []
        for index, action in enumerate(PREFIX, start=1):
            before = float(adapter.env.stepper.time)
            try:
                result = adapter.step(action)
            except Exception as error:
                report["failed_prefix_action"] = {"index_1_based": index, "action": action,
                    "type": type(error).__name__, "message": str(error)}
                raise
            rows.append({"index_1_based": index, "action": action,
                "simulation_start": before, "simulation_end": float(adapter.env.stepper.time),
                "reason": result.reason, "terminated": result.terminated,
                "truncated": result.truncated})
            report["prefix_replayed_count"] = len(rows)
            if result.terminated or result.truncated:
                raise RuntimeError(f"Saved prefix became terminal at action {index}")
        report["prefix_replay"] = {"expected_count": 13, "replayed_count": len(rows), "actions": rows}
        report["last_completed_stage"] = "REPLAYING_TARGET_PREFIX"
        env = adapter.env
        previous = dict(env.controller.last_command)
        requested = gazebo_physics_twist("left")
        transition = classify_physics_command_transition(previous, requested)
        prehistory = dict((env.telemetry.get("action_transition") or {}).get(
            "world_pose_history_summary") or {})
        if previous != gazebo_physics_twist("down") or transition != "LINEAR_TO_ROTATION":
            raise RuntimeError("Replayed prefix did not establish exact DOWN-to-LEFT target")
        sensor_sequence = int((env.telemetry.get("gazebo_dqn_training") or {}).get(
            "sensor_after", {}).get("sequence", -1))
        callback = _task_outcome_callback(adapter, initial_sensor_sequence=sensor_sequence)
        request = ControlExecutionRequest("left", previous, requested, transition)
        executor = GazeboDownToLeftControlExecutor(adapter, pre_braking_history=prehistory)
        report["target_precondition"] = {"previous_action": "down", "agent_intent": "left",
            "transition_type": transition, "previous_command": previous,
            "requested_command": requested, "pre_braking_world_body_history": prehistory}
        report.update(status="EXECUTING_EXPERIMENTAL_TARGET",
            failure_stage="EXECUTING_EXPERIMENTAL_TARGET",
            last_completed_stage="REPLAYING_TARGET_PREFIX")
        start = float(env.stepper.time)
        execution = executor.execute_plan(executor.plan(request), on_braking_chunk=callback)
        process = adapter.manager.status()
        bounded_plan = {"request": request.to_dict(),
            "phases": [phase.to_dict() for phase in execution.phases],
            "requires_execution_bound": False}
        report["execution"] = {"plan": bounded_plan,
            "result": execution.to_dict(), "phase_evidence":
                execution.to_dict().get("execution_evidence", {}).get("phase_evidence", []),
            "elapsed_execution_time": float(env.stepper.time) - start,
            "elapsed_discount_units": (float(env.stepper.time) - start) /
                NOMINAL_DISCOUNT_TIME_UNIT_SECONDS,
            "step_result": None if execution.step_result is None else {
                "reason": execution.step_result.reason,
                "terminated": execution.step_result.terminated,
                "truncated": execution.step_result.truncated,
                "pose_validation": env.telemetry.get("pose_validation")},
            "process_status": process}
        report["acceptance"] = _acceptance(execution, process)
        report["last_completed_stage"] = "ACCEPTANCE_COMPLETE"
        report["status"] = "ACCEPTANCE_COMPLETE"
        report["failure_stage"] = None
        report["verdict"] = ("LINEAR_TO_ROTATION_DOWN_TO_LEFT_ACTUAL_PASS"
            if report["acceptance"]["all_pass"] else
            "LINEAR_TO_ROTATION_DOWN_TO_LEFT_REJECTED")
    except Exception as error:
        report.update(status="FAILED", verdict="DOWN_TO_LEFT_L2R_EXECUTOR_FAILED",
            error={"type": type(error).__name__, "message": str(error)},
            failure_category="physical_control_failure" if isinstance(error, PhysicalControlFailure)
                else "infrastructure_or_replay_failure")
    finally:
        if adapter is not None:
            try:
                report["process_status"] = adapter.manager.status()
                adapter.close()
                report["shutdown"] = "PASS"
            except Exception as error:
                report["shutdown"] = "FAIL"
                report["shutdown_error"] = {"type": type(error).__name__, "message": str(error)}
        if report.get("acceptance") is not None:
            report["acceptance"]["checks"]["shutdown_pass"] = report["shutdown"] == "PASS"
            report["acceptance"]["all_pass"] = all(report["acceptance"]["checks"].values())
            if not report["acceptance"]["all_pass"]:
                report["verdict"] = "LINEAR_TO_ROTATION_DOWN_TO_LEFT_REJECTED"
        report["evidence_file"] = str(output / "down_to_left_control_executor.json")
        nonfinite = []
        report = _strict_json_evidence(report, nonfinite=nonfinite)
        report["nonfinite_field_paths"] = nonfinite
        if nonfinite and report.get("acceptance") is not None:
            report["acceptance"]["checks"]["strict_json_evidence_finite"] = False
            report["acceptance"]["all_pass"] = False
            report["verdict"] = "LINEAR_TO_ROTATION_DOWN_TO_LEFT_REJECTED"
        write_json(output / "down_to_left_control_executor.json", report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--failure-evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--gui", action="store_true")
    args = parser.parse_args(argv)
    report = run_verifier(args.artifact_dir, args.failure_evidence, args.output, gui=args.gui)
    print("Gazebo DOWN-to-LEFT L2R executor: " + report["verdict"])
    print("evidence: " + report["evidence_file"])
    return 0 if report["verdict"] == "LINEAR_TO_ROTATION_DOWN_TO_LEFT_ACTUAL_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
