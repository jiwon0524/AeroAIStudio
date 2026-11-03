#!/usr/bin/env python3
"""Replay the exact saved action prefix from the failed Gazebo DQN Stage 1 run.

This host-only verifier uses the failed run's DQN replay buffer as the source of
truth for completed actions and the failed production exception for the rejected
action. It does not load or execute the DQN policy.
"""
from __future__ import annotations

import argparse
import ast
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import torch

from aero_ai_studio.core.storage import write_json
from aero_ai_studio.scenario.models import ScenarioSpec
from aero_ai_studio.simulation.action_mapping import gazebo_physics_action_mapping
from aero_ai_studio.training.gazebo_physics import GazeboPhysicsTrainingEnvironment


ERROR_PREFIX = "Physics movement outside validated tolerance: "


def parse_failed_validation(error_text: str) -> dict:
    if not isinstance(error_text, str) or not error_text.startswith(ERROR_PREFIX):
        raise ValueError("Artifact does not contain a production physics validator failure")
    value = ast.literal_eval(error_text[len(ERROR_PREFIX):])
    if not isinstance(value, dict) or value.get("command_mode_transition") != "ROTATION_TO_LINEAR":
        raise ValueError("Saved failure is not the expected ROTATION_TO_LINEAR transition")
    return value


def action_for_twist(twist: dict, action_mapping: list[dict]) -> str:
    linear = float(twist.get("linear", {}).get("x", 0.0))
    angular = float(twist.get("angular", {}).get("z", 0.0))
    matches = []
    for item in action_mapping:
        expected = item["twist"]
        if (math.isclose(linear, float(expected["linear_x"]), rel_tol=0., abs_tol=1e-9) and
                math.isclose(angular, float(expected["angular_z"]), rel_tol=0., abs_tol=1e-9)):
            matches.append(item["action"])
    if len(matches) != 1:
        raise ValueError(f"Saved Twist does not identify exactly one PHYSICS action: {twist}")
    return matches[0]


def build_replay_sequence(checkpoint: dict, failure: dict, metrics: list,
                          action_mapping: list[dict]) -> dict:
    """Validate and reconstruct actions without consulting policy/RNG decisions."""
    buffer = checkpoint.get("buffer")
    if not isinstance(buffer, list) or not buffer:
        raise ValueError("Failed-run checkpoint has no replay-buffer action history")
    if int(checkpoint.get("global_step", -1)) != len(buffer):
        raise ValueError("Checkpoint global_step does not match saved replay-buffer length")
    if metrics:
        raise ValueError("Replay is limited to a failure before any completed episode")
    actions = []
    names = [entry["action"] for entry in action_mapping]
    for index, transition in enumerate(buffer):
        if not isinstance(transition, (list, tuple)) or len(transition) != 5:
            raise ValueError(f"Malformed replay transition at index {index}")
        action_index = transition[1]
        if type(action_index) is not int or not 0 <= action_index < len(names):
            raise ValueError(f"Invalid saved action index at transition {index}")
        if bool(transition[4]):
            raise ValueError("Replay buffer contains a terminal transition; episode boundary is ambiguous")
        actions.append(names[action_index])
    first_observation = buffer[0][0]
    if (not isinstance(first_observation, (list, tuple)) or len(first_observation) != 22 or
            not all(math.isfinite(float(value)) for value in first_observation)):
        raise ValueError("Checkpoint does not contain a finite sensor_vector_v1 initial observation")

    previous = action_for_twist(failure.get("previous_action_twist") or
                                failure.get("previous_command_twist") or {}, action_mapping)
    failed_action = action_for_twist(failure.get("requested_command_twist") or {}, action_mapping)
    if actions[-1] != previous:
        raise ValueError("Last saved replay action disagrees with failure's previous command")
    if failure.get("command_mode_transition") != "ROTATION_TO_LINEAR":
        raise ValueError("Failure transition classification changed")
    return {"completed_actions": actions, "failed_action": failed_action,
            "action_sequence": actions + [failed_action],
            "failed_action_index_1_based": len(actions) + 1,
            "previous_action": previous, "failure_action": failed_action,
            "completed_action_count": len(actions), "episode": 1,
            "episode_inference_basis": "empty metrics and no completed episode records; trainer starts at episode 1",
            "sequence_source": "checkpoint replay-buffer action indices plus requested Twist in saved validator exception",
            "sequence_complete_through_failure": True,
            "first_saved_observation_vector": [float(value) for value in first_observation]}


