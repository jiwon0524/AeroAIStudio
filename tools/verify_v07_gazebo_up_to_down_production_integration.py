#!/usr/bin/env python3
"""Actual-host production-path verifier for the exact UP→DOWN macro."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aero_ai_studio.agents.base import Transition
from aero_ai_studio.core.storage import write_json
from aero_ai_studio.observation.encoder import observation_vector
from aero_ai_studio.scenario.models import ScenarioSpec
from aero_ai_studio.simulation.action_mapping import gazebo_physics_action_mapping, gazebo_physics_twist
from aero_ai_studio.simulation.base import PhysicalControlFailure
from aero_ai_studio.training.gazebo_physics import GazeboPhysicsTrainingEnvironment
from aero_ai_studio.training.temporal import (
    MacroRewardAccumulator,
    NOMINAL_DISCOUNT_TIME_UNIT_SECONDS,
)
from enum import Enum
from tools.verify_v07_gazebo_control_executor_up_to_down import (
    PREFIX,
    _validate_prefix_sources,
)
from tools.verify_v07_gazebo_control_executor_linear_reversal import extract_reversal_replay


def _phase(execution, name):
    return next((row for row in execution.get("execution_phases", [])
                 if row.get("phase") == name), None)


def canonical_production_execution_evidence(training):
    """Resolve the production macro summary from trainer telemetry.

    Trainer telemetry wraps the ControlExecutionResult under
    ``execution_evidence``. That production summary in turn contains a second,
    lower-level ``execution_evidence`` object. Reward/SMDP/collision fields
    belong to the former; physical phase details are read from its
    ``execution_phases`` (and nested raw evidence where needed).
    """
    if not isinstance(training, dict):
        return None
    evidence = training.get("execution_evidence")
    return evidence if isinstance(evidence, dict) else None


def _finite_number(value):
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _optional_metric(value, unavailable_reason):
    finite = _finite_number(value)
    return {"value": finite,
        "status": "AVAILABLE" if finite is not None else "UNAVAILABLE",
        "reason": None if finite is not None else unavailable_reason}


def find_nonfinite_paths(value, path="$", *, _seen=None):
    """Return exact JSON-style paths for nested NaN and +/-Inf floats."""
    if _seen is None:
        _seen = set()
    if isinstance(value, float):
        return [] if math.isfinite(value) else [path]
    if isinstance(value, dict):
        identity = id(value)
        if identity in _seen:
            return [path + "<cycle>"]
        _seen.add(identity)
        found = []
        for key, item in value.items():
            name = str(key)
            child = f"{path}.{name}" if name.isidentifier() else \
                f"{path}[{json.dumps(name, ensure_ascii=False)}]"
            found.extend(find_nonfinite_paths(item, child, _seen=_seen))
        _seen.remove(identity)
        return found
    if isinstance(value, (list, tuple)):
        identity = id(value)
        if identity in _seen:
            return [path + "<cycle>"]
        _seen.add(identity)
        found = []
        for index, item in enumerate(value):
            found.extend(find_nonfinite_paths(item, f"{path}[{index}]", _seen=_seen))
        _seen.remove(identity)
        return found
    return []


def _strict_json_value(value):
    """Convert evidence containers to strict JSON values; non-finite => null."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): _strict_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_strict_json_value(item) for item in value]
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise TypeError(f"Unsupported report evidence type: {type(value).__name__}")


def prepare_report_for_json(report):
    """Audit all evidence and prohibit acceptance when any non-finite value exists."""
    paths = find_nonfinite_paths(report)
    report["nonfinite_field_paths"] = paths
    report["json_evidence_audit"] = {
        "status": "PASS" if not paths else "FAIL",
        "classification": (None if not paths else "REQUIRED_EVIDENCE_NONFINITE"),
        "nonfinite_field_paths": list(paths),
        "representation": "non-finite numeric values are serialized as null",
    }
    if paths:
        report["failure_stage"] = report.get("failure_stage") or "REPORT_JSON_VALIDATION"
        report["error"] = report.get("error") or {
            "type": "NonFiniteEvidenceError",
            "message": "Non-finite required report evidence: " + ", ".join(paths)}
        acceptance = report.get("acceptance")
        if isinstance(acceptance, dict):
            checks = acceptance.setdefault("checks", {})
            checks["strict_json_evidence_finite"] = False
            acceptance["all_pass"] = False
            report["verdict"] = "PRODUCTION_UP_TO_DOWN_INTEGRATION_REJECTED"
            report["status"] = "ACCEPTANCE_REJECTED"
        elif report.get("target_physical_result_returned"):
            report["verdict"] = "PRODUCTION_UP_TO_DOWN_INTEGRATION_REJECTED"
            report["status"] = "FAILED"
    result = _strict_json_value(report)
    remaining = find_nonfinite_paths(result)
    if remaining:
        raise ValueError("Strict JSON preparation left non-finite fields: " +
                         ", ".join(remaining))
    return result


