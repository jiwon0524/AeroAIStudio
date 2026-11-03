from __future__ import annotations
import importlib.util
from pathlib import Path
from threading import Event

import pytest

from aero_ai_studio.agents.q_learning import QLearningAgent
from aero_ai_studio.core.storage import read_json
from aero_ai_studio.deploy.export import export_local
from aero_ai_studio.explainability.brain_map import BrainEvent
from aero_ai_studio.models.registry import ModelRegistry
from aero_ai_studio.projects.repository import Project, ProjectRepository
from aero_ai_studio.replay.replay_engine import ReplayEngine
from aero_ai_studio.scenario.models import ScenarioSpec, SceneObject
from aero_ai_studio.scenario.repository import ScenarioRepository
from aero_ai_studio.simulation.grid_world import GridWorld
from aero_ai_studio.training.logger import RunLogger
from aero_ai_studio.training.trainer import Trainer, TrainingConfig


def small() -> ScenarioSpec:
    return ScenarioSpec(width=4, height=4, goal=(3, 3), objects=[SceneObject("wall", (1, 1))])


def test_scenario_save_load(tmp_path: Path):
    spec = small()
    spec.randomization = {"obstacle_position": True, "sensor_noise": True}
    path = tmp_path / "scenario.json"
    ScenarioRepository.save(path, spec)
    assert ScenarioRepository.load(path) == spec


def test_project_persistence(tmp_path: Path):
    repo = ProjectRepository(tmp_path)
    project = Project("시험 ../project", description="local", objective="navigation")
    root = repo.save(project)
    assert root.parent == tmp_path / "projects"
    assert all((root / x).is_dir() for x in ("scenarios", "runs", "models", "replays"))
    assert repo.list() == [project]


def test_reset_step_collision():
    env = GridWorld(small(), 20)
    assert env.reset() == (0, 0)
    safe = env.step("right")
    assert safe.observation == (1, 0) and safe.reward == 1 and not safe.terminated
    collision = env.step("down")
    assert collision.reason == "collision" and collision.reward == -100
    assert collision.observation == (1, 0) and collision.terminated
    with pytest.raises(RuntimeError):
        env.step("left")
    assert env.reset() == (0, 0)
    assert env.get_state()["steps"] == 0
    assert env.step("up").reason == "collision"


def test_goal_timeout_and_action_validation():
    env = GridWorld(small())
    for action in ["right"] * 3 + ["down"] * 3:
        result = env.step(action)
    assert result.reason == "goal" and result.reward == 100 and result.terminated
    assert not result.truncated
    env = GridWorld(small(), max_steps=1)
    with pytest.raises(ValueError):
        env.step("fly")
    assert env.step("right").truncated


def test_randomization_seed_and_validation():
    spec = small()
    spec.randomization = {"obstacle_position": True, "obstacle_count": True}
    env = GridWorld(spec)
    env.reset(91)
    state = env.get_state()
    env.reset(91)
    assert env.get_state() == state
    assert spec.start not in env.obstacles and spec.goal not in env.obstacles
    spec.objects = [SceneObject("wall", (0, 1)), SceneObject("wall", (1, 0))]
    spec.randomization = {}
    with pytest.raises(ValueError, match="unreachable"):
        GridWorld(spec)
    spec = small()
    spec.world_mode = "korea_real"
    with pytest.raises(ValueError, match="Synthetic"):
        GridWorld(spec)


def test_q_update_and_roundtrip(tmp_path: Path):
    agent = QLearningAgent(learning_rate=0.1, gamma=0.95)
    agent.scores((1, 0))["right"] = 10
    agent.update((0, 0), "right", 2, (1, 0), False)
    assert agent.scores((0, 0))["right"] == pytest.approx(1.15)
    agent.update((0, 0), "up", -100, (1, 0), True)
    assert agent.scores((0, 0))["up"] == -10
    path = tmp_path / "q_table.json"
    agent.save(path)
    assert QLearningAgent.load(path).table == agent.table


def test_episode_and_replay_roundtrip(tmp_path: Path):
    episode = {"episode": 1, "success": False, "reason": "timeout", "total_reward": -1,
               "steps": [{"state": [0, 0]}, {"state": [1, 0]}]}
    logger = RunLogger(tmp_path)
    logger.save_episode(episode)
    assert logger.load_episode(1) == episode
    replay = ReplayEngine()
    replay.load(tmp_path, 1)
    assert replay.seek(1) == {"state": [1, 0]}
    assert replay.seek(100) == {"state": [1, 0]}
    assert replay.seek(-1) == {"state": [0, 0]}


def test_full_training_model_export(tmp_path: Path):
    root, agent, meta = Trainer(small(), TrainingConfig(episodes=500, max_steps=40)).run(tmp_path / "runs")
    rows = read_json(root / "metrics.json")
    assert len(rows) == 500
    assert meta["status"] == "completed"
    assert sum(r["success"] for r in rows[-100:]) > 75
    failures = ReplayEngine.episodes(root, "failed")
    assert failures and all(not r["success"] for r in failures)
    replay = ReplayEngine()
    replay.load(root, failures[0]["episode"])
    step = replay.seek(0)
    assert set(step["q_values"]) == {"up", "down", "left", "right"}
    assert "before update" in BrainEvent(step).text()
    for i in range(replay.count - 1):
        assert replay.seek(i)["new_state"] == replay.seek(i + 1)["state"]
    model = ModelRegistry.save(tmp_path / "models", "test", agent, meta)
    assert ModelRegistry.list(tmp_path / "models")[0][1]["training_run"] == root.name
    destination = export_local(model, tmp_path / "export")
    spec = importlib.util.spec_from_file_location("exported", destination / "policy.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.act(0, 0) in ("right", "down")
    with pytest.raises(ValueError, match="Unseen"):
        module.act(99, 99)
    # Greedy inference is tested separately from exploration-influenced training metrics.
    env = GridWorld(small(), 40)
    state = env.reset()
    for _ in range(40):
        result = env.step(module.act(*state))
        state = result.observation
        if result.terminated or result.truncated:
            break
    assert result.reason == "goal"


def test_cancel_saves_partial_run(tmp_path: Path):
    cancel = Event()
    def progress(row):
        if row["episode"] == 5:
            cancel.set()
    root, _, meta = Trainer(small(), TrainingConfig(episodes=100)).run(tmp_path, progress, cancel)
    assert meta["status"] == "cancelled" and meta["episodes_completed"] == 5
    assert len(read_json(root / "metrics.json")) == 5
    assert (root / "q_table.json").exists()
