from pathlib import Path
from statistics import mean
from aero_ai_studio.core.storage import read_json


def compare_runs(runs: list[Path], models: Path | None = None) -> list[dict]:
    linked = list(models.glob('*/metadata.json')) if models else []
    result = []
    for path in runs:
        meta, rows = read_json(path / 'run.json'), read_json(path / 'metrics.json')
        cfg = meta['config']
        matching_models = [(p.parent, m) for p in linked if (m := read_json(p))['training_run'] == path.name]
        evaluations = [e for _, m in matching_models for e in (m.get('evaluation') if isinstance(m.get('evaluation'), list) else [])]
        eval_summary = read_json(Path(evaluations[-1]['path']) / 'evaluation.json') if evaluations and (Path(evaluations[-1]['path']) / 'evaluation.json').exists() else {}
        result.append({'run': path.name, 'episodes': len(rows),
                       'final_success_rate': rows[-1]['success_rate'] if rows else 0,
                       'average_reward': mean(r['reward'] for r in rows) if rows else 0,
                       'average_steps': mean(r['steps'] for r in rows) if rows else 0,
                       'learning_rate': cfg['learning_rate'], 'gamma': cfg['gamma'],
                       'algorithm': cfg.get('algorithm','q_learning'), 'observation': cfg.get('observation_mode','basic'),
                       'evaluation_success': eval_summary.get('success_rate'),
                       'collision_rate': sum('collision' in r['reason'] for r in rows)/len(rows) if rows else 0,
                       'timeout_rate': sum(r['reason']=='timeout' for r in rows)/len(rows) if rows else 0,
                       'training_seconds': meta.get('training_seconds'),
                       'model_size_bytes': sum(f.stat().st_size for p,_ in matching_models for f in p.iterdir() if f.is_file()),
                       'final_epsilon': meta.get('final_epsilon', cfg['epsilon'] * cfg['epsilon_decay'] ** len(rows)),
                       'models': [f"{m['name']} v{m['version']}" for p in linked if (m := read_json(p))['training_run'] == path.name],
                       'series': rows})
    return result
