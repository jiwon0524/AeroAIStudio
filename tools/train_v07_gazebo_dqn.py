#!/usr/bin/env python3
"""Train/export the verifier-compatible DQN on actual Gazebo PHYSICS.

This command intentionally starts Gazebo and must be run on the validated Ubuntu host.
"""
from __future__ import annotations

import argparse
from collections import deque
from dataclasses import asdict
import json
import math
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from threading import Event

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aero_ai_studio.agents.dqn import DQNAgent
from aero_ai_studio.core.storage import write_json
from aero_ai_studio.gazebo.dqn_runtime import DQNCheckpointError, checkpoint_contract
from aero_ai_studio.models.registry import ModelRegistry
from aero_ai_studio.simulation.action_mapping import gazebo_physics_action_mapping
from aero_ai_studio.simulation.base import PhysicalControlFailure
from aero_ai_studio.training.gazebo_dqn import dqn_validation_scenario, estimate_training_cost, find_actual_action_cost
from aero_ai_studio.training.gazebo_physics import GazeboPhysicsTrainingEnvironment
from aero_ai_studio.training.trainer import Trainer, TrainingConfig


def _parser():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="kind", required=True)
    for kind in ("smoke", "full"):
        p = sub.add_parser(kind)
        p.add_argument("--output", type=Path, required=True)
        p.add_argument("--episodes", type=int, default=5 if kind == "smoke" else 1000)
        p.add_argument("--seed", type=int, default=42)
        p.add_argument("--max-steps", type=int, default=20 if kind == "smoke" else 250)
        p.add_argument("--resume", type=Path)
        p.add_argument("--gui", action="store_true")
        p.add_argument("--checkpoint-interval", type=int, default=1 if kind == "smoke" else 10)
        if kind == "full":
            p.add_argument("--curriculum", action="store_true")
            p.add_argument("--evaluation-interval", type=int, default=25)
            p.add_argument("--evaluation-episodes", type=int, default=3)
    return parser


def _config(args):
    smoke = args.kind == "smoke"
    return TrainingConfig(
        episodes=args.episodes, learning_rate=.001, gamma=.95, epsilon=1., epsilon_decay=.995,
        epsilon_end=.05, max_steps=args.max_steps, seed=args.seed,
        checkpoint_interval=args.checkpoint_interval, visual_interval=1,
        algorithm="dqn", observation_mode="sensor", state_encoder="canonical", local_radius=2,
        batch_size=1 if smoke else 64, buffer_size=10000,
        target_interval=1 if smoke else 500, double_dqn=True,
        warmup_steps=1 if smoke else 256, reward_clip=10., reward_version="v2",
        safety_enabled=False, simulator="gazebo", gazebo_control_mode="PHYSICS",
        training_kind="smoke" if smoke else "full",
        curriculum_enabled=bool(getattr(args, "curriculum", False)),
        curriculum_interval=getattr(args, "evaluation_interval", 25),
        curriculum_threshold=.8,
    )


def _copy_export(agent, config, scenario, directory, summary):
    directory.mkdir(parents=True, exist_ok=True)
    agent.save(directory / "model.pt")
    write_json(directory / "training_config.json", asdict(config))
    write_json(directory / "scenario.json", scenario.to_dict())
    metadata = {
        "schema_version": "0.7.1", "algorithm": "dqn", "training_config": asdict(config),
        "scenario": scenario.to_dict(), "agent_metadata": agent.get_metadata(),
        "action_mapping": gazebo_physics_action_mapping(), "summary": summary,
        "training_kind": config.training_kind, "simulator": "gazebo",
        "gazebo_control_mode": "PHYSICS", "observation_mode": "sensor",
        "observation_encoder": "sensor_vector_v1", "observation_dim": 22,
        "seed": config.seed, "episodes": config.episodes,
        "episodes_completed": summary.get("episodes_completed", 0),
        "total_steps": summary.get("total_steps", agent.global_step),
        "reward_config": {"goal": 100., "collision": -100., "danger": -50.,
            "progress": "2 * (distance_before - distance_after)", "step": -.1,
            "DQN reward_clip": config.reward_clip},
        "compatible_with_verify_v07_dqn": False,
    }
    try:
        checkpoint_contract_from_payload(metadata)
        metadata["compatible_with_verify_v07_dqn"] = True
    except DQNCheckpointError:
        pass
    write_json(directory / "metadata.json", metadata)
    return metadata


