#!/usr/bin/env python3
"""Replay the saved Stage 1 prefix through production R2L macro integration."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aero_ai_studio.core.storage import write_json
from aero_ai_studio.observation.encoder import observation_vector
from aero_ai_studio.scenario.models import ScenarioSpec
from aero_ai_studio.simulation.base import ACTIONS, PhysicalControlFailure
from aero_ai_studio.training.gazebo_physics import GazeboPhysicsTrainingEnvironment
from aero_ai_studio.training.temporal import NOMINAL_DISCOUNT_TIME_UNIT_SECONDS
from tools.verify_v07_gazebo_stage1_failure_replay import extract_replay


def _macro_reward(chunks: list[dict], gamma: float) -> float:
    reward = 0.0
    elapsed = 0.0
    for chunk in chunks:
        reward += gamma ** (elapsed / NOMINAL_DISCOUNT_TIME_UNIT_SECONDS) * float(chunk["reward"])
        elapsed += float(chunk["elapsed_execution_time"])
    return reward


def run_verifier(artifact_dir: Path, output: Path, *, gui: bool = False,
                 env_factory=None) -> dict:
    replay = extract_replay(Path(artifact_dir))
    artifact_dir = Path(artifact_dir)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    config = json.loads((artifact_dir / "training_config.json").read_text(encoding="utf-8"))
    report = {
        "schema_version": "0.7.1",
        "verifier": "production Gazebo R2L macro integration",
        "status": "NOT_STARTED",
        "dqn_used": False,
        "training_used": False,
        "uses_production_training_environment": True,
        "uses_production_environment_step": True,
        "uses_production_validator": True,
        "target_action_index_1_based": replay["failed_action_index_1_based"],
        "action_sequence": replay["action_sequence"],
        "replay_source": replay,
        "actions": [],
    }
    env = None
    try:
        env = (env_factory or GazeboPhysicsTrainingEnvironment)(
            ScenarioSpec.from_dict(replay["scenario"]), int(config["max_steps"]),
            root=output / "worlds", gui=gui, max_sensor_age_ms=20,
            gamma=float(config.get("gamma", .95)))
        env.reset(replay["episode_reset_seed"])
        if env.injected or env.control_mode != "PHYSICS":
            raise RuntimeError("Verifier requires actual Gazebo transport in PHYSICS mode")
        if not env.process or env.process.poll() is not None:
            raise RuntimeError("Gazebo process is not alive after fresh-process initialization")
        if int(getattr(env, "restart_fallbacks", 0)) != 0:
            raise RuntimeError("Unexpected restart fallback during fresh-process initialization")
        initial_actual=observation_vector(env.get_agent_observation("sensor",2))
        initial_reference=replay["first_saved_observation_vector"]
        report.update(initial_reset_evidence=dict(env.last_reset_evidence),
            initial_pose=dict(env.env.pose),
            first_observation_reference=initial_reference,
            first_observation_actual=initial_actual,
            initial_observation_exact_match=initial_actual==initial_reference,
            original_direct_failure={
                "world_forward_displacement": replay["failed_transition_evidence"].get(
                    "world_forward_displacement"),
                "world_yaw_delta": replay["failed_transition_evidence"].get("world_yaw_delta"),
                "command_mode_transition": replay["failed_transition_evidence"].get(
                    "command_mode_transition"),
            })

        from aero_ai_studio.agents.dqn import ReplayBuffer

        target = None
        for index, action in enumerate(replay["action_sequence"], start=1):
            observation = env.get_agent_observation("sensor", 2)
            before_vector = observation_vector(observation)
            before_decisions = int(env.env.steps)
            entry = {"decision_index": index, "agent_intent": action,
                     "before_simulation_time": float(env.env.stepper.time),
                     "before_pose": dict(env.env.pose)}
            try:
                result = env.step(action)
                next_observation = env.get_agent_observation("sensor", 2)
                next_vector = observation_vector(next_observation)
                entry.update(
                    reward=float(result.reward), reason=result.reason,
                    terminated=bool(result.terminated), truncated=bool(result.truncated),
                    elapsed_execution_time=result.elapsed_execution_time,
                    elapsed_discount_units=result.elapsed_discount_units,
                    after_simulation_time=float(env.env.stepper.time),
                    after_pose=dict(env.env.pose),
                    environment_decision_delta=int(env.env.steps) - before_decisions,
                    execution_evidence=result.execution_evidence)
                if index == replay["failed_action_index_1_based"]:
                    evidence=result.execution_evidence or {}
                    chunks=evidence.get("reward_chunks", [])
                    gamma=float(config.get("gamma", .95))
                    recomputed_reward=_macro_reward(chunks,gamma) if chunks else None
                    expected_units=(float(result.elapsed_execution_time) /
                                    NOMINAL_DISCOUNT_TIME_UNIT_SECONDS
                                    if result.elapsed_execution_time is not None else None)
                    phases=evidence.get("execution_phases", [])
                    acquire=next((phase for phase in phases
                                  if phase.get("phase")=="ACQUIRE_LINEAR"),{})
                    brake=next((phase for phase in phases
                                if phase.get("phase")=="BRAKE_ANGULAR"),{})
                    transition=dict(env.env.telemetry.get("action_transition") or {})
                    collision=bool(evidence.get("collision") or
                        env.env.collision_event is not None or
                        transition.get("collision_may_block_motion"))
                    replay_payload=(
                        before_vector, ACTIONS.index(action), float(result.reward),
                        next_vector, bool(result.terminated or result.truncated),
                        float(result.elapsed_discount_units))
                    # Exercise the same six-field normalization contract used by DQN.
                    normalized=ReplayBuffer.normalize_transition(replay_payload)
                    target={**entry,
                        "transition_type":evidence.get("transition_type"),
                        "execution_phases":[phase.get("phase") for phase in phases],
                        "executed_commands":evidence.get("executed_commands"),
                        "control_chunk_count":evidence.get("control_chunk_count"),
                        "macro_reward":evidence.get("macro_reward"),
                        "recomputed_macro_reward":recomputed_reward,
                        "expected_elapsed_discount_units":expected_units,
                        "replay_transition_payload":{"field_count":len(normalized),
                            "action_index":normalized[1],"reward":normalized[2],
                            "done":normalized[4],"elapsed_discount_units":normalized[5]},
                        "production_pose_validation":acquire.get("production_pose_validation"),
                        "collision":collision,
                        "acceptance_checks":{
                            "R2L_execution_evidence": evidence.get("transition_type")=="ROTATION_TO_LINEAR",
                            "brake_before_acquire": (len(phases)>=2 and
                                phases[0].get("phase")=="BRAKE_ANGULAR" and
                                phases[-1].get("phase")=="ACQUIRE_LINEAR"),
                            "braking_reward_chunks_present": any(
                                chunk.get("phase")=="BRAKE_ANGULAR" for chunk in chunks),
                            "body_feedback_braking_pass": brake.get("completion_result") is True,
                            "control_chunk_count_matches_rewards": evidence.get(
                                "control_chunk_count")==len(chunks),
                            "one_agent_decision": int(env.env.steps)-before_decisions==1,
                            "elapsed_units_match": (expected_units is not None and math.isclose(
                                float(result.elapsed_discount_units),expected_units,rel_tol=0.,abs_tol=1e-9)),
                            "executor_reported_macro_reward_matches": (evidence.get("macro_reward") is not None and
                                math.isclose(float(result.reward),float(evidence["macro_reward"]),
                                    rel_tol=0.,abs_tol=1e-8)),
                            "macro_reward_matches_chunks": (recomputed_reward is not None and math.isclose(
                                float(result.reward),recomputed_reward,rel_tol=0.,abs_tol=1e-8)),
                            "physical_execution_status_pass": evidence.get("physical_status")=="EXECUTED",
                            "one_six_field_transition": len(normalized)==6 and normalized[1]==ACTIONS.index("down"),
                            "production_validator_pass": acquire.get("production_pose_validation",{}).get("valid") is True,
                            "collision_false": not collision,
                        }}
                    target["acceptance_checks"]["all_pass"] = all(
                        target["acceptance_checks"].values())
                if result.terminated or result.truncated:
                    report["actions"].append(entry)
                    break
            except PhysicalControlFailure as error:
                entry["physical_control_failure"] = error.to_dict()
                report["actions"].append(entry)
                if index == replay["failed_action_index_1_based"]:
                    target=entry
                break
            except Exception as error:
                entry["exception"]={"type":type(error).__name__,"message":str(error)}
                report["actions"].append(entry)
                if index == replay["failed_action_index_1_based"]:
                    target=entry
                break
            report["actions"].append(entry)
        report["target_transition"] = target
        checks=(target or {}).get("acceptance_checks",{})
        if target is None:
            report["status"]="TARGET_TRANSITION_NOT_REACHED"
        elif checks.get("all_pass") is True:
            report["status"]="PRODUCTION_R2L_MACRO_ACTUAL_VERIFIED"
        elif target.get("physical_control_failure"):
            report["status"]="PHYSICAL_CONTROL_FAILURE"
        elif target.get("exception"):
            report["status"]="INFRASTRUCTURE_FAILURE"
        else:
            report["status"]="PRODUCTION_R2L_MACRO_REJECTED_OR_INCOMPLETE"
        report["final_process"] = env.manager.status()
    except Exception as error:
        report.update(status="INFRASTRUCTURE_FAILURE",
                      error={"type":type(error).__name__,"message":str(error)})
    finally:
        if env is not None:
            try:
                env.close()
                report["shutdown"]="PASS"
            except Exception as error:
                report["shutdown"]="FAIL"
                report["shutdown_error"]=str(error)
        report["evidence_file"]=str(output / "r2l_production_integration.json")
        write_json(output / "r2l_production_integration.json",report)
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--gui",action="store_true")
    args=parser.parse_args(argv)
    report=run_verifier(args.artifact_dir,args.output,gui=args.gui)
    print("Gazebo production R2L integration: "+report["status"])
    print("target action: "+str((report.get("target_transition") or {}).get("decision_index","NOT REACHED")))
    print("evidence: "+report["evidence_file"])
    return 0 if report["status"]=="PRODUCTION_R2L_MACRO_ACTUAL_VERIFIED" else 1


if __name__=="__main__":
    raise SystemExit(main())
