import json
from pathlib import Path

import pytest

from aero_ai_studio.training.gazebo_physics import reset_odometry_contract


def evaluate(sample, *, epoch=0., start=.1, end=.2, before_reset=8,
             after_reset=9, before_settle=10):
    return reset_odometry_contract(sample,reset_epoch_sim_time=epoch,
        settle_start_sim_time=start,settle_end_sim_time=end,
        sequence_before_reset=before_reset,sequence_after_reset=after_reset,
        sequence_before_settle=before_settle)


def odom(timestamp=.19,sequence=11,linear=0.,angular=0.):
    return {'timestamp':timestamp,'receive_sequence':sequence,
            'linear_x':linear,'angular_z':angular}


def test_new_epoch_fresh_stopped_odometry_passes():
    result=evaluate(odom())
    assert result['pass'] is True
    assert result['timestamp_after_epoch'] and result['timestamp_fresh']
    assert result['receive_sequence_new'] and result['receive_sequence_after_epoch']
    assert result['linear_stopped'] and result['angular_stopped']


def test_old_receive_sequence_fails_even_when_timestamp_and_velocity_look_fresh():
    result=evaluate(odom(sequence=10))
    assert result['pass'] is False
    assert not result['receive_sequence_new']


def test_old_epoch_timestamp_after_clock_rewind_fails():
    result=evaluate(odom(timestamp=12.4))
    assert result['pass'] is False
    assert result['timestamp_after_epoch']
    assert not result['timestamp_fresh']


def test_actual_smoke_sample_011_is_epoch_new_but_stale_at_settle_end():
    path=Path(__file__).parent/'fixtures'/'gazebo_reset_odometry_epoch_actual.json'
    fixture=json.loads(path.read_text())
    result=evaluate(fixture['odometry'],epoch=fixture['reset_epoch_sim_time'],
        start=fixture['settle_start_sim_time'],end=fixture['settle_end_sim_time'],
        before_reset=9,after_reset=10,before_settle=10)
    assert result['odom_present'] is True
    assert result['receive_sequence_new'] is True
    assert result['receive_sequence_after_epoch'] is True
    assert result['timestamp_after_epoch'] is True
    assert result['linear_stopped'] and result['angular_stopped']
    assert result['timestamp_fresh'] is False
    assert result['failure_reason']=='timestamp_fresh'


def test_reset_epoch_contract_reports_each_independent_subcondition():
    result=evaluate(odom(timestamp=.11,sequence=11),epoch=0.,start=.1,end=.2,
        before_reset=9,after_reset=10,before_settle=10)
    assert result['odom_present'] is True
    assert result['receive_sequence_new'] is True
    assert result['receive_sequence_after_epoch'] is True
    assert result['timestamp_after_epoch'] is True
    assert result['linear_stopped'] and result['angular_stopped']
    assert result['timestamp_fresh'] is False
    assert result['pass'] is False
    assert result['failure_reason']=='timestamp_fresh'


def test_simulation_clock_rewind_uses_receive_epoch_and_new_sim_time():
    result=evaluate(odom(timestamp=.01,sequence=12),epoch=0.,start=0.,end=.02,
        before_reset=11,after_reset=11,before_settle=11)
    assert result['pass'] is True
    assert result['timestamp_after_epoch'] and result['receive_sequence_new']


def test_null_epoch_sequence_baseline_never_silently_passes():
    result=reset_odometry_contract(odom(timestamp=.19,sequence=11),
        reset_epoch_sim_time=0.,settle_start_sim_time=.1,settle_end_sim_time=.2,
        sequence_before_reset=None,sequence_after_reset=None,sequence_before_settle=10)
    assert result['receive_sequence_new'] is True
    assert result['receive_sequence_after_epoch'] is False
    assert result['pass'] is False


def test_actual_seed43_odometry_passes_with_explicit_fresh_process_baseline():
    path=Path(__file__).parent/'fixtures'/'gazebo_reset_fresh_process_odometry_actual.json'
    fixture=json.loads(path.read_text());sample=fixture['selected']
    result=reset_odometry_contract(sample,
        reset_epoch_sim_time=0.,settle_start_sim_time=fixture['settle_start_sim_time'],
        settle_end_sim_time=fixture['settle_end_sim_time'],sequence_before_reset=None,
        sequence_after_reset=fixture['baseline_receive_sequence'],sequence_before_settle=10)
    assert result['pass'] is True
    assert result['receive_sequence_after_epoch'] is True
    assert result['timestamp_fresh'] is True
    assert result['linear_stopped'] and result['angular_stopped']


@pytest.mark.parametrize('linear,angular,failed',[(.1,0.,'linear_stopped'),(0.,-.1,'angular_stopped')])
def test_fresh_odometry_with_residual_wheel_motion_fails(linear,angular,failed):
    result=evaluate(odom(linear=linear,angular=angular))
    assert result['pass'] is False
    assert failed in result['failure_reason']


def test_fresh_process_and_reused_process_use_identical_epoch_contract():
    fresh_process=evaluate(odom(timestamp=.19,sequence=2),before_reset=0,
        after_reset=1,before_settle=1)
    reused_process=evaluate(odom(timestamp=.19,sequence=111),before_reset=99,
        after_reset=105,before_settle=110)
    assert fresh_process['pass'] is True
    assert reused_process['pass'] is True
