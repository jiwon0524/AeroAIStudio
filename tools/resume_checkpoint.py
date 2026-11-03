"""Resume a committed checkpoint in a fresh Python process, preserving its source Run."""
import argparse
from pathlib import Path
from aero_ai_studio.training.checkpoint import CheckpointStore
from aero_ai_studio.training.trainer import Trainer, TrainingConfig
from aero_ai_studio.scenario.models import ScenarioSpec


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument('--checkpoint', type=Path, required=True)
    p.add_argument('--runs', type=Path, required=True)
    p.add_argument('--episodes', type=int, required=True)
    args = p.parse_args()
    saved = CheckpointStore.load(args.checkpoint)
    config = TrainingConfig(**saved['config'])
    config.episodes = args.episodes
    config.visual_delay = 0
    root, _, meta = Trainer(ScenarioSpec.from_dict(saved['scenario']), config).run(args.runs, resume=args.checkpoint)
    print(f"Resumed episode {meta['resume_episode']} -> {meta['episodes_completed']}: {root}")


if __name__ == '__main__':
    main()
