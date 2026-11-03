#!/usr/bin/env python3
"""Actual-host verifier for the exact production DOWN→LEFT L2R macro."""
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
from aero_ai_studio.training.temporal import (
    MacroRewardAccumulator, NOMINAL_DISCOUNT_TIME_UNIT_SECONDS)
from tools.verify_v07_gazebo_control_executor_down_to_left import PREFIX
from tools.verify_v07_gazebo_control_executor_linear_reversal import extract_reversal_replay
from tools.verify_v07_gazebo_up_to_down_production_integration import (
    _recompute_macro_reward, _strict_json_value, find_nonfinite_paths)


def _phase(execution, name):
    return next((row for row in execution.get("execution_phases", [])
                 if row.get("phase") == name), None)


def _validate_sources(replay, retry):
    actions = (replay.get("completed_episode_actions") or [[]])[0]
    if actions[:14] != PREFIX + ["left"]:
        raise ValueError("Saved Stage1 episode does not contain the exact action-14 DOWN→LEFT target")
    episode_rows = retry.get("episode_replays") or []
    rows = episode_rows[0].get("actions") or [] if episode_rows else []
    failed = retry.get("failed_replay_action") or {}
    if ([row.get("action") for row in rows] != PREFIX or
            failed.get("episode") != 1 or
            failed.get("episode_action_index_1_based") != 14 or
            failed.get("global_action_index_1_based") != 14 or
            failed.get("action") != "left" or
            failed.get("type") != "PhysicalControlFailure"):
        raise ValueError("Composition retry evidence does not prove action-14 DOWN→LEFT")
    return {"episode": 1, "target_action_index_in_episode_1_based": 14,
        "target_global_action_index_1_based": 14, "expected_prefix_count": 13,
        "prefix": PREFIX, "failure_evidence": failed, "source_match": True}


def _acceptance(result, training, previous_command, before_steps, after_steps,
                payload, process_alive, recomputed):
    execution = training.get("execution_evidence") or {}
    phases = execution.get("execution_phases") or []
    brake = _phase(execution, "BRAKE_LINEAR") or {}
    acquire = _phase(execution, "ACQUIRE_ANGULAR") or {}
    brake_chunks = brake.get("chunks") or []
    reward_chunks = execution.get("reward_chunks") or []
    last_stop = (brake_chunks[-1].get("body_stopped_contract") or {}
                 if brake_chunks else {})
    history_contract = acquire.get("world_pose_history_contract") or {}
    history = acquire.get("world_pose_history") or {}
    samples = history.get("world_angular_velocity_samples") or []
    angular = []
    for row in samples:
        try:
            t, value = float(row["simulation_timestamp"]), float(row["angular_velocity"])
        except (KeyError, TypeError, ValueError, OverflowError):
            angular = []
            break
        if not math.isfinite(t) or not math.isfinite(value):
            angular = []
            break
        angular.append((t, value))
    ordered = bool(angular and all(b[0] > a[0] for a, b in zip(angular, angular[1:])))
    epsilon = .02
    first_left = next((i for i, (_, v) in enumerate(angular) if v > epsilon), None)
    no_reverse = bool(first_left is not None and all(
        v >= -epsilon for _, v in angular[first_left:]))
    validator = acquire.get("production_pose_validation") or {}
    acquisition_collision = acquire.get("collision")
    summary_collision = execution.get("collision")
    brake_collisions_valid = bool(brake_chunks and all(
        isinstance(row.get("collision_events"), list) and not row["collision_events"]
        for row in brake_chunks))
    elapsed = result.elapsed_execution_time
    units = result.elapsed_discount_units
    action_index = next(row["index"] for row in gazebo_physics_action_mapping()
                        if row["action"] == "left")
    checks = {
        "exact_intent_and_previous_action": training.get("agent_intent") == "left" and
            training.get("previous_action") == "down" and
            previous_command == gazebo_physics_twist("down"),
        "exact_transition_and_activation": training.get("transition_type") ==
            "LINEAR_TO_ROTATION" and training.get("production_macro") is True and
            training.get("activation_pair") == "DOWN_TO_LEFT" and
            (training.get("control_executor_activation") or {}).get("active") is True,
        "plan_brake_then_acquire": [row.get("phase") for row in phases] ==
            ["BRAKE_LINEAR", "ACQUIRE_ANGULAR"],
        "neutral_command_before_left": bool(brake.get("command", {}).get("linear", {}).get("x") == 0. and
            brake.get("command", {}).get("angular", {}).get("z") == 0. and
            acquire.get("command") == gazebo_physics_twist("left") and
            acquire.get("command_published_after_braking") is True and
            isinstance(acquire.get("brake_completion_publish_sequence"), int) and
            isinstance(acquire.get("acquire_command_publish_sequence"), int) and
            acquire["brake_completion_publish_sequence"] <
            acquire["acquire_command_publish_sequence"]),
        "world_body_stopped": last_stop.get("pass") is True and
            last_stop.get("world_body_is_authority") is True and bool(brake_chunks),
        "left_angular_body_response": history_contract.get("pass") is True and ordered and
            first_left is not None and no_reverse and
            _finite(acquire.get("end_body_angular_velocity")) is not None and
            float(acquire["end_body_angular_velocity"]) > epsilon,
        "production_validator": validator.get("valid") is True,
        "sensor_and_contact": acquire.get("sensor_contract_pass") is True and
            acquire.get("contact_contract_pass") is True,
        "collision_explicitly_false": summary_collision is False and
            acquisition_collision is False and brake_collisions_valid,
        "process_healthy": process_alive,
        "physical_status_executed": execution.get("physical_status") == "EXECUTED",
        "macro_reward_finite_exact": all(_finite(value) is not None for value in
            (execution.get("macro_reward"), result.reward, recomputed)) and
            math.isclose(float(execution["macro_reward"]), float(result.reward),
                         rel_tol=0., abs_tol=1e-10) and
            math.isclose(float(recomputed), float(result.reward), rel_tol=0., abs_tol=1e-10),
        "reward_chunks_match_control_chunks": bool(reward_chunks) and
            len(reward_chunks) == execution.get("control_chunk_count") and
            len(reward_chunks) == len(brake_chunks) + 1 and
            sum(row.get("phase") == "BRAKE_LINEAR" for row in reward_chunks) ==
                len(brake_chunks) and
            sum(row.get("phase") == "ACQUIRE_ANGULAR" for row in reward_chunks) == 1 and
            all(_finite(row.get("reward")) is not None and
                _finite(row.get("elapsed_execution_time")) is not None
                for row in reward_chunks),
        "measured_elapsed_and_units": _finite(elapsed) is not None and float(elapsed) > 0. and
            _finite(units) is not None and float(units) > 0. and
            math.isclose(float(units), float(elapsed) /
                NOMINAL_DISCOUNT_TIME_UNIT_SECONDS, rel_tol=0., abs_tol=1e-8) and
            math.isclose(float(execution.get("elapsed_execution_time", math.nan)),
                float(elapsed), rel_tol=0., abs_tol=1e-10),
        "one_agent_decision": after_steps - before_steps == 1,
        "one_six_field_left_transition": len(payload) == 6 and payload[1] == action_index and
            payload[2] == result.reward and payload[4] ==
                bool(result.terminated or result.truncated) and
            math.isclose(payload[5], float(units), rel_tol=0., abs_tol=1e-10),
        "reward_chunk_durations_sum": bool(reward_chunks) and math.isclose(
            sum(float(row["elapsed_execution_time"]) for row in reward_chunks),
            float(elapsed), rel_tol=0., abs_tol=1e-8),
    }
    return {"checks": checks, "all_pass": all(checks.values()),
        "macro_reward_recomputed": recomputed,
        "reward_chunk_count": len(reward_chunks),
        "control_chunk_count": execution.get("control_chunk_count"),
        "elapsed_execution_time": elapsed, "elapsed_discount_units": units,
        "left_action_index": action_index}


