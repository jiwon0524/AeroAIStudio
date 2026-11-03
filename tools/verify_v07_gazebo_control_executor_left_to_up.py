#!/usr/bin/env python3
"""DQN-free actual-host verifier for saved LEFT→UP R2L action 138."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aero_ai_studio.core.storage import write_json
from aero_ai_studio.gazebo.control_executor import GazeboLeftToUpControlExecutor
from aero_ai_studio.gazebo.entity_controller import summarize_world_pose_history
from aero_ai_studio.scenario.models import ScenarioSpec
from aero_ai_studio.simulation.action_mapping import (
    classify_physics_command_transition, gazebo_physics_twist)
from aero_ai_studio.simulation.base import PhysicalControlFailure
from aero_ai_studio.simulation.control_execution import (
    ControlExecutionRequest, ControlExecutionStatus)
from aero_ai_studio.training.gazebo_physics import GazeboPhysicsTrainingEnvironment
from aero_ai_studio.training.temporal import NOMINAL_DISCOUNT_TIME_UNIT_SECONDS
from tools.verify_v07_gazebo_control_executor_linear_reversal import extract_reversal_replay
from tools.verify_v07_gazebo_control_executor_linear_reversal import _task_outcome_callback


def _finite(value):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _nonfinite_paths(value, path="$", found=None):
    found = [] if found is None else found
    if isinstance(value, float) and not math.isfinite(value):
        found.append(path)
    elif isinstance(value, dict):
        for key, child in value.items():
            _nonfinite_paths(child, f"{path}.{key}", found)
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _nonfinite_paths(child, f"{path}[{index}]", found)
    return found


def _json_value(value):
    if isinstance(value, dict):
        return {str(key): _json_value(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(child) for child in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def validate_sources(replay, retry):
    actions = (replay.get("completed_episode_actions") or [[]])[0]
    if len(actions) < 138 or actions[137] != "up" or actions[136] != "left":
        raise ValueError("Saved Stage1 episode does not contain LEFT→UP at action 138")
    rows = ((retry.get("episode_replays") or [{}])[0].get("actions") or [])
    failed = retry.get("failed_replay_action") or {}
    if (len(rows) != 137 or [row.get("action") for row in rows] != actions[:137] or
            any(row.get("episode_action_index_1_based") != index or
                row.get("global_action_index_1_based") != index
                for index, row in enumerate(rows, start=1)) or
            failed.get("episode") != 1 or
            failed.get("episode_action_index_1_based") != 138 or
            failed.get("global_action_index_1_based") != 138 or
            failed.get("action") != "up" or
            failed.get("type") != "PhysicalControlFailure" or
            retry.get("target_episode") != 2 or
            retry.get("target_action_index_in_episode_1_based") != 40 or
            retry.get("target_global_action_index_1_based") != 290):
        raise ValueError("Retry4 does not prove the exact saved 137-action prefix and action-138 failure")
    return {"target_episode": 1, "target_action_index_in_episode_1_based": 138,
        "target_global_action_index_1_based": 138, "expected_prefix_count": 137,
        "previous_action": "left", "target_action": "up",
        "failed_action_evidence": failed, "prefix_source_match": True}


def assess_execution(result, process_status):
    data = result.to_dict()
    evidence = data.get("execution_evidence") or {}
    phases = evidence.get("phase_evidence") or []
    brake = next((row for row in phases if row.get("phase") == "BRAKE_ANGULAR"), {})
    acquire = next((row for row in phases if row.get("phase") == "ACQUIRE_LINEAR"), {})
    chunks = brake.get("chunks") or []
    stopped = (chunks[-1].get("body_stopped_contract") or {}) if chunks else {}
    history_contract = acquire.get("world_pose_history_contract") or {}
    history = acquire.get("world_pose_history") or {}
    body_samples = history.get("world_forward_velocity_samples") or []
    forward = []
    for row in body_samples:
        timestamp, velocity = _finite(row.get("simulation_timestamp")), _finite(
            row.get("forward_velocity"))
        if timestamp is None or velocity is None:
            forward = []
            break
        forward.append((timestamp, velocity))
    ordered = bool(forward and all(b[0] > a[0] for a, b in zip(forward, forward[1:])))
    first_up = next((i for i, (_, velocity) in enumerate(forward) if velocity > .02), None)
    no_opposite = bool(first_up is not None and all(
        velocity >= -.02 for _, velocity in forward[first_up:]))
    validator = acquire.get("production_pose_validation") or {}
    elapsed = _finite(data.get("elapsed_simulation_time"))
    units = None if elapsed is None else elapsed / NOMINAL_DISCOUNT_TIME_UNIT_SECONDS
    # The production action-transition record is retained in low-level phase evidence.
    publish_ordered = (acquire.get("command_published_after_braking") is True and
        isinstance(acquire.get("brake_completion_publish_sequence"), int) and
        isinstance(acquire.get("acquire_command_publish_sequence"), int) and
        acquire["acquire_command_publish_sequence"] > acquire["brake_completion_publish_sequence"])
    checks = {
        "exact_left_to_up_request": data.get("agent_intent") == "up" and
            data.get("transition_type") == "ROTATION_TO_LINEAR" and
            evidence.get("left_rotation_precondition", {}).get("pass") is True,
        "actual_left_rotation_precondition": evidence.get(
            "left_rotation_precondition", {}).get("world_pose_is_authority") is True and
            _finite(evidence.get("left_rotation_precondition", {}).get(
                "end_body_angular_velocity")) is not None and
            evidence["left_rotation_precondition"]["end_body_angular_velocity"] > .02,
        "plan_brake_angular_then_acquire_linear": [p.get("phase") for p in phases] ==
            ["BRAKE_ANGULAR", "ACQUIRE_LINEAR"],
        "neutral_brake_command": brake.get("command") ==
            {"linear": {"x": 0.0}, "angular": {"z": 0.0}},
        "world_body_stop_contract": stopped.get("pass") is True and
            stopped.get("world_body_is_authority") is True and
            brake.get("completion_result") is True and bool(chunks),
        "requested_up_command_after_braking": acquire.get("command") ==
            gazebo_physics_twist("up") and publish_ordered and
            data.get("executed_commands", [])[:1] ==
                [{"linear": {"x": 0.0}, "angular": {"z": 0.0}}] and
            data.get("executed_commands", [])[-1:] == [gazebo_physics_twist("up")],
        "fresh_dense_ordered_acquisition_pose": history_contract.get("pass") is True and ordered,
        "up_body_response_without_reversal": first_up is not None and no_opposite and
            _finite(acquire.get("end_body_forward_velocity")) is not None and
            acquire["end_body_forward_velocity"] > .02 and
            _finite(acquire.get("end_body_angular_velocity")) is not None and
            abs(acquire["end_body_angular_velocity"]) <= .02 and
            _finite(acquire.get("world_forward_displacement")) is not None and
            acquire["world_forward_displacement"] > 0.,
        "production_movement_validator": validator.get("valid") is True,
        "sensor_contract": evidence.get("acquisition_sensor_contract_pass") is True and
            (evidence.get("acquisition_sensor_evidence") or {}).get(
                "source") == "gazebo_lidar" and
            (evidence.get("acquisition_sensor_evidence") or {}).get("dimension") == 22 and
            all(_sensor_evidence_pass((row.get("task_outcome") or {}).get(
                "sensor_contract")) for row in chunks),
        "contact_healthy_and_collision_false": _contact_evidence_pass(
            evidence.get("acquisition_contact_evidence")) and
            all(_contact_evidence_pass((row.get("task_outcome") or {}))
                for row in chunks) and acquire.get("collision") is False and
            all(isinstance(row.get("collision_events"), list) and
                not row["collision_events"] for row in chunks),
        "process_healthy": process_status.get("status") == "Running" and
            process_status.get("available") is True,
        "execution_status_executed": data.get("status") == "EXECUTED",
        "measured_duration_and_discount_units": elapsed is not None and elapsed > 0. and
            units is not None and math.isclose(units,
                elapsed / NOMINAL_DISCOUNT_TIME_UNIT_SECONDS, rel_tol=0., abs_tol=1e-10),
        "phase_durations_match_total": elapsed is not None and
            _finite(brake.get("elapsed_simulation_time")) is not None and
            _finite(acquire.get("elapsed_simulation_time")) is not None and
            math.isclose(float(brake["elapsed_simulation_time"])+
                float(acquire["elapsed_simulation_time"]), elapsed,
                rel_tol=0., abs_tol=1e-8),
    }
    return {"checks": checks, "all_pass": all(checks.values()),
        "elapsed_execution_time": elapsed, "elapsed_discount_units": units,
        "brake_chunk_count": len(chunks), "phases": [row.get("phase") for row in phases]}


def _sensor_evidence_pass(sensor):
    if not isinstance(sensor, dict):
        return False
    age = _finite(sensor.get("age_ms"))
    sequence = sensor.get("sequence")
    return bool(sensor.get("source") == "gazebo_lidar" and
        type(sequence) is int and sequence >= 0 and age is not None and
        -2. <= age <= 20. and sensor.get("dimension") == 22)


def _contact_evidence_pass(evidence):
    if not isinstance(evidence, dict):
        return False
    state = evidence.get("state") or evidence.get("contact_state")
    schema = evidence.get("schema") or evidence.get("contact_schema")
    topic = evidence.get("expected_topic") or evidence.get("contact_topic")
    return bool(isinstance(state, dict) and isinstance(schema, dict) and
        isinstance(topic, str) and topic and state.get("topic") == topic and
        state.get("semantics") == "event_only" and
        isinstance(state.get("assessment"), str) and
        schema.get("message_type") == "gz.msgs.Contacts")


def run_verifier(artifact_dir, failure_evidence_path, output, *, gui=False,
                 env_factory=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    report = {"schema_version": "0.7.1",
        "verifier": "experimental actual-host LEFT-to-UP R2L executor",
        "status": "ARTIFACT_EXTRACTION", "verdict": "LEFT_TO_UP_R2L_EXECUTOR_FAILED",
        "failure_stage": "ARTIFACT_EXTRACTION", "last_completed_stage": None,
        "dqn_used": False, "training_used": False,
        "production_routing_activated": False, "target_episode": 1,
        "target_action_index_in_episode_1_based": 138,
        "target_global_action_index_1_based": 138, "prefix_replayed_count": 0,
        "execution": None, "acceptance": None, "error": None,
        "shutdown": "NOT_ATTEMPTED"}
    adapter = None
    stage = "ARTIFACT_EXTRACTION"
    try:
        replay = extract_reversal_replay(Path(artifact_dir))
        retry = json.loads(Path(failure_evidence_path).read_text(encoding="utf-8"))
        report["source_reconstruction"] = validate_sources(replay, retry)
        report["replay_source"] = {"run_id": replay["run_id"],
            "saved_run_status": replay.get("saved_run_status"),
            "episode_1_action_count": len(replay["completed_episode_actions"][0])}
        report["last_completed_stage"] = stage

        stage = "ENVIRONMENT_STARTUP"
        report.update(status=stage, failure_stage=stage)
        factory = env_factory or GazeboPhysicsTrainingEnvironment
        adapter = factory(ScenarioSpec.from_dict(replay["scenario"]),
            replay["max_steps"], root=output / "worlds", gui=gui,
            max_sensor_age_ms=20)
        stage = "INITIAL_RESET"
        report.update(status=stage, failure_stage=stage,
            last_completed_stage="ENVIRONMENT_STARTUP")
        adapter.reset(int(replay["training_seed"]) + 1)
        report["initial_reset_evidence"] = dict(adapter.last_reset_evidence)
        if adapter.injected or adapter.control_mode != "PHYSICS":
            raise RuntimeError("Verifier requires actual Gazebo transport in PHYSICS mode")
        if adapter.process is None or adapter.process.poll() is not None:
            raise RuntimeError("Gazebo process is not alive after fresh initialization")
        if int(getattr(adapter, "restart_fallbacks", 0)) != 0:
            raise RuntimeError("Fresh initialization unexpectedly used restart fallback")
        report["initial_pid"] = adapter.process.pid
        report["last_completed_stage"] = stage

        stage = "REPLAYING_PREFIX"
        report.update(status=stage, failure_stage=stage)
        prefix = replay["completed_episode_actions"][0][:137]
        rows = []
        prehistory = None
        prehistory_raw = []
        prehistory_start = None
        for index, action in enumerate(prefix, start=1):
            base = adapter.env
            before = float(base.stepper.time)
            cursor = base.transport.cursor(base.controller.pose_topic) if index == 137 else None
            try:
                step = adapter.step(action)
            except Exception as error:
                report["failed_prefix_action"] = {"index_1_based": index,
                    "action": action, "type": type(error).__name__, "message": str(error)}
                raise
            row = {"index_1_based": index, "action": action,
                "simulation_start": before, "simulation_end": float(base.stepper.time),
                "reason": step.reason, "terminated": step.terminated,
                "truncated": step.truncated}
            rows.append(row)
            report["prefix_replayed_count"] = len(rows)
            if cursor is not None:
                prehistory_start = before
                prehistory_raw = base.controller.pose_history_after(
                    cursor, before, float(base.stepper.time))
                prehistory = summarize_world_pose_history(
                    prehistory_raw, before, float(base.stepper.time))
                row["world_pose_history_summary"] = prehistory
            if step.terminated or step.truncated:
                raise RuntimeError(f"Saved prefix terminated at action {index}: {step.reason}")
        report["prefix_replay"] = {"expected_count": 137,
            "replayed_count": len(rows), "actions": rows}
        report["last_completed_stage"] = stage

        env = adapter.env
        previous = dict(env.controller.last_command)
        requested = gazebo_physics_twist("up")
        transition = classify_physics_command_transition(previous, requested)
        if previous != gazebo_physics_twist("left") or transition != "ROTATION_TO_LINEAR":
            raise RuntimeError("Saved prefix did not establish exact LEFT→UP target commands")
        sensor_sequence = int((env.telemetry.get("gazebo_dqn_training") or {}).get(
            "sensor_after", {}).get("sequence", -1))
        task_callback = _task_outcome_callback(adapter,
            initial_sensor_sequence=sensor_sequence)
        def callback(row):
            outcome = task_callback(row)
            outcome["contact_topic"] = adapter.env.contact_topic
            return outcome
        request = ControlExecutionRequest("up", previous, requested, transition)
        executor = GazeboLeftToUpControlExecutor(adapter,
            pre_braking_history=prehistory or {})
        plan = executor.plan(request)
        report["target_precondition"] = {"previous_action": "left",
            "agent_intent": "up", "transition_type": transition,
            "previous_command": previous, "requested_command": requested,
            "pre_braking_world_body_history": prehistory,
            "pre_braking_world_body_history_raw": prehistory_raw,
            "pre_braking_interval": [prehistory_start, float(env.stepper.time)]}
        stage = "EXECUTING_EXPERIMENTAL_TARGET"
        report.update(status=stage, failure_stage=stage,
            last_completed_stage="REPLAYING_PREFIX")
        result = executor.execute_plan(plan, on_braking_chunk=callback)
        process = adapter.manager.status()
        report["execution"] = result.to_dict()
        report["execution_status"] = result.status.value
        report["process_status"] = process
        report["acceptance"] = assess_execution(result, process)
        if result.status is ControlExecutionStatus.EXECUTED:
            report["last_completed_stage"] = "ACCEPTANCE_COMPLETE"
            report["status"] = "ACCEPTANCE_COMPLETE"
            report["failure_stage"] = None
            report["verdict"] = ("ROTATION_TO_LINEAR_LEFT_TO_UP_ACTUAL_PASS"
                if report["acceptance"]["all_pass"] else "LEFT_TO_UP_R2L_REJECTED")
        else:
            report["last_completed_stage"] = "TARGET_EXECUTION_RETURNED"
            report["status"] = result.status.value
            report["failure_stage"] = "TARGET_EXECUTION"
            report["verdict"] = {
                ControlExecutionStatus.PHYSICAL_CONTROL_FAILURE:
                    "LEFT_TO_UP_PHYSICAL_CONTROL_FAILURE",
                ControlExecutionStatus.INFRASTRUCTURE_FAILURE:
                    "LEFT_TO_UP_INFRASTRUCTURE_FAILURE",
                ControlExecutionStatus.INCONCLUSIVE:
                    "LEFT_TO_UP_PRECONDITION_NOT_MET",
                ControlExecutionStatus.COLLISION: "LEFT_TO_UP_COLLISION",
                ControlExecutionStatus.TASK_TERMINAL: "LEFT_TO_UP_TASK_TERMINAL",
            }.get(result.status, "LEFT_TO_UP_R2L_REJECTED")
    except Exception as error:
        report.update(status="FAILED", failure_stage=stage,
            verdict="LEFT_TO_UP_R2L_EXECUTOR_FAILED",
            error={"type": type(error).__name__, "message": str(error)})
        report["failure_category"] = ("physical_control_failure"
            if isinstance(error, PhysicalControlFailure) else "infrastructure_or_replay_failure")
    finally:
        if adapter is not None:
            try:
                report["final_process_status"] = adapter.manager.status()
                adapter.close()
                report["shutdown"] = "PASS"
            except Exception as error:
                report["shutdown"] = "FAIL"
                report["shutdown_error"] = {"type": type(error).__name__,
                    "message": str(error)}
        if isinstance(report.get("acceptance"), dict):
            report["acceptance"]["checks"]["shutdown_pass"] = report["shutdown"] == "PASS"
            report["acceptance"]["all_pass"] = all(report["acceptance"]["checks"].values())
            if report["acceptance"]["all_pass"]:
                report["verdict"] = "ROTATION_TO_LINEAR_LEFT_TO_UP_ACTUAL_PASS"
            elif report.get("execution_status") == "EXECUTED":
                report["verdict"] = "LEFT_TO_UP_R2L_REJECTED"
        report["evidence_file"] = str(output / "control_executor_left_to_up.json")
        nonfinite = _nonfinite_paths(report)
        report["nonfinite_field_paths"] = nonfinite
        if nonfinite and isinstance(report.get("acceptance"), dict):
            report["acceptance"]["checks"]["strict_json_finite"] = False
            report["acceptance"]["all_pass"] = False
            report["verdict"] = "LEFT_TO_UP_R2L_REJECTED"
            report["status"] = "ACCEPTANCE_REJECTED"
        safe = _json_value(report)
        write_json(output / "control_executor_left_to_up.json", safe)
        report = safe
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--failure-evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--gui", action="store_true")
    args = parser.parse_args(argv)
    report = run_verifier(args.artifact_dir, args.failure_evidence, args.output,
                          gui=args.gui)
    print("Gazebo LEFT-to-UP R2L executor: " + report["verdict"])
    print("evidence: " + report["evidence_file"])
    return 0 if report["verdict"] == "ROTATION_TO_LINEAR_LEFT_TO_UP_ACTUAL_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