def _write_report_with_fallback(path, report):
    try:
        prepared = prepare_report_for_json(report)
        write_json(path, prepared)
        return prepared
    except Exception as error:
        # Preserve compact runtime facts and any serializable target evidence
        # when an unsupported nested value defeats the normal report write.
        try:
            target = report.get("target_execution") or {}
            target_evidence = _strict_json_value(
                target.get("production_training_evidence"))
        except Exception:
            target_evidence = None
        try:
            target_summary = _strict_json_value({key: target.get(key)
                for key in ("step_result", "recomputed_macro_reward",
                            "recomputed_macro_reward_status",
                            "recomputed_macro_reward_unavailable_reason",
                            "replay_transition_count", "replay_transition_field_count")
                if key in target})
        except Exception:
            target_summary = None
        fallback = {
            "schema_version": report.get("schema_version", "0.7.1"),
            "verifier": report.get("verifier"),
            "status": "REPORT_SERIALIZATION_FAILED",
            "verdict": "PRODUCTION_UP_TO_DOWN_INTEGRATION_FAILED",
            "failure_stage": "REPORT_SERIALIZATION",
            "last_completed_stage": report.get("last_completed_stage"),
            "error": {"type": type(error).__name__, "message": str(error)},
            "serialization_failure": True,
            "nonfinite_field_paths": list(report.get("nonfinite_field_paths", [])),
            "production_environment_step_used_for_target": report.get(
                "production_environment_step_used_for_target", False),
            "target_production_step_call_started": report.get(
                "target_production_step_call_started", False),
            "target_physical_result_returned": report.get(
                "target_physical_result_returned", False),
            "acceptance_calculation_completed": report.get(
                "acceptance_calculation_completed", False),
            "target_execution_summary": target_summary,
            "production_training_evidence": target_evidence,
            "acceptance": _strict_json_value(report.get("acceptance")),
            "shutdown": report.get("shutdown", "NOT_ATTEMPTED"),
        }
        write_json(path, fallback)
        return fallback


