import math

import pytest
from types import SimpleNamespace

from aero_ai_studio.gazebo.entity_controller import GazeboEntityController, summarize_world_pose_history
from aero_ai_studio.gazebo.transport import stamp
from aero_ai_studio.simulation.action_mapping import (
    classify_physics_command_transition,
    physics_transition_requires_world_pose_history,
)


def _pose(t, x, y=0., yaw=0.):
    return {"simulation_timestamp": t, "world_x": x, "world_y": y, "world_yaw": yaw}


def test_pose_history_orders_samples_and_deduplicates_timestamps():
    summary = summarize_world_pose_history(
        [_pose(.2, .02), _pose(.0, 0.), _pose(.1, .01), _pose(.1, .011)], 0., .2)
    assert summary["world_pose_sample_timestamps"] == [0., .1, .2]
    assert summary["world_pose_x"] == [0., .011, .02]
    assert summary["world_pose_history_fresh"]
    assert summary["world_pose_timestamp_source"] == (
        "Pose_V.header.stamp simulation time; contained Pose.header.stamp fallback")


@pytest.mark.parametrize("positions,expected_sign", [
    ([0., .01, .02], 1),
    ([.02, .01, 0.], -1),
])
def test_world_body_forward_and_reverse_trajectory_velocity(positions, expected_sign):
    summary = summarize_world_pose_history(
        [_pose(i * .01, x) for i, x in enumerate(positions)], 0., .02)
    assert summary["world_forward_displacement_samples"][-1]["forward_displacement"] * expected_sign > 0
    assert all(item["forward_velocity"] * expected_sign > 0
               for item in summary["world_forward_velocity_samples"])
    assert summary["world_velocity_sample_count"] == 2
    assert summary["body_forward_velocity_samples"]==summary["world_forward_velocity_samples"]
    assert summary["world_pose_velocity_method"] == "finite_difference_adjacent_pose_samples"
    sample=summary['world_angular_velocity_samples'][0]
    assert sample['simulation_timestamp']==pytest.approx(.005)
    assert sample['interval_start']==pytest.approx(0.)
    assert sample['interval_end']==pytest.approx(.01)
    assert sample['sample_interval']==pytest.approx(.01)


@pytest.mark.parametrize("positions,crossing_time", [
    ([0., -.01, -.01, 0., .01], .015),
    ([0., .01, .01, 0., -.01], .015),
])
def test_world_body_velocity_direction_crossing(positions, crossing_time):
    summary = summarize_world_pose_history(
        [_pose(i * .01, x) for i, x in enumerate(positions)], 0., .04)
    assert summary["world_velocity_zero_crossing"]
    assert summary["world_velocity_zero_crossing_time"] == pytest.approx(crossing_time)


def test_world_body_angular_velocity_uses_wrapped_yaw_difference():
    summary = summarize_world_pose_history([
        _pose(0., 0., yaw=math.pi-.01),
        _pose(.01, 0., yaw=-math.pi+.01),
        _pose(.02, 0., yaw=-math.pi+.03),
    ], 0., .02)
    samples=summary['world_angular_velocity_samples']
    assert summary['world_angular_velocity_sample_count']==2
    assert samples[0]['angular_velocity']==pytest.approx(2.)
    assert samples[1]['angular_velocity']==pytest.approx(2.)
    assert summary['world_start_angular_velocity']==pytest.approx(2.)
    assert summary['world_end_angular_velocity']==pytest.approx(2.)


@pytest.mark.parametrize('previous,requested,expected',[
    ({'linear':{'x':.5},'angular':{'z':0.}}, {'linear':{'x':0.},'angular':{'z':-.8}}, 'LINEAR_TO_ROTATION'),
    ({'linear':{'x':.5},'angular':{'z':0.}}, {'linear':{'x':0.},'angular':{'z':.8}}, 'LINEAR_TO_ROTATION'),
    ({'linear':{'x':-.5},'angular':{'z':0.}}, {'linear':{'x':0.},'angular':{'z':.8}}, 'LINEAR_TO_ROTATION'),
    ({'linear':{'x':0.},'angular':{'z':-.8}}, {'linear':{'x':.5},'angular':{'z':0.}}, 'ROTATION_TO_LINEAR'),
    ({'linear':{'x':0.},'angular':{'z':.8}}, {'linear':{'x':-.5},'angular':{'z':0.}}, 'ROTATION_TO_LINEAR'),
    ({'linear':{'x':.5},'angular':{'z':0.}}, {'linear':{'x':-.5},'angular':{'z':0.}}, 'LINEAR_REVERSAL'),
    ({'linear':{'x':0.},'angular':{'z':.8}}, {'linear':{'x':0.},'angular':{'z':-.8}}, 'ROTATION_REVERSAL'),
    ({'linear':{'x':.5},'angular':{'z':0.}}, {'linear':{'x':.5},'angular':{'z':0.}}, 'STEADY_LINEAR'),
    ({'linear':{'x':0.},'angular':{'z':-.8}}, {'linear':{'x':0.},'angular':{'z':-.8}}, 'STEADY_ROTATION'),
    ({'linear':{'x':0.},'angular':{'z':0.}}, {'linear':{'x':.5},'angular':{'z':0.}}, 'OTHER'),
])
def test_physics_command_transition_classification_is_diagnostic_only(previous,requested,expected):
    assert classify_physics_command_transition(previous,requested)==expected


