#!/usr/bin/env python3
"""Read-only actual-host diagnostic for production macro composition at actions 80–82."""
from __future__ import annotations

import argparse
import json
import math
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
from tools.verify_v07_gazebo_control_executor_left_to_up import validate_sources
from tools.verify_v07_gazebo_control_executor_linear_reversal import extract_reversal_replay
from tools.verify_v07_gazebo_up_to_down_production_integration import (
    _strict_json_value, find_nonfinite_paths)


EXPECTED_ACTIONS = {78: "left", 79: "right", 80: "down", 81: "up", 82: "down"}
PAIR_ROUTES = {
    ("right", "down"): ("RIGHT_TO_DOWN", "GazeboControlExecutor"),
    ("down", "up"): ("DOWN_TO_UP", "GazeboLinearReversalControlExecutor"),
    ("up", "down"): ("UP_TO_DOWN", "GazeboLinearReversalControlExecutor"),
    ("down", "left"): ("DOWN_TO_LEFT", "GazeboDownToLeftControlExecutor"),
    ("left", "up"): ("LEFT_TO_UP", "GazeboLeftToUpControlExecutor"),
}


def _safe(value):
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): _safe(child) for key, child in value.items()}
    if isinstance(value, (tuple, list)):
        return [_safe(child) for child in value]
    if hasattr(value, "to_dict"):
        return _safe(value.to_dict())
    return repr(value)


def _route(previous_action, action, previous_command, requested_command):
    transition = classify_physics_command_transition(previous_command, requested_command)
    pair = (previous_action, action)
    if previous_command != gazebo_physics_twist(previous_action):
        return transition, None, "DIRECT"
    if transition == "LINEAR_REVERSAL" and pair in PAIR_ROUTES:
        activation, executor = PAIR_ROUTES[pair]
        return transition, activation, executor
    if transition == "ROTATION_TO_LINEAR" and pair in PAIR_ROUTES:
        activation, executor = PAIR_ROUTES[pair]
        return transition, activation, executor
    if transition == "LINEAR_TO_ROTATION" and pair in PAIR_ROUTES:
        activation, executor = PAIR_ROUTES[pair]
        return transition, activation, executor
    return transition, None, "DIRECT"


def _runtime_snapshot(adapter):
    env = adapter.env
    transition = dict(env.telemetry.get("action_transition") or {})
    summary = transition.get("world_pose_history_summary") or {}
    raw_pose = transition.get("world_pose_history") or []
    timestamps = [row.get("simulation_timestamp") for row in raw_pose]
    gaps = [float(b) - float(a) for a, b in zip(timestamps, timestamps[1:])
            if isinstance(a, (int, float)) and isinstance(b, (int, float))]
    odometry = transition.get("odometry_after")
    process = getattr(env, "process", None)
    manager = getattr(adapter, "manager", None)
    contacts = getattr(env, "contacts", None)
    sensor = getattr(getattr(env, "sensors", None), "frame", None)
    stepper = getattr(env, "stepper", None)
    controller = getattr(env, "controller", None)
    return _safe({
        "simulation_time": getattr(stepper, "time", None),
        "simulation_iteration_evidence": getattr(stepper, "last_verification", None),
        "environment_step_count": getattr(env, "steps", None),
        "pose": getattr(env, "pose", None),
        "process": {"pid": getattr(process, "pid", None),
                    "poll": process.poll() if process is not None else None,
                    "manager_status": manager.status() if manager else None,
                    "partition": getattr(manager, "partition", None),
                    "world_name": getattr(env, "world_name", None)},
        "controller": {"last_command": getattr(controller, "last_command", None),
                       "last_published_command": getattr(controller,
                           "last_published_command", None),
                       "publish_sequence": getattr(controller, "publish_sequence", None)},
        "action_transition": transition,
        "retained_world_pose_history": {"summary": summary, "raw": raw_pose,
            "timestamps": timestamps, "gaps": gaps,
            "max_gap": max(gaps) if gaps else None},
        "wheel_odometry_corroboration": odometry,
        "contact_state": getattr(contacts, "state", None),
        "collision_event": getattr(env, "collision_event", None),
        "sensor_frame": {"source": getattr(sensor, "source", None),
                          "timestamp": getattr(sensor, "timestamp", None),
                          "sequence": getattr(sensor, "sequence", None)},
        "production_training_telemetry": env.telemetry.get("gazebo_dqn_training"),
        "pose_validation": env.telemetry.get("pose_validation"),
        "reset_provenance": getattr(adapter, "last_reset_evidence", None),
    })


