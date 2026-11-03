#!/usr/bin/env python3
"""Actual-host verifier for the exact production UP→RIGHT L2R macro."""
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
from tools.verify_v07_gazebo_control_executor_up_to_right import PREFIX
from tools.verify_v07_gazebo_control_executor_linear_reversal import extract_reversal_replay
from tools.verify_v07_gazebo_up_to_down_production_integration import (
    _recompute_macro_reward, _strict_json_value, find_nonfinite_paths)


def _finite(value):
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _phase(execution, name):
    return next((row for row in execution.get("execution_phases", [])
                 if row.get("phase") == name), {})


def _validate_sources(replay, actual_executor):
    actions = (replay.get("completed_episode_actions") or [[]])[0]
    if actions[:8] != PREFIX + ["right"]:
        raise ValueError("Saved Stage1 episode does not contain exact action-8 UP→RIGHT")
    acceptance = actual_executor.get("acceptance") or {}
    execution = actual_executor.get("execution") or {}
    if (actual_executor.get("verdict") != "UP_TO_RIGHT_L2R_ACTUAL_PASS" or
            acceptance.get("all_pass") is not True or execution.get("status") != "EXECUTED"):
        raise ValueError("Phase 3G-A actual UP→RIGHT executor evidence is not PASS")
    return {"target_episode": 1, "target_action_index_in_episode_1_based": 8,
        "target_global_action_index_1_based": 8, "expected_prefix_count": 7,
        "prefix_actions": list(PREFIX), "target_action": "right",
        "actual_executor_verdict": actual_executor.get("verdict"),
        "actual_executor_evidence": str(actual_executor.get("evidence_file")),
        "source_match": True}


