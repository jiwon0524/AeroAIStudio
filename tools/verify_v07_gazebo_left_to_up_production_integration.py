#!/usr/bin/env python3
"""Actual-host production verifier for exact LEFT→UP R2L integration."""
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
from aero_ai_studio.simulation.action_mapping import (
    gazebo_physics_action_mapping, gazebo_physics_twist)
from aero_ai_studio.simulation.base import PhysicalControlFailure
from aero_ai_studio.training.gazebo_physics import GazeboPhysicsTrainingEnvironment
from aero_ai_studio.training.temporal import NOMINAL_DISCOUNT_TIME_UNIT_SECONDS
from tools.verify_v07_gazebo_control_executor_left_to_up import validate_sources
from tools.verify_v07_gazebo_control_executor_linear_reversal import extract_reversal_replay
from tools.verify_v07_gazebo_up_to_down_production_integration import (
    _recompute_macro_reward, _strict_json_value, find_nonfinite_paths)


def _finite(value):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _phase(execution, name):
    return next((row for row in execution.get("execution_phases", [])
                 if row.get("phase") == name), None)


def _sensor_pass(sensor):
    if not isinstance(sensor, dict):
        return False
    age = _finite(sensor.get("age_ms"))
    return bool(sensor.get("source") == "gazebo_lidar" and
        type(sensor.get("sequence")) is int and sensor["sequence"] >= 0 and
        age is not None and -2. <= age <= 20. and sensor.get("dimension") == 22)


def _contact_pass(evidence):
    if not isinstance(evidence, dict):
        return False
    state = evidence.get("state") or {}
    schema = evidence.get("schema") or {}
    topic = evidence.get("expected_topic")
    return bool(evidence.get("contract_pass") is True and isinstance(state, dict) and
        isinstance(schema, dict) and isinstance(topic, str) and topic and
        state.get("topic") == topic and state.get("semantics") == "event_only" and
        isinstance(state.get("assessment"), str) and
        schema.get("message_type") == "gz.msgs.Contacts")


