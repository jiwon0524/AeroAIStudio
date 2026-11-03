from pathlib import Path
from aero_ai_studio.core.storage import read_json, write_json


class RunLogger:
    def __init__(self, root: Path):
        self.root = root
        (root / "episodes").mkdir(parents=True, exist_ok=True)

    def save_episode(self, episode: dict) -> None:
        write_json(self.root / "episodes" / f"episode_{episode['episode']:04d}.json", episode)

    def load_episode(self, number: int) -> dict:
        return read_json(self.root / "episodes" / f"episode_{number:04d}.json")
