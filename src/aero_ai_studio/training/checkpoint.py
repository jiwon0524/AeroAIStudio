from __future__ import annotations
from pathlib import Path
from uuid import uuid4
import logging
import math
from aero_ai_studio.core.storage import read_json, write_json
from aero_ai_studio.agents.q_learning import QLearningAgent


def nested_tuple(value):
    return tuple(nested_tuple(v) for v in value) if isinstance(value, list) else value


class CheckpointStore:
    @staticmethod
    def save(run: Path, agent: QLearningAgent, episode: int, epsilon: float, config: dict,
             scenario: dict, metrics: list[dict], curriculum_state: dict | None=None) -> Path:
        parent = run / "checkpoints"
        parent.mkdir(parents=True, exist_ok=True)
        target = parent / f"episode_{episode:06d}"
        # Committed checkpoints are immutable; no torn multi-file transactions.
        if target.exists():
            return target
        stage = parent / f".pending_{uuid4().hex}"
        payload = {"schema_version": "0.4", "episode": episode, "epsilon": epsilon,
                   "config": config, "scenario": scenario, "metrics": metrics,
                   "q_table": getattr(agent, 'table', {}), "agent_rng": agent.rng.getstate(),
                   'agent_metadata': agent.get_metadata(), "source_run": str(run.resolve())}
        if curriculum_state is not None:payload['curriculum_state']=curriculum_state
        if agent.artifact_name != 'q_table.json':
            agent.save(stage / agent.artifact_name)
            payload['agent_artifact'] = agent.artifact_name
        write_json(stage / "checkpoint.json", payload)
        CheckpointStore.load(stage)
        stage.rename(target)
        logging.getLogger(__name__).info("checkpoint save %s episode=%s", target, episode)
        return target

    @staticmethod
    def load(path: Path) -> dict:
        data = read_json(path / "checkpoint.json")
        from aero_ai_studio.training.trainer import TrainingConfig
        from aero_ai_studio.scenario.models import ScenarioSpec
        TrainingConfig(**data['config']).validate()
        ScenarioSpec.from_dict(data['scenario'])
        if data["schema_version"] != "0.4" or len(data["metrics"]) != data["episode"]:
            raise ValueError("Invalid checkpoint metrics/schema")
        if [r["episode"] for r in data["metrics"]] != list(range(1, data["episode"] + 1)):
            raise ValueError("Checkpoint episode sequence is invalid")
        agent = QLearningAgent(data["config"]["learning_rate"], data["config"]["gamma"])
        agent.rng.setstate(nested_tuple(data["agent_rng"]))
        if any(set(v) != {"up", "down", "left", "right"} for v in data["q_table"].values()):
            raise ValueError("Invalid checkpoint Q-table")
        if not 0 <= data['epsilon'] <= 1 or any(not math.isfinite(v) for row in data['q_table'].values() for v in row.values()):
            raise ValueError('Non-finite checkpoint values')
        if data.get('agent_artifact'):
            if data['agent_artifact'] != 'model.pt' or not (path / 'model.pt').exists():
                raise ValueError('DQN checkpoint weights missing')
            data['_agent_path'] = str(path.resolve())
        return data

    @staticmethod
    def restore_agent(data: dict) -> QLearningAgent:
        if data.get('agent_artifact'):
            from aero_ai_studio.agents.factory import load_agent
            return load_agent(Path(data['_agent_path']))
        meta = data.get('agent_metadata', {})
        agent = QLearningAgent(data["config"]["learning_rate"], data["config"]["gamma"],
                              encoder=meta.get('encoder','basic'), observation_mode=meta.get('observation_mode','basic'), local_radius=meta.get('local_radius',2))
        agent.table = data["q_table"]
        agent.rng.setstate(nested_tuple(data["agent_rng"]))
        return agent
