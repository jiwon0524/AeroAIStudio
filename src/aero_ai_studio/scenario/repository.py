from pathlib import Path
from aero_ai_studio.core.storage import read_json, write_json
from aero_ai_studio.scenario.models import ScenarioSpec


class ScenarioRepository:
    @staticmethod
    def save(path: Path, scenario: ScenarioSpec) -> None:
        scenario.validate()
        write_json(path, scenario.to_dict())

    @staticmethod
    def load(path: Path) -> ScenarioSpec:
        return ScenarioSpec.from_dict(read_json(path))
