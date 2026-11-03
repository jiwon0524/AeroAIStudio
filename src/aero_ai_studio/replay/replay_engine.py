from pathlib import Path
from aero_ai_studio.core.storage import read_json
from aero_ai_studio.training.logger import RunLogger


class ReplayEngine:
    def __init__(self):
        self.episode: dict = {}
        self.index = 0

    def load(self, run: Path, episode: int) -> dict:
        self.episode = RunLogger(run).load_episode(episode)
        self.index = 0
        return self.episode

    @property
    def count(self) -> int:
        return len(self.episode.get("steps", []))

    def seek(self, index: int) -> dict | None:
        if not self.count:
            return None
        self.index = max(0, min(index, self.count - 1))
        return self.episode["steps"][self.index]

    @staticmethod
    def episodes(run: Path, failure_filter: str = "all") -> list[dict]:
        rows = read_json(run / "metrics.json")
        return [r for r in rows if failure_filter == "all" or
                (failure_filter == "success" and r['success']) or
                (failure_filter == "failed" and not r["success"]) or r["reason"] == failure_filter]

    @staticmethod
    def best_episode(run: Path, criterion: str) -> int | None:
        rows = ReplayEngine.episodes(run)
        candidates = [r for r in rows if r['success']]
        if criterion == 'highest_reward':
            candidates = rows
        if not candidates:
            return None
        chosen = min(candidates, key=lambda r: r['steps']) if criterion == 'shortest' else max(candidates, key=lambda r: r['reward'])
        return chosen['episode']