def test_pose_history_is_captured_for_validated_physics_transitions():
    linear={'linear':{'x':.5},'angular':{'z':0.}}
    reverse={'linear':{'x':-.5},'angular':{'z':0.}}
    right={'linear':{'x':0.},'angular':{'z':-.8}}
    rotation={'linear':{'x':0.},'angular':{'z':.8}}
    forward={'linear':{'x':.5},'angular':{'z':0.}}
    assert physics_transition_requires_world_pose_history(linear,reverse)
    assert physics_transition_requires_world_pose_history(linear,right)
    assert physics_transition_requires_world_pose_history(rotation,forward)
    assert not physics_transition_requires_world_pose_history(right,rotation)
    assert physics_transition_requires_world_pose_history(right,rotation,capture_all=True)


def test_sparse_or_stale_pose_history_is_explicitly_insufficient():
    sparse = summarize_world_pose_history([_pose(0., 0.), _pose(.1, .01)], 0., .1)
    stale = summarize_world_pose_history([_pose(0., 0.), _pose(.02, .01)], 0., .1)
    assert sparse["world_pose_history_fresh"] and not sparse["world_pose_history_dense_enough"]
    assert not stale["world_pose_history_fresh"] and not stale["world_pose_history_dense_enough"]
    assert sparse['world_pose_history_available'] and stale['world_pose_history_available']

    missing=summarize_world_pose_history([],0.,.1)
    assert not missing['world_pose_history_available']
    assert missing['world_angular_velocity_sample_count']==0


def test_stationary_world_pose_history_does_not_masquerade_as_wheel_motion():
    summary = summarize_world_pose_history([_pose(i * .01, 1.5) for i in range(11)], 0., .1)
    assert summary["world_pose_history_dense_enough"]
    assert summary["world_start_forward_velocity"] == pytest.approx(0.)
    assert summary["world_end_forward_velocity"] == pytest.approx(0.)
    # This telemetry describes only body world-pose finite differences; wheel
    # odometry remains a separate signal maintained by the action transition.
    assert "wheel" not in summary["world_pose_velocity_method"]


def test_pose_v_timestamp_falls_back_to_contained_pose_header():
    assert stamp({"header": {}, "pose": [
        {"header": {"stamp": {"sec": 12, "nsec": 300000000}}}
    ]}) == pytest.approx(12.3)


def test_entity_controller_extracts_only_timestamped_agent_poses_from_buffered_frames():
    frames = [
        (1, {"header": {"stamp": {"sec": 4, "nsec": 0}}, "pose": [
            {"name": "simple_agent", "position": {"x": 1., "y": 2.},
             "orientation": {"w": 1.}},
            {"name": "wall", "position": {"x": 8., "y": 8.},
             "orientation": {"w": 1.}},
        ]}),
        (2, {"header": {"stamp": {"sec": 4, "nsec": 10000000}}, "pose": [
            {"name": "simple_agent", "position": {"x": 1.01, "y": 2.},
             "orientation": {"w": 1.}},
        ]}),
    ]
    transport = SimpleNamespace(subscribe=lambda *_: None,
        messages_after=lambda topic, sequence, timeout=0: frames,
        sample=lambda topic, min_time=-1, timeout=5: frames[-1][1])
    controller = GazeboEntityController(transport, "test", "simple_agent")
    samples = controller.pose_history_after(0, 4., 4.01)
    assert [sample["simulation_timestamp"] for sample in samples] == [4., 4.01]
    assert [sample["world_x"] for sample in samples] == [1., 1.01]
    assert controller.get_pose(min_time=4.)["x"] == 1.01
    assert controller.last_pose_frame_timestamp == pytest.approx(4.01)