def checkpoint_contract_from_payload(metadata):
    """Run the same compatibility predicates used by verifier without loading weights."""
    config = metadata["training_config"]
    agent = metadata["agent_metadata"]
    expected = gazebo_physics_action_mapping()
    if (config.get("algorithm") != "dqn" or config.get("simulator") != "gazebo" or
        config.get("gazebo_control_mode") != "PHYSICS" or config.get("observation_mode") != "sensor" or
        config.get("training_kind") != "full" or agent.get("input_size") != 22 or
        agent.get("encoder") != "sensor_vector_v1" or agent.get("architecture") != "mlp_22_128_128_4" or
        agent.get("action_mapping") != expected):
        raise DQNCheckpointError("Export is not a full compatible Gazebo PHYSICS DQN")


def _compatibility_check(directory):
    try:
        checkpoint_contract(directory)
        return True
    except DQNCheckpointError:
        return False


def _gazebo_version():
    try:
        result = subprocess.run(["gz", "sim", "--versions"], capture_output=True, text=True, timeout=4, check=False)
        return (result.stdout or result.stderr).strip()[:500] or None
    except (OSError, subprocess.TimeoutExpired):
        return None


def _episode_report(rows, window=50):
    recent = rows[-window:]
    count = len(rows)
    return {
        "episodes_completed": count,
        "total_steps": sum(row["steps"] for row in rows),
        "success_rate": sum(bool(row["success"]) for row in rows) / count if count else 0.,
        "last_n_success_rate": sum(bool(row["success"]) for row in recent) / len(recent) if recent else 0.,
        "collision_rate": sum("collision" in row["reason"] for row in rows) / count if count else 0.,
        "timeout_rate": sum(row["reason"] in ("timeout", "max_steps") for row in rows) / count if count else 0.,
        "average_reward": sum(row["reward"] for row in rows) / count if count else 0.,
        "average_steps": sum(row["steps"] for row in rows) / count if count else 0.,
    }


def _evaluation_key(outcome):
    """Prefer goal success, then fewer collisions/timeouts, then higher return."""
    return (float(outcome["success_rate"]), -float(outcome["collision_rate"]),
            -float(outcome["timeout_rate"]), float(outcome["mean_reward"]))


def _training_failure_summary(error, training_kind):
    """Keep physical control outcomes distinct from simulator infrastructure faults."""
    physical=isinstance(error,PhysicalControlFailure)
    payload={"status":"physical_control_failure" if physical else "infrastructure_failure",
        "training_kind":training_kind,
        "category":("physical_control_failure" if physical else
                    getattr(error,"category",getattr(error,"failure_category","training_error"))),
        "error":str(error),"policy_mode":"dqn","control_mode":"PHYSICS",
        "Safety":"OFF","training_enabled":True,
        "compatible_with_verify_v07_dqn":False}
    if physical:payload["failure"]=error.to_dict()
    return payload