def _validate_sources(replay, retry, failed_report):
    # Reuse exact Phase 3F-A saved-prefix provenance validation.
    from tools.verify_v07_gazebo_control_executor_left_to_up import (
        validate_sources as validate_left_up_sources)
    check = validate_left_up_sources(replay, retry)
    actions = (replay.get("completed_episode_actions") or [[]])[0]
    rows = ((retry.get("episode_replays") or [{}])[0].get("actions") or [])
    failed = failed_report.get("failed_prefix_action") or {}
    if len(actions) < 82 or [actions[index - 1] for index in range(78, 83)] != [
            EXPECTED_ACTIONS[index] for index in range(78, 83)]:
        raise ValueError("Saved Stage1 source does not match actions 78–82")
    if len(rows) < 82 or [row.get("action") for row in rows[77:82]] != [
            EXPECTED_ACTIONS[index] for index in range(78, 83)]:
        raise ValueError("Composition retry4 does not retain the expected action sequence")
    if (failed_report.get("prefix_replayed_count") != 81 or
            failed.get("index_1_based") != 82 or failed.get("action") != "down" or
            failed.get("type") != "PhysicalControlFailure"):
        raise ValueError("Phase 3F-B artifact does not prove the action-82 failure")
    return {"target": check, "source_actions_78_to_82": [
            actions[index - 1] for index in range(78, 83)],
        "retry4_actions_78_to_82": [row.get("action") for row in rows[77:82]],
        "retry4_rows_80_to_82": rows[79:82],
        "failed_run_prefix_replayed_count": 81,
        "failed_run_action": _safe(failed)}


