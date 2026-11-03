from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

from aero_ai_studio.core.storage import identifier, now, read_json, write_json


@dataclass
class Project:
    name: str
    description: str = ""
    ai_type: str = "Q-Learning"
    objective: str = "Obstacle Avoidance"
    id: str = field(default_factory=lambda: identifier("project"))
    created_date: str = field(default_factory=now)
    scenario: str | None = None
    model: str | None = None
    training_runs: list[str] = field(default_factory=list)


class ProjectRepository:
    def __init__(self, workspace: Path):
        self.root = workspace.resolve() / "projects"
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, project: Project) -> Path:
        if not project.id.startswith("project_") or not project.id.replace("_", "").isalnum():
            raise ValueError("Invalid project ID")
        return self.root / project.id

    def save(self, project: Project) -> Path:
        if not project.name.strip():
            raise ValueError("Project name is required")
        root = self.path(project)
        for folder in ("scenarios", "runs", "models", "replays"):
            (root / folder).mkdir(parents=True, exist_ok=True)
        write_json(root / "project.json", asdict(project))
        return root

    def list(self) -> list[Project]:
        return sorted((Project(**read_json(p)) for p in self.root.glob("*/project.json")),
                      key=lambda p: p.created_date, reverse=True)
