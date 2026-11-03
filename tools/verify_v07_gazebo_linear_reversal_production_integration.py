#!/usr/bin/env python3
"""Actual-host verifier for the exact production DOWN→UP macro integration.

Replays the saved Stage 1 episode/action prefix through the production PHYSICS
environment, then calls ``GazeboPhysicsTrainingEnvironment.step('up')`` at the
saved LINEAR_REVERSAL target. It does not instantiate or train a DQN.
"""
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
    classify_physics_command_transition,
    gazebo_physics_action_mapping,
    gazebo_physics_twist,
)
from aero_ai_studio.simulation.base import PhysicalControlFailure
from aero_ai_studio.training.gazebo_physics import (
    LINEAR_REVERSAL_VERIFIED_ACTION_PAIR,
    GazeboPhysicsTrainingEnvironment,
)
from aero_ai_studio.training.temporal import NOMINAL_DISCOUNT_TIME_UNIT_SECONDS
from tools.verify_v07_gazebo_control_executor_linear_reversal import (
    _episode_boundary_reset_gate,
    extract_reversal_replay,
)


def _phase(evidence, name):
    phases = evidence.get("execution_phases") or (
        (evidence.get("execution_evidence") or {}).get("phase_evidence") or [])
    return next((item for item in phases if item.get("phase") == name), None)


def assess_production_macro(result, evidence, *, previous_command, before_steps,
                            after_steps, process_alive, replay_transition):
    """Return deterministic acceptance predicates for a production macro result."""
    activation = evidence.get("control_executor_activation") or {}
    execution = evidence.get("execution_evidence") or result.execution_evidence or {}
    brake = _phase(execution, "BRAKE_LINEAR")
    acquire = _phase(execution, "ACQUIRE_LINEAR")
    brake_stopped = bool(brake and brake.get("completion_result") is True and
        brake.get("chunks") and brake["chunks"][-1].get(
            "body_stopped_contract", {}).get("pass") is True)
    ordering = bool(acquire and
        acquire.get("command_published_after_braking") is True and
        isinstance(acquire.get("brake_completion_event_sequence"), int) and
        isinstance(acquire.get("acquire_command_publish_event_sequence"), int) and
        acquire["brake_completion_event_sequence"] <
        acquire["acquire_command_publish_event_sequence"])
    validator = (acquire or {}).get("production_pose_validation") or {}
    history = (acquire or {}).get("world_pose_history_contract") or {}
    acquisition_body = bool(acquire and history.get("pass") is True and
        acquire.get("requested_direction_established") is True and
        float(acquire.get("world_forward_displacement", 0.)) > 0. and
        float(acquire.get("end_body_forward_velocity", 0.)) > .02)
    elapsed = float(result.elapsed_execution_time or 0.)
    units = float(result.elapsed_discount_units)
    rewards = evidence.get("reward_chunks") or []
    checks = {
        "agent_intent_up": evidence.get("agent_intent") == "up",
        "previous_action_down": evidence.get("previous_action") == "down",
        "previous_command_down": previous_command == gazebo_physics_twist("down"),
        "transition_linear_reversal": evidence.get("transition_type") == "LINEAR_REVERSAL",
        "production_macro_active": evidence.get("production_macro") is True and
            activation.get("active") is True,
        "exact_activation_pair": evidence.get("activation_pair") == "DOWN_TO_UP" and
            activation.get("activation_pair") == "DOWN_TO_UP",
        "brake_and_acquire_present": brake is not None and acquire is not None,
        "brake_world_body_stopped": brake_stopped,
        "brake_before_acquire_publish": ordering,
        "acquisition_world_body_valid": acquisition_body,
        "production_validator_pass": validator.get("valid") is True,
        "collision_false": evidence.get("collision") is False and
            (acquire or {}).get("collision") is False,
        "sensor_contract_pass": (acquire or {}).get("sensor_contract_pass") is True,
        "contact_contract_pass": (acquire or {}).get("contact_contract_pass") is True,
        "process_alive": bool(process_alive),
        "macro_reward_finite": math.isfinite(float(evidence.get("macro_reward", math.nan))),
        "macro_reward_matches_step_result": math.isclose(
            float(evidence.get("macro_reward", math.nan)), float(result.reward),
            rel_tol=0., abs_tol=1e-10),
        "elapsed_time_positive": math.isfinite(elapsed) and elapsed > 0.,
        "discount_units_match_measured_time": math.isfinite(units) and
            math.isclose(units, elapsed / NOMINAL_DISCOUNT_TIME_UNIT_SECONDS,
                         rel_tol=0., abs_tol=1e-8),
        "one_agent_decision": after_steps - before_steps == 1,
        "one_six_field_replay_transition": len(replay_transition) == 6 and
            replay_transition[1] == 0 and replay_transition[2] == result.reward and
            replay_transition[4] == (result.terminated or result.truncated) and
            math.isclose(replay_transition[5], units, rel_tol=0., abs_tol=1e-10),
        "reward_chunk_count_matches_execution": len(rewards) ==
            evidence.get("control_chunk_count") and len(rewards) >= 2,
    }
    return {"checks": checks, "all_pass": all(checks.values()),
            "phase_names": [item.get("phase") for item in
                (execution.get("execution_phases") or
                 (execution.get("execution_evidence") or {}).get("phase_evidence") or [])]}


