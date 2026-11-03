#!/usr/bin/env python3
"""Replay a saved Gazebo Stage 1 prefix and experimentally execute DOWN→UP safely.

This host-only diagnostic does not instantiate a DQN or alter production routing.
It replays the saved action history through the production PHYSICS environment,
then uses a bounded world-Pose_V BRAKE_LINEAR phase before production ``step('up')``.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import torch

from aero_ai_studio.core.storage import write_json
from aero_ai_studio.gazebo.control_executor import GazeboLinearReversalControlExecutor
from aero_ai_studio.scenario.models import ScenarioSpec
from aero_ai_studio.simulation.action_mapping import (
    classify_physics_command_transition,
    gazebo_physics_action_mapping,
    gazebo_physics_twist,
)
from aero_ai_studio.simulation.control_execution import (
    ControlExecutionRequest,
    ControlExecutionStatus,
)
from aero_ai_studio.simulation.base import PhysicalControlFailure
from aero_ai_studio.training.gazebo_physics import GazeboPhysicsTrainingEnvironment


def _action_for_twist(twist: dict, mapping: list[dict]) -> str:
    linear = float(twist.get("linear", {}).get("x", 0.))
    angular = float(twist.get("angular", {}).get("z", 0.))
    matches = [row["action"] for row in mapping
        if math.isclose(linear, float(row["twist"]["linear_x"]), rel_tol=0., abs_tol=1e-9)
        and math.isclose(angular, float(row["twist"]["angular_z"]), rel_tol=0., abs_tol=1e-9)]
    if len(matches) != 1:
        raise ValueError(f"Saved Twist does not map to one PHYSICS action: {twist}")
    return matches[0]


def build_reversal_replay(checkpoint: dict, failure: dict, metrics: list,
                          action_mapping: list[dict], *, artifact_dir: Path,
                          run_dir: Path, config: dict, scenario: dict) -> dict:
    """Reconstruct completed episode actions and the exact target reversal."""
    buffer = checkpoint.get("buffer")
    if not isinstance(buffer, list) or not buffer:
        raise ValueError("Failed-run checkpoint has no saved replay transitions")
    if int(checkpoint.get("global_step", -1)) != len(buffer):
        raise ValueError("Checkpoint global_step does not match replay-buffer length")
    if not metrics:
        raise ValueError("No completed episode metrics; cannot locate the failed episode boundary")
    validator = failure.get("validator_evidence") or {}
    if (validator.get("command_mode_transition") != "LINEAR_REVERSAL" or
            failure.get("transition_type") != "LINEAR_REVERSAL"):
        raise ValueError("Saved failure is not a production LINEAR_REVERSAL rejection")
    previous = _action_for_twist(
        validator.get("previous_action_twist") or validator.get("previous_command_twist") or {},
        action_mapping)
    failed = _action_for_twist(validator.get("requested_command_twist") or {}, action_mapping)
    if (previous, failed) != ("down", "up"):
        raise ValueError(f"Saved target is {previous}→{failed}; expected DOWN→UP")
    if failure.get("collision") or validator.get("collision_may_block_motion") is True or \
            validator.get("contact_blocked_world_motion") is True:
        raise ValueError("Saved target was collision/contact blocked, not a clean reversal failure")
    if config.get("safety_enabled", False):
        raise ValueError("Cannot reconstruct executed actions exactly from replay when Safety may override them")

    names = [row["action"] for row in action_mapping]
    actions = []
    transition_lengths = set()
    for index, transition in enumerate(buffer):
        if not isinstance(transition, (list, tuple)) or len(transition) not in (5, 6):
            raise ValueError(f"Malformed saved replay transition at index {index}")
        action_index = transition[1]
        if type(action_index) is not int or not 0 <= action_index < len(names):
            raise ValueError(f"Invalid saved action index at transition {index}")
        transition_lengths.add(len(transition))
        actions.append(names[action_index])
    completed_episode_counts = [int(row["steps"]) for row in metrics]
    completed_actions = sum(completed_episode_counts)
    if completed_actions >= len(actions):
        raise ValueError("Replay buffer does not contain a partial failed episode after completed metrics")
    failed_episode_actions = actions[completed_actions:]
    if not failed_episode_actions or failed_episode_actions[-1] != previous:
        raise ValueError("Last accepted saved action does not match previous DOWN command")
    expected_failed_transition_count = len(actions) - completed_actions + 1
    if expected_failed_transition_count < 2:
        raise ValueError("Failed episode prefix is too short to replay the reversal")

    # Verify done markers identify the metrics boundaries and no partial-episode
    # transition is terminal. The DQN-free verifier uses actions only.
    boundaries = set()
    cursor = 0
    for count in completed_episode_counts:
        if count <= 0 or cursor + count > len(buffer):
            raise ValueError("Episode metrics do not align with saved replay length")
        cursor += count
        boundaries.add(cursor - 1)
    for index, transition in enumerate(buffer):
        done = bool(transition[4])
        if done != (index in boundaries):
            raise ValueError(f"Replay done flag disagrees with episode boundary at index {index}")

    completed_groups = []
    boundary_cursor = 0
    for count in completed_episode_counts:
        completed_groups.append(actions[boundary_cursor:boundary_cursor + count])
        boundary_cursor += count
    return {
        "artifact_dir": str(Path(artifact_dir)),
        "run_dir": str(Path(run_dir)),
        "run_id": Path(run_dir).name,
        "sequence_source": "saved replay-buffer action indices; completed episode lengths from metrics; rejected command from validator evidence",
        "dqn_used": False,
        "training_used": False,
        "replay_transition_field_lengths": sorted(transition_lengths),
        "saved_global_step": int(checkpoint["global_step"]),
        "saved_replay_length": len(buffer),
        "completed_episode_metrics": metrics,
        "completed_episode_action_counts": completed_episode_counts,
        "completed_episode_actions": completed_groups,
        "failed_episode_number": len(metrics) + 1,
        "failed_episode_reset_seed": int(config["seed"]) + len(metrics) + 1,
        "failed_episode_saved_prefix": failed_episode_actions,
        "target_action": failed,
        "target_action_index_in_episode_1_based": len(failed_episode_actions) + 1,
        "target_global_action_index_1_based": len(actions) + 1,
        "previous_action": previous,
        "transition_type": "LINEAR_REVERSAL",
        "saved_failure_simulation_interval": [
            (failure.get("action_transition") or {}).get("action_command_sim_time"),
            (failure.get("action_transition") or {}).get("zero_command_sim_time")],
        "saved_failure_validator_evidence": validator,
        "saved_failure_contact_state": failure.get("contact_state"),
        "saved_failure_collision": bool(failure.get("collision")),
        "scenario": scenario,
        "max_steps": int(config["max_steps"]),
        "training_seed": int(config["seed"]),
    }


def extract_reversal_replay(artifact_dir: Path) -> dict:
    artifact_dir = Path(artifact_dir)
    config = json.loads((artifact_dir / "training_config.json").read_text(encoding="utf-8"))
    scenario = json.loads((artifact_dir / "scenario.json").read_text(encoding="utf-8"))
    run_candidates = []
    for run_json in sorted((artifact_dir / "runs").glob("run_*/run.json")):
        run = json.loads(run_json.read_text(encoding="utf-8"))
        evidence = (run.get("failure") or {}).get("evidence") or {}
        validator = evidence.get("validator_evidence") or {}
        if (run.get("status") == "physical_control_failure" and
                validator.get("command_mode_transition") == "LINEAR_REVERSAL"):
            run_candidates.append((run_json.parent, run, evidence))
    if len(run_candidates) != 1:
        raise ValueError(f"Expected one saved LINEAR_REVERSAL failure run, found {len(run_candidates)}")
    run_dir, run, failure = run_candidates[0]
    metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
    checkpoint = torch.load(run_dir / "model.pt", map_location="cpu", weights_only=True)
    if run.get("failure_category") != "physical_control_failure":
        raise ValueError("Source run failure is not classified as physical_control_failure")
    replay = build_reversal_replay(checkpoint, failure, metrics,
        gazebo_physics_action_mapping(), artifact_dir=artifact_dir, run_dir=run_dir,
        config=config, scenario=scenario)
    episode_trace_actions = []
    for metric in metrics:
        episode_file = run_dir / "episodes" / f"episode_{int(metric['episode']):04d}.json"
        if episode_file.is_file():
            episode_data = json.loads(episode_file.read_text(encoding="utf-8"))
            trace = [row.get("action") for row in episode_data.get("steps", [])]
            if len(trace) != int(metric["steps"]):
                raise ValueError(f"Saved episode action trace length mismatch: {episode_file}")
            episode_trace_actions.append(trace)
    if episode_trace_actions and episode_trace_actions != replay["completed_episode_actions"]:
        raise ValueError("Replay-buffer actions disagree with saved completed episode action traces")
    replay["completed_episode_trace_crosscheck"] = (
        "PASS" if episode_trace_actions else "NOT_RECORDED")
    replay["saved_run_status"] = run.get("status")
    replay["saved_run_failure_reason"] = run.get("error")
    replay["saved_run_failure_category"] = run.get("failure_category")
    return replay


def _task_outcome_callback(adapter, *, initial_sensor_sequence):
    prior_sequence = initial_sensor_sequence

    def callback(row):
        nonlocal prior_sequence
        observation = adapter.get_agent_observation("sensor", 2)
        sensor = adapter._require_actual_sensor(observation, prior_sequence)
        prior_sequence = sensor["sequence"]
        base = adapter.env
        contacts = list(row.get("collision_events") or [])
        if contacts:
            reason, terminated = "collision", True
        elif math.dist((base.pose["x"], base.pose["y"]), base.goal) <= adapter.goal_radius:
            reason, terminated = "goal", True
        elif any(item.type == "danger_zone" and
                 math.hypot(base.pose["x"] - (item.position[0] + .5),
                            base.pose["y"] - (item.position[1] + .5)) < .5
                 for item in adapter.scenario.objects):
            reason, terminated = "danger_zone", True
        else:
            reason, terminated = "moving", False
        base.telemetry["contacts"] = dict(getattr(base.contacts, "state", {}))
        return {"reason": reason, "terminated": terminated, "truncated": False,
                "collision": bool(contacts), "collision_events": contacts,
                "sensor_contract": sensor,
                "contact_state": dict(getattr(base.contacts, "state", {})),
                "contact_schema": getattr(base.contacts, "schema", None)}
    return callback


def _episode_boundary_reset_gate(reset_evidence, *, fallback_count_before,
                                 fallback_count_after, pid_before, pid_after,
                                 process_alive):
    """Require explicit proof of a successful same-process persistent reset."""
    evidence = dict(reset_evidence or {})
    primary = dict(evidence.get("primary_reset_attempt") or {})
    reset_method = evidence.get("reset_method")
    primary_method = primary.get("reset_method")
    count = evidence.get("restart_fallback_count", fallback_count_after)
    try:
        count = int(count)
    except (TypeError, ValueError):
        count = None
    try:
        before_count = int(fallback_count_before)
        after_count = int(fallback_count_after)
    except (TypeError, ValueError):
        before_count = after_count = None
    count_increased = (before_count is not None and after_count is not None and
                       after_count > before_count)
    process_replaced = (pid_before is not None and pid_after is not None and
                        pid_before != pid_after)
    explicit_fallback = bool(evidence.get("restart_fallback_used") is True or
                             primary.get("restart_fallback_used") is True or
                             reset_method == "fresh_process_restart" or
                             primary_method == "fresh_process_restart")
    actual_fallback = bool(explicit_fallback or count_increased)
    normal_reset_pass = (evidence.get("normal_reset_pass") is True and
                         primary.get("normal_reset_pass") is True)
    persistent_method = (
        reset_method == "world_control_reset_model_only_after_quiescence" and
        primary_method == "world_control_reset_model_only_after_quiescence")
    same_process = pid_before is not None and pid_before == pid_after
    process_reused = evidence.get("process_reused") is True
    provenance_consistent = bool(
        not actual_fallback and not process_replaced and
        evidence.get("restart_fallback_used") is False and
        count == after_count and persistent_method and normal_reset_pass and
        process_reused and same_process and process_alive)
    if actual_fallback:
        reason = "process restart fallback detected"
    elif process_replaced:
        reason = "process identity changed; deterministic replay cannot continue"
    elif not provenance_consistent:
        reason = "persistent reset provenance is missing or internally inconsistent"
    else:
        reason = None
    return {
        "continue_replay": provenance_consistent,
        "actual_process_restart_fallback": actual_fallback,
        "explicit_fallback_used": explicit_fallback,
        "fallback_count_before": before_count,
        "fallback_count_after": after_count,
        "fallback_count_increased": count_increased,
        "reported_fallback_count": count,
        "pid_before": pid_before,
        "pid_after": pid_after,
        "process_replaced": process_replaced,
        "process_alive": bool(process_alive),
        "process_reused": evidence.get("process_reused"),
        "reset_method": reset_method,
        "primary_reset_method": primary_method,
        "restart_fallback_used": evidence.get("restart_fallback_used"),
        "primary_restart_fallback_used": primary.get("restart_fallback_used"),
        "normal_reset_pass": evidence.get("normal_reset_pass"),
        "primary_normal_reset_pass": primary.get("normal_reset_pass"),
        "provenance_consistent": provenance_consistent,
        "reason": reason,
        # Preserve the failed primary attempt if restart fallback succeeded.
        "original_persistent_reset_failure": primary or None,
    }


def run_verifier(artifact_dir: Path, output: Path, *, gui=False, env_factory=None) -> dict:
    replay = extract_reversal_replay(Path(artifact_dir))
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": "0.7.1",
        "verifier": "actual Gazebo experimental DOWN-to-UP linear reversal executor",
        "status": "NOT_STARTED",
        "verdict": "LINEAR_REVERSAL_EXECUTOR_INFRASTRUCTURE_FAILURE",
        "control_mode": "PHYSICS",
        "dqn_used": False,
        "training_used": False,
        "production_linear_reversal_routing_changed": False,
        "uses_production_environment_step_for_saved_prefix": True,
        "uses_production_environment_step_for_up_acquisition": True,
        "uses_production_physical_validator": True,
        "uses_actual_sensor_and_contact_path": True,
        "replay_source": replay,
        "episode_replays": [],
        "target_episode_prefix_actions": [],
        "target_episode": replay["failed_episode_number"],
        "target_action_index_in_episode_1_based": replay["target_action_index_in_episode_1_based"],
        "target_global_action_index_1_based": replay["target_global_action_index_1_based"],
        "expected_target_episode_prefix_length": len(replay["failed_episode_saved_prefix"]),
    }
    adapter = None
    try:
        scenario = ScenarioSpec.from_dict(replay["scenario"])
        factory = env_factory or GazeboPhysicsTrainingEnvironment
        adapter = factory(scenario, replay["max_steps"], root=output / "worlds",
                          gui=gui, max_sensor_age_ms=20)
        adapter.reset(int(replay["training_seed"]) + 1)
        if adapter.injected or adapter.control_mode != "PHYSICS":
            raise RuntimeError("Verifier requires actual Gazebo transport in PHYSICS mode")
        if not adapter.process or adapter.process.poll() is not None:
            raise RuntimeError("Fresh Gazebo process is not alive after initial reset")
        if int(getattr(adapter, "restart_fallbacks", 0)) != 0:
            raise RuntimeError("Fresh-process initialization unexpectedly used restart fallback")
        process_pid = getattr(adapter.process, "pid", None)
        report.update(status="RUNNING", world=adapter.world_name,
                      partition=adapter.manager.partition,
                      initial_pid=process_pid,
                      initial_reset_evidence=dict(adapter.last_reset_evidence),
                      process=adapter.manager.status())

        # Replay all completed episodes in one process. This includes the actual
        # persistent reset boundary before the failed episode, not just its seed.
        global_index = 0
        episode_action_groups = replay["completed_episode_actions"] + [
            replay["failed_episode_saved_prefix"]]
        for episode_offset, actions in enumerate(episode_action_groups):
            episode_number = episode_offset + 1
            if episode_offset:
                reset_seed = int(replay["training_seed"]) + episode_number
                fallback_count_before = int(getattr(adapter, "restart_fallbacks", 0))
                adapter.reset(reset_seed)
                pid_after_reset = getattr(adapter.process, "pid", None)
                fallback_count_after = int(getattr(adapter, "restart_fallbacks", 0))
                reset_evidence = dict(adapter.last_reset_evidence)
                manager_status = adapter.manager.status()
                reset_gate = _episode_boundary_reset_gate(
                    reset_evidence,
                    fallback_count_before=fallback_count_before,
                    fallback_count_after=fallback_count_after,
                    pid_before=process_pid,
                    pid_after=pid_after_reset,
                    process_alive=(manager_status.get("status") == "Running" and
                                   manager_status.get("available") is True))
                boundary_record = {
                    "episode": episode_number,
                    "reset_seed": reset_seed,
                    "reset_evidence": reset_evidence,
                    "reset_method": reset_evidence.get("reset_method"),
                    "restart_fallback_used": reset_evidence.get("restart_fallback_used"),
                    "pid_before": process_pid,
                    "pid_after": pid_after_reset,
                    "same_process": pid_after_reset == process_pid,
                    "reset_replay_gate": reset_gate,
                }
                # Persist the boundary attempt before enforcing deterministic
                # replay policy, so a fallback's original failure is retained.
                report["episode_replays"].append(boundary_record)
                if not reset_gate["continue_replay"]:
                    report["final_process"] = manager_status
                    report["reset_replay_gate_failure"] = reset_gate["reason"]
                    report["verdict"] = (
                        "LINEAR_REVERSAL_PREFIX_RESET_FALLBACK" if
                        reset_gate["actual_process_restart_fallback"] else
                        "LINEAR_REVERSAL_PREFIX_RESET_PROVENANCE_INCONCLUSIVE")
                    report["status"] = report["verdict"]
                    raise _ReplayStopped()
            else:
                report["episode_replays"].append({
                    "episode": episode_number,
                    "reset_seed": int(replay["training_seed"]) + episode_number,
                    "reset_evidence": dict(adapter.last_reset_evidence),
                    "reset_method": adapter.last_reset_evidence.get("reset_method"),
                    "restart_fallback_used": adapter.last_reset_evidence.get("restart_fallback_used"),
                })
            is_failed_episode = episode_number == replay["failed_episode_number"]
            for local_index, action in enumerate(actions, start=1):
                global_index += 1
                base = adapter.env
                before_time = float(base.stepper.time)
                before_pose = dict(base.pose)
                entry = {"episode": episode_number,
                         "episode_action_index_1_based": local_index,
                         "global_action_index_1_based": global_index,
                         "agent_intent": action,
                         "before_simulation_time": before_time,
                         "before_pose": before_pose}
                if is_failed_episode and local_index == len(actions):
                    pose_cursor = base.transport.cursor(base.controller.pose_topic)
                    pre_start = before_time
                try:
                    step_result = adapter.step(action)
                except PhysicalControlFailure as error:
                    entry["failure"] = ({"type": type(error).__name__,
                                         "message": str(error)})
                    entry["after_simulation_time"] = float(base.stepper.time)
                    entry["after_pose"] = dict(base.pose) if base.pose else None
                    if is_failed_episode:
                        report["target_episode_prefix_actions"].append(entry)
                        report["verdict"] = "LINEAR_REVERSAL_PREFIX_PHYSICAL_FAILURE"
                    else:
                        report["verdict"] = "LINEAR_REVERSAL_PREFIX_DIVERGED"
                        report["episode_replays"][-1].setdefault("actions", []).append(entry)
                    report["status"] = report["verdict"]
                    raise _ReplayStopped() from error
                except Exception as error:
                    entry["failure"] = {"type": type(error).__name__, "message": str(error)}
                    entry["after_simulation_time"] = float(base.stepper.time)
                    entry["after_pose"] = dict(base.pose) if base.pose else None
                    report["verdict"] = "LINEAR_REVERSAL_PREFIX_INFRASTRUCTURE_FAILURE"
                    report["status"] = report["verdict"]
                    if is_failed_episode:
                        report["target_episode_prefix_actions"].append(entry)
                    else:
                        report["episode_replays"][-1].setdefault("actions", []).append(entry)
                    raise _ReplayStopped() from error
                entry.update(after_simulation_time=float(base.stepper.time),
                    after_pose=dict(base.pose),
                    transition_type=(base.telemetry.get("action_transition") or {}).get(
                        "command_mode_transition"),
                    pose_validation=base.telemetry.get("pose_validation"),
                    reason=step_result.reason,
                    terminated=step_result.terminated,
                    truncated=step_result.truncated)
                if is_failed_episode:
                    report["target_episode_prefix_actions"].append(entry)
                else:
                    report["episode_replays"][-1].setdefault("actions", []).append(entry)
                if step_result.terminated or step_result.truncated:
                    expected_end = local_index == len(actions)
                    if not expected_end:
                        report["verdict"] = "LINEAR_REVERSAL_PREFIX_DIVERGED"
                        report["status"] = report["verdict"]
                        report["divergence"] = {"episode": episode_number,
                            "action_index": local_index, "reason": step_result.reason,
                            "expected_episode_end": False}
                        raise _ReplayStopped()
                    if not is_failed_episode:
                        expected_reason = replay["completed_episode_metrics"][episode_offset]["reason"]
                        if step_result.reason != expected_reason:
                            report["verdict"] = "LINEAR_REVERSAL_PREFIX_DIVERGED"
                            report["status"] = report["verdict"]
                            report["divergence"] = {"episode": episode_number,
                                "expected_reason": expected_reason,
                                "actual_reason": step_result.reason}
                            raise _ReplayStopped()
                elif not is_failed_episode and local_index == len(actions):
                    report["verdict"] = "LINEAR_REVERSAL_PREFIX_DIVERGED"
                    report["status"] = report["verdict"]
                    report["divergence"] = {"episode": episode_number,
                        "expected_episode_end": True, "actual_terminated": False,
                        "actual_truncated": False}
                    raise _ReplayStopped()

            if is_failed_episode:
                base = adapter.env
                pre_raw = base.controller.pose_history_after(
                    pose_cursor, pre_start, float(base.stepper.time))
                from aero_ai_studio.gazebo.entity_controller import summarize_world_pose_history
                prehistory = summarize_world_pose_history(pre_raw, pre_start,
                                                          float(base.stepper.time))
                previous = dict(base.controller.last_command)
                requested = gazebo_physics_twist("up")
                transition = classify_physics_command_transition(previous, requested)
                request = ControlExecutionRequest("up", previous, requested, transition)
                report.update(
                    target_episode=episode_number,
                    target_action_index_in_episode_1_based=len(actions) + 1,
                    target_global_action_index_1_based=global_index + 1,
                    target_request=request.to_dict(),
                    target_pre_braking_history=prehistory,
                    target_pre_braking_history_raw=pre_raw,
                    target_pre_braking_interval=[pre_start, float(base.stepper.time)],
                    replayed_previous_command=previous,
                    actual_transition_classification=transition,
                    saved_failure_reference=replay["saved_failure_validator_evidence"],
                )
                if transition != "LINEAR_REVERSAL":
                    report["verdict"] = "LINEAR_REVERSAL_PREFIX_DIVERGED"
                else:
                    initial_observation = adapter.get_agent_observation("sensor", 2)
                    initial_sensor = adapter._require_actual_sensor(initial_observation)
                    executor = GazeboLinearReversalControlExecutor(
                        adapter, pre_braking_history=prehistory)
                    result = executor.execute_plan(executor.plan(request),
                        on_braking_chunk=_task_outcome_callback(
                            adapter, initial_sensor_sequence=initial_sensor["sequence"]))
                    result_data = result.to_dict()
                    report["execution_result"] = result_data
                    report["production_validator"] = result.validator_evidence
                    report["final_process"] = adapter.manager.status()
                    if result.status is ControlExecutionStatus.EXECUTED:
                        report["verdict"] = "LINEAR_REVERSAL_EXECUTOR_ACTUAL_PASS"
                    elif result.status is ControlExecutionStatus.PHYSICAL_CONTROL_FAILURE:
                        phases = (result.execution_evidence or {}).get("phase_evidence", [])
                        last_phase = phases[-1].get("phase") if phases else None
                        report["verdict"] = (
                            "LINEAR_REVERSAL_BRAKING_FAILED" if last_phase == "BRAKE_LINEAR"
                            else "LINEAR_REVERSAL_ACQUISITION_FAILED")
                    elif result.status is ControlExecutionStatus.COLLISION:
                        report["verdict"] = "LINEAR_REVERSAL_COLLISION_DURING_EXECUTION"
                    elif result.status is ControlExecutionStatus.TASK_TERMINAL:
                        report["verdict"] = "LINEAR_REVERSAL_TASK_TERMINAL_DURING_BRAKING"
                    elif result.status is ControlExecutionStatus.INCONCLUSIVE:
                        report["verdict"] = "LINEAR_REVERSAL_PRECONDITION_NOT_MET"
                    else:
                        report["verdict"] = "LINEAR_REVERSAL_EXECUTOR_INFRASTRUCTURE_FAILURE"
                report["status"] = report["verdict"]
        if report["status"] == "RUNNING":
            report["status"] = report["verdict"]
    except _ReplayStopped:
        pass
    except Exception as error:
        report.update(status="LINEAR_REVERSAL_EXECUTOR_INFRASTRUCTURE_FAILURE",
            verdict="LINEAR_REVERSAL_EXECUTOR_INFRASTRUCTURE_FAILURE",
            error={"type": type(error).__name__, "message": str(error)})
    finally:
        if adapter is not None:
            try:
                adapter.close()
                report["shutdown"] = "PASS"
            except Exception as error:
                report["shutdown"] = "FAIL"
                report["shutdown_error"] = str(error)
        report["evidence_file"] = str(output / "linear_reversal_control_executor.json")
        write_json(output / "linear_reversal_control_executor.json", report)
    return report


class _ReplayStopped(Exception):
    """Internal control flow after preserving a prefix divergence report."""


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", type=Path, required=True,
        help="Stage 1 output containing the failed run, replay checkpoint, and metrics")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--gui", action="store_true")
    args = parser.parse_args(argv)
    report = run_verifier(args.artifact_dir, args.output, gui=args.gui)
    print("Gazebo linear reversal executor: " + report["verdict"])
    print("evidence: " + report["evidence_file"])
    return 0 if report["verdict"] == "LINEAR_REVERSAL_EXECUTOR_ACTUAL_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