def assess_production_up_to_down(result, training, *, previous_command,
                                 before_steps, after_steps, process_alive,
                                 replay_payload, recomputed_reward):
    execution = canonical_production_execution_evidence(training) or {}
    brake = _phase(execution, "BRAKE_LINEAR")
    acquire = _phase(execution, "ACQUIRE_LINEAR")
    chunks_value = execution.get("reward_chunks")
    chunks = chunks_value if isinstance(chunks_value, list) else []
    brake_chunks = (brake or {}).get("chunks") or []
    final_stop = (brake_chunks[-1].get("body_stopped_contract", {})
                  if brake_chunks else {})
    validator = (acquire or {}).get("production_pose_validation") or {}
    history = (acquire or {}).get("world_pose_history_contract") or {}
    elapsed = _finite_number(result.elapsed_execution_time)
    units = _finite_number(result.elapsed_discount_units)
    displacement = _finite_number((acquire or {}).get("world_forward_displacement"))
    end_forward = _finite_number((acquire or {}).get("end_body_forward_velocity"))
    end_angular = _finite_number((acquire or {}).get("end_body_angular_velocity"))
    macro_reward = _finite_number(execution.get("macro_reward"))
    result_reward = _finite_number(result.reward)
    recomputed = _finite_number(recomputed_reward)
    before = int(before_steps)
    after = int(after_steps)
    body_history = (acquire or {}).get("world_pose_history") or {}
    body_velocity_samples = body_history.get("world_forward_velocity_samples", [])
    requested_direction_samples = []
    for row in body_velocity_samples:
        try:
            velocity = float(row.get("forward_velocity"))
        except (AttributeError, TypeError, ValueError):
            continue
        if math.isfinite(velocity) and velocity < -.02:
            requested_direction_samples.append(row)
    zero_command = (brake or {}).get("command") or {}
    acquire_command = (acquire or {}).get("command") or {}
    payload_reward = _finite_number(replay_payload[2]) if len(replay_payload) == 6 else None
    payload_units = _finite_number(replay_payload[5]) if len(replay_payload) == 6 else None
    transition_payload_ok = bool(len(replay_payload) == 6 and replay_payload[1] == 1 and
        result_reward is not None and payload_reward is not None and
        math.isclose(payload_reward, result_reward, rel_tol=0., abs_tol=1e-10) and
        replay_payload[4] == bool(result.terminated or result.truncated) and
        units is not None and payload_units is not None and
        math.isclose(payload_units, units, rel_tol=0., abs_tol=1e-10))
    checks = {
        "intent_down_after_up": training.get("agent_intent") == "down" and
            training.get("previous_action") == "up" and
            previous_command == gazebo_physics_twist("up"),
        "exact_transition_and_activation_pair": training.get("transition_type") ==
            "LINEAR_REVERSAL" and training.get("production_macro") is True and
            training.get("activation_pair") == "UP_TO_DOWN" and
            (training.get("control_executor_activation") or {}).get("active") is True and
            (training.get("control_executor_activation") or {}).get("activation_pair") ==
            "UP_TO_DOWN",
        "brake_then_acquire": bool(brake and acquire and
            [row.get("phase") for row in execution.get("execution_phases", [])] ==
            ["BRAKE_LINEAR", "ACQUIRE_LINEAR"]),
        "neutral_twist_during_braking": zero_command.get("linear", {}).get("x") == 0. and
            zero_command.get("angular", {}).get("z") == 0.,
        "brake_world_body_stopped": bool(final_stop.get("pass") is True and
            final_stop.get("world_body_is_authority") is True and
            len(brake_chunks) >= 1),
        "command_ordering": bool((acquire or {}).get(
            "command_published_after_braking") is True and
            isinstance((acquire or {}).get("brake_completion_event_sequence"), int) and
            isinstance((acquire or {}).get("acquire_command_publish_event_sequence"), int) and
            (acquire or {}).get("brake_completion_event_sequence") <
            (acquire or {}).get("acquire_command_publish_event_sequence")),
        "down_world_body_acquisition": bool(history.get("pass") is True and
            (acquire or {}).get("requested_direction_established") is True and
            requested_direction_samples and displacement is not None and displacement < 0. and
            end_forward is not None and end_forward < -.02 and
            acquire_command == gazebo_physics_twist("down") and end_angular is not None and
            abs(end_angular) <= .02),
        "production_validator_pass": validator.get("valid") is True,
        "sensor_contact_pass": (acquire or {}).get("sensor_contract_pass") is True and
            (acquire or {}).get("contact_contract_pass") is True,
        "collision_false": execution.get("collision") is False and
            (acquire or {}).get("collision") is False and
            bool(brake_chunks) and all(
                isinstance(row.get("collision_events"), list) and
                not row["collision_events"] for row in brake_chunks) and
            all("collision_events" not in row or
                isinstance(row.get("collision_events"), list) and
                not row["collision_events"]
                for row in ((acquire or {}), chunks[-1] if chunks else {})),
        "physical_execution_status_pass": execution.get("physical_status") == "EXECUTED",
        "process_alive": bool(process_alive),
        "macro_reward_finite_and_exact": macro_reward is not None and
            result_reward is not None and recomputed is not None and
            math.isclose(macro_reward, result_reward, rel_tol=0., abs_tol=1e-10) and
            math.isclose(recomputed, result_reward, rel_tol=0., abs_tol=1e-10),
        "elapsed_and_discount_units_measured": elapsed is not None and elapsed > 0. and
            units is not None and units > 0. and
            _finite_number(execution.get("elapsed_execution_time")) is not None and
            _finite_number(execution.get("elapsed_discount_units")) is not None and
            math.isclose(_finite_number(execution.get("elapsed_execution_time")), elapsed,
                         rel_tol=0., abs_tol=1e-10) and
            math.isclose(_finite_number(execution.get("elapsed_discount_units")), units,
                         rel_tol=0., abs_tol=1e-10) and
            math.isclose(units, elapsed / NOMINAL_DISCOUNT_TIME_UNIT_SECONDS,
                         rel_tol=0., abs_tol=1e-8),
        "one_agent_decision": after - before == 1,
        "one_six_field_down_transition": transition_payload_ok,
        "reward_chunk_count_matches_control_chunks": len(chunks) ==
            execution.get("control_chunk_count") and len(chunks) >= 2,
        "reward_chunk_durations_match_execution": bool(elapsed is not None and
            all(_finite_number(row.get("elapsed_execution_time")) is not None
                for row in chunks) and math.isclose(
                    sum(float(row["elapsed_execution_time"]) for row in chunks), elapsed,
                    rel_tol=0., abs_tol=1e-8)),
    }
    return {"checks": checks, "all_pass": all(checks.values()),
        "macro_reward_recomputed": recomputed,
        "macro_reward_recomputation_status": ("AVAILABLE" if recomputed is not None
            else "UNAVAILABLE_REQUIRED_FOR_ACCEPTANCE"),
        "reward_chunk_count": len(chunks),
        "brake_chunk_count": len(brake_chunks)}


