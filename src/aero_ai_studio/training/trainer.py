from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Event
from typing import Callable
import logging
import shutil
import time

from aero_ai_studio.agents.q_learning import QLearningAgent
from aero_ai_studio.core.storage import identifier, now, write_json
from aero_ai_studio.scenario.models import ScenarioSpec
from aero_ai_studio.simulation.base import TrainingEnvironment
from aero_ai_studio.simulation.grid_world import GridWorld
from aero_ai_studio.training.logger import RunLogger
from aero_ai_studio.training.checkpoint import CheckpointStore
from aero_ai_studio.explainability.brain_map import record_step
from aero_ai_studio.agents.base import Agent, Transition
from aero_ai_studio.agents.factory import create_agent, policy_observation


def _training_failure_metadata(error: Exception) -> dict:
    """Serialize a typed training failure without conflating it with run failure."""
    result = {
        'status': getattr(error, 'training_status', 'failed'),
        'error': str(error),
        'completed_date': now(),
    }
    to_dict = getattr(error, 'to_dict', None)
    if callable(to_dict):
        result['failure'] = to_dict()
    category = getattr(error, 'category', None)
    if category is None:
        category = getattr(error, 'failure_category', None)
    if category is not None:
        result['failure_category'] = category
    return result


@dataclass
class TrainingConfig:
    episodes: int = 1000
    learning_rate: float = 0.1
    gamma: float = 0.95
    epsilon: float = 1.0
    epsilon_decay: float = 0.995
    max_steps: int = 200
    seed: int = 42
    checkpoint_interval: int = 100
    visual_interval: int = 10
    visual_delay: float = 0.0
    algorithm: str = 'q_learning'
    observation_mode: str = 'basic'
    state_encoder: str = 'basic'
    local_radius: int = 2
    batch_size: int = 64
    buffer_size: int = 10000
    target_interval: int = 500
    epsilon_end: float = 0.0
    safety_enabled: bool=False
    safety_threshold: float=1.05
    reward_version: str='legacy'
    double_dqn: bool=False
    warmup_steps: int=0
    reward_clip: float=0.
    curriculum_enabled: bool=False
    curriculum_interval: int=100
    curriculum_threshold: float=.8
    simulator: str='grid'
    training_kind: str='standard'
    curriculum_minimum_episodes: tuple=()
    curriculum_minimum_evaluations: int=1
    gazebo_control_mode: str='KINEMATIC'

    def validate(self) -> None:
        if not 1 <= self.episodes <= 100000 or not 1 <= self.max_steps <= 10000:
            raise ValueError("Episodes/max steps outside supported range")
        if not 0 < self.learning_rate <= 1 or not 0 <= self.gamma <= 1:
            raise ValueError("Invalid learning rate/gamma")
        if not 0 <= self.epsilon <= 1 or not 0 < self.epsilon_decay <= 1:
            raise ValueError("Invalid epsilon/decay")
        if self.checkpoint_interval < 1 or self.visual_interval < 1 or not 0 <= self.visual_delay <= 1:
            raise ValueError("Invalid checkpoint/render settings")
        if self.algorithm not in ('q_learning', 'dqn') or self.observation_mode not in ('basic', 'local', 'sensor'):
            raise ValueError('Invalid algorithm/policy observation; FULL_DEBUG is visualization only')
        if self.state_encoder not in ('basic', 'compact','canonical') or not 1 <= self.local_radius <= 3:
            raise ValueError('Invalid encoder/local radius')
        if (self.algorithm == 'dqn' or self.state_encoder == 'compact') and self.observation_mode == 'basic':
            raise ValueError('DQN/Compact require LOCAL or SENSOR observations')
        if self.state_encoder=='canonical' and self.observation_mode!='sensor':raise ValueError('Canonical encoder requires SENSOR')
        if not 1 <= self.batch_size <= self.buffer_size or self.target_interval < 1 or not 0 <= self.epsilon_end <= self.epsilon:
            raise ValueError('Invalid DQN buffer/target/epsilon settings')
        if self.reward_version not in ('legacy','v2') or self.safety_threshold<0 or not 0<=self.warmup_steps<=self.buffer_size or self.reward_clip<0:
            raise ValueError('Invalid Safety/Reward/DQN V2 settings')
        if self.curriculum_interval<1 or not 0<=self.curriculum_threshold<=1:raise ValueError('Invalid curriculum settings')
        if self.simulator not in ('grid','gazebo'):raise ValueError('Invalid simulator')
        if self.curriculum_enabled and self.simulator not in ('grid','gazebo'):raise ValueError('Unsupported curriculum simulator')
        if self.curriculum_minimum_episodes:
            if len(self.curriculum_minimum_episodes)!=5 or any(type(n) is not int or n<1 for n in self.curriculum_minimum_episodes):
                raise ValueError('Curriculum requires five positive stage minimums')
            if self.curriculum_enabled and self.episodes<sum(self.curriculum_minimum_episodes):
                raise ValueError('Episode budget is smaller than the sum of curriculum stage minimums')
        if self.curriculum_minimum_evaluations<1:raise ValueError('Invalid minimum evaluations')
        if self.gazebo_control_mode not in ('KINEMATIC','PHYSICS'):raise ValueError('Unknown control mode')
        if self.simulator=='gazebo' and self.gazebo_control_mode=='PHYSICS' and self.observation_mode!='sensor':
            raise ValueError('Physics differential-drive policy requires body-relative SENSOR observations')
        if self.training_kind not in ('standard','smoke','full'):raise ValueError('Unknown training kind')
        if self.simulator=='gazebo' and (self.algorithm!='dqn' or self.gazebo_control_mode!='PHYSICS' or self.observation_mode!='sensor'):
            raise ValueError('Gazebo DQN training requires algorithm=dqn, PHYSICS and SENSOR')
        if self.simulator=='gazebo' and self.training_kind not in ('smoke','full'):
            raise ValueError('Gazebo training must be explicitly marked smoke or full')