def run(args):
    if args.kind == "smoke" and not 2 <= args.episodes <= 5:
        raise SystemExit("smoke --episodes must be between 2 and 5")
    if args.kind == "full" and args.episodes < 1:
        raise SystemExit("full --episodes must be positive")
    config = _config(args); config.validate()
    scenario = dqn_validation_scenario()
    output = args.output.expanduser().resolve(); output.mkdir(parents=True, exist_ok=True)
    (output / "models").mkdir(exist_ok=True)
    action_cost = find_actual_action_cost(ROOT / "validation" / "v071-host")
    evaluation_interval = 1 if args.kind == "smoke" else args.evaluation_interval
    evaluation_episodes = 0 if args.kind == "smoke" else args.evaluation_episodes
    cost = estimate_training_cost(args.episodes, args.max_steps, evaluation_interval,
                                  evaluation_episodes, action_cost)
    write_json(output / "training_cost_estimate.json", cost)
    write_json(output / "training_config.json", asdict(config))
    write_json(output / "scenario.json", scenario.to_dict())
    print("Gazebo PHYSICS training cost estimate:", json.dumps(cost, sort_keys=True), flush=True)
    if action_cost:
        print(f"Reference: {action_cost['actions_per_episode']} actual Core 7 actions, "
              f"mean {action_cost['mean_action_seconds']:.3f}s/action; estimates are host-dependent.", flush=True)
    else:
        print("No prior actual Core 7 timing artifact found; wall-time estimate unavailable.", flush=True)

    stop = Event()
    previous_handler = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    trainer = Trainer(scenario, config, environment_factory=lambda spec, steps:
        GazeboPhysicsTrainingEnvironment(spec, steps, root=output / "worlds", gui=args.gui,
                                         gamma=config.gamma))
    start = time.monotonic(); rolling = deque(maxlen=50); best_key = None; best_path = None
    eval_history_path = output / "evaluation_history.json"
    eval_history = json.loads(eval_history_path.read_text(encoding="utf-8")) if eval_history_path.exists() else []
    completed_evaluations = [row for row in eval_history if row.get("status") == "complete"]
    if completed_evaluations:
        best_key = max(_evaluation_key(row) for row in completed_evaluations)
        if (output / "models" / "best" / "model.pt").is_file():
            best_path = str(output / "models" / "best")
    latest_dir = output / "models" / "latest"
    best_dir = output / "models" / "best"
    def progress(row):
        rolling.append(row)
        elapsed = time.monotonic() - start
        completed = len(rolling)  # rolling rates are intentionally recent-window rates
        success_rate = sum(bool(x["success"]) for x in rolling) / completed
        collision_rate = sum("collision" in x["reason"] for x in rolling) / completed
        remaining = max(0, args.episodes - row["episode"])
        mean_ep = elapsed / max(1, row["episode"])
        eta = remaining * mean_ep
        print(f"episode={row['episode']}/{args.episodes} steps={row['steps']} reward={row['reward']:.2f} "
              f"reason={row['reason']} epsilon={row['epsilon']:.3f} recent_success={success_rate:.2%} "
              f"recent_collision={collision_rate:.2%} episode_s={row['episode_wall_seconds']:.1f} "
              f"elapsed_s={elapsed:.0f} eta_s={eta:.0f}", flush=True)

    def evaluation_hook(agent, episode, rows, env, curriculum, run_metadata):
        nonlocal best_key, best_path
        summary = _episode_report(rows)
        summary.update(training_kind=config.training_kind, episodes_completed=len(rows),
                       total_steps=agent.global_step, optimizer_updates=agent.optimizer_updates,
                       target_updates=agent.target_updates)
        _copy_export(agent, config, scenario, latest_dir, summary)
        do_eval = args.kind == "full" and (
            episode % args.evaluation_interval == 0 or episode == args.episodes)
        if not do_eval:
            return
        target_match = getattr(env, "scenario", None) is not None and env.scenario.to_dict() == scenario.to_dict()
        if not target_match:
            eval_history.append({"episode": episode, "status": "skipped", "reason": "curriculum_not_at_target_scenario"})
            write_json(output / "evaluation_history.json", eval_history)
            return
        score = curriculum.evaluate(agent, scenario, trainer.environment_factory, args.max_steps,
            args.seed + 2_000_000 + episode * 100, episodes=args.evaluation_episodes, env=env)
        outcome = dict(curriculum.last_evaluation)
        outcome.update(episode=episode, status="complete", mean_reward=(
            sum(item["reward"] for item in outcome["episodes"]) / max(1, len(outcome["episodes"]))),
            collision_rate=sum("collision" in item["reason"] for item in outcome["episodes"]) / max(1, len(outcome["episodes"])),
            timeout_rate=sum(item["reason"] in ("timeout", "max_steps") for item in outcome["episodes"]) / max(1, len(outcome["episodes"])))
        eval_history.append(outcome); write_json(output / "evaluation_history.json", eval_history)
        key = _evaluation_key(outcome)
        if best_key is None or key > best_key:
            best_key = key
            meta = _copy_export(agent, config, scenario, best_dir, {**summary, "evaluation": outcome})
            best_path = str(best_dir)
            # Registry retains immutable, versioned training artifacts alongside latest/best aliases.
            run_record = {"id": output.name, "scenario": scenario.to_dict(),
                          "success_rate": score, "average_reward": outcome["mean_reward"],
                          "config": asdict(config)}
            registry = ModelRegistry.save(output / "models" / "registry", "gazebo_dqn", agent, run_record,
                                          notes=f"Target-scenario evaluation at episode {episode}")
            meta["registry_version"] = str(registry)
            write_json(best_dir / "metadata.json", meta)

    try:
        run_path, agent, run_meta = trainer.run(output / "runs", progress=progress, cancel=stop,
            resume=args.resume, evaluation_hook=evaluation_hook)
    except Exception as error:
        failure = _training_failure_summary(error,config.training_kind)
        write_json(output / "training_summary.json", failure)
        print(f"Training stopped ({failure['status']}):", json.dumps(failure, sort_keys=True), flush=True)
        return 2
    finally:
        signal.signal(signal.SIGINT, previous_handler)
    rows = json.loads((run_path / "metrics.json").read_text(encoding="utf-8"))
    summary = _episode_report(rows)
    summary.update({"status": run_meta["status"], "policy_mode": "dqn", "inference_mode": "epsilon_greedy_training",
        "training_enabled": True, "control_mode": "PHYSICS", "Safety": "OFF", "training_kind": config.training_kind,
        "seed": config.seed, "curriculum_enabled": config.curriculum_enabled,
        "curriculum": run_meta.get("curriculum_state"), "reward_config": {
            "goal": 100., "collision": -100., "danger": -50.,
            "progress": "2 * (distance_before - distance_after)", "step": -.1,
            "DQN reward_clip": config.reward_clip},
        "optimizer_updates": agent.optimizer_updates, "target_updates": agent.target_updates,
        "best_checkpoint": best_path, "latest_checkpoint": str(latest_dir),
        "episodes_with_reset_evidence": sum(bool(json.loads(p.read_text()).get("reset_evidence"))
            for p in (run_path / "episodes").glob("episode_*.json")),
        "restart_fallbacks": sum(1 for p in (run_path / "episodes").glob("episode_*.json")
            for ev in [json.loads(p.read_text()).get("reset_evidence") or {}] if ev.get("restart_fallback_count", 0) > 0),
        "gazebo_version": _gazebo_version(), "run": str(run_path)})
    if config.training_kind == "smoke":
        episode_files = sorted((run_path / "episodes").glob("episode_*.json"))
        reset_rows = [json.loads(path.read_text(encoding="utf-8")) for path in episode_files]
        smoke_checks = {
            "replay_inserted": len(agent.buffer) > 0,
            "optimizer_updated": agent.optimizer_updates > 0,
            "target_updated": agent.target_updates > 0,
            "actual_reset_evidence_each_episode": len(reset_rows) == len(rows) and all(
                row.get("reset_evidence", {}).get("sensor_fresh") and
                row.get("reset_evidence", {}).get("odometry_fresh_and_stopped") for row in reset_rows),
            "actual_sensor_observation_22d": all(
                row.get("reset_evidence", {}).get("observation_contract", {}).get("source") == "gazebo_lidar" and
                row.get("reset_evidence", {}).get("observation_contract", {}).get("dimension") == 22
                for row in reset_rows),
            "training_kind_is_smoke": config.training_kind == "smoke",
            "verifier_compatibility_rejected": not _compatibility_check(latest_dir),
        }
        summary["smoke_pipeline_checks"] = smoke_checks
        summary["smoke_pipeline_pass"] = run_meta["status"] == "completed" and all(smoke_checks.values())
    summary["compatible_with_verify_v07_dqn"] = (
        config.training_kind == "full" and run_meta["status"] == "completed" and _compatibility_check(latest_dir))
    if config.training_kind == "full":
        summary["best_compatible_with_verify_v07_dqn"] = best_path is not None and _compatibility_check(best_dir)
    write_json(output / "training_summary.json", summary)
    print("Training summary:", json.dumps(summary, sort_keys=True), flush=True)
    if config.training_kind == "smoke" and not summary.get("smoke_pipeline_pass"):
        return 1
    return 0 if run_meta["status"] in ("completed", "cancelled") else 1


if __name__ == "__main__":
    raise SystemExit(run(_parser().parse_args()))