def assess_production_left_to_up(result, training, *, previous_command,
                                 before_steps, after_steps, process_alive,
                                 replay_payload, recomputed_reward):
    execution = training.get("execution_evidence") or {}
    # The training adapter owns the macro summary at `execution`; the
    # executor-specific physical proof is nested under `execution_evidence`.
    # Keep these authorities distinct, as reward/SMDP fields live on the
    # adapter summary while precondition/sensor/Contact fields live raw.
    raw = execution.get("execution_evidence") or {}
    brake = _phase(execution, "BRAKE_ANGULAR") or {}
    acquire = _phase(execution, "ACQUIRE_LINEAR") or {}
    phases = execution.get("execution_phases") or []
    brake_chunks = brake.get("chunks") or []
    reward_chunks = execution.get("reward_chunks") or []
    final_stop = ((brake_chunks[-1].get("body_stopped_contract") or {})
                  if brake_chunks else {})
    history_contract = acquire.get("world_pose_history_contract") or {}
    history = acquire.get("world_pose_history") or {}
    samples = history.get("world_forward_velocity_samples") or []
    forward = []
    for row in samples:
        stamp, velocity = _finite(row.get("simulation_timestamp")), _finite(
            row.get("forward_velocity"))
        if stamp is None or velocity is None:
            forward = []
            break
        forward.append((stamp, velocity))
    ordered = bool(forward and all(b[0] > a[0] for a, b in zip(forward, forward[1:])))
    first_up = next((i for i, (_, value) in enumerate(forward) if value > .02), None)
    no_opposite_after_up = bool(first_up is not None and all(
        value >= -.02 for _, value in forward[first_up:]))
    validator = acquire.get("production_pose_validation") or {}
    initial = raw.get("left_rotation_precondition") or {}
    sensor = raw.get("acquisition_sensor_evidence") or {}
    contact = raw.get("acquisition_contact_evidence") or {}
    elapsed = _finite(result.elapsed_execution_time)
    units = _finite(result.elapsed_discount_units)
    macro_reward = _finite(execution.get("macro_reward"))
    recomputed = _finite(recomputed_reward)
    action_index = next(row["index"] for row in gazebo_physics_action_mapping()
                        if row["action"] == "up")
    transition_reward = _finite(replay_payload[2]) if len(replay_payload) == 6 else None
    transition_units = _finite(replay_payload[5]) if len(replay_payload) == 6 else None
    payload_ok = bool(len(replay_payload) == 6 and replay_payload[1] == action_index and
        transition_reward is not None and transition_reward == result.reward and
        replay_payload[4] == bool(result.terminated or result.truncated) and
        units is not None and transition_units is not None and
        math.isclose(transition_units, units, rel_tol=0., abs_tol=1e-10))
    checks = {
        "exact_left_to_up_intent": training.get("agent_intent") == "up" and
            training.get("previous_action") == "left" and
            previous_command == gazebo_physics_twist("left"),
        "exact_activation_pair": training.get("transition_type") ==
            "ROTATION_TO_LINEAR" and training.get("production_macro") is True and
            training.get("activation_pair") == "LEFT_TO_UP" and
            (training.get("control_executor_activation") or {}).get("active") is True and
            (training.get("control_executor_activation") or {}).get(
                "verified_action_pair") == ["left", "up"],
        "initial_actual_left_rotation": initial.get("pass") is True and
            initial.get("world_pose_is_authority") is True and
            _finite(initial.get("end_body_angular_velocity")) is not None and
            initial["end_body_angular_velocity"] > .02 and
            any((_finite(row.get("angular_velocity")) or 0.) > .02
                for row in initial.get("world_angular_velocity_samples", [])),
        "brake_angular_then_acquire_linear": [row.get("phase") for row in phases] ==
            ["BRAKE_ANGULAR", "ACQUIRE_LINEAR"],
        "neutral_then_up_publish_order": brake.get("command") ==
            {"linear": {"x": 0.0}, "angular": {"z": 0.0}} and
            acquire.get("command") == gazebo_physics_twist("up") and
            acquire.get("command_published_after_braking") is True and
            isinstance(acquire.get("brake_completion_publish_sequence"), int) and
            isinstance(acquire.get("acquire_command_publish_sequence"), int) and
            acquire["acquire_command_publish_sequence"] >
                acquire["brake_completion_publish_sequence"],
        "world_body_stop_contract": brake.get("completion_result") is True and
            final_stop.get("pass") is True and
            final_stop.get("world_body_is_authority") is True and bool(brake_chunks),
        "up_world_body_response": history_contract.get("pass") is True and ordered and
            first_up is not None and no_opposite_after_up and
            _finite(acquire.get("end_body_forward_velocity")) is not None and
            acquire["end_body_forward_velocity"] > .02 and
            _finite(acquire.get("end_body_angular_velocity")) is not None and
            abs(acquire["end_body_angular_velocity"]) <= .02 and
            _finite(acquire.get("world_forward_displacement")) is not None and
            acquire["world_forward_displacement"] > 0.,
        "production_pose_validator": validator.get("valid") is True,
        "sensor_contract": raw.get("acquisition_sensor_contract_pass") is True and
            _sensor_pass(sensor),
        "contact_contract": _contact_pass(contact),
        "collision_explicit_false": execution.get("collision") is False and
            acquire.get("collision") is False and bool(brake_chunks) and all(
                isinstance(row.get("collision_events"), list) and
                not row["collision_events"] for row in brake_chunks),
        "process_alive": process_alive,
        "physical_status_executed": execution.get("physical_status") == "EXECUTED",
        "macro_reward_finite_and_exact": macro_reward is not None and
            _finite(result.reward) is not None and recomputed is not None and
            math.isclose(macro_reward, float(result.reward), rel_tol=0., abs_tol=1e-10) and
            math.isclose(recomputed, float(result.reward), rel_tol=0., abs_tol=1e-10),
        "reward_chunks_match_physical_chunks": bool(reward_chunks) and
            len(reward_chunks) == execution.get("control_chunk_count") ==
                len(brake_chunks) + 1 and
            sum(row.get("phase") == "BRAKE_ANGULAR" for row in reward_chunks) ==
                len(brake_chunks) and
            sum(row.get("phase") == "ACQUIRE_LINEAR" for row in reward_chunks) == 1 and
            all(_finite(row.get("reward")) is not None and
                _finite(row.get("elapsed_execution_time")) is not None
                for row in reward_chunks),
        "measured_duration_discount_units": elapsed is not None and elapsed > 0. and
            units is not None and units > 0. and
            math.isclose(units, elapsed / NOMINAL_DISCOUNT_TIME_UNIT_SECONDS,
                rel_tol=0., abs_tol=1e-8) and
            _finite(execution.get("elapsed_execution_time")) is not None and
            math.isclose(float(execution["elapsed_execution_time"]), elapsed,
                rel_tol=0., abs_tol=1e-10),
        "phase_durations_sum_to_macro": elapsed is not None and
            _finite(brake.get("elapsed_simulation_time")) is not None and
            _finite(acquire.get("elapsed_simulation_time")) is not None and
            math.isclose(float(brake["elapsed_simulation_time"])+
                float(acquire["elapsed_simulation_time"]), elapsed,
                rel_tol=0., abs_tol=1e-8),
        "one_agent_decision": int(after_steps) - int(before_steps) == 1,
        "one_six_field_up_transition": payload_ok,
        "reward_chunks_sum_to_elapsed": bool(reward_chunks) and elapsed is not None and
            math.isclose(sum(float(row["elapsed_execution_time"])
                for row in reward_chunks), elapsed, rel_tol=0., abs_tol=1e-8),
    }
    return {"checks": checks, "all_pass": all(checks.values()),
        "macro_reward_recomputed": recomputed,
        "reward_chunk_count": len(reward_chunks),
        "control_chunk_count": execution.get("control_chunk_count"),
        "elapsed_execution_time": elapsed, "elapsed_discount_units": units,
        "up_action_index": action_index}