def assess_production_up_to_right(result, training, previous_command, before_steps,
                                  after_steps, payload, process_alive, recomputed):
    execution = training.get("execution_evidence") or {}
    raw = execution.get("execution_evidence") or {}
    phases = execution.get("execution_phases") or []
    brake = _phase(execution, "BRAKE_LINEAR")
    acquire = _phase(execution, "ACQUIRE_ANGULAR")
    chunks = brake.get("chunks") or []
    rewards = execution.get("reward_chunks") or []
    stop = chunks[-1].get("body_stopped_contract") or {} if chunks else {}
    history_contract = acquire.get("world_pose_history_contract") or {}
    history = acquire.get("world_pose_history") or {}
    angular_samples = history.get("world_angular_velocity_samples") or []
    angular = []
    for row in angular_samples:
        stamp, value = _finite(row.get("simulation_timestamp")), _finite(row.get("angular_velocity"))
        if stamp is None or value is None:
            angular = []
            break
        angular.append((stamp, value))
    ordered = bool(angular and all(b[0] > a[0] for a, b in zip(angular, angular[1:])))
    epsilon = .02
    first_right = next((i for i, (_, value) in enumerate(angular) if value < -epsilon), None)
    no_opposite = bool(first_right is not None and all(
        value <= epsilon for _, value in angular[first_right:]))
    validator = acquire.get("production_pose_validation") or {}
    brake_collision_rows = bool(chunks) and all(
        isinstance(row.get("collision_events"), list) and not row["collision_events"]
        for row in chunks)
    elapsed, units = _finite(result.elapsed_execution_time), _finite(result.elapsed_discount_units)
    right_index = next(row["index"] for row in gazebo_physics_action_mapping()
                       if row["action"] == "right")
    action_index = payload[1] if len(payload) == 6 else None
    macro_reward = _finite(execution.get("macro_reward"))
    checks = {
        "exact_up_to_right_intent": training.get("agent_intent") == "right" and
            training.get("previous_action") == "up" and
            previous_command == gazebo_physics_twist("up"),
        "exact_production_activation": training.get("transition_type") ==
            "LINEAR_TO_ROTATION" and training.get("production_macro") is True and
            training.get("activation_pair") == "UP_TO_RIGHT" and
            (training.get("control_executor_activation") or {}).get("active") is True and
            (training.get("control_executor_activation") or {}).get(
                "verified_action_pair") == ["up", "right"],
        "brake_then_acquire": [row.get("phase") for row in phases] ==
            ["BRAKE_LINEAR", "ACQUIRE_ANGULAR"],
        "neutral_before_right_by_publish_sequence": brake.get("command") ==
            {"linear": {"x": 0.0}, "angular": {"z": 0.0}} and
            acquire.get("command") == gazebo_physics_twist("right") and
            acquire.get("command_published_after_braking") is True and
            isinstance(acquire.get("brake_completion_publish_sequence"), int) and
            isinstance(acquire.get("acquire_command_publish_sequence"), int) and
            acquire["brake_completion_publish_sequence"] <
            acquire["acquire_command_publish_sequence"],
        "actual_up_body_precondition": raw.get("initial_source_body_motion_established") is True and
            raw.get("source_action") == "up",
        "world_body_stopped": bool(chunks) and stop.get("pass") is True and
            stop.get("world_body_is_authority") is True,
        "right_angular_world_body_response": history_contract.get("pass") is True and
            ordered and first_right is not None and no_opposite and
            _finite(acquire.get("end_body_angular_velocity")) is not None and
            float(acquire["end_body_angular_velocity"]) < -epsilon,
        "production_validator": validator.get("valid") is True,
        "sensor_contact_healthy": acquire.get("sensor_contract_pass") is True and
            acquire.get("contact_contract_pass") is True,
        "authoritative_collision_false": execution.get("collision") is False and
            acquire.get("collision") is False and brake_collision_rows,
        "process_healthy": process_alive,
        "physical_status_executed": execution.get("physical_status") == "EXECUTED",
        "macro_reward_finite_and_exact": macro_reward is not None and
            _finite(result.reward) is not None and _finite(recomputed) is not None and
            math.isclose(macro_reward, float(result.reward), rel_tol=0., abs_tol=1e-10) and
            math.isclose(float(recomputed), float(result.reward), rel_tol=0., abs_tol=1e-10),
        "reward_chunks_match_physics_chunks": bool(rewards) and
            len(rewards) == execution.get("control_chunk_count") == len(chunks) + 1 and
            sum(row.get("phase") == "BRAKE_LINEAR" for row in rewards) == len(chunks) and
            sum(row.get("phase") == "ACQUIRE_ANGULAR" for row in rewards) == 1 and
            all(_finite(row.get("reward")) is not None and
                _finite(row.get("elapsed_execution_time")) is not None for row in rewards),
        "measured_duration_and_discount_units": elapsed is not None and elapsed > 0 and
            units is not None and units > 0 and math.isclose(units,
                elapsed / NOMINAL_DISCOUNT_TIME_UNIT_SECONDS, rel_tol=0., abs_tol=1e-8) and
            math.isclose(float(execution.get("elapsed_execution_time", math.nan)),
                         elapsed, rel_tol=0., abs_tol=1e-10),
        "one_agent_decision": after_steps - before_steps == 1,
        "one_six_field_right_transition": len(payload) == 6 and action_index == right_index and
            payload[2] == result.reward and payload[4] ==
                bool(result.terminated or result.truncated) and units is not None and
            math.isclose(float(payload[5]), units, rel_tol=0., abs_tol=1e-10),
        "reward_chunk_durations_sum": bool(rewards) and elapsed is not None and
            math.isclose(sum(float(row["elapsed_execution_time"]) for row in rewards),
                         elapsed, rel_tol=0., abs_tol=1e-8),
    }
    return {"checks": checks, "all_pass": all(checks.values()),
        "macro_reward_recomputed": recomputed, "reward_chunk_count": len(rewards),
        "control_chunk_count": execution.get("control_chunk_count"),
        "elapsed_execution_time": elapsed, "elapsed_discount_units": units,
        "right_action_index": right_index}


