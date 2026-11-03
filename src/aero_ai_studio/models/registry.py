from pathlib import Path
import shutil
from aero_ai_studio.agents.q_learning import QLearningAgent
from aero_ai_studio.core.storage import identifier, now, read_json, write_json
from aero_ai_studio.agents.factory import load_agent


class ModelRegistry:
    @staticmethod
    def save(root: Path, name: str, agent: QLearningAgent, run: dict, notes: str = "", parent: Path | None = None) -> Path:
        if not name.strip():
            raise ValueError("Model name is required")
        path = root / identifier("model")
        family = [(p, m) for p, m in ModelRegistry.list(root) if m['name'] == name]
        previous = max(family, key=lambda item: int(item[1]['version']), default=None)
        if parent:
            previous = (parent, read_json(parent / 'metadata.json'))
        version = max((int(m['version']) for _, m in family), default=0) + 1
        metadata = {"name": name, "version": str(version), "algorithm": agent.get_metadata()['algorithm'],
                    "training_run": run["id"], "scenario": run["scenario"],
                    "success_rate": run["success_rate"], "average_reward": run["average_reward"],
                    "created_date": now(), "evaluation": [], "notes": notes,
                    "parent_version": {'id': previous[0].name, 'version': previous[1]['version']} if previous else None,
                    "training_metrics_label": "includes exploration; separate evaluation required",
                    'agent_metadata': agent.get_metadata(), 'training_config': run.get('config', {})}
        agent.save(path / agent.artifact_name)
        write_json(path / "metadata.json", metadata)
        return path

    @staticmethod
    def list(root: Path) -> list[tuple[Path, dict]]:
        return [(p.parent, read_json(p)) for p in sorted(root.glob("*/metadata.json"))]

    @staticmethod
    def attach_evaluation(model: Path, evaluation: Path, summary: dict) -> None:
        meta = read_json(model / 'metadata.json')
        if not isinstance(meta.get('evaluation'), list):
            meta['evaluation'] = []
        meta['evaluation'].append({'id': evaluation.name, 'path': str(evaluation.resolve()),
                                   'success_rate': summary['success_rate'], 'created_date': summary['created_date']})
        write_json(model / 'metadata.json', meta)

    @staticmethod
    def rename(model: Path, name: str) -> None:
        if not name.strip():
            raise ValueError('Model name is required')
        meta = read_json(model / 'metadata.json')
        if any(p != model and m['name'] == name.strip() and m['version'] == meta['version'] for p, m in ModelRegistry.list(model.parent)):
            raise ValueError('That model name/version already exists')
        meta['name'] = name.strip()
        write_json(model / 'metadata.json', meta)

    @staticmethod
    def duplicate(model: Path) -> Path:
        meta = read_json(model / 'metadata.json')
        run = {'id': meta['training_run'], 'scenario': meta['scenario'],
               'success_rate': meta['success_rate'], 'average_reward': meta['average_reward']}
        run['config'] = meta.get('training_config', {})
        return ModelRegistry.save(model.parent, meta['name'], load_agent(model), run,
                                  notes=f"Duplicated from {model.name}", parent=model)

    @staticmethod
    def delete(root: Path, model: Path) -> None:
        resolved = model.resolve()
        if resolved.parent != root.resolve() or not resolved.name.startswith('model_') or not (resolved / 'metadata.json').exists():
            raise ValueError('Invalid model directory')
        shutil.rmtree(resolved)