def extract_replay(artifact_dir: Path) -> dict:
    artifact_dir = Path(artifact_dir)
    summary = json.loads((artifact_dir / "training_summary.json").read_text(encoding="utf-8"))
    config = json.loads((artifact_dir / "training_config.json").read_text(encoding="utf-8"))
    scenario = json.loads((artifact_dir / "scenario.json").read_text(encoding="utf-8"))
    run_dirs = sorted((artifact_dir / "runs").glob("run_*/model.pt"))
    if len(run_dirs) != 1:
        raise ValueError(f"Expected exactly one failed run checkpoint, found {len(run_dirs)}")
    run_dir = run_dirs[0].parent
    metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
    checkpoint = torch.load(run_dirs[0], map_location="cpu", weights_only=True)
    failure = parse_failed_validation(summary.get("error", ""))
    mapping = gazebo_physics_action_mapping()
    replay = build_replay_sequence(checkpoint, failure, metrics, mapping)
    if summary.get("status") != "infrastructure_failure" or summary.get("category") != "validator_failure":
        raise ValueError("Artifact summary is not the expected failed Stage 1 run")
    if int(checkpoint.get("global_step", -1)) != replay["completed_action_count"]:
        raise ValueError("Global action count disagrees with reconstructed action prefix")
    replay.update({"artifact_dir": str(artifact_dir), "run_dir": str(run_dir),
        "run_id": run_dir.name, "training_seed": config["seed"],
        "episode_reset_seed": int(config["seed"]) + 1,
        "reset_type": "fresh_process_initialization",
        "scenario": scenario, "scenario_start_grid": scenario.get("start"),
        "physical_start_pose_expected": {
            "x": float(scenario["start"][0]) + .5,
            "y": float(scenario["start"][1]) + .5,
            "yaw": 0.0},
        "checkpoint_global_step": checkpoint.get("global_step"),
        "checkpoint_replay_buffer_length": len(checkpoint.get("buffer", [])),
        "completed_episode_metrics": metrics,
        "failed_transition_evidence": failure,
        "failed_action_simulation_interval": [
            failure.get("odometry_before", {}).get("timestamp"),
            failure.get("odometry_after", {}).get("timestamp")],
        "actual_absolute_world_pose_at_failure": "not recorded in source artifact"})
    return replay


def classify_acceptance(validation: dict | None, collision_blocked: bool) -> str:
    validation = validation or {}
    if validation.get("valid") is not True or collision_blocked:
        return "NONE"
    if validation.get("discrepancy_classification") == "validated_rotation_to_linear_transient":
        return "ROTATION_TO_LINEAR_TRANSIENT"
    return "NORMAL"