def run_verifier(artifact_dir, failure_evidence_path, output, *, gui=False,
                 env_factory=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    report = {"schema_version": "0.7.1",
        "verifier": "production exact LEFT-to-UP ROTATION_TO_LINEAR integration",
        "status": "ARTIFACT_EXTRACTION", "verdict": "PRODUCTION_LEFT_TO_UP_INTEGRATION_FAILED",
        "failure_stage": "ARTIFACT_EXTRACTION", "last_completed_stage": None,
        "dqn_used": False, "training_used": False,
        "production_environment_step_used_for_target": False,
        "target_episode": 1, "target_action_index_in_episode_1_based": 138,
        "target_global_action_index_1_based": 138, "expected_prefix_count": 137,
        "prefix_replayed_count": 0, "target_action": "up", "acceptance": None,
        "shutdown": "NOT_ATTEMPTED", "error": None}
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
        adapter = (env_factory or GazeboPhysicsTrainingEnvironment)(
            ScenarioSpec.from_dict(replay["scenario"]), replay["max_steps"],
            root=output / "worlds", gui=gui, max_sensor_age_ms=20)
        stage = "INITIAL_RESET"
        report.update(status=stage, failure_stage=stage,
                      last_completed_stage="ENVIRONMENT_STARTUP")
        adapter.reset(int(replay["training_seed"]) + 1)
        report["reset_evidence"] = dict(adapter.last_reset_evidence)
        if adapter.injected or adapter.control_mode != "PHYSICS":
            raise RuntimeError("Verifier requires actual Gazebo PHYSICS mode")
        if adapter.process is None or adapter.process.poll() is not None:
            raise RuntimeError("Gazebo process is not alive after initial reset")
        if int(getattr(adapter, "restart_fallbacks", 0)) != 0:
            raise RuntimeError("Fresh process initialization unexpectedly used restart fallback")
        report["initial_pid"] = adapter.process.pid
        report["last_completed_stage"] = stage

        stage = "REPLAYING_PREFIX"
        report.update(status=stage, failure_stage=stage)
        prefix = replay["completed_episode_actions"][0][:137]
        rows = []
        for index, action in enumerate(prefix, start=1):
            start = float(adapter.env.stepper.time)
            try:
                step = adapter.step(action)
            except Exception as error:
                report["failed_prefix_action"] = {"index_1_based": index,
                    "action": action, "type": type(error).__name__, "message": str(error)}
                raise
            rows.append({"index_1_based": index, "action": action,
                "simulation_start": start, "simulation_end": float(adapter.env.stepper.time),
                "reason": step.reason, "terminated": step.terminated,
                "truncated": step.truncated})
            report["prefix_replayed_count"] = len(rows)
            if step.terminated or step.truncated:
                raise RuntimeError(f"Saved prefix terminated at action {index}: {step.reason}")
        report["prefix_replay"] = {"expected_count": 137,
            "replayed_count": len(rows), "actions": rows}
        report["last_completed_stage"] = stage

        env = adapter.env
        previous = dict(env.controller.last_command)
        if previous != gazebo_physics_twist("left"):
            raise RuntimeError("Action 137 did not leave LEFT as the previous command")
        before_observation = adapter.get_agent_observation("sensor", 2)
        before_steps = int(env.steps)
        start_time = float(env.stepper.time)
        stage = "EXECUTING_PRODUCTION_TARGET"
        report.update(status=stage, failure_stage=stage,
            last_completed_stage="REPLAYING_PREFIX",
            production_environment_step_used_for_target=True)
        try:
            result = adapter.step("up")
        except PhysicalControlFailure as error:
            report["target_failure"] = error.to_dict()
            raise
        report["target_physical_result_returned"] = True
        training = dict(env.telemetry.get("gazebo_dqn_training") or {})
        after_observation = adapter.get_agent_observation("sensor", 2)
        action_index = next(row["index"] for row in gazebo_physics_action_mapping()
                            if row["action"] == "up")
        transition = Transition(before_observation, "up", float(result.reward),
            after_observation, bool(result.terminated or result.truncated),
            result.elapsed_discount_units)
        payload = [observation_vector(before_observation), action_index, transition.reward,
            observation_vector(after_observation), transition.done,
            transition.elapsed_discount_units]
        execution = training.get("execution_evidence") or {}
        recomputed = _recompute_macro_reward(adapter.gamma,
            execution.get("reward_chunks") or [])
        process = adapter.manager.status()
        report["target_execution"] = {"episode": 1,
            "episode_action_index_1_based": 138, "global_action_index_1_based": 138,
            "previous_action": "left", "agent_intent": "up",
            "simulation_start": start_time,
            "simulation_end": float(env.stepper.time),
            "step_result": {"reward": result.reward,
                "terminated": result.terminated, "truncated": result.truncated,
                "reason": result.reason,
                "elapsed_execution_time": result.elapsed_execution_time,
                "elapsed_discount_units": result.elapsed_discount_units},
            "production_training_evidence": training,
            "recomputed_macro_reward": recomputed,
            "replay_transition_count": 1, "replay_transition_field_count": len(payload),
            "replay_transition_payload": payload, "dqn_replay_inserted": False}
        report["acceptance"] = assess_production_left_to_up(result, training,
            previous_command=previous, before_steps=before_steps,
            after_steps=int(env.steps),
            process_alive=(process.get("status") == "Running" and
                           process.get("available") is True),
            replay_payload=payload, recomputed_reward=recomputed)
        report["acceptance_calculation_completed"] = True
        report["process_status"] = process
        report["last_completed_stage"] = "ACCEPTANCE_COMPLETE"
        report["status"] = "ACCEPTANCE_COMPLETE"
        report["failure_stage"] = None
        report["verdict"] = ("PRODUCTION_LEFT_TO_UP_ROTATION_TO_LINEAR_ACTUAL_VERIFIED"
            if report["acceptance"]["all_pass"] else
            "PRODUCTION_LEFT_TO_UP_INTEGRATION_REJECTED")
    except Exception as error:
        report.update(status="FAILED", failure_stage=stage,
            verdict="PRODUCTION_LEFT_TO_UP_INTEGRATION_FAILED",
            error={"type": type(error).__name__, "message": str(error)})
        report["failure_category"] = ("physical_control_failure"
            if isinstance(error, PhysicalControlFailure) else "infrastructure_or_replay_failure")
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
        if isinstance(report.get("acceptance"), dict):
            report["acceptance"]["checks"]["shutdown_pass"] = report["shutdown"] == "PASS"
            report["acceptance"]["all_pass"] = all(report["acceptance"]["checks"].values())
            report["verdict"] = ("PRODUCTION_LEFT_TO_UP_ROTATION_TO_LINEAR_ACTUAL_VERIFIED"
                if report["acceptance"]["all_pass"] else
                "PRODUCTION_LEFT_TO_UP_INTEGRATION_REJECTED")
        report["evidence_file"] = str(output / "left_to_up_production_integration.json")
        nonfinite = find_nonfinite_paths(report)
        report["nonfinite_field_paths"] = nonfinite
        report["json_evidence_audit"] = {"status": "PASS" if not nonfinite else "FAIL",
            "nonfinite_field_paths": nonfinite}
        if nonfinite and isinstance(report.get("acceptance"), dict):
            report["acceptance"]["checks"]["strict_json_finite"] = False
            report["acceptance"]["all_pass"] = False
            report["status"] = "ACCEPTANCE_REJECTED"
            report["verdict"] = "PRODUCTION_LEFT_TO_UP_INTEGRATION_REJECTED"
        safe = _strict_json_value(report)
        write_json(output / "left_to_up_production_integration.json", safe)
        report.clear()
        report.update(safe)
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
    print("Gazebo production LEFT-to-UP integration: " + report["verdict"])
    print("evidence: " + report["evidence_file"])
    return 0 if report["verdict"] == \
        "PRODUCTION_LEFT_TO_UP_ROTATION_TO_LINEAR_ACTUAL_VERIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