def run_verifier(artifact_dir, executor_evidence_path, output, *, gui=False,
                 env_factory=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    report = {"schema_version": "0.7.1",
        "verifier": "production exact UP→RIGHT LINEAR_TO_ROTATION integration",
        "status": "ARTIFACT_EXTRACTION", "verdict": "PRODUCTION_UP_TO_RIGHT_INTEGRATION_FAILED",
        "failure_stage": "ARTIFACT_EXTRACTION", "last_completed_stage": None,
        "dqn_used": False, "training_used": False, "production_activation": True,
        "production_environment_step_used_for_target": False,
        "target_episode": 1, "target_action_index_in_episode_1_based": 8,
        "target_global_action_index_1_based": 8, "expected_prefix_count": 7,
        "prefix_replayed_count": 0, "target_action": "right", "acceptance": None,
        "shutdown": "NOT_ATTEMPTED", "error": None}
    adapter = None
    stage = "ARTIFACT_EXTRACTION"
    try:
        replay = extract_reversal_replay(Path(artifact_dir))
        actual_executor = json.loads(Path(executor_evidence_path).read_text(encoding="utf-8"))
        report["source_reconstruction"] = _validate_sources(replay, actual_executor)
        report["phase3ga_actual_evidence"] = {
            "verdict": actual_executor.get("verdict"),
            "evidence_file": str(executor_evidence_path),
            "acceptance": actual_executor.get("acceptance"),
            "execution": actual_executor.get("execution"),
        }
        report["replay_source"] = {"run_id": replay["run_id"],
            "scenario_source": replay.get("artifact_dir"),
            "episode_1_action_count": len(replay["completed_episode_actions"][0])}

        stage = "ENVIRONMENT_STARTUP"
        report.update(status=stage, failure_stage=stage, last_completed_stage="ARTIFACT_EXTRACTION")
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
            raise RuntimeError("Gazebo process is not alive after initialization")
        report["initial_pid"] = adapter.process.pid
        report["last_completed_stage"] = stage

        stage = "REPLAYING_PRODUCTION_PREFIX"
        report.update(status=stage, failure_stage=stage)
        actions = replay["completed_episode_actions"][0][:7]
        if actions != PREFIX:
            raise ValueError("Saved action prefix differs from Phase 3G-A source sequence")
        prefix_rows = []
        for index, action in enumerate(actions, start=1):
            start = float(adapter.env.stepper.time)
            try:
                step = adapter.step(action)
            except Exception as error:
                report["prefix_failure"] = {"index_1_based": index, "action": action,
                    "type": type(error).__name__, "message": str(error)}
                raise
            prefix_rows.append({"index_1_based": index, "action": action,
                "simulation_start": start, "simulation_end": float(adapter.env.stepper.time),
                "reason": step.reason, "terminated": step.terminated,
                "truncated": step.truncated})
            report["prefix_replayed_count"] = len(prefix_rows)
            if step.terminated or step.truncated:
                raise RuntimeError(f"Production prefix became terminal at action {index}")
        report["prefix_replay"] = {"expected_count": 7, "replayed_count": 7,
            "actions": prefix_rows}
        report["last_completed_stage"] = stage

        env = adapter.env
        previous = dict(env.controller.last_command)
        if previous != gazebo_physics_twist("up"):
            raise RuntimeError("Action 7 did not leave exact UP command before target")
        before_observation = adapter.get_agent_observation("sensor", 2)
        before_steps = int(env.steps)
        start_time = float(env.stepper.time)
        stage = "EXECUTING_PRODUCTION_TARGET"
        report.update(status=stage, failure_stage=stage,
            last_completed_stage="REPLAYING_PRODUCTION_PREFIX")
        report["target_production_step_call_started"] = True
        report["production_environment_step_used_for_target"] = True
        try:
            result = adapter.step("right")
        except PhysicalControlFailure as error:
            report["target_failure"] = error.to_dict()
            raise
        report["target_physical_result_returned"] = True
        training = dict(env.telemetry.get("gazebo_dqn_training") or {})
        after_observation = adapter.get_agent_observation("sensor", 2)
        right_index = next(row["index"] for row in gazebo_physics_action_mapping()
                           if row["action"] == "right")
        transition = Transition(before_observation, "right", float(result.reward),
            after_observation, bool(result.terminated or result.truncated),
            result.elapsed_discount_units)
        payload = [observation_vector(before_observation), right_index, transition.reward,
            observation_vector(after_observation), transition.done,
            transition.elapsed_discount_units]
        canonical = training.get("execution_evidence") or {}
        recomputed = _recompute_macro_reward(adapter.gamma, canonical.get("reward_chunks") or [])
        process = adapter.manager.status()
        report["target_execution"] = {"episode": 1, "episode_action_index_1_based": 8,
            "global_action_index_1_based": 8, "previous_action": "up", "agent_intent": "right",
            "simulation_start": start_time, "simulation_end": float(env.stepper.time),
            "step_result": {"reward": result.reward, "terminated": result.terminated,
                "truncated": result.truncated, "reason": result.reason,
                "elapsed_execution_time": result.elapsed_execution_time,
                "elapsed_discount_units": result.elapsed_discount_units},
            "production_training_evidence": training,
            "macro_reward_recomputed": recomputed,
            "replay_transition_count": 1, "replay_transition_field_count": len(payload),
            "replay_transition_payload": payload, "dqn_replay_inserted": False}
        acceptance = assess_production_up_to_right(result, training, previous,
            before_steps, int(env.steps), payload,
            process_alive=(process.get("status") == "Running" and
                           process.get("available") is True), recomputed=recomputed)
        report["acceptance"] = acceptance
        report["status"] = "ACCEPTANCE_COMPLETE"
        report["last_completed_stage"] = "ACCEPTANCE_COMPLETE"
        report["failure_stage"] = None
        report["verdict"] = ("PRODUCTION_UP_TO_RIGHT_LINEAR_TO_ROTATION_ACTUAL_VERIFIED"
            if acceptance["all_pass"] else "PRODUCTION_UP_TO_RIGHT_INTEGRATION_REJECTED")
    except Exception as error:
        report.update(status="FAILED", failure_stage=stage,
            verdict="PRODUCTION_UP_TO_RIGHT_INTEGRATION_FAILED",
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
        if report.get("acceptance") is not None:
            report["acceptance"]["checks"]["shutdown_pass"] = report["shutdown"] == "PASS"
            report["acceptance"]["all_pass"] = all(report["acceptance"]["checks"].values())
            report["verdict"] = ("PRODUCTION_UP_TO_RIGHT_LINEAR_TO_ROTATION_ACTUAL_VERIFIED"
                if report["acceptance"]["all_pass"] else "PRODUCTION_UP_TO_RIGHT_INTEGRATION_REJECTED")
        report["evidence_file"] = str(output / "up_to_right_production_integration.json")
        nonfinite = find_nonfinite_paths(report)
        report["nonfinite_field_paths"] = nonfinite
        report["json_evidence_audit"] = {"status": "PASS" if not nonfinite else "FAIL",
            "nonfinite_field_paths": nonfinite}
        if nonfinite:
            if isinstance(report.get("acceptance"), dict):
                report["acceptance"]["checks"]["strict_json_finite"] = False
                report["acceptance"]["all_pass"] = False
            report["status"] = "ACCEPTANCE_REJECTED" if report.get("acceptance") else "FAILED"
            report["verdict"] = "PRODUCTION_UP_TO_RIGHT_INTEGRATION_REJECTED"
        prepared = _strict_json_value(report)
        write_json(output / "up_to_right_production_integration.json", prepared)
        report.clear()
        report.update(prepared)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--executor-evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--gui", action="store_true")
    args = parser.parse_args(argv)
    report = run_verifier(args.artifact_dir, args.executor_evidence,
        args.output, gui=args.gui)
    print("Gazebo production UP-to-RIGHT integration: " + report["verdict"])
    print("evidence: " + report["evidence_file"])
    return 0 if report["verdict"] == \
        "PRODUCTION_UP_TO_RIGHT_LINEAR_TO_ROTATION_ACTUAL_VERIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