def _recompute_macro_reward(gamma, chunks):
    if not chunks:
        return None
    accumulator = MacroRewardAccumulator(gamma, NOMINAL_DISCOUNT_TIME_UNIT_SECONDS)
    for chunk in chunks:
        accumulator.add_chunk(chunk["reward"], chunk["elapsed_execution_time"],
            terminal=bool(chunk.get("terminated") or chunk.get("truncated")))
    return accumulator.result().reward


def run_verifier(artifact_dir: Path, retry_evidence_path: Path, output: Path,
                 *, gui=False, env_factory=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    report = {"schema_version": "0.7.1",
        "verifier": "production exact UP-to-DOWN LINEAR_REVERSAL integration",
        "status": "INITIALIZING", "verdict": "PRODUCTION_UP_TO_DOWN_INTEGRATION_FAILED",
        "failure_stage": "ARTIFACT_EXTRACTION", "last_completed_stage": None,
        "dqn_used": False, "training_used": False,
        "production_environment_step_used_for_target": False,
        "target_production_step_call_started": False,
        "target_physical_result_returned": False,
        "acceptance_calculation_completed": False,
        "production_linear_reversal_routing_changed": True,
        "production_activation": True, "target_action": "down",
        "target_transition": "UP_TO_DOWN", "prefix_actions": PREFIX,
        "acceptance": None, "error": None, "shutdown": "NOT_ATTEMPTED"}
    adapter = None
    stage = "ARTIFACT_EXTRACTION"
    try:
        replay = extract_reversal_replay(Path(artifact_dir))
        retry = json.loads(Path(retry_evidence_path).read_text(encoding="utf-8"))
        source_check = _validate_prefix_sources(replay, retry)
        report["source_reconstruction"] = source_check
        report["last_completed_stage"] = "ARTIFACT_EXTRACTION"

        stage = "ENVIRONMENT_STARTUP"
        report.update(status=stage, failure_stage=stage)
        scenario = ScenarioSpec.from_dict(replay["scenario"])
        factory = env_factory or GazeboPhysicsTrainingEnvironment
        adapter = factory(scenario, replay["max_steps"], root=output / "worlds",
                          gui=gui, max_sensor_age_ms=20)
        stage = "INITIAL_RESET"
        report.update(status=stage, failure_stage=stage,
                      last_completed_stage="ENVIRONMENT_STARTUP")
        adapter.reset(int(replay["training_seed"]) + 1)
        report["reset_evidence"] = dict(adapter.last_reset_evidence)
        if adapter.injected or adapter.control_mode != "PHYSICS":
            raise RuntimeError("Verifier requires actual Gazebo transport in PHYSICS mode")
        if adapter.process is None or adapter.process.poll() is not None:
            raise RuntimeError("Gazebo process is not alive after fresh initialization")
        if int(getattr(adapter, "restart_fallbacks", 0)) != 0:
            raise RuntimeError("Fresh initialization unexpectedly used restart fallback")
        report["process"] = adapter.manager.status()
        report["initial_pid"] = adapter.process.pid
        report["last_completed_stage"] = "INITIAL_RESET"

        stage = "REPLAYING_PREFIX"
        report.update(status=stage, failure_stage=stage)
        prefix_rows = []
        for index, action in enumerate(PREFIX, start=1):
            start = float(adapter.env.stepper.time)
            try:
                prefix_result = adapter.step(action)
            except Exception as error:
                report["failed_prefix_action"] = {"index": index, "action": action,
                    "type": type(error).__name__, "message": str(error)}
                raise
            row = {"index": index, "action": action, "simulation_start": start,
                "simulation_end": float(adapter.env.stepper.time),
                "reason": prefix_result.reason, "terminated": prefix_result.terminated,
                "truncated": prefix_result.truncated}
            prefix_rows.append(row)
            if prefix_result.terminated or prefix_result.truncated:
                raise RuntimeError(f"Saved prefix became terminal at action {index}")
        report["prefix_replay"] = {"expected_count": len(PREFIX),
            "replayed_count": len(prefix_rows), "steps": prefix_rows}
        report["last_completed_stage"] = "REPLAYING_PREFIX"

        env = adapter.env
        previous_command = dict(env.controller.last_command)
        if previous_command != gazebo_physics_twist("up"):
            raise RuntimeError("Prefix did not leave UP as the previous physical command")
        report["pre_target"] = {"previous_action": "up", "requested_action": "down",
            "previous_command": previous_command,
            "requested_command": gazebo_physics_twist("down"),
            "decision_count": int(env.steps), "simulation_time": float(env.stepper.time)}
        before_observation = adapter.get_agent_observation("sensor", 2)
        before_vector = observation_vector(before_observation)
        before_steps = int(env.steps)
        start_time = float(env.stepper.time)
        stage = "EXECUTING_PRODUCTION_TARGET"
        report.update(status=stage, failure_stage=stage,
            last_completed_stage="REPLAYING_PREFIX",
            production_environment_step_used_for_target=True,
            target_production_step_call_started=True)
        try:
            result = adapter.step("down")
        except PhysicalControlFailure as error:
            report["target_failure"] = error.to_dict()
            raise
        report["target_physical_result_returned"] = True
        report["last_completed_stage"] = "TARGET_PHYSICAL_RESULT_RETURNED"
        report["failure_stage"] = "ACCEPTANCE_CALCULATION"
        report["status"] = "BUILDING_ACCEPTANCE"
        report["target_execution"] = {
            "decision_index": 6, "previous_action": "up", "agent_intent": "down",
            "simulation_start": start_time,
            "simulation_end": float(env.stepper.time),
            "step_result": {"reward": result.reward,
                "terminated": result.terminated, "truncated": result.truncated,
                "reason": result.reason,
                "elapsed_execution_time": result.elapsed_execution_time,
                "elapsed_discount_units": result.elapsed_discount_units},
            "production_training_evidence": dict(
                env.telemetry.get("gazebo_dqn_training") or {}),
        }
        after_observation = adapter.get_agent_observation("sensor", 2)
        after_vector = observation_vector(after_observation)
        training = dict(env.telemetry.get("gazebo_dqn_training") or {})
        mapping = gazebo_physics_action_mapping()
        down_index = next(row["index"] for row in mapping if row["action"] == "down")
        done = bool(result.terminated or result.truncated)
        transition = Transition(before_observation, "down", float(result.reward),
            after_observation, done, result.elapsed_discount_units)
        payload = [before_vector, down_index, transition.reward, after_vector,
            transition.done, transition.elapsed_discount_units]
        canonical_execution = canonical_production_execution_evidence(training) or {}
        chunks = canonical_execution.get("reward_chunks") or []
        try:
            recomputed = _recompute_macro_reward(adapter.gamma, chunks)
        except (TypeError, ValueError, OverflowError) as error:
            report["required_metric_failure"] = {
                "metric": "macro_reward_recomputation",
                "type": type(error).__name__, "message": str(error)}
            raise
        recomputed_metric = _optional_metric(recomputed,
            "required reward chunks were not recorded")
        process = adapter.manager.status()
        assessment = assess_production_up_to_down(result, training,
            previous_command=previous_command, before_steps=before_steps,
            after_steps=int(env.steps),
            process_alive=(process.get("status") == "Running" and
                           process.get("available") is True),
            replay_payload=payload, recomputed_reward=recomputed)
        report["target_execution"] = {"decision_index": 6,
            "previous_action": "up", "agent_intent": "down",
            "transition_type": training.get("transition_type"),
            "production_macro": training.get("production_macro"),
            "activation_pair": training.get("activation_pair"),
            "simulation_start": start_time,
            "simulation_end": float(env.stepper.time),
            "step_result": {"reward": result.reward,
                "terminated": result.terminated, "truncated": result.truncated,
                "reason": result.reason,
                "elapsed_execution_time": result.elapsed_execution_time,
                "elapsed_discount_units": result.elapsed_discount_units},
            "production_training_evidence": training,
            "recomputed_macro_reward": recomputed_metric["value"],
            "recomputed_macro_reward_status": recomputed_metric["status"],
            "recomputed_macro_reward_unavailable_reason": recomputed_metric["reason"],
            "replay_transition_count": 1,
            "replay_transition_field_count": len(payload),
            "replay_transition_payload": payload,
            "dqn_replay_inserted": False,
            "acceptance": assessment,
            "process": process}
        report["acceptance"] = assessment
        report["acceptance_calculation_completed"] = True
        report["process_status"] = process
        report["verdict"] = ("PRODUCTION_UP_TO_DOWN_LINEAR_REVERSAL_ACTUAL_VERIFIED"
            if assessment["all_pass"] else "PRODUCTION_UP_TO_DOWN_INTEGRATION_REJECTED")
        report.update(status="ACCEPTANCE_COMPLETE", failure_stage=None,
                      last_completed_stage="ACCEPTANCE_COMPLETE")
    except Exception as error:
        report.update(status="FAILED", failure_stage=stage,
            verdict="PRODUCTION_UP_TO_DOWN_INTEGRATION_FAILED",
            error={"type": type(error).__name__, "message": str(error)})
        if isinstance(error, PhysicalControlFailure):
            report["failure_category"] = "physical_control_failure"
        elif report.get("required_metric_failure") is not None:
            report["failure_category"] = "required_metric_failure"
        elif adapter is not None:
            report["failure_category"] = "infrastructure_or_replay_failure"
    finally:
        if adapter is not None:
            try:
                report["process_status"] = adapter.manager.status()
                report["reset_evidence"] = dict(adapter.last_reset_evidence)
                adapter.close()
                report["shutdown"] = "PASS"
            except Exception as error:
                report["shutdown"] = "FAIL"
                report["shutdown_error"] = {"type": type(error).__name__,
                    "message": str(error)}
        if report.get("acceptance") is not None:
            report["acceptance"]["checks"]["shutdown_pass"] = report["shutdown"] == "PASS"
            report["acceptance"]["all_pass"] = all(report["acceptance"]["checks"].values())
            report["verdict"] = ("PRODUCTION_UP_TO_DOWN_LINEAR_REVERSAL_ACTUAL_VERIFIED"
                if report["acceptance"]["all_pass"] else
                "PRODUCTION_UP_TO_DOWN_INTEGRATION_REJECTED")
        report["evidence_file"] = str(output / "up_to_down_production_integration.json")
        prepared = _write_report_with_fallback(
            output / "up_to_down_production_integration.json", report)
        report.clear()
        report.update(prepared)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--retry-evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--gui", action="store_true")
    args = parser.parse_args(argv)
    report = run_verifier(args.artifact_dir, args.retry_evidence, args.output,
                          gui=args.gui)
    print("Gazebo production UP-to-DOWN integration: " + report["verdict"])
    print("evidence: " + report["evidence_file"])
    return 0 if report["verdict"] == \
        "PRODUCTION_UP_TO_DOWN_LINEAR_REVERSAL_ACTUAL_VERIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