def _finite(value):
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def run_verifier(artifact_dir, failure_evidence_path, output, *, gui=False,
                 env_factory=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    report = {"schema_version": "0.7.1",
        "verifier": "production exact DOWN-to-LEFT LINEAR_TO_ROTATION integration",
        "status": "INITIALIZING", "verdict": "PRODUCTION_DOWN_TO_LEFT_INTEGRATION_FAILED",
        "failure_stage": "ARTIFACT_EXTRACTION", "last_completed_stage": None,
        "dqn_used": False, "training_used": False, "production_activation": True,
        "production_environment_step_used_for_target": False,
        "target_episode": 1, "target_action_index_in_episode_1_based": 14,
        "target_global_action_index_1_based": 14, "expected_prefix_count": 13,
        "prefix_replayed_count": 0, "target_action": "left", "acceptance": None,
        "shutdown": "NOT_ATTEMPTED", "error": None}
    adapter = None
    stage = "ARTIFACT_EXTRACTION"
    try:
        replay = extract_reversal_replay(Path(artifact_dir))
        retry = json.loads(Path(failure_evidence_path).read_text(encoding="utf-8"))
        report["source_reconstruction"] = _validate_sources(replay, retry)
        report["replay_source"] = {"run_id": replay["run_id"],
            "scenario_source": replay.get("artifact_dir"),
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
            raise RuntimeError("Gazebo process is not alive after initialization")
        report["initial_pid"] = adapter.process.pid
        report["last_completed_stage"] = stage

        stage = "REPLAYING_TARGET_PREFIX"
        report.update(status=stage, failure_stage=stage)
        actions = replay["completed_episode_actions"][0][:13]
        if actions != PREFIX:
            raise ValueError("Stage1 action prefix differs from composition retry source")
        prefix_rows = []
        for index, action in enumerate(actions, start=1):
            start = float(adapter.env.stepper.time)
            try:
                step = adapter.step(action)
            except Exception as error:
                report["prefix_failure"] = {"index_1_based": index,
                    "action": action, "type": type(error).__name__, "message": str(error)}
                raise
            prefix_rows.append({"index_1_based": index, "action": action,
                "simulation_start": start, "simulation_end": float(adapter.env.stepper.time),
                "reason": step.reason, "terminated": step.terminated,
                "truncated": step.truncated})
            report["prefix_replayed_count"] = len(prefix_rows)
            if step.terminated or step.truncated:
                raise RuntimeError(f"Saved prefix became terminal at action {index}")
        report["prefix_replay"] = {"expected_count": 13,
            "replayed_count": len(prefix_rows), "actions": prefix_rows}
        report["last_completed_stage"] = stage

        env = adapter.env
        previous = dict(env.controller.last_command)
        if previous != gazebo_physics_twist("down"):
            raise RuntimeError("Action 13 did not leave exact DOWN command before target")
        before_observation = adapter.get_agent_observation("sensor", 2)
        before_steps = int(env.steps)
        start_time = float(env.stepper.time)
        stage = "EXECUTING_PRODUCTION_TARGET"
        report.update(status=stage, failure_stage=stage,
            last_completed_stage="REPLAYING_TARGET_PREFIX",
            production_environment_step_used_for_target=True)
        try:
            result = adapter.step("left")
        except PhysicalControlFailure as error:
            report["target_failure"] = error.to_dict()
            raise
        report["target_physical_result_returned"] = True
        training = dict(env.telemetry.get("gazebo_dqn_training") or {})
        after_observation = adapter.get_agent_observation("sensor", 2)
        mapping = gazebo_physics_action_mapping()
        left_index = next(row["index"] for row in mapping if row["action"] == "left")
        transition = Transition(before_observation, "left", float(result.reward),
            after_observation, bool(result.terminated or result.truncated),
            result.elapsed_discount_units)
        payload = [observation_vector(before_observation), left_index, transition.reward,
            observation_vector(after_observation), transition.done,
            transition.elapsed_discount_units]
        canonical = training.get("execution_evidence") or {}
        recomputed = _recompute_macro_reward(adapter.gamma,
            canonical.get("reward_chunks") or [])
        process = adapter.manager.status()
        report["target_execution"] = {"episode": 1, "episode_action_index_1_based": 14,
            "global_action_index_1_based": 14, "previous_action": "down",
            "agent_intent": "left", "simulation_start": start_time,
            "simulation_end": float(env.stepper.time),
            "step_result": {"reward": result.reward, "terminated": result.terminated,
                "truncated": result.truncated, "reason": result.reason,
                "elapsed_execution_time": result.elapsed_execution_time,
                "elapsed_discount_units": result.elapsed_discount_units},
            "production_training_evidence": training,
            "recomputed_macro_reward": recomputed,
            "replay_transition_count": 1, "replay_transition_field_count": len(payload),
            "replay_transition_payload": payload, "dqn_replay_inserted": False}
        acceptance = _acceptance(result, training, previous, before_steps,
            int(env.steps), payload,
            process_alive=(process.get("status") == "Running" and
                           process.get("available") is True),
            recomputed=recomputed)
        report["acceptance"] = acceptance
        report["last_completed_stage"] = "ACCEPTANCE_COMPLETE"
        report["status"] = "ACCEPTANCE_COMPLETE"
        report["failure_stage"] = None
        report["verdict"] = ("PRODUCTION_DOWN_TO_LEFT_LINEAR_TO_ROTATION_ACTUAL_VERIFIED"
            if acceptance["all_pass"] else "PRODUCTION_DOWN_TO_LEFT_INTEGRATION_REJECTED")
    except Exception as error:
        report.update(status="FAILED", failure_stage=stage,
            verdict="PRODUCTION_DOWN_TO_LEFT_INTEGRATION_FAILED",
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
            report["verdict"] = ("PRODUCTION_DOWN_TO_LEFT_LINEAR_TO_ROTATION_ACTUAL_VERIFIED"
                if report["acceptance"]["all_pass"] else
                "PRODUCTION_DOWN_TO_LEFT_INTEGRATION_REJECTED")
        report["evidence_file"] = str(output / "down_to_left_production_integration.json")
        nonfinite = find_nonfinite_paths(report)
        report["nonfinite_field_paths"] = nonfinite
        if nonfinite:
            report["json_evidence_audit"] = {"status": "FAIL",
                "nonfinite_field_paths": nonfinite}
            if isinstance(report.get("acceptance"), dict):
                report["acceptance"]["checks"]["strict_json_finite"] = False
                report["acceptance"]["all_pass"] = False
            report["status"] = "ACCEPTANCE_REJECTED" if report.get("acceptance") else "FAILED"
            report["verdict"] = "PRODUCTION_DOWN_TO_LEFT_INTEGRATION_REJECTED"
        else:
            report["json_evidence_audit"] = {"status": "PASS",
                "nonfinite_field_paths": []}
        prepared = _strict_json_value(report)
        write_json(output / "down_to_left_production_integration.json", prepared)
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
    report = run_verifier(args.artifact_dir, args.failure_evidence, args.output,
                          gui=args.gui)
    print("Gazebo production DOWN-to-LEFT integration: " + report["verdict"])
    print("evidence: " + report["evidence_file"])
    return 0 if report["verdict"] == \
        "PRODUCTION_DOWN_TO_LEFT_LINEAR_TO_ROTATION_ACTUAL_VERIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
