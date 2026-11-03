from __future__ import annotations
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Event
from typing import Callable
from statistics import mean
import logging

from aero_ai_studio.agents.q_learning import QLearningAgent
from aero_ai_studio.core.storage import identifier, now, write_json
from aero_ai_studio.scenario.models import ScenarioSpec
from aero_ai_studio.simulation.base import TrainingEnvironment
from aero_ai_studio.simulation.grid_world import GridWorld
from aero_ai_studio.training.logger import RunLogger
from aero_ai_studio.agents.factory import load_agent, policy_observation
from aero_ai_studio.core.storage import read_json


@dataclass
class EvaluationConfig:
    episodes: int = 100
    max_steps: int = 200
    seed: int = 10042
    safety_enabled: bool=False
    safety_threshold: float=1.05
    reward_version: str='legacy'
    suite: str='custom'

    def validate(self) -> None:
        if not 1 <= self.episodes <= 100000 or not 1 <= self.max_steps <= 10000:
            raise ValueError("Invalid evaluation episode/step limits")
        if self.safety_threshold<0 or self.reward_version not in ('legacy','v2'):raise ValueError('Invalid Safety/Reward settings')


class Evaluator:
    def __init__(self, scenario: ScenarioSpec, config: EvaluationConfig,
                 environment_factory: Callable[[ScenarioSpec, int], TrainingEnvironment] = GridWorld):
        config.validate()
        self.scenario, self.config, self.environment_factory = scenario, config, environment_factory

    def run(self, model: Path, evaluations: Path, progress: Callable[[dict], None] | None = None,
            cancel: Event | None = None) -> tuple[Path, dict]:
        # A private agent copy means neither source weights nor RNG are mutated.
        agent = load_agent(model)
        metadata = read_json(model / 'metadata.json')
        training = metadata.get('training_config', {})
        if not training:
            run_file = model.parent.parent / 'runs' / metadata.get('training_run','') / 'run.json'
            if run_file.exists():
                training = read_json(run_file)['config']
        if training:
            train_seeds = range(training['seed'] + 1, training['seed'] + training['episodes'] + 1)
            eval_seeds = range(self.config.seed + 1, self.config.seed + self.config.episodes + 1)
            if max(train_seeds.start, eval_seeds.start) < min(train_seeds.stop, eval_seeds.stop):
                raise ValueError('Evaluation seeds overlap training reset seeds; select a disjoint seed range')
        agent.rng.seed(self.config.seed)
        env = self.environment_factory(self.scenario, self.config.max_steps)
        env.reward_version=self.config.reward_version
        from aero_ai_studio.safety.layer import SafetyLayer
        shield=SafetyLayer(self.config.safety_enabled,self.config.safety_threshold)
        root = evaluations / identifier("eval")
        logger = RunLogger(root)
        rows: list[dict] = []
        info = {"id": root.name, "mode": "evaluation", "epsilon": 0.0, "model": str(model.resolve()),
                "created_date": now(), "config": asdict(self.config), "scenario": self.scenario.to_dict(),
                "status": "running", "tie_break": "seeded random among maximal Q-values only",
                "path_metric_scope": "static occupancy shortest path; excludes dynamic timing and danger/slow costs"}
        write_json(root / "evaluation.json", info)
        logging.getLogger(__name__).info('evaluation start model=%s output=%s', model, root)
        try:
            for number in range(1, self.config.episodes + 1):
                if cancel and cancel.is_set():
                    break
                state = env.reset(self.config.seed + number)
                agent.reset()
                optimum = env.get_metrics().get("shortest_path_distance")
                total, distance, events = 0.0, 0, []
                overrides=0
                useful=harmful=near=0
                for index in range(self.config.max_steps):
                    before = env.get_state()
                    observation = policy_observation(env, agent)
                    proposed = agent.select_action(observation, 0.0)
                    decision = agent.get_decision_info()
                    values, exploring = decision['q_values'], decision['exploring']
                    safety_observation=env.get_agent_observation('sensor',agent.local_radius) if self.config.safety_enabled else observation
                    safety=shield.check(proposed,safety_observation,values)
                    action=safety.final_action
                    overrides+=int(safety.override)
                    result = env.step(action)
                    after = env.get_state()
                    from aero_ai_studio.explainability.brain_map import record_step
                    events.append(record_step(number, index, state, values, action, exploring, 0.0, before, after, result))
                    events[-1].update(observation=observation.to_dict(), next_observation=policy_observation(env, agent).to_dict(),
                                      agent_decision=decision, algorithm=decision['algorithm'],proposed_action=proposed,final_action=action,
                                      safety=safety.to_dict(),safety_observation=safety_observation.to_dict() if self.config.safety_enabled else None,
                                      reward_components=env.get_metrics().get('reward_components',{}),
                                      pose=before.get('pose'),next_pose=after.get('pose'),timestamp=after.get('timestamp'),
                                      minimum_clearance=env.get_metrics().get('minimum_clearance'))
                    from aero_ai_studio.evaluation.safety_metrics import safety_step_metrics
                    measured=env.get_agent_observation('sensor',agent.local_radius)
                    audit=safety_step_metrics(measured,safety)
                    useful+=int(audit['useful_override_heuristic']);harmful+=int(audit['harmful_override_heuristic']);near+=int(audit['near_collision'])
                    events[-1].update(schema_version='0.7',telemetry=after.get('telemetry',{}),safety_metrics=audit)
                    distance += abs(state[0] - result.observation[0]) + abs(state[1] - result.observation[1])
                    state = result.observation
                    total += result.reward
                    if result.terminated or result.truncated:
                        break
                success = result.reason == "goal"
                row = {"episode": number, "success": success, "reason": result.reason,
                       "reward": total, "steps": len(events), "distance": distance,
                       "shortest_path_ratio": optimum / distance if success and optimum and distance else None,
                       "path_efficiency": distance / optimum if success and optimum else None,
                       'safety_override_count':overrides,'minimum_clearance':env.get_metrics().get('minimum_clearance'),
                       'useful_override_heuristic':useful,'harmful_override_heuristic':harmful,'near_collision_count':near}
                rows.append(row)
                logger.save_episode({**row, "total_reward": total, "steps": events, "mode": "evaluation"})
                if progress:
                    progress(dict(row))
            successes = [r for r in rows if r["success"]]
            info.update(status="cancelled" if cancel and cancel.is_set() else "completed",
                        completed_date=now(), episodes_completed=len(rows),
                        success_rate=len(successes) / len(rows) if rows else 0,
                        failure_rate=1 - len(successes) / len(rows) if rows else 0,
                        average_reward=mean(r["reward"] for r in rows) if rows else 0,
                        average_steps=mean(r["steps"] for r in rows) if rows else 0,
                        collision_count=sum("collision" in r["reason"] for r in rows),
                        timeout_count=sum(r["reason"] == "timeout" for r in rows),
                        shortest_path_ratio=mean(r["shortest_path_ratio"] for r in successes) if successes else None,
                        path_efficiency=mean(r["path_efficiency"] for r in successes) if successes else None,
                        collision_rate=sum('collision' in r['reason'] for r in rows)/len(rows) if rows else 0,
                        timeout_rate=sum(r['reason']=='timeout' for r in rows)/len(rows) if rows else 0,
                        safety_override_count=sum(r['safety_override_count'] for r in rows),
                        useful_override_heuristic=sum(r['useful_override_heuristic'] for r in rows),
                        harmful_override_heuristic=sum(r['harmful_override_heuristic'] for r in rows),
                        near_collision_count=sum(r['near_collision_count'] for r in rows),critical_clearance_threshold=.5,
                        average_minimum_clearance=mean(r['minimum_clearance'] for r in rows if r['minimum_clearance'] is not None) if any(r['minimum_clearance'] is not None for r in rows) else None)
        except Exception as error:
            info.update(status="failed", error=str(error))
            logging.getLogger(__name__).exception('evaluation error %s', root)
            raise
        finally:
            env.close()
            write_json(root / "metrics.json", rows)
            write_json(root / "evaluation.json", info)
            logging.getLogger(__name__).info('evaluation end output=%s status=%s', root, info['status'])
        return root, info