def _set_stage(report, stage, *, completed=None):
    report["status"] = stage
    report["failure_stage"] = stage
    if completed is not None:
        report["last_completed_stage"] = completed


def _capture_runtime_evidence(report, adapter):
    """Keep the most recent process/reset provenance in every failure report."""
    if adapter is None:
        return
    report["process_status"] = None
    manager = getattr(adapter, "manager", None)
    if manager is not None:
        try:
            report["process_status"] = manager.status()
        except Exception as error:
            report["process_status_error"] = {
                "type": type(error).__name__, "message": str(error)}
    reset = getattr(adapter, "last_reset_evidence", None)
    if reset is not None:
        report["last_reset_evidence"] = dict(reset)
    report["restart_fallback_count"] = int(
        getattr(adapter, "restart_fallbacks", 0))


def _validate_replayed_target_prefix(report, saved_prefix):
    rows = report.get("target_episode_prefix_actions", [])
    if len(rows) != len(saved_prefix):
        raise RuntimeError(
            f"Target prefix replay incomplete: expected {len(saved_prefix)}, "
            f"replayed {len(rows)}")
    if [row["action"] for row in rows] != list(saved_prefix):
        raise RuntimeError("Replayed target prefix differs from saved action sequence")


def run_verifier(artifact_dir: Path, output: Path, *, gui=False, env_factory=None) -> dict:
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": "0.7.1",
        "verifier": "actual Gazebo exact DOWN-to-UP production macro integration",
        "status": "INITIALIZING",
        "failure_stage": "ARTIFACT_EXTRACTION",
        "last_completed_stage": None,
        "verdict": "PRODUCTION_LINEAR_REVERSAL_INTEGRATION_FAILED",
        "dqn_used": False,
        "training_used": False,
        "production_environment_step_used_for_target": False,
        "production_linear_reversal_routing_changed": True,
        "replay_source": None,
        "target_episode": None,
        "target_action_index_in_episode_1_based": None,
        "target_global_action_index_1_based": None,
        "expected_target_prefix_length": None,
        "target_episode_prefix_actions": [],
        "replayed_completed_episode_count": 0,
        "target_prefix_expected_count": None,
        "target_prefix_replayed_count": 0,
        "process_status": None,
        "last_reset_evidence": None,
        "episode_boundary_reset_gate_evidence": [],
        "acceptance": None,
        "error": None,
    }
    adapter = None
    current_stage = "ARTIFACT_EXTRACTION"
    replay = None
    saved_prefix = []
    try:
        replay = extract_reversal_replay(Path(artifact_dir))
        target_episode = int(replay["failed_episode_number"])
        target_index = int(replay["target_action_index_in_episode_1_based"])
        target_global = int(replay["target_global_action_index_1_based"])
        saved_prefix = list(replay["failed_episode_saved_prefix"])
        report.update(replay_source=replay, target_episode=target_episode,
            target_action_index_in_episode_1_based=target_index,
            target_global_action_index_1_based=target_global,
            expected_target_prefix_length=len(saved_prefix),
            target_prefix_expected_count=len(saved_prefix))
        report["last_completed_stage"] = "ARTIFACT_EXTRACTION"

        current_stage = "ENVIRONMENT_STARTUP"
        _set_stage(report, current_stage, completed="ARTIFACT_EXTRACTION")
        scenario = ScenarioSpec.from_dict(replay["scenario"])
        factory = env_factory or GazeboPhysicsTrainingEnvironment
        adapter = factory(scenario, replay["max_steps"], root=output / "worlds",
                          gui=gui, max_sensor_age_ms=20)
        current_stage = "INITIAL_RESET"
        _set_stage(report, current_stage, completed="ENVIRONMENT_STARTUP")
        adapter.reset(int(replay["training_seed"]) + 1)
        _capture_runtime_evidence(report, adapter)
        if adapter.injected or adapter.control_mode != "PHYSICS":
            raise RuntimeError("Verifier requires actual Gazebo transport in PHYSICS mode")
        if adapter.process is None or adapter.process.poll() is not None:
            raise RuntimeError("Fresh Gazebo process is not alive after initial reset")
        if int(getattr(adapter, "restart_fallbacks", 0)) != 0:
            raise RuntimeError("Fresh-process initialization unexpectedly used restart fallback")
        process_pid = adapter.process.pid
        report.update(status="REPLAYING_COMPLETED_EPISODES", failure_stage=None,
            last_completed_stage="INITIAL_RESET", initial_pid=process_pid,
            initial_reset_evidence=dict(adapter.last_reset_evidence),
            process=adapter.manager.status(), world=adapter.world_name,
            partition=adapter.manager.partition)

        episode_groups = replay["completed_episode_actions"] + [saved_prefix]
        global_index = 0
        for offset, actions in enumerate(episode_groups):
            episode_number = offset + 1
            if offset:
                current_stage = "EPISODE_BOUNDARY_RESET"
                _set_stage(report, current_stage,
                    completed="EPISODE_REPLAY" if episode_number == 2 else
                    "TARGET_PREFIX_REPLAY")
                fallback_before = int(adapter.restart_fallbacks)
                try:
                    adapter.reset(int(replay["training_seed"]) + episode_number)
                except Exception:
                    _capture_runtime_evidence(report, adapter)
                    report["episode_boundary_reset_gate_evidence"].append({
                        "episode": episode_number, "reset_evidence": getattr(
                            adapter, "last_reset_evidence", None),
                        "reset_call_failed": True})
                    raise
                fallback_after = int(adapter.restart_fallbacks)
                pid_after = getattr(adapter.process, "pid", None)
                status = adapter.manager.status()
                reset_evidence = dict(adapter.last_reset_evidence)
                from tools.verify_v07_gazebo_control_executor_linear_reversal import (
                    _episode_boundary_reset_gate,
                )
                gate = _episode_boundary_reset_gate(reset_evidence,
                    fallback_count_before=fallback_before,
                    fallback_count_after=fallback_after,
                    pid_before=process_pid, pid_after=pid_after,
                    process_alive=(status.get("status") == "Running" and
                                   status.get("available") is True))
                boundary = {"episode": episode_number, "reset_evidence": reset_evidence,
                    "pid_before": process_pid, "pid_after": pid_after,
                    "reset_replay_gate": gate}
                report.setdefault("episode_boundaries", []).append(boundary)
                report["episode_boundary_reset_gate_evidence"].append(boundary)
                report["last_reset_evidence"] = reset_evidence
                if not gate["continue_replay"]:
                    report["final_process"] = status
                    report["verdict"] = ("PRODUCTION_REPLAY_RESET_FALLBACK" if
                        gate["actual_process_restart_fallback"] else
                        "PRODUCTION_REPLAY_RESET_PROVENANCE_INCONCLUSIVE")
                    raise _StopReplay()
                report["last_completed_stage"] = "EPISODE_BOUNDARY_RESET"

            episode_record = {"episode": episode_number, "actions": []}
            report.setdefault("episode_replays", []).append(episode_record)
            current_stage = ("REPLAYING_COMPLETED_EPISODES" if
                episode_number < target_episode else "REPLAYING_TARGET_PREFIX")
            _set_stage(report, current_stage,
                completed="EPISODE_BOUNDARY_RESET" if offset else "INITIAL_RESET")
            for local_index, action in enumerate(actions, start=1):
                global_index += 1
                before = float(adapter.env.stepper.time)
                try:
                    result = adapter.step(action)
                except Exception as error:
                    report["failed_replay_action"] = {"episode": episode_number,
                        "episode_action_index_1_based": local_index,
                        "global_action_index_1_based": global_index,
                        "action": action, "type": type(error).__name__,
                        "message": str(error)}
                    report["error"] = {"type": type(error).__name__,
                        "message": str(error)}
                    _capture_runtime_evidence(report, adapter)
                    report["target_prefix_replayed_count"] = len(
                        report["target_episode_prefix_actions"])
                    raise _StopReplay()
                row = {"episode_action_index_1_based": local_index,
                    "global_action_index_1_based": global_index, "action": action,
                    "simulation_start": before,
                    "simulation_end": float(adapter.env.stepper.time),
                    "reason": result.reason, "terminated": result.terminated,
                    "truncated": result.truncated}
                episode_record["actions"].append(row)
                if episode_number < target_episode and result.terminated or \
                        episode_number < target_episode and result.truncated:
                    report["replayed_completed_episode_count"] += 1
                if result.terminated or result.truncated:
                    expected_last = local_index == len(actions)
                    if not expected_last:
                        report["divergence"] = {"episode": episode_number,
                            "action_index": local_index, "reason": result.reason,
                            "expected_episode_end": False}
                        raise _StopReplay()
                    if episode_number < target_episode:
                        expected_reason = replay["completed_episode_metrics"][offset]["reason"]
                        if result.reason != expected_reason:
                            report["divergence"] = {"episode": episode_number,
                                "expected_reason": expected_reason,
                                "actual_reason": result.reason}
                            raise _StopReplay()
                elif episode_number < target_episode and local_index == len(actions):
                    report["divergence"] = {"episode": episode_number,
                        "expected_episode_end": True, "actual_terminated": False,
                        "actual_truncated": False}
                    raise _StopReplay()
                if episode_number == target_episode:
                    report["target_episode_prefix_actions"].append(row)
                    report["target_prefix_replayed_count"] = len(
                        report["target_episode_prefix_actions"])
                report["last_completed_stage"] = "TARGET_PREFIX_REPLAY" if \
                    episode_number == target_episode else "EPISODE_REPLAY"

        current_stage = "TARGET_PREFIX_VALIDATION"
        _set_stage(report, current_stage, completed="TARGET_PREFIX_REPLAY")
        if target_episode != len(replay["completed_episode_actions"]) + 1:
            raise RuntimeError("Target episode is not adjacent to saved completed episodes")
        _validate_replayed_target_prefix(report, saved_prefix)
        base = adapter.env
        previous_command = dict(base.controller.last_command)
        target_transition = classify_physics_command_transition(
            previous_command, gazebo_physics_twist("up"))
        if (saved_prefix[-1:] != ["down"] or
                previous_command != gazebo_physics_twist("down") or
                target_transition != "LINEAR_REVERSAL"):
            raise RuntimeError("Replayed target does not end in the saved DOWN→UP state")

        from types import SimpleNamespace
        policy = SimpleNamespace(observation_mode="sensor", local_radius=2)
        before_observation = adapter.get_agent_observation("sensor", 2)
        before_vector = observation_vector(before_observation)
        steps_before = int(base.steps)
        start_time = float(base.stepper.time)
        current_stage = "EXECUTING_TARGET"
        _set_stage(report, current_stage, completed="TARGET_PREFIX_VALIDATION")
        report["target_production_step_call_started"] = True
        report["production_environment_step_used_for_target"] = True
        try:
            # Deliberately route through production adapter; no executor direct call.
            result = adapter.step("up")
        except PhysicalControlFailure as error:
            report["target_failure"] = error.to_dict()
            report["error"] = {"type": type(error).__name__,
                "message": str(error)}
            raise _StopReplay()
        next_observation = adapter.get_agent_observation(policy.observation_mode,
                                                         policy.local_radius)
        next_vector = observation_vector(next_observation)
        mapping = gazebo_physics_action_mapping()
        up_index = next(row["index"] for row in mapping if row["action"] == "up")
        done = bool(result.terminated or result.truncated)
        replay_transition = Transition(before_observation, "up", float(result.reward),
            next_observation, done, result.elapsed_discount_units)
        replay_payload = [before_vector, up_index, replay_transition.reward, next_vector,
            replay_transition.done, replay_transition.elapsed_discount_units]
        evidence = dict(result.execution_evidence or {})
        training = dict(base.telemetry.get("gazebo_dqn_training") or {})
        process_status = adapter.manager.status()
        report["target_execution"] = {
            "target_request": {"episode": target_episode,
                "decision_index": target_index, "global_action_index": target_global,
                "previous_action": "down", "agent_intent": "up",
                "command_mode_transition": target_transition},
            "before_simulation_time": start_time,
            "after_simulation_time": float(base.stepper.time),
            "before_episode_step_count": steps_before,
            "after_episode_step_count": int(base.steps),
            "step_result": {"reward": result.reward, "terminated": result.terminated,
                "truncated": result.truncated, "reason": result.reason,
                "elapsed_execution_time": result.elapsed_execution_time,
                "elapsed_discount_units": result.elapsed_discount_units},
            "production_training_telemetry": training,
            "execution_evidence": evidence,
            "replay_transition_count": 1,
            "replay_transition_field_count": len(replay_payload),
            "replay_transition_payload": replay_payload,
            "dqn_replay_inserted": False,
            "process": process_status,
        }
        assessment = assess_production_macro(result, training,
            previous_command=previous_command, before_steps=steps_before,
            after_steps=int(base.steps),
            process_alive=(process_status.get("status") == "Running" and
                           process_status.get("available") is True),
            replay_transition=replay_payload)
        report["acceptance"] = assessment
        report["final_process"] = process_status
        report["verdict"] = ("PRODUCTION_LINEAR_REVERSAL_INTEGRATION_ACTUAL_PASS"
                             if assessment["all_pass"] else
                             "PRODUCTION_LINEAR_REVERSAL_INTEGRATION_REJECTED")
        report["status"] = "ACCEPTANCE_COMPLETE"
        report["failure_stage"] = None
        report["last_completed_stage"] = "ACCEPTANCE_COMPLETE"
    except _StopReplay:
        report["status"] = "FAILED"
        report["failure_stage"] = current_stage
        report["error"] = report.get("error") or {
            "type": "ReplayRejected",
            "message": str(report.get("divergence") or
                report.get("episode_boundary_reset_gate_evidence", [{}])[-1] or
                report.get("verdict"))}
    except Exception as error:
        report.update(status="FAILED", failure_stage=current_stage,
            verdict="PRODUCTION_LINEAR_REVERSAL_INTEGRATION_FAILED",
            error={"type": type(error).__name__, "message": str(error)})
        _capture_runtime_evidence(report, adapter)
    except BaseException as error:
        # Preserve evidence for interrupts/system-exit while still allowing the
        # caller/process to retain the original control-flow behavior.
        report.update(status="FAILED", failure_stage=current_stage,
            verdict="PRODUCTION_LINEAR_REVERSAL_INTEGRATION_FAILED",
            error={"type": type(error).__name__, "message": str(error)})
        _capture_runtime_evidence(report, adapter)
        report["interrupted"] = True
        raise
    finally:
        if adapter is not None:
            try:
                adapter.close()
                report["shutdown"] = "PASS"
            except Exception as error:
                report["shutdown"] = "FAIL"
                report["shutdown_error"] = str(error)
            _capture_runtime_evidence(report, adapter)
        if report.get("acceptance"):
            report["acceptance"]["checks"]["shutdown_pass"] = report.get("shutdown") == "PASS"
            report["acceptance"]["all_pass"] = all(
                report["acceptance"]["checks"].values())
            report["verdict"] = ("PRODUCTION_LINEAR_REVERSAL_INTEGRATION_ACTUAL_PASS"
                if report["acceptance"]["all_pass"] else
                "PRODUCTION_LINEAR_REVERSAL_INTEGRATION_REJECTED")
            report["status"] = "ACCEPTANCE_COMPLETE"
        report["target_prefix_replayed_count"] = len(
            report.get("target_episode_prefix_actions", []))
        report["evidence_file"] = str(output / "linear_reversal_production_integration.json")
        write_json(output / "linear_reversal_production_integration.json", report)
    return report


class _StopReplay(Exception):
    pass


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--gui", action="store_true")
    args = parser.parse_args(argv)
    report = run_verifier(args.artifact_dir, args.output, gui=args.gui)
    print("Gazebo production DOWN→UP integration: " + report["verdict"])
    print("evidence: " + report["evidence_file"])
    return 0 if report["verdict"] == "PRODUCTION_LINEAR_REVERSAL_INTEGRATION_ACTUAL_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
