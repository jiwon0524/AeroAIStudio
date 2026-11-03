#!/usr/bin/env python3
"""DQN-free actual-host verification for experimental UP-to-DOWN reversal."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aero_ai_studio.core.storage import write_json
from aero_ai_studio.gazebo.control_executor import (
    GazeboLinearReversalControlExecutor,
    _contact_contract_pass,
)
from aero_ai_studio.scenario.models import ScenarioSpec
from aero_ai_studio.simulation.action_mapping import (
    classify_physics_command_transition,
    gazebo_physics_twist,
)
from aero_ai_studio.simulation.control_execution import (
    ControlExecutionRequest,
    ControlExecutionStatus,
    plan_control_execution,
)
from aero_ai_studio.simulation.base import PhysicalControlFailure
from aero_ai_studio.training.gazebo_physics import GazeboPhysicsTrainingEnvironment
from aero_ai_studio.training.temporal import NOMINAL_DISCOUNT_TIME_UNIT_SECONDS
from tools.verify_v07_gazebo_control_executor_linear_reversal import (
    extract_reversal_replay,
)


PREFIX = ["up", "down", "up", "up", "up"]


def _validate_prefix_sources(replay: dict, retry_evidence: dict) -> dict:
    """Cross-check the exact early prefix against both saved actual artifacts."""
    episode_actions = replay["completed_episode_actions"][0]
    if episode_actions[:5] != PREFIX or episode_actions[5:7] != ["down", "up"]:
        raise ValueError("Saved Stage1 action sequence does not match retry2 actions 1–7")
    rows = (retry_evidence.get("episode_replays") or [{}])[0].get("actions", [])
    recorded = [row.get("action") for row in rows]
    if recorded[:6] != episode_actions[:6]:
        raise ValueError("Retry2 replay evidence disagrees with saved Stage1 action sequence")
    failed = retry_evidence.get("failed_replay_action") or {}
    if (failed.get("episode") != 1 or
            failed.get("episode_action_index_1_based") != 7 or
            failed.get("action") != "up" or
            failed.get("action") != episode_actions[6] or
            failed.get("type") != "PhysicalControlFailure"):
        raise ValueError("Retry2 evidence does not identify the expected action-7 failure")
    return {"source_stage1_actions": episode_actions[:7],
        "retry2_replayed_actions": recorded[:6],
        "retry2_failed_action": failed,
        "prefix_actions": PREFIX,
        "target_action": "down",
        "target_corresponds_to_saved_action_index_1_based": 6,
        "prefix_crosscheck_pass": True}


def _sensor_and_task_callback(adapter, prior_sequence):
    def check_chunk(row):
        observation = adapter.get_agent_observation("sensor", 2)
        contract = adapter._require_actual_sensor(observation, prior_sequence[0])
        prior_sequence[0] = contract["sequence"]
        env = adapter.env
        contact_state = dict(getattr(getattr(env, "contacts", None), "state", {}))
        contact_schema = getattr(getattr(env, "contacts", None), "schema", None)
        if not _contact_contract_pass(env, contact_state, contact_schema):
            raise RuntimeError("Contact publisher/schema readiness failed during braking")
        pose = row["pose_after"]
        goal = env.goal
        goal_radius = float(adapter.goal_radius)
        goal_reached = math.dist((pose["x"], pose["y"]), goal) <= goal_radius
        return {"reason": "goal" if goal_reached else "moving",
            "terminated": goal_reached, "truncated": False, "collision": False,
            "sensor_contract": contract, "contact_state": contact_state,
            "contact_schema": contact_schema}
    return check_chunk


def run_verifier(artifact_dir: Path, retry_evidence_path: Path, output: Path,
                 *, gui=False, env_factory=None) -> dict:
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    report = {"schema_version": "0.7.1",
        "verifier": "DQN-free experimental Gazebo UP-to-DOWN LINEAR_REVERSAL",
        "status": "INITIALIZING", "verdict": "INCONCLUSIVE",
        "failure_stage": "ARTIFACT_EXTRACTION", "last_completed_stage": None,
        "dqn_used": False, "training_used": False,
        "production_routing_used_for_target": False,
        "production_activation": False, "acceptance": None,
        "prefix_actions": PREFIX, "target_action": "down",
        "target_episode": 1, "target_action_index_in_episode_1_based": 6,
        "transition_type": "LINEAR_REVERSAL", "previous_action": "up",
        "requested_action": "down", "process_status": None,
        "reset_evidence": None, "error": None, "shutdown": "NOT_ATTEMPTED"}
    adapter = None
    try:
        replay = extract_reversal_replay(Path(artifact_dir))
        retry_evidence = json.loads(Path(retry_evidence_path).read_text(encoding="utf-8"))
        report["replay_source"] = _validate_prefix_sources(replay, retry_evidence)
        report["saved_stage1_replay_source"] = replay["run_id"]
        report["last_completed_stage"] = "ARTIFACT_EXTRACTION"

        report.update(status="ENVIRONMENT_STARTUP", failure_stage="ENVIRONMENT_STARTUP")
        scenario = ScenarioSpec.from_dict(replay["scenario"])
        factory = env_factory or GazeboPhysicsTrainingEnvironment
        adapter = factory(scenario, replay["max_steps"], root=output / "worlds",
                          gui=gui, max_sensor_age_ms=20)
        report.update(status="INITIAL_RESET", failure_stage="INITIAL_RESET",
                      last_completed_stage="ENVIRONMENT_STARTUP")
        adapter.reset(int(replay["training_seed"]) + 1)
        report["reset_evidence"] = dict(adapter.last_reset_evidence)
        if adapter.injected or adapter.control_mode != "PHYSICS":
            raise RuntimeError("Verifier requires actual Gazebo transport in PHYSICS mode")
        process = adapter.process
        if process is None or process.poll() is not None:
            raise RuntimeError("Gazebo process is not alive after fresh initialization")
        if int(getattr(adapter, "restart_fallbacks", 0)) != 0:
            raise RuntimeError("Fresh initialization unexpectedly used restart fallback")
        report["initial_pid"] = process.pid
        report["process_status"] = adapter.manager.status()
        report.update(status="REPLAYING_PREFIX", failure_stage="REPLAYING_PREFIX",
                      last_completed_stage="INITIAL_RESET")

        prefix_steps = []
        for index, action in enumerate(PREFIX, start=1):
            before = float(adapter.env.stepper.time)
            try:
                result = adapter.step(action)
            except PhysicalControlFailure as error:
                raise _VerifierFailure("prefix_physical_control_failure", str(error),
                    evidence={"prefix_action_index_1_based": index,
                        "action": action, "failure": error.to_dict(),
                        "completed_prefix_steps": prefix_steps}) from error
            except Exception as error:
                raise _VerifierFailure("prefix_infrastructure_failure", str(error),
                    evidence={"prefix_action_index_1_based": index,
                        "action": action, "completed_prefix_steps": prefix_steps}) from error
            prefix_steps.append({"index_1_based": index, "action": action,
                "simulation_start": before,
                "simulation_end": float(adapter.env.stepper.time),
                "elapsed_simulation_time": float(adapter.env.stepper.time) - before,
                "reason": result.reason, "terminated": result.terminated,
                "truncated": result.truncated,
                "execution_evidence": result.execution_evidence,
                "physics_validation": adapter.env.telemetry.get("pose_validation"),
                "sensor": (adapter.env.telemetry.get("gazebo_dqn_training") or {}).get(
                    "sensor_after"),
                "contact": dict(getattr(adapter.env, "contacts", None).state)
                    if getattr(adapter.env, "contacts", None) else None})
            if result.terminated or result.truncated:
                raise _VerifierFailure("prefix_task_terminal",
                    "Saved prefix terminated before the target reversal",
                    evidence={"completed_prefix_steps": prefix_steps})
        report["prefix_replay"] = {"expected_count": 5,
            "replayed_count": len(prefix_steps), "steps": prefix_steps}
        if len(prefix_steps) != 5 or prefix_steps[-1]["action"] != "up":
            raise _VerifierFailure("prefix_mismatch", "UP-to-DOWN precondition prefix mismatch",
                                   evidence=report["prefix_replay"])
        report["last_completed_stage"] = "REPLAYING_PREFIX"

        env = adapter.env
        previous_command = dict(env.controller.last_command)
        requested_command = gazebo_physics_twist("down")
        transition = classify_physics_command_transition(previous_command,
                                                          requested_command)
        if (previous_command != gazebo_physics_twist("up") or
                transition != "LINEAR_REVERSAL"):
            raise _VerifierFailure("target_precondition_failed",
                "Prefix did not leave the requested UP to DOWN command transition",
                evidence={"previous_command": previous_command,
                    "requested_command": requested_command,
                    "transition_type": transition})
        prehistory = dict((env.telemetry.get("action_transition") or {}).get(
            "world_pose_history_summary") or {})
        report.update(status="EXECUTING_EXPERIMENTAL_TARGET",
            failure_stage="EXECUTING_EXPERIMENTAL_TARGET",
            last_completed_stage="REPLAYING_PREFIX")
        target_start = float(env.stepper.time)
        request = ControlExecutionRequest("down", previous_command,
            requested_command, "LINEAR_REVERSAL")
        executor = GazeboLinearReversalControlExecutor(adapter,
            pre_braking_history=prehistory, previous_action="up",
            requested_action="down")
        prior_sequence = [int((env.telemetry.get("gazebo_dqn_training") or {}).get(
            "sensor_after", {}).get("sequence", -1))]
        execution = executor.execute_plan(executor.plan(request),
            on_braking_chunk=_sensor_and_task_callback(adapter, prior_sequence))
        execution_dict = execution.to_dict()
        elapsed = float(env.stepper.time) - target_start
        report["execution"] = {"request": request.to_dict(),
            "plan": execution_dict["phases"],
            "result": execution_dict,
            "phase_evidence": (execution.execution_evidence or {}).get("phase_evidence", []),
            "executed_commands": execution_dict["executed_commands"],
            "elapsed_execution_time": elapsed,
            "elapsed_discount_units": elapsed / NOMINAL_DISCOUNT_TIME_UNIT_SECONDS,
            "control_chunk_count": sum(len(phase.get("chunks", []))
                for phase in (execution.execution_evidence or {}).get("phase_evidence", [])) +
                int(any(phase.get("phase") == "ACQUIRE_LINEAR"
                    for phase in (execution.execution_evidence or {}).get("phase_evidence", []))),
            "elapsed_discount_time_unit_seconds": NOMINAL_DISCOUNT_TIME_UNIT_SECONDS,
            "physical_status": execution.status.value,
            "pre_braking_world_body_history": prehistory,
            "wheel_odometry_corroboration": (env.telemetry.get("action_transition") or {}).get(
                "odometry_history"),
            "production_routing_used": False}
        status = execution.status
        if status is ControlExecutionStatus.EXECUTED:
            report["verdict"] = "LINEAR_REVERSAL_UP_TO_DOWN_ACTUAL_PASS"
            report["acceptance"] = {"braking_world_body_stopped": True,
                "acquisition_world_body_direction": True,
                "production_validator": True, "collision": False,
                "sensor_contact_process": True}
        elif status in (ControlExecutionStatus.PHYSICAL_CONTROL_FAILURE,
                        ControlExecutionStatus.INCONCLUSIVE):
            report["verdict"] = "LINEAR_REVERSAL_UP_TO_DOWN_PHYSICAL_FAILURE"
        elif status is ControlExecutionStatus.COLLISION:
            report["verdict"] = "LINEAR_REVERSAL_UP_TO_DOWN_COLLISION"
        elif status is ControlExecutionStatus.TASK_TERMINAL:
            report["verdict"] = "LINEAR_REVERSAL_UP_TO_DOWN_TASK_TERMINAL"
        else:
            report["verdict"] = "LINEAR_REVERSAL_UP_TO_DOWN_INFRASTRUCTURE_FAILURE"
        report["process_status"] = adapter.manager.status()
        report["status"] = "COMPLETE"
        report["failure_stage"] = None
        report["last_completed_stage"] = "EXPERIMENTAL_TARGET_COMPLETE"
    except _VerifierFailure as error:
        report.update(status="FAILED", verdict=(
            "LINEAR_REVERSAL_UP_TO_DOWN_PHYSICAL_FAILURE" if
            error.category == "prefix_physical_control_failure" else
            "LINEAR_REVERSAL_UP_TO_DOWN_INFRASTRUCTURE_FAILURE"),
            failure_stage=error.category, error={"type": type(error).__name__,
                "message": str(error)}, failure_evidence=error.evidence)
    except Exception as error:
        report.update(status="FAILED", verdict="LINEAR_REVERSAL_UP_TO_DOWN_INFRASTRUCTURE_FAILURE",
            error={"type": type(error).__name__, "message": str(error)})
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
        report["evidence_file"] = str(output / "up_to_down_control_executor.json")
        write_json(output / "up_to_down_control_executor.json", report)
    return report


class _VerifierFailure(RuntimeError):
    def __init__(self, category, message, *, evidence=None):
        super().__init__(message)
        self.category = category
        self.evidence = evidence or {}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--retry-evidence", type=Path, required=True,
        help="Phase 3C-B retry2 report used to cross-check saved actions 1–7")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--gui", action="store_true")
    args = parser.parse_args(argv)
    report = run_verifier(args.artifact_dir, args.retry_evidence, args.output,
                          gui=args.gui)
    print("Gazebo experimental UP-to-DOWN reversal: " + report["verdict"])
    print("evidence: " + report["evidence_file"])
    return 0 if report["verdict"] == "LINEAR_REVERSAL_UP_TO_DOWN_ACTUAL_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
