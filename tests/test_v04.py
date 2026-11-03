from __future__ import annotations
from copy import deepcopy
from pathlib import Path
from threading import Event
import pytest

from aero_ai_studio.core.storage import read_json, write_json
from aero_ai_studio.scenario.models import ScenarioSpec, DynamicObject, SceneObject, ObservationSpec
from aero_ai_studio.scenario.generator import generate_scenario
from aero_ai_studio.simulation.grid_world import GridWorld
from aero_ai_studio.simulation.base import SimulationEnvironment
from aero_ai_studio.training.trainer import Trainer, TrainingConfig
from aero_ai_studio.training.checkpoint import CheckpointStore
from aero_ai_studio.models.registry import ModelRegistry
from aero_ai_studio.evaluation.evaluator import Evaluator, EvaluationConfig
from aero_ai_studio.explainability.failure_analyzer import analyze_failure, detect_loop
from aero_ai_studio.explainability.brain_map import BrainEvent
from aero_ai_studio.training.comparison import compare_runs


def tiny() -> ScenarioSpec:
    return ScenarioSpec(width=4, height=4, goal=(3, 3))


def test_evaluation_greedy_does_not_train(tmp_path: Path):
    run, agent, meta = Trainer(tiny(), TrainingConfig(episodes=300, max_steps=30)).run(tmp_path / 'runs')
    model = ModelRegistry.save(tmp_path / 'models', 'agent', agent, meta)
    original = (model / 'q_table.json').read_bytes()
    output, info = Evaluator(tiny(), EvaluationConfig(20, 30, 999)).run(model, tmp_path / 'evaluations')
    assert info['success_rate'] == 1 and info['failure_rate'] == 0
    assert info['shortest_path_ratio'] == 1 and info['path_efficiency'] == 1
    assert info['average_steps'] == 6
    assert (model / 'q_table.json').read_bytes() == original
    assert not (run / 'evaluation.json').exists()
    for file in (output / 'episodes').glob('*.json'):
        for step in read_json(file)['steps']:
            assert step['epsilon'] == 0 and not step['exploring']
            assert step['q_values'][step['selected_action']] == max(step['q_values'].values())


def test_checkpoint_and_exact_resume(tmp_path: Path):
    cfg = TrainingConfig(episodes=80, max_steps=30, checkpoint_interval=10)
    full, full_agent, _ = Trainer(tiny(), cfg).run(tmp_path / 'full')
    stop = Event()
    def progress(row):
        if row['episode'] == 30:
            stop.set()
    first, _, meta = Trainer(tiny(), cfg).run(tmp_path / 'partial', progress, stop)
    cp = Path(meta['last_checkpoint'])
    saved = CheckpointStore.load(cp)
    assert saved['episode'] == 30
    assert saved['epsilon'] == pytest.approx(cfg.epsilon * cfg.epsilon_decay ** 30)
    resumed, agent, info = Trainer(tiny(), cfg).run(tmp_path / 'resumed', resume=cp)
    assert info['resume_episode'] == 31
    assert agent.table == full_agent.table
    assert read_json(resumed / 'metrics.json') == read_json(full / 'metrics.json')
    assert read_json(first / 'run.json')['status'] == 'cancelled'
    assert CheckpointStore.load(cp) == saved


def test_scenario_schema_migration_and_serialization():
    old = {'name': 'legacy', 'width': 4, 'height': 4, 'start': [0, 0], 'goal': [3, 3], 'objects': []}
    migrated = ScenarioSpec.from_dict(old)
    assert migrated.schema_version == '0.4' and migrated.grid_size == (4, 4)
    migrated.dynamic_objects = [DynamicObject(position=(2, 1), movement='vertical')]
    migrated.observation = ObservationSpec(mode='extended')
    assert ScenarioSpec.from_dict(migrated.to_dict()) == migrated
    with pytest.raises(ValueError):
        ScenarioSpec.from_dict({**old, 'schema_version': '9'})


def test_random_generation_reproducible():
    a = generate_scenario(20, 88, 'extreme')
    assert a == generate_scenario(20, 88, 'extreme')
    assert a != generate_scenario(20, 89, 'extreme')
    assert len(a.dynamic_objects) == 6
    assert GridWorld(a).get_metrics()['shortest_path_distance'] is not None


def test_dynamic_update_and_collision():
    s = tiny()
    s.dynamic_objects = [DynamicObject(position=(2, 1), movement='horizontal')]
    env = GridWorld(s)
    env.step('down')
    assert env.get_state()['dynamic_objects'][0]['position'] == [3, 1]
    s.dynamic_objects = [DynamicObject(position=(1, 1), movement='vertical', direction=-1)]
    env = GridWorld(s)
    r = env.step('right')
    assert r.reason == 'moving_obstacle_collision' and r.terminated and r.reward == -100
    # Adjacent swap is conservatively treated as collision too.
    s.dynamic_objects = [DynamicObject(position=(1, 0), movement='horizontal', direction=-1)]
    assert GridWorld(s).step('right').reason == 'moving_obstacle_collision'


def test_danger_slow_and_extended_observation():
    s = tiny()
    s.objects = [SceneObject('danger_zone', (1, 0)), SceneObject('slow_zone', (0, 1))]
    env = GridWorld(s)
    assert env.step('down').reward == -2
    env.reset()
    assert env.step('right').reason == 'danger_zone'
    data = env.get_extended_observation()
    assert data['agent'] == [1, 0] and len(data['local_grid']) == 3


