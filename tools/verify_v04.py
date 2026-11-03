"""Actual A/B/C and exact 430→431 checkpoint validation, without touching user workspaces."""
from __future__ import annotations
import argparse
from dataclasses import asdict
from pathlib import Path
from threading import Event
from collections import Counter
import random
import time

from aero_ai_studio.core.storage import read_json, write_json
from aero_ai_studio.core.logging import configure_logging
from aero_ai_studio.scenario.models import ScenarioSpec, SceneObject
from aero_ai_studio.scenario.generator import generate_scenario
from aero_ai_studio.simulation.grid_world import GridWorld
from aero_ai_studio.training.trainer import Trainer, TrainingConfig
from aero_ai_studio.models.registry import ModelRegistry
from aero_ai_studio.evaluation.evaluator import Evaluator, EvaluationConfig


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = args.output.resolve()
    configure_logging(root)
    summary = {}
    basic = ScenarioSpec(objects=[SceneObject('wall', (8, y)) for y in range(4, 16)])
    randomized = generate_scenario(20, 73, 'normal', density=0.10, moving_count=0, danger_count=0)
    randomized.randomization = {'obstacle_position': True}
    baseline_agent, baseline_rows = None, None
    cfg = TrainingConfig(episodes=1000)
    for name, scenario in [('A_basic', basic), ('B_random_obstacles', randomized)]:
        start = time.monotonic()
        run, agent, meta = Trainer(scenario, cfg).run(root / name / 'runs')
        model = ModelRegistry.save(root / name / 'models', name, agent, meta)
        evaluation, result = Evaluator(scenario, EvaluationConfig(100, 200, 10042)).run(model, root / name / 'evaluations')
        ModelRegistry.attach_evaluation(model, evaluation, result)
        rows = read_json(run / 'metrics.json')
        summary[name] = {'training_episodes': len(rows), 'training_success_rate': meta['success_rate'],
                         'last_100_training_success': sum(r['success'] for r in rows[-100:]) / 100,
                         'training_average_reward': meta['average_reward'],
                         'evaluation': {k: result[k] for k in ('episodes_completed', 'success_rate', 'failure_rate',
                                        'average_reward', 'average_steps', 'collision_count', 'timeout_count',
                                        'shortest_path_ratio', 'path_efficiency')},
                         'evaluation_seed': 10042, 'elapsed_seconds': round(time.monotonic() - start, 3)}
        if name == 'A_basic':
            baseline_agent, baseline_rows = agent, rows
        print(name, summary[name], flush=True)
    scenario = generate_scenario(20, 91, 'hard', density=0.10, moving_count=5, danger_count=3)
    env, rng = GridWorld(scenario, 100), random.Random(91)
    steps = changed = 0
    reasons = Counter()
    for episode in range(100):
        env.reset(91 + episode)
        for _ in range(100):
            before = env.get_state()['dynamic_objects']
            valid = [a for a, info in env.action_evidence().items() if info['valid']]
            result = env.step(rng.choice(valid or ['up']))
            steps += 1
            changed += before != env.get_state()['dynamic_objects']
            if result.terminated or result.truncated:
                reasons[result.reason] += 1
                break
    env.close()
    summary['C_dynamic'] = {'episodes': 100, 'steps': steps, 'dynamic_changed_steps': changed, 'terminal_reasons': dict(reasons)}
    assert changed > 0
    print('C_dynamic', summary['C_dynamic'], flush=True)
    stop = Event()
    def progress(row):
        if row['episode'] == 430:
            stop.set()
    partial, _, partial_meta = Trainer(basic, cfg).run(root / 'resume' / 'partial', progress, stop)
    checkpoint = Path(partial_meta['last_checkpoint'])
    resumed, resumed_agent, meta = Trainer(basic, cfg).run(root / 'resume' / 'continued', resume=checkpoint)
    summary['checkpoint_resume'] = {'saved_episode': 430, 'resumed_at': meta['resume_episode'],
                                     'final_episode': meta['episodes_completed'],
                                     'q_table_exact_match': resumed_agent.table == baseline_agent.table,
                                     'metrics_exact_match': read_json(resumed / 'metrics.json') == baseline_rows}
    assert summary['checkpoint_resume']['q_table_exact_match'] and summary['checkpoint_resume']['metrics_exact_match']
    summary['scope'] = 'A is fixed-map evaluation, B uses held-out reset seeds. Neither implies real-world/generalized flight capability.'
    write_json(root / 'performance_v04.json', summary)
    print('checkpoint_resume', summary['checkpoint_resume'], flush=True)


if __name__ == '__main__':
    main()