def run_diagnostic(artifact_dir, retry_evidence_path, failed_evidence_path, output,
                   *, trials=1, gui=False, env_factory=None):
    output = Path(output)
    if trials < 1:
        raise ValueError("trials must be at least one")
    output.mkdir(parents=True, exist_ok=False)
    replay = extract_reversal_replay(Path(artifact_dir))
    retry = json.loads(Path(retry_evidence_path).read_text(encoding="utf-8"))
    failed_report = json.loads(Path(failed_evidence_path).read_text(encoding="utf-8"))
    source = _validate_sources(replay, retry, failed_report)
    reports = []
    factory = env_factory or GazeboPhysicsTrainingEnvironment
    for trial in range(1, trials + 1):
        trial_report = {"trial": trial, "status": "ARTIFACTS_VALIDATED",
            "production_behavior_modified": False, "dqn_used": False,
            "training_used": False, "actions": [], "shutdown": "NOT_ATTEMPTED",
            "source_reconstruction": source, "error": None}
        adapter = None
        current_action = None
        previous_action = None
        try:
            trial_root = output / f"trial-{trial:02d}"
            adapter = factory(ScenarioSpec.from_dict(replay["scenario"]),
                replay["max_steps"], root=trial_root / "worlds", gui=gui,
                max_sensor_age_ms=20)
            trial_report["status"] = "ENVIRONMENT_STARTED"
            adapter.reset(int(replay["training_seed"]) + 1)
            trial_report["reset_provenance"] = _safe(adapter.last_reset_evidence)
            trial_report["process_start"] = _runtime_snapshot(adapter).get("process")
            if adapter.injected or adapter.control_mode != "PHYSICS":
                raise RuntimeError("Diagnostic requires actual Gazebo PHYSICS mode")
            if adapter.process is None or adapter.process.poll() is not None:
                raise RuntimeError("Gazebo process not alive after initial reset")
            trial_report["status"] = "REPLAYING_ACTIONS_1_TO_82"
            actions = replay["completed_episode_actions"][0][:82]
            prior_action = None
            for index, action in enumerate(actions, start=1):
                current_action = index
                previous_action = prior_action
                if index in (80, 81, 82):
                    env = adapter.env
                    previous_command = dict(env.controller.last_command or {})
                    requested_command = gazebo_physics_twist(action)
                    transition = classify_physics_command_transition(
                        previous_command, requested_command)
                    _classified, route, executor = _route(prior_action, action,
                        previous_command, requested_command)
                    before = _runtime_snapshot(adapter)
                    row = {"global_action_index": index,
                        "episode_action_index": index,
                        "previous_action": prior_action, "requested_action": action,
                        "transition_classification": transition,
                        "runtime_previous_command_matches_saved_action":
                            previous_command == gazebo_physics_twist(prior_action),
                        "activation_pair_expected_from_production_source": route,
                        "selected_macro_expected_from_production_source": executor,
                        "production_environment_step_used": True,
                        "agent_decision_number_before": getattr(env, "steps", None),
                        "simulation_start": getattr(env.stepper, "time", None),
                        "previous_command": previous_command,
                        "requested_command": requested_command,
                        "command_publish_sequence_before": getattr(
                            env.controller, "publish_sequence", None),
                        "pre_action_runtime": before,
                        "status": "STEP_STARTED", "last_completed_phase": None}
                    trial_report["actions"].append(row)
                try:
                    result = adapter.step(action)
                    if index in (80, 81, 82):
                        env = adapter.env
                        training = dict(env.telemetry.get("gazebo_dqn_training") or {})
                        row.update(status="STEP_RETURNED",
                            simulation_end=float(env.stepper.time),
                            elapsed_execution_time=result.elapsed_execution_time,
                            elapsed_discount_units=result.elapsed_discount_units,
                            agent_decision_number_after=getattr(env, "steps", None),
                            control_chunk_count=(training.get("control_chunk_count") or
                                (training.get("execution_evidence") or {}).get(
                                    "control_chunk_count")),
                            actual_transition_type=training.get("transition_type"),
                            actual_activation_pair=training.get("activation_pair"),
                            actual_macro=training.get("production_macro"),
                            executed_command_sequence=(training.get(
                                "execution_evidence") or {}).get("executed_commands"),
                            production_training_evidence=training,
                            step_result={"reward": result.reward,
                                "terminated": result.terminated,
                                "truncated": result.truncated, "reason": result.reason},
                            post_action_runtime=_runtime_snapshot(adapter))
                        phases = ((training.get("execution_evidence") or {}).get(
                            "execution_phases") or [])
                        row["last_completed_phase"] = (phases[-1].get("phase")
                            if phases else "DIRECT_STEP")
                    elif result.terminated or result.truncated:
                        raise RuntimeError(f"Saved prefix terminal at action {index}")
                except Exception as error:
                    if index in (80, 81, 82):
                        row.update(status="STEP_RAISED",
                            exception={"type": type(error).__name__,
                                "message": str(error),
                                "physical_evidence": getattr(error, "evidence", None),
                                "failure_category": getattr(error,
                                    "failure_category", None)},
                            post_action_runtime=_runtime_snapshot(adapter))
                        phases = ((getattr(error, "evidence", {}) or {}).get(
                            "execution_evidence", {}).get("execution_evidence", {}).get(
                                "phase_evidence", []))
                        row["last_completed_phase"] = (phases[-1].get("phase")
                            if phases else None)
                    trial_report.update(status="FAILED", failure_action=index,
                        failure_exception={"type": type(error).__name__,
                            "message": str(error)},
                        last_completed_action=index - 1)
                    raise
                prior_action = action
            trial_report.update(status="ACTIONS_80_TO_82_COMPLETE",
                actions_1_to_82_replayed=True)
        except Exception as error:
            if trial_report.get("error") is None:
                trial_report["error"] = {"type": type(error).__name__,
                    "message": str(error)}
            if trial_report.get("status") != "FAILED":
                trial_report["status"] = "FAILED"
        finally:
            if adapter is not None:
                try:
                    trial_report["final_runtime"] = _runtime_snapshot(adapter)
                    adapter.close()
                    trial_report["shutdown"] = "PASS"
                except Exception as error:
                    trial_report["shutdown"] = "FAIL"
                    trial_report["shutdown_error"] = {"type": type(error).__name__,
                        "message": str(error)}
        reports.append(trial_report)

    report = {"schema_version": "0.7.1",
        "verifier": "read-only production macro composition diagnostic actions 80–82",
        "verdict": "MACRO_COMPOSITION_DIAGNOSTIC_COMPLETE",
        "production_behavior_modified": False, "actual_gazebo_run_by_codex": False,
        "trials_requested": trials, "source_reconstruction": source, "trials": reports}
    nonfinite = find_nonfinite_paths(report)
    report["nonfinite_field_paths"] = nonfinite
    report["json_evidence_audit"] = {"status": "PASS" if not nonfinite else "FAIL",
        "nonfinite_field_paths": nonfinite}
    path = output / "macro_composition_80_82.json"
    write_json(path, _strict_json_value(report))
    report["evidence_file"] = str(path)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--retry-evidence", type=Path, required=True)
    parser.add_argument("--failed-verifier-evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--trials", type=int, default=1)
    parser.add_argument("--gui", action="store_true")
    args = parser.parse_args(argv)
    report = run_diagnostic(args.artifact_dir, args.retry_evidence,
        args.failed_verifier_evidence, args.output, trials=args.trials, gui=args.gui)
    print("Gazebo macro composition diagnostic: " + report["trials"][0]["status"])
    print("evidence: " + report["evidence_file"])
    return 0 if all(trial["shutdown"] == "PASS" for trial in report["trials"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