def test_simulation_contract():
    env = GridWorld(tiny())
    assert isinstance(env, SimulationEnvironment)
    assert env.capabilities.supports_dynamic_objects and not env.capabilities.supports_3d
    assert env.reset() == env.get_observation()
    assert env.render() == env.get_state()
    assert env.get_metrics()['shortest_path_distance'] == 6
    env.close()
    assert env.closed


def test_atomic_invalid_write_preserves_existing(tmp_path: Path):
    path = tmp_path / 'important.json'
    write_json(path, {'ok': 1})
    with pytest.raises(ValueError):
        write_json(path, {'bad': float('nan')})
    assert read_json(path) == {'ok': 1}
    assert not list(tmp_path.glob('*.tmp'))


def log_step(position, next_position, action='right', reason='moving'):
    return {'state': list(position), 'new_state': list(next_position), 'goal': [3, 3],
            'selected_action': action, 'q_values': {'up': 0, 'down': 1, 'left': -3, 'right': 5},
            'exploring': False, 'reason': reason}


def test_failure_analyzer_collision():
    episode = {'success': False, 'reason': 'collision', 'steps': [log_step((2, 2), (2, 2), reason='collision')]}
    result = analyze_failure(episode)
    assert result['failure_type'] == 'Collision' and result['failure_step'] == 1
    assert result['relevant_q_values']['right'] == 5
    assert any('maximal' in cause for cause in result['possible_causes'])


def test_timeout_analyzer_and_loop_detection():
    steps = [log_step((0, 0), (1, 0)), log_step((1, 0), (0, 0), 'left')] * 5
    loop = detect_loop(steps)
    assert loop['period'] == 2
    result = analyze_failure({'success': False, 'reason': 'timeout', 'steps': steps})
    assert result['failure_type'] == 'Timeout' and result['loop']
    assert result['max_state_visits'] == 5
    assert any('Step limit' in s for s in result['possible_causes'])
    assert detect_loop([log_step((0, i), (0, i + 1)) for i in range(8)]) is None


def test_dynamic_failure_and_danger_analysis():
    step = log_step((0, 0), (1, 0))
    data = analyze_failure({'success': False, 'reason': 'moving_obstacle_collision', 'steps': [step]})
    assert any('motion' in cause for cause in data['possible_causes'])
    assert analyze_failure({'success': False, 'reason': 'danger_zone', 'steps': [step]})['failure_type'] == 'Danger Zone'


def test_model_versioning_and_evaluation_link(tmp_path: Path):
    _, agent, meta = Trainer(tiny(), TrainingConfig(episodes=10)).run(tmp_path / 'runs')
    one = ModelRegistry.save(tmp_path / 'models', 'ObstacleAgent', agent, meta, notes='first')
    two = ModelRegistry.save(tmp_path / 'models', 'ObstacleAgent', agent, meta)
    assert read_json(one / 'metadata.json')['version'] == '1'
    assert read_json(two / 'metadata.json')['version'] == '2'
    assert read_json(two / 'metadata.json')['parent_version']['id'] == one.name
    three = ModelRegistry.duplicate(two)
    assert read_json(three / 'metadata.json')['version'] == '3'
    ModelRegistry.attach_evaluation(two, tmp_path / 'eval', {'success_rate': 0.5, 'created_date': 'now'})
    assert read_json(two / 'metadata.json')['evaluation'][0]['success_rate'] == 0.5
    ModelRegistry.rename(three, 'Renamed')
    assert read_json(three / 'metadata.json')['name'] == 'Renamed'
    with pytest.raises(ValueError):
        ModelRegistry.delete(tmp_path / 'models', tmp_path / 'runs')
    ModelRegistry.delete(tmp_path / 'models', three)
    assert len(ModelRegistry.list(tmp_path / 'models')) == 2


def test_training_comparison_and_success_replay(tmp_path: Path):
    from aero_ai_studio.replay.replay_engine import ReplayEngine
    run, agent, meta = Trainer(tiny(), TrainingConfig(episodes=200)).run(tmp_path / 'runs')
    ModelRegistry.save(tmp_path / 'models', 'ComparisonAgent', agent, meta)
    result = compare_runs([run], tmp_path / 'models')[0]
    assert result['episodes'] == 200 and result['models'] == ['ComparisonAgent v1']
    assert result['final_epsilon'] == meta['final_epsilon']
    assert ReplayEngine.best_episode(run, 'shortest') is not None
    assert all(r['success'] for r in ReplayEngine.episodes(run, 'success'))


def test_visual_sampling_and_manual_checkpoint(tmp_path: Path):
    events, request = [], Event()
    request.set()
    run, _, _ = Trainer(tiny(), TrainingConfig(episodes=5, visual_interval=2)).run(tmp_path, checkpoint_request=request, visual=events.append)
    assert {s['episode'] for s in events} == {1, 2, 4}
    assert (run / 'checkpoints' / 'episode_000001' / 'checkpoint.json').exists()
    assert not request.is_set()
    for s in events:
        text = BrainEvent(s).text()
        assert 'Decision Type:' in text and 'Risk' in text and 'Mission' in text


def test_adapter_lifecycle_on_error(tmp_path: Path):
    instances = []
    class BrokenEnvironment(GridWorld):
        def step(self, action):
            raise RuntimeError('simulated adapter failure')
    def factory(spec, steps):
        env = BrokenEnvironment(spec, steps)
        instances.append(env)
        return env
    with pytest.raises(RuntimeError, match='adapter failure'):
        Trainer(tiny(), TrainingConfig(episodes=1), factory).run(tmp_path)
    assert instances[0].closed
    assert read_json(next(tmp_path.glob('*/run.json')))['status'] == 'failed'
