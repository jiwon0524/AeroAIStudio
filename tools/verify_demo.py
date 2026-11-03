"""Reproducible full-size demo, greedy evaluation and Qt screenshots.

Run from the project root: python tools/verify_demo.py --output ../../work/demo
"""
from __future__ import annotations
import argparse
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path

from PySide6.QtWidgets import QApplication
from aero_ai_studio.core.storage import read_json, write_json
from aero_ai_studio.projects.repository import Project, ProjectRepository
from aero_ai_studio.scenario.models import ScenarioSpec, SceneObject
from aero_ai_studio.scenario.repository import ScenarioRepository
from aero_ai_studio.training.trainer import Trainer, TrainingConfig
from aero_ai_studio.models.registry import ModelRegistry
from aero_ai_studio.deploy.export import export_local
from aero_ai_studio.simulation.grid_world import GridWorld
from aero_ai_studio.ui.window import MainWindow


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    repo = ProjectRepository(output / "workspace")
    project = Project("Warehouse · Obstacle Avoidance", "Reproducible V0.3 validation")
    root = repo.save(project)
    scenario = ScenarioSpec(objects=[SceneObject("wall", (8, y)) for y in range(4, 16)])
    ScenarioRepository.save(root / "scenarios" / "scenario.json", scenario)
    project.scenario = "scenarios/scenario.json"
    run, agent, meta = Trainer(scenario, TrainingConfig()).run(root / "runs")
    project.training_runs.append(run.name)
    model = ModelRegistry.save(root / "models", "warehouse_agent_v1", agent, meta)
    project.model = str(model.relative_to(root))
    repo.save(project)
    export_local(model, root / "exports" / model.name)
    env = GridWorld(scenario)
    state = env.reset()
    trajectory = []
    for _ in range(200):
        action, _ = agent.choose(state, 0)
        result = env.step(action)
        trajectory.append({"state": state, "action": action, "reward": result.reward})
        state = result.observation
        if result.terminated or result.truncated:
            break
    rows = read_json(run / "metrics.json")
    summary = {"episodes": len(rows), "overall_training_success": meta["success_rate"],
               "last_100_training_success": sum(r["success"] for r in rows[-100:]) / 100,
               "average_training_reward": meta["average_reward"], "collisions": meta["collision_count"],
               "greedy_result": result.reason, "greedy_steps": len(trajectory),
               "note": "Single fixed synthetic scenario; not a generalization or hardware evaluation"}
    write_json(output / "summary.json", summary)
    write_json(output / "greedy_trajectory.json", trajectory)
    app = QApplication.instance() or QApplication([])
    window = MainWindow(output / "workspace")
    window.resize(1500, 960)
    window.show()
    for index, name in ((0, "dashboard"), (3, "scenario"), (5, "replay"), (4, "brain"), (8, "models")):
        window.nav.setCurrentRow(index)
        if index == 5:
            window.failure_filter.setCurrentText("collision")
            window.episode_select.setCurrentIndex(window.episode_select.count() - 1)
            window.seek(min(4, window.replay.count - 1))
        app.processEvents()
        window.grab().save(str(output / f"{name}.png"))
    window.close()
    print(summary)


if __name__ == "__main__":
    main()