class Trainer:
    def __init__(self, scenario: ScenarioSpec, config: TrainingConfig,
                 environment_factory: Callable[[ScenarioSpec, int], TrainingEnvironment] | None = None):
        config.validate()
        self.scenario = scenario
        self.config = config
        from aero_ai_studio.simulation.factory import environment_factory as resolve
        self.environment_factory = environment_factory or resolve(config.simulator,control_mode=config.gazebo_control_mode)

    def run(self, runs: Path, progress: Callable[[dict], None] | None = None,
            cancel: Event | None = None, resume: Path | None = None,
            checkpoint_request: Event | None = None,
            visual: Callable[[dict], None] | None = None,
            evaluation_hook: Callable | None = None) -> tuple[Path, Agent, dict]:
        cfg = self.config
        started = time.monotonic()
        saved = CheckpointStore.load(resume) if resume else None
        if saved:
            if ScenarioSpec.from_dict(saved['scenario']).to_dict() != self.scenario.to_dict():
                raise ValueError('Resume scenario must match checkpoint snapshot')
            for key in ('learning_rate', 'gamma', 'epsilon_decay', 'max_steps', 'seed'):
                if saved['config'][key] != asdict(cfg)[key]:
                    raise ValueError(f'Resume cannot change {key}')
            defaults = asdict(TrainingConfig())
            for key in ('algorithm','observation_mode','state_encoder','local_radius','batch_size','buffer_size','target_interval','epsilon_end',
                        'safety_enabled','safety_threshold','reward_version','double_dqn','warmup_steps','reward_clip','curriculum_enabled','curriculum_interval','curriculum_threshold','simulator',
                        'curriculum_minimum_episodes','curriculum_minimum_evaluations','gazebo_control_mode','training_kind'):
                old=saved['config'].get(key, defaults[key]);new=asdict(cfg)[key]
                changed=list(old)!=list(new) if key=='curriculum_minimum_episodes' else old!=new
                if changed:
                    raise ValueError(f'Resume cannot change {key}')
            if cfg.episodes <= saved['episode']:
                raise ValueError('Total episodes must exceed checkpoint episode')
            source = Path(saved['source_run'])
            for row in saved['metrics']:
                if not (source / 'episodes' / f"episode_{row['episode']:04d}.json").exists():
                    raise ValueError('Checkpoint source episode logs are missing; restore the original run folder')
        from aero_ai_studio.safety.layer import SafetyLayer
        shield=SafetyLayer(cfg.safety_enabled,cfg.safety_threshold)
        from aero_ai_studio.training.curriculum import CurriculumSchedule
        if cfg.simulator=='gazebo' and cfg.gazebo_control_mode=='PHYSICS' and cfg.curriculum_enabled:
            from aero_ai_studio.training.gazebo_curriculum import GazeboPhysicsCurriculum
            curriculum=GazeboPhysicsCurriculum(threshold=cfg.curriculum_threshold,
                minimum_episodes=tuple(cfg.curriculum_minimum_episodes),
                minimum_evaluations=cfg.curriculum_minimum_evaluations,target_scenario=self.scenario)
        else:
            curriculum=CurriculumSchedule(threshold=cfg.curriculum_threshold,minimum_episodes=tuple(cfg.curriculum_minimum_episodes),
                                          minimum_evaluations=cfg.curriculum_minimum_evaluations)
        curriculum_events=[]
        if saved and saved.get('curriculum_state'):
            curriculum_events=curriculum.restore(saved['curriculum_state'],saved['episode'])
        active_scenario=curriculum.scenario(self.scenario.width,cfg.seed) if cfg.curriculum_enabled else self.scenario
        env = self.environment_factory(active_scenario,cfg.max_steps)
        env.reward_version=cfg.reward_version
        compact_physics=(cfg.simulator=='gazebo' and cfg.gazebo_control_mode=='PHYSICS')
        agent = create_agent(cfg)
        root = runs / identifier("run")
        logger = RunLogger(root)
        metadata = {"id": root.name, "created_date": now(), "status": "running",
                    "config": asdict(cfg), "scenario": self.scenario.to_dict()}
        write_json(root / "run.json", metadata)
        epsilon = cfg.epsilon
        rows: list[dict] = []
        successes = collisions = 0
        log = logging.getLogger(__name__)
        if saved:
            agent = CheckpointStore.restore_agent(saved)
            epsilon = saved['epsilon']
            rows = saved['metrics']
            successes = sum(r['success'] for r in rows)
            collisions = sum('collision' in r['reason'] for r in rows)
            source = Path(saved['source_run'])
            for row in rows:
                src = source / 'episodes' / f"episode_{row['episode']:04d}.json"
                shutil.copy2(src, root / 'episodes' / src.name)
            metadata.update(parent_run=source.name, resumed_from=str(resume.resolve()), resume_episode=saved['episode'] + 1)
            write_json(root / 'run.json', metadata)
        log.info('training start run=%s resume=%s', root, resume)
        last_checkpoint = None
        def checkpoint() -> None:
            nonlocal last_checkpoint
            last_checkpoint = CheckpointStore.save(root, agent, len(rows), epsilon, asdict(cfg), self.scenario.to_dict(), rows,
                                                   curriculum_state=curriculum.state_dict(curriculum_events))
            write_json(root / 'metrics.json', rows)
            metadata['last_checkpoint'] = str(last_checkpoint.resolve())
            write_json(root / 'run.json', metadata)
        try:
            for number in range(len(rows) + 1, cfg.episodes + 1):
                if cancel and cancel.is_set():
                    break
                state = env.reset(cfg.seed + number)
                agent.reset()
                events: list[dict] = []
                total = 0.0
                reason = "cancelled"
                overrides=0
                episode_started=time.monotonic();action_wall_seconds=0.;cancelled_mid_episode=False
                for step in range(cfg.max_steps):
                    action_started=time.monotonic()
                    snapshot = env.get_state()
                    observation = policy_observation(env, agent)
                    proposed = agent.select_action(observation, epsilon)
                    decision = agent.get_decision_info()
                    scores, exploring = decision['q_values'], decision['exploring']
                    safety_observation=env.get_agent_observation('sensor',cfg.local_radius) if cfg.safety_enabled else observation
                    safety=shield.check(proposed,safety_observation,scores)
                    action=safety.final_action
                    overrides+=int(safety.override)
                    result = env.step(action)
                    decision_id=f'episode-{number}-decision-{step+1}'
                    if result.execution_evidence is not None:
                        result.execution_evidence['decision_reference']=decision_id
                    done = result.terminated or result.truncated
                    next_observation = policy_observation(env, agent)
                    agent.learn(Transition(observation, proposed, result.reward, next_observation, done,
                                           result.elapsed_discount_units))
                    next_state=env.get_state()
                    elapsed_action=time.monotonic()-action_started
                    action_wall_seconds+=elapsed_action
                    if compact_physics:
                        action_telemetry=next_state.get('telemetry',{}).get('gazebo_dqn_training',{})
                        events.append({'step':step,'action':action,'reward':float(result.reward),
                            'reason':result.reason,'done':done,'simulation_time':next_state.get('timestamp'),
                            'pose_before':snapshot.get('pose'),'pose_after':next_state.get('pose'),
                            'decision_id':decision_id,'agent_intent':proposed,
                            'elapsed_execution_time':result.elapsed_execution_time,
                            'elapsed_discount_units':result.elapsed_discount_units,
                            'execution_evidence':result.execution_evidence,
                            'sensor_sequence':(next_observation.sensor_state.get('sequence') if hasattr(next_observation,'sensor_state') else None),
                            'wall_step_seconds':action_telemetry.get('training_action_wall_seconds',elapsed_action)})
                    else:
                        events.append(record_step(number, step, state, scores, action, exploring, epsilon,
                                                  snapshot, next_state, result))
                        events[-1].update(observation=observation.to_dict(), next_observation=next_observation.to_dict(),
                                          agent_decision=decision, algorithm=decision['algorithm'],proposed_action=proposed,
                                          final_action=action,safety=safety.to_dict(),safety_observation=safety_observation.to_dict() if cfg.safety_enabled else None,
                                          reward_components=env.get_metrics().get('reward_components',{}),
                                          pose=snapshot.get('pose'),next_pose=next_state.get('pose'),timestamp=next_state.get('timestamp'),
                                          minimum_clearance=env.get_metrics().get('minimum_clearance'))
                        events[-1].update(schema_version='0.7',telemetry=next_state.get('telemetry',{}))
                    if visual and not compact_physics and (number == 1 or number % cfg.visual_interval == 0):
                        visual(dict(events[-1]))
                        if cfg.visual_delay and not (cancel and cancel.is_set()):
                            time.sleep(cfg.visual_delay)
                    total += result.reward
                    state = result.observation
                    reason = result.reason
                    if done:
                        break
                    if cfg.simulator=='gazebo' and cancel and cancel.is_set():
                        cancelled_mid_episode=True
                        break
                if cancelled_mid_episode:
                    # Keep transitions already learned, but exclude this partial
                    # episode from metrics so resume starts a clean episode.
                    break
                if reason == "moving":
                    reason = "cancelled"
                success = reason == "goal"
                successes += int(success)
                collisions += int('collision' in reason)
                episode = {"episode": number, "success": success, "reason": reason,
                           "total_reward": total, "steps": events,'minimum_clearance':env.get_metrics().get('minimum_clearance'),
                           'safety_override_count':overrides,'curriculum_stage':curriculum.stage if cfg.curriculum_enabled else None,
                           'episode_wall_seconds':time.monotonic()-episode_started,
                           'action_wall_seconds':action_wall_seconds,
                           'mean_action_wall_seconds':action_wall_seconds/max(1,len(events)),
                           'reset_evidence':getattr(env,'last_reset_evidence',None) if compact_physics else None}
                logger.save_episode(episode)
                row = {"episode": number, "reward": total, "steps": len(events), "success": success,
                       "reason": reason, "success_rate": successes / number,
                       "collision_count": collisions, "epsilon": epsilon,'safety_override_count':overrides,
                       'minimum_clearance':env.get_metrics().get('minimum_clearance'),
                       'curriculum_stage':curriculum.stage if cfg.curriculum_enabled else None}
                if compact_physics:
                    row.update(episode_wall_seconds=episode['episode_wall_seconds'],
                               action_wall_seconds=action_wall_seconds,
                               mean_action_wall_seconds=episode['mean_action_wall_seconds'])
                rows.append(row)
                if progress:
                    progress(dict(row))
                epsilon = max(cfg.epsilon_end, epsilon * cfg.epsilon_decay)
                if cfg.curriculum_enabled:curriculum.record_episode()
                if cfg.curriculum_enabled and number%cfg.curriculum_interval==0:
                    spec=curriculum.scenario(self.scenario.width,cfg.seed)
                    reuse=(cfg.simulator=='gazebo' and cfg.gazebo_control_mode=='PHYSICS' and
                           getattr(env,'scenario',None) is not None and env.scenario.to_dict()==spec.to_dict())
                    score=curriculum.evaluate(agent,spec,self.environment_factory,cfg.max_steps,cfg.seed+5000000+number*10,
                        episodes=1 if cfg.simulator=='gazebo' else 10,env=env if reuse else None)
                    prior=curriculum.stage
                    exposure=curriculum.episodes_in_stage
                    promoted=curriculum.update(score,remaining_budget=cfg.episodes-number)
                    curriculum_events.append({'episode':number,'stage':prior,'evaluation_success':score,'promoted':promoted,'next_stage':curriculum.stage,
                                              'episodes_in_evaluated_stage':exposure})
                    write_json(root/'curriculum.json',curriculum_events)
                    if promoted:
                        env.close()
                        env=self.environment_factory(curriculum.scenario(self.scenario.width,cfg.seed),cfg.max_steps)
                        env.reward_version=cfg.reward_version
                if evaluation_hook:
                    evaluation_hook(agent,number,rows,env,curriculum,metadata)
                if number % cfg.checkpoint_interval == 0 or (checkpoint_request and checkpoint_request.is_set()):
                    checkpoint()
                    if checkpoint_request:
                        checkpoint_request.clear()
        except Exception as error:
            metadata.update(_training_failure_metadata(error))
            write_json(root / "run.json", metadata)
            write_json(root / "metrics.json", rows)
            agent.save(root / agent.artifact_name)
            log.exception('training error %s', root)
            raise
        finally:
            env.close()
        checkpoint()
        metadata.update(status="cancelled" if cancel and cancel.is_set() else "completed",
                        completed_date=now(), episodes_completed=len(rows),
                        success_rate=successes / len(rows) if rows else 0,
                        average_reward=sum(r["reward"] for r in rows) / len(rows) if rows else 0,
                        collision_count=collisions, final_epsilon=epsilon,
                        average_steps=sum(r['steps'] for r in rows) / len(rows) if rows else 0,
                        training_seconds=time.monotonic() - started, agent_metadata=agent.get_metadata(),
                        curriculum_complete=curriculum.complete() if cfg.curriculum_enabled else None,
                        curriculum_state=curriculum.state_dict(curriculum_events) if cfg.curriculum_enabled else None,
                        hard_training_episodes=sum(r.get('curriculum_stage')==4 for r in rows))
        write_json(root / "metrics.json", rows)
        agent.save(root / agent.artifact_name)
        write_json(root / "run.json", metadata)
        log.info('training end run=%s status=%s', root, metadata['status'])
        return root, agent, metadata
