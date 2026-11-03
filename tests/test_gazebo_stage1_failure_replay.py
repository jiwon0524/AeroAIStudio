import importlib.util
from pathlib import Path

import pytest

from aero_ai_studio.simulation.action_mapping import gazebo_physics_action_mapping


_MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "verify_v07_gazebo_stage1_failure_replay.py"
_SPEC = importlib.util.spec_from_file_location("stage1_failure_replay", _MODULE_PATH)
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def _failure():
    return {
        "command_mode_transition": "ROTATION_TO_LINEAR",
        "previous_action_twist": {"linear": {"x": 0.0}, "angular": {"z": -0.8}},
        "requested_command_twist": {"linear": {"x": -0.5}, "angular": {"z": 0.0}},
    }


def _checkpoint(actions):
    return {"global_step": len(actions),
            "buffer": [([0.0] * 22, index, 0.0, [0.0] * 22, False) for index in actions]}


def test_saved_action_indices_are_replayed_in_order_through_failed_action():
    # Prefix ends in right; saved exception identifies down as the rejected step.
    indices = [0, 2, 3]
    replay = _MODULE.build_replay_sequence(_checkpoint(indices), _failure(), [],
                                            gazebo_physics_action_mapping())
    assert replay["action_sequence"] == ["up", "left", "right", "down"]
    assert replay["failed_action_index_1_based"] == 4
    assert replay["previous_action"] == "right"
    assert replay["sequence_complete_through_failure"] is True


def test_replay_rejects_terminal_or_inconsistent_action_history():
    checkpoint = _checkpoint([3])
    checkpoint["buffer"][0] = (*checkpoint["buffer"][0][:-1], True)
    with pytest.raises(ValueError, match="terminal transition"):
        _MODULE.build_replay_sequence(checkpoint, _failure(), [], gazebo_physics_action_mapping())
    with pytest.raises(ValueError, match="disagrees"):
        _MODULE.build_replay_sequence(_checkpoint([0]), _failure(), [], gazebo_physics_action_mapping())


def test_failure_parser_requires_saved_r2l_production_exception():
    parsed = _MODULE.parse_failed_validation(
        _MODULE.ERROR_PREFIX + repr(_failure()))
    assert parsed["command_mode_transition"] == "ROTATION_TO_LINEAR"
    with pytest.raises(ValueError):
        _MODULE.parse_failed_validation("unrelated error")


@pytest.mark.parametrize(("validation", "blocked", "expected"), [
    ({"valid": True, "discrepancy_classification": "translation_signals_close"}, False, "NORMAL"),
    ({"valid": True, "discrepancy_classification": "validated_rotation_to_linear_transient"}, False,
     "ROTATION_TO_LINEAR_TRANSIENT"),
    ({"valid": False, "discrepancy_classification": "wheel_odometry_without_world_translation"}, False, "NONE"),
    ({"valid": True, "discrepancy_classification": "validated_rotation_to_linear_transient"}, True, "NONE"),
])
def test_acceptance_path_reports_normal_transient_and_rejection(validation, blocked, expected):
    assert _MODULE.classify_acceptance(validation, blocked) == expected
