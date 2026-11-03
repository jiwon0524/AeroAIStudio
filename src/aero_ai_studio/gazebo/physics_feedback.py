"""Shared finite-difference feedback contracts for Gazebo physical motion."""
from __future__ import annotations

import math

from aero_ai_studio.gazebo.entity_controller import VELOCITY_DIRECTION_EPSILON


BODY_STOPPED_EPSILON = VELOCITY_DIRECTION_EPSILON
QUIESCENCE_CHUNK_ITERATIONS = 100
QUIESCENCE_MAX_CHUNKS = 20
PRE_RESET_QUIESCENCE_CHUNK_ITERATIONS = QUIESCENCE_CHUNK_ITERATIONS
PRE_RESET_QUIESCENCE_MAX_CHUNKS = QUIESCENCE_MAX_CHUNKS


def body_stopped_contract(summary, *, epsilon=BODY_STOPPED_EPSILON):
    """Require fresh/dense world-pose velocities to remain inside the deadband."""
    linear = [float(row['forward_velocity'])
              for row in summary.get('world_forward_velocity_samples', ())]
    angular = [float(row['angular_velocity'])
               for row in summary.get('world_angular_velocity_samples', ())]
    history_ok = bool(summary.get('world_pose_history_available') and
                      summary.get('world_pose_history_fresh') and
                      summary.get('world_pose_history_dense_enough'))
    finite = bool(linear and angular and all(math.isfinite(v) for v in linear + angular))
    max_linear = max((abs(v) for v in linear), default=None)
    max_angular = max((abs(v) for v in angular), default=None)
    linear_stopped = bool(finite and max_linear <= epsilon)
    angular_stopped = bool(finite and max_angular <= epsilon)
    passed = bool(history_ok and finite and linear_stopped and angular_stopped)
    return {
        'history_available': bool(summary.get('world_pose_history_available')),
        'history_fresh': bool(summary.get('world_pose_history_fresh')),
        'history_dense': bool(summary.get('world_pose_history_dense_enough')),
        'history_max_gap': summary.get('world_pose_history_max_gap'),
        'world_body_is_authority': True,
        'odometry_is_supporting_evidence_only': True,
        'velocity_epsilon_mps_and_radps': epsilon,
        'max_abs_forward_velocity': max_linear,
        'max_abs_angular_velocity': max_angular,
        'end_forward_velocity': summary.get('world_end_forward_velocity'),
        'end_angular_velocity': summary.get('world_end_angular_velocity'),
        'linear_stopped': linear_stopped,
        'angular_stopped': angular_stopped,
        'pass': passed,
        'failure_reason': None if passed else ','.join(name for name, ok in (
            ('history_unavailable_stale_or_sparse', history_ok),
            ('velocity_samples_missing_or_nonfinite', finite),
            ('body_forward_velocity_not_stopped', linear_stopped),
            ('body_angular_velocity_not_stopped', angular_stopped)) if not ok),
    }
