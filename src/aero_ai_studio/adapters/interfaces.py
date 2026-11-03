"""Future adapters. V0.4 contains no hardware or map-service integration."""
from typing import Protocol
from aero_ai_studio.scenario.models import ScenarioSpec


class KoreaMapProvider(Protocol):
    def search_location(self, query: str) -> list[dict]: ...
    def get_bounds(self, location_id: str) -> tuple[float, float, float, float]: ...
    def get_roads(self, bounds: tuple) -> list[dict]: ...
    def get_buildings(self, bounds: tuple) -> list[dict]: ...
    def generate_scene_spec(self, bounds: tuple) -> ScenarioSpec: ...


class KoreaMapAdapter:
    """Provider injection; reference imagery must respect provider licensing."""
    def __init__(self, provider: KoreaMapProvider):
        self.provider = provider

    def search_location(self, query: str) -> list[dict]:
        return self.provider.search_location(query)

    def get_bounds(self, location_id: str) -> tuple:
        return self.provider.get_bounds(location_id)

    def get_roads(self, bounds: tuple) -> list[dict]:
        return self.provider.get_roads(bounds)

    def get_buildings(self, bounds: tuple) -> list[dict]:
        return self.provider.get_buildings(bounds)

    def generate_scene_spec(self, bounds: tuple) -> ScenarioSpec:
        return self.provider.generate_scene_spec(bounds)


class VideoAnalysisAdapter(Protocol):
    def analyze(self, source: str) -> list[dict]: ...


class PaperAnalysisAdapter(Protocol):
    def parse(self, source: str) -> str: ...
    def analyze(self, text: str, mode: str) -> dict: ...
    def experiment_spec(self, analysis: dict) -> ScenarioSpec: ...


class ExportAdapter(Protocol):
    def export(self, model: str, destination: str) -> str: ...


class PlaceholderExportAdapter:
    def __init__(self, target: str):
        self.target = target

    def export(self, model: str, destination: str) -> str:
        raise NotImplementedError(f"{self.target} export is not implemented in V0.4")
