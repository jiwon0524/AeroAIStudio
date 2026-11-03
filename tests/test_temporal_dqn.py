from __future__ import annotations

import math

import pytest

from aero_ai_studio.agents.base import Transition
from aero_ai_studio.agents.dqn import DQNAgent, ReplayBuffer, _double_dqn_targets
from aero_ai_studio.simulation.grid_world import GridWorld
from aero_ai_studio.scenario.models import ScenarioSpec
from aero_ai_studio.training.temporal import MacroRewardAccumulator


def _obs():
    return GridWorld(ScenarioSpec(width=4, height=4, goal=(3, 3))).get_agent_observation("sensor")


def test_transition_duration_defaults_to_one_and_rejects_invalid():
    obs = _obs()
    assert Transition(obs, "up", 0.0, obs, False).elapsed_discount_units == 1.0
    for value in (0.0, -1.0, math.inf, math.nan):
        with pytest.raises(ValueError, match="elapsed_discount_units"):
            Transition(obs, "up", 0.0, obs, False, value)


def test_dqn_discount_units_one_matches_existing_target_exactly():
    torch = pytest.importorskip("torch")
    rewards = torch.tensor([1.0, 2.0])
    dones = torch.tensor([0.0, 0.0])
    bootstrap = torch.tensor([4.0, 5.0])
    discounts, targets = _double_dqn_targets(rewards, dones, torch.ones(2), bootstrap, 0.95)
    assert discounts.tolist() == pytest.approx([0.95, 0.95])
    assert targets.tolist() == pytest.approx((rewards + 0.95 * bootstrap).tolist())


def test_variable_and_fractional_batch_discounts_and_terminal_mask():
    torch = pytest.importorskip("torch")
    units = torch.tensor([1.0, 2.0, 3.0, 2.5])
    rewards = torch.tensor([0.0, 0.0, 0.0, 0.0])
    dones = torch.tensor([0.0, 0.0, 1.0, 0.0])
    bootstrap = torch.tensor([1.0, 1.0, 9.0, 1.0])
    discounts, targets = _double_dqn_targets(rewards, dones, units, bootstrap, 0.95)
    assert discounts.shape == targets.shape == (4,)
    assert discounts.tolist() == pytest.approx([0.95, 0.95**2, 0.95**3, 0.95**2.5])
    assert targets.tolist() == pytest.approx([0.95, 0.95**2, 0.0, 0.95**2.5])


def test_double_dqn_online_argmax_and_target_evaluation_with_duration(monkeypatch):
    torch = pytest.importorskip("torch")
    agent = DQNAgent(gamma=0.9, batch_size=1, buffer_size=8, target_interval=100,
                     double_dqn=True, warmup_steps=1, seed=4)
    with torch.no_grad():
        for parameter in agent.network.parameters():
            parameter.zero_()
        for parameter in agent.target.parameters():
            parameter.zero_()
        agent.network[-1].bias.copy_(torch.tensor([1.0, 2.0, 7.0, 4.0]))
        agent.target[-1].bias.copy_(torch.tensor([100.0, 200.0, 3.0, 400.0]))
    captured = []
    original = torch.nn.functional.smooth_l1_loss

    def capture(q, target):
        captured.extend(target.tolist())
        return original(q, target)

    monkeypatch.setattr(torch.nn.functional, "smooth_l1_loss", capture)
    obs = _obs()
    for index in range(4):
        agent.learn(Transition(obs, "up", 1.0, obs, False, 2.5 if index == 3 else 1.0))
    # The sampled item may be any one of the four; all network values are fixed.
    assert captured
    allowed = [1 + 0.9 * 3, 1 + 0.9**2.5 * 3]
    assert all(any(value == pytest.approx(expected) for expected in allowed) for value in captured)


def test_macro_reward_accumulator_discount_and_fractional_duration():
    accumulator = MacroRewardAccumulator(0.95)
    accumulator.add_chunk(1.0, 0.1)
    accumulator.add_chunk(2.0, 0.1)
    accumulator.add_chunk(3.0, 0.1)
    result = accumulator.result()
    assert result.reward == pytest.approx(1 + 0.95 * 2 + 0.95**2 * 3)
    assert result.elapsed_execution_time == pytest.approx(0.3)
    assert result.elapsed_discount_units == pytest.approx(3.0)
    assert not result.terminal

    fractional = MacroRewardAccumulator(0.95)
    fractional.add_chunk(2.0, 0.05)
    fractional.add_chunk(4.0, 0.2, terminal=True)
    assert fractional.result().reward == pytest.approx(2 + 0.95**0.5 * 4)
    assert fractional.result().elapsed_discount_units == pytest.approx(2.5)
    assert fractional.result().terminal
    with pytest.raises(ValueError, match="terminal chunk"):
        fractional.add_chunk(10.0, 0.1)


def test_replay_old_and_new_duration_items_and_checkpoint_round_trip(tmp_path):
    torch = pytest.importorskip("torch")
    obs = _obs()
    agent = DQNAgent(batch_size=8, buffer_size=20, seed=7)
    agent.learn(Transition(obs, "right", 1.0, obs, False))
    agent.learn(Transition(obs, "down", 2.0, obs, True, 2.5))
    assert agent.buffer.items[0][-1] == 1.0
    assert agent.buffer.items[1][-1] == 2.5
    path = tmp_path / "new.pt"
    agent.save(path)
    data = torch.load(path, map_location="cpu", weights_only=True)
    assert data["schema_version"] == "0.6"
    restored = DQNAgent.load(path)
    assert [item[-1] for item in restored.buffer.items] == [1.0, 2.5]
    assert restored.global_step == agent.global_step
    assert restored.learn_steps == agent.learn_steps
    assert restored.optimizer_updates == agent.optimizer_updates
    assert restored.target_updates == agent.target_updates
    assert restored.rng.getstate() == agent.rng.getstate()
    assert all(torch.equal(a, b) for a, b in zip(agent.target.parameters(), restored.target.parameters()))

    # Model a pre-temporal schema 0.5 checkpoint with five-field replay entries.
    data["schema_version"] = "0.5"
    data["buffer"] = [tuple(item[:5]) for item in data["buffer"]]
    data["metadata"].pop("discount_time_unit_seconds", None)
    old_path = tmp_path / "old.pt"
    torch.save(data, old_path)
    migrated = DQNAgent.load(old_path)
    assert [item[-1] for item in migrated.buffer.items] == [1.0, 1.0]
    assert migrated.global_step == agent.global_step
    assert migrated.learn_steps == agent.learn_steps
    assert migrated.optimizer_updates == agent.optimizer_updates
    assert migrated.target_updates == agent.target_updates


def test_legacy_replay_buffer_samples_five_field_items_as_unit_duration():
    import random

    buffer = ReplayBuffer(4)
    legacy = ("s", 0, 1.0, "n", False)
    current = ("s2", 1, 2.0, "n2", False, 2.5)
    buffer.append(legacy)
    buffer.append(current)
    sample = buffer.sample(2, random.Random(1))
    assert {item[-1] for item in sample} == {1.0, 2.5}
