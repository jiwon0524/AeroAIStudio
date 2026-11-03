#!/usr/bin/env python3
"""Host-only actual Gazebo check of feedback-based R2L braking/acquisition."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from aero_ai_studio.core.storage import write_json
from aero_ai_studio.gazebo.control_executor import GazeboControlExecutor
from aero_ai_studio.gazebo.entity_controller import summarize_world_pose_history
from aero_ai_studio.scenario.models import ScenarioSpec
from aero_ai_studio.simulation.action_mapping import (
    classify_physics_command_transition,
    gazebo_physics_twist,
)
from aero_ai_studio.simulation.control_execution import (
    ControlExecutionRequest,
    ControlExecutionStatus,
)
from aero_ai_studio.simulation.base import PhysicalControlFailure
from aero_ai_studio.training.gazebo_physics import GazeboPhysicsTrainingEnvironment
from verify_v07_gazebo_stage1_failure_replay import extract_replay


def build_target_request(env, replay):
    """Build the target request from the replayed final action and saved intent."""
    if replay["failed_action"] != "down" or replay["previous_action"] != "right":
        raise ValueError("Saved Stage 1 target is not right → down")
    base = env.env
    previous = dict(base.controller.last_command)
    requested = gazebo_physics_twist(replay["failed_action"])
    transition = classify_physics_command_transition(previous, requested)
    if transition != "ROTATION_TO_LINEAR":
        raise ValueError(f"Replayed commands classify as {transition}, expected ROTATION_TO_LINEAR")
    return ControlExecutionRequest(
        agent_intent=replay["failed_action"],
        previous_command=previous,
        requested_command=requested,
        transition_type=transition,
    )


def run_verifier(artifact_dir: Path, output: Path, *, gui=False, env_factory=None):
    replay = extract_replay(Path(artifact_dir))
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": "0.7.1",
        "verifier": "actual Gazebo feedback R2L control executor",
        "status": "NOT_STARTED",
        "verdict": "R2L_EXECUTOR_INFRASTRUCTURE_FAILURE",
        "dqn_used": False,
        "training_used": False,
        "production_training_path_wired": False,
        "uses_production_prefix_env_step": True,
        "uses_production_acquisition_env_step_and_validator": True,
        "uses_actual_sensor_and_contact_path": True,
        "replay_source": replay,
        "prefix_actions": [],
    }
    env = None
    try:
        factory = env_factory or GazeboPhysicsTrainingEnvironment
        scenario = ScenarioSpec.from_dict(replay["scenario"])
        config_path = Path(artifact_dir) / "training_config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        env = factory(scenario, int(config["max_steps"]), root=output / "worlds",
                      gui=gui, max_sensor_age_ms=20)
        env.reset(int(replay["episode_reset_seed"]))
        if env.injected or env.control_mode != "PHYSICS":
            raise RuntimeError("Verifier requires actual Gazebo transport in PHYSICS mode")
        if not env.process or env.process.poll() is not None:
            raise RuntimeError("Fresh Gazebo process is not alive after initialization")
        if int(getattr(env, "restart_fallbacks", 0)) != 0:
            raise RuntimeError("Initial fresh-process setup used an unexpected restart fallback")

        prefix = replay["completed_actions"]
        if len(prefix) != 33 or replay["failed_action_index_1_based"] != 34:
            raise ValueError("Expected the saved 33-action prefix and target action 34")
        precondition_history = None
        precondition_raw = []
        precondition_start = None
        for index, action in enumerate(prefix, start=1):
            base = env.env
            cursor = None
            start = float(base.stepper.time)
            if index == len(prefix):
                precondition_start = start
                cursor = base.transport.cursor(base.controller.pose_topic)
            before = dict(base.pose)
            result = env.step(action)
            row = {
                "action_index_1_based": index,
                "agent_intent": action,
                "before_pose": before,
                "before_simulation_time": start,
                "after_pose": dict(base.pose),
                "after_simulation_time": float(base.stepper.time),
                "terminated": result.terminated,
                "truncated": result.truncated,
                "reason": result.reason,
                "pose_validation": base.telemetry.get("pose_validation"),
            }
            report["prefix_actions"].append(row)
            if cursor is not None:
                precondition_raw = base.controller.pose_history_after(
                    cursor, start, float(base.stepper.time))
                precondition_history = summarize_world_pose_history(
                    precondition_raw, start, float(base.stepper.time))
            if result.terminated or result.truncated:
                raise RuntimeError(f"Saved prefix terminated early at action {index}: {result.reason}")

        request = build_target_request(env, replay)
        report.update(
            status="RUNNING",
            process=env.manager.status(),
            partition=env.manager.partition,
            world=env.world_name,
            initial_reset_evidence=dict(env.last_reset_evidence),
            target_action_index_1_based=34,
            target_request=request.to_dict(),
            pre_braking_history=precondition_history,
            pre_braking_history_raw=precondition_raw,
            pre_braking_interval=[precondition_start, float(env.env.stepper.time)],
            direct_failure_reference=replay["failed_transition_evidence"],
        )
        executor = GazeboControlExecutor(env, pre_braking_history=precondition_history or {})
        plan = executor.plan(request)
        result = executor.execute_plan(plan)
        execution = result.to_dict()
        report["execution_result"] = execution
        report["production_validator"] = (
            execution.get("execution_evidence", {}).get("acquisition_phase", {})
            .get("production_pose_validation"))
        if result.status == ControlExecutionStatus.EXECUTED:
            report["verdict"] = "R2L_EXECUTOR_ACTUAL_PASS"
        elif result.status == ControlExecutionStatus.COLLISION:
            report["verdict"] = "R2L_EXECUTOR_COLLISION"
        elif result.status == ControlExecutionStatus.PHYSICAL_CONTROL_FAILURE:
            phases = execution.get("execution_evidence", {}).get("phase_evidence", [])
            report["verdict"] = ("R2L_EXECUTOR_BRAKING_FAILED" if phases and
                phases[-1].get("phase") == "BRAKE_ANGULAR" else
                "R2L_EXECUTOR_LINEAR_ACQUISITION_FAILED")
        elif result.status == ControlExecutionStatus.INCONCLUSIVE:
            report["verdict"] = "R2L_EXECUTOR_PRECONDITION_NOT_MET"
        else:
            report["verdict"] = "R2L_EXECUTOR_INFRASTRUCTURE_FAILURE"
        report["status"] = report["verdict"]
        report["final_process"] = env.manager.status()
    except PhysicalControlFailure as error:
        report.update(status="R2L_EXECUTOR_PREFIX_PHYSICAL_FAILURE",
                      verdict="R2L_EXECUTOR_PREFIX_PHYSICAL_FAILURE",
                      error=error.to_dict())
    except Exception as error:
        report.update(status="R2L_EXECUTOR_INFRASTRUCTURE_FAILURE",
                      verdict="R2L_EXECUTOR_INFRASTRUCTURE_FAILURE",
                      error={"type": type(error).__name__, "message": str(error)})
    finally:
        if env is not None:
            try:
                env.close()
                report["shutdown"] = "PASS"
            except Exception as error:
                report["shutdown"] = "FAIL"
                report["shutdown_error"] = str(error)
        report["evidence_file"] = str(output / "control_executor_r2l.json")
        write_json(output / "control_executor_r2l.json", report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", type=Path, required=True,
                        help="Saved Stage 1 failure run output directory")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--gui", action="store_true")
    args = parser.parse_args(argv)
    report = run_verifier(args.artifact_dir, args.output, gui=args.gui)
    print("Gazebo R2L control executor: " + report["verdict"])
    print("evidence: " + report["evidence_file"])
    return 0 if report["verdict"] == "R2L_EXECUTOR_ACTUAL_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