def run_replay(artifact_dir: Path, output: Path, *, gui=False, env_factory=None) -> dict:
    replay = extract_replay(artifact_dir)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    report = {"schema_version": "0.7.1", "verifier": "saved Gazebo DQN Stage 1 action replay",
        "status": "NOT_STARTED", "control_mode": "PHYSICS", "dqn_used": False,
        "training_used": False, "uses_production_training_environment": True,
        "uses_production_env_step": True, "uses_actual_sensor_and_contact_path": True,
        "action_sequence": replay["action_sequence"], "replay_source": replay,
        "actions": []}
    env = None
    try:
        scenario = ScenarioSpec.from_dict(replay["scenario"])
        factory = env_factory or GazeboPhysicsTrainingEnvironment
        env = factory(scenario, int(json.loads((Path(artifact_dir) / "training_config.json").read_text())["max_steps"]),
            root=output / "worlds", gui=gui, max_sensor_age_ms=20)
        # Match Trainer.run(): its first operation is env.reset(seed), which
        # performs the fresh process launch/initialization through prepare().
        env.reset(replay["episode_reset_seed"])
        if env.injected or env.control_mode != "PHYSICS":
            raise RuntimeError("Replay requires actual Gazebo transport in PHYSICS mode")
        if not env.process or env.process.poll() is not None:
            raise RuntimeError("Fresh Gazebo process is not alive after training reset")
        if int(getattr(env, "restart_fallbacks", 0)) != 0:
            raise RuntimeError("Replay initial reset used an unexpected restart fallback")
        from aero_ai_studio.observation.encoder import observation_vector
        initial_observation = observation_vector(env.get_agent_observation("sensor", 2))
        reference_observation = replay["first_saved_observation_vector"]
        report.update(status="RUNNING", process=env.manager.status(),
            partition=env.manager.partition, world=env.world_name,
            initial_reset_evidence=dict(env.last_reset_evidence),
            initial_sensor_contract=env.last_reset_evidence.get("observation_contract"),
            initial_pose=dict(env.env.pose),
            first_observation_reference=reference_observation,
            first_observation_actual=initial_observation,
            initial_observation_exact_match=initial_observation == reference_observation)
        target_entry = None
        for index, action in enumerate(replay["action_sequence"], start=1):
            base = env.env
            entry = {"action_index_1_based": index, "action": action,
                "before_pose": dict(base.pose),
                "before_simulation_time": float(base.stepper.time)}
            try:
                result = env.step(action)
                entry["result"] = {"terminated": result.terminated, "truncated": result.truncated,
                    "reason": result.reason, "reward": result.reward}
            except Exception as error:
                entry["exception"] = {"type": type(error).__name__, "message": str(error)}
            transition = base.telemetry.get("action_transition")
            validation = base.telemetry.get("pose_validation")
            entry["action_transition"] = transition
            entry["pose_validation"] = validation
            entry["contact_state"] = dict(getattr(getattr(base, "contacts", None), "state", {}))
            entry["collision_event"] = (None if base.collision_event is None else
                base.collision_event.to_dict() if hasattr(base.collision_event, "to_dict") else str(base.collision_event))
            entry["after_pose"] = None if base.pose is None else dict(base.pose)
            entry["after_simulation_time"] = float(base.stepper.time)
            if index == replay["failed_action_index_1_based"]:
                entry["world_pose_history_summary"] = (transition or {}).get("world_pose_history_summary")
                entry["world_pose_history"] = (transition or {}).get("world_pose_history")
                entry["step_evidence"] = dict(base.stepper.last_verification)
                transient = (validation or {}).get("discrepancy_classification") == \
                    "validated_rotation_to_linear_transient"
                entry["normal_movement_valid"] = bool(
                    (validation or {}).get("valid") is True and not transient)
                entry["production_pose_validation_pass"] = (validation or {}).get("valid") is True
                body = entry["world_pose_history_summary"] or {}
                entry["world_pose_evidence_pass"] = bool(
                    body.get("world_pose_history_available") is True and
                    body.get("world_pose_history_fresh") is True and
                    body.get("world_pose_history_dense_enough") is True and
                    (validation or {}).get("rotation_to_linear_body_history_interval_ok") is True)
                blocked = bool((validation or {}).get("collision_may_block_motion") is True or
                    (entry["contact_state"] or {}).get("new_contact_event") is True or
                    entry["collision_event"] is not None)
                entry["collision_contact_blocked"] = blocked
                entry["collision"] = blocked
                entry["rotation_to_linear_transient_valid"] = transient and (validation or {}).get(
                    "rotation_to_linear_transient_valid") is True
                entry["acceptance_path"] = classify_acceptance(validation, blocked)
                target_entry = entry
            report["actions"].append(entry)
            if "exception" in entry:
                break
            if result.terminated or result.truncated:
                break
        report["target_transition_found"] = target_entry is not None
        report["target_transition"] = target_entry
        report["target_action_index_1_based"] = replay["failed_action_index_1_based"]
        if target_entry is None:
            report["status"] = "TARGET_TRANSITION_NOT_REACHED"
        elif target_entry.get("action_index_1_based") != replay["failed_action_index_1_based"] or \
                (target_entry.get("action_transition") or {}).get("command_mode_transition") != "ROTATION_TO_LINEAR":
            report["status"] = "REPLAY_DIVERGED_BEFORE_TARGET"
        elif target_entry.get("acceptance_path") == "ROTATION_TO_LINEAR_TRANSIENT":
            report["status"] = "R2L_TRANSIENT_ACTUAL_VERIFIED"
        elif target_entry.get("acceptance_path") == "NORMAL":
            report["status"] = "STAGE1_SEQUENCE_ACTUAL_PASS_TRANSIENT_NOT_REPRODUCED"
        elif ((target_entry.get("exception") or {}).get("message", "").startswith(ERROR_PREFIX) or
              (target_entry.get("pose_validation") or {}).get("valid") is False):
            report["status"] = "PRODUCTION_VALIDATOR_REJECTED_TRANSITION"
        elif target_entry.get("exception"):
            report["status"] = "INFRASTRUCTURE_FAILURE"
        else:
            report["status"] = "REPLAY_INCONCLUSIVE"
        report["final_process"] = env.manager.status()
    except Exception as error:
        report.update(status="INFRASTRUCTURE_FAILURE", error={"type": type(error).__name__, "message": str(error)})
    finally:
        if env is not None:
            try:
                env.close()
                report["shutdown"] = "PASS"
            except Exception as error:
                report["shutdown"] = "FAIL"
                report["shutdown_error"] = str(error)
        report["evidence_file"] = str(output / "stage1_failure_replay.json")
        write_json(output / "stage1_failure_replay.json", report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--gui", action="store_true")
    args = parser.parse_args(argv)
    report = run_replay(args.artifact_dir, args.output, gui=args.gui)
    print("Gazebo Stage 1 failure replay: " + report["status"])
    target = report.get("target_transition") or {}
    print("target action: " + str(target.get("action_index_1_based", "NOT REACHED")))
    print("acceptance path: " + str(target.get("acceptance_path", "NONE")))
    print("evidence: " + report["evidence_file"])
    return 0 if report["status"] in (
        "R2L_TRANSIENT_ACTUAL_VERIFIED",
        "STAGE1_SEQUENCE_ACTUAL_PASS_TRANSIENT_NOT_REPRODUCED") else 1


if __name__ == "__main__":
    raise SystemExit(main())
