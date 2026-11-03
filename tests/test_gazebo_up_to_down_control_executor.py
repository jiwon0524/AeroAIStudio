import pytest

from tools.verify_v07_gazebo_control_executor_up_to_down import (
    PREFIX,
    _validate_prefix_sources,
)


def test_up_to_down_verifier_crosschecks_retry2_actions_and_target():
    actions = ["up", "down", "up", "up", "up", "down", "up"]
    replay = {"completed_episode_actions": [actions]}
    retry = {"episode_replays": [{"actions": [
        {"action": action} for action in actions]}],
        "failed_replay_action": {"episode": 1,
            "episode_action_index_1_based": 7, "action": "up",
            "type": "PhysicalControlFailure"}}
    evidence = _validate_prefix_sources(replay, retry)
    assert evidence["prefix_actions"] == PREFIX
    assert evidence["target_action"] == "down"
    assert evidence["target_corresponds_to_saved_action_index_1_based"] == 6
    assert evidence["prefix_crosscheck_pass"] is True


@pytest.mark.parametrize("actions", [
    ["up", "down", "up", "up", "down", "down", "up"],
    ["up", "down", "up", "up", "up", "up", "up"],
])
def test_up_to_down_verifier_rejects_nonmatching_saved_sequence(actions):
    replay = {"completed_episode_actions": [actions]}
    retry = {"episode_replays": [{"actions": [
        {"action": action} for action in actions]}],
        "failed_replay_action": {"episode": 1,
            "episode_action_index_1_based": 7, "action": "up",
            "type": "PhysicalControlFailure"}}
    with pytest.raises(ValueError):
        _validate_prefix_sources(replay, retry)


def test_up_to_down_verifier_is_experimental_and_does_not_activate_production():
    from pathlib import Path
    source = (Path(__file__).parents[1] /
        "tools/verify_v07_gazebo_control_executor_up_to_down.py").read_text()
    assert '"production_activation": False' in source
    assert "executor.execute_plan" in source
    assert "adapter.step(action)" in source  # saved prefix uses production PHYSICS path
