# Collision approach direction correction

The host has demonstrated real contact transport and parsing. The supplied
`validation/v071-host/collision-contact-fix/collision.json` must remain FAIL:
its contact pair contains boundary_2 rather than static_obstacle_2. It is
preserved unchanged. No Gazebo runtime was executed for this correction.

## Observed path and root cause

The reset pose was (1.5,1.5), yaw approximately zero, with quaternion w=1.
The target was observed at (3.5,1.5); its world bearing is atan2(0,2)=0.
The first forward step reached x=1.4736137108864806, then x=1.4236134061955756.
The final pose was (0.2996652254181247,1.5), yaw approximately 7.7e-14.
The target distance increased from 2.0 to 3.2003347745818753 m.
Boundary_2 is the left boundary, centered at x=0 with a near face at x=.075.
The agent's body half-length is .225; its center near x=.300 at impact is
consistent with that boundary contact. This is actual world -X motion at yaw
zero, not a yaw/quaternion sign error or avoidance-policy action.

The generated wheels have roll=+pi/2, while their joints used an unqualified
local xyz=(0,0,1). SDF joint poses default to the child link frame; axes default
to the joint frame. That local +Z resolves to **model -Y** after the wheel roll.
DiffDrive uses positive wheel rates for positive Twist.linear.x. With reversed
axles, positive rates roll the robot backward. Both joints now explicitly use
`<xyz expressed_in="__model__">0 1 0</xyz>`. The wheel geometry and poses are
unchanged. The installed data-only SDFormat parser resolves the original axes
to (0,-1,0) and the corrected axes to (0,1,0).

The DiffDrive formulas remain `(linear - angular*separation/2)/radius` for the
left wheel and `(linear + angular*separation/2)/radius` for the right. With +Y
axles these give body +X travel for positive linear.x and CCW world yaw for
positive angular.z. Controller command signs are not inverted to compensate.

Quaternion-to-yaw remains atan2(2*(w*z+x*y),1-2*(y*y+z*z)), the correct +Z CCW
convention. Reset yaw and observed yaw agree. The old challenge did not calculate
bearing or align; it simply sent `up`. Its `physical_travel` was the nonnegative
start/end Euclidean displacement, so it could not distinguish approaching the
target from moving away. Its target-distance formula was correct and actually
recorded the growing distance, but it was checked only at impact.

## Deterministic challenge

The collision stage uses no RuleAgent or obstacle-avoidance action. It:

1. Resets and reads actual agent/target poses, choosing static_obstacle_2 when
   present. A distant target in the straight scenario still permits the existing
   safe approach placement; the front-obstacle scenario starts at (1.5,1.5).
2. Calculates world bearing atan2(target_y-y,target_x-x) and wrapped yaw error
   atan2(sin(bearing-yaw),cos(bearing-yaw)). Positive error commands left with
   positive angular.z; negative error commands right.
3. Rotates with zero linear command to measured yaw alignment. It verifies the
   signed observed rotation, and checks the tolerance before linear approach.
   The initial alignment tolerance is .041 rad (just over half a discrete .08
   rad turn); the approach tolerance is .09 rad. If drift exceeds the approach
   tolerance it realigns toward the same target, never away from it.
4. Advances with positive linear.x. Each physics step records action, actual
   command, before/after position/quaternion/yaw, signed yaw delta, target bearing,
   yaw error, distance before/after, distance decrease and projections of actual
   displacement onto the body-forward and target directions. Failed steps are
   recorded in a finally block too.
5. Fails immediately on reversed progress, non-decreasing free-approach distance,
   wrong rotation or unexpected boundary/obstacle contact, retaining trajectory
   and original contact evidence. It never re-labels a boundary contact as PASS.
6. Requires the previously established real Gazebo event, exact agent/target
   collision names, raw received message and physically decreasing target
   distance before impact. The final contact step may have zero displacement
   because the obstacle blocks motion; prior progress must exceed .1 m.

`physical_travel` is now cumulative measured path length; `net_displacement`
is the start/end Euclidean displacement, and `approach_travel` excludes alignment
steps. `target_distance_reduction` independently proves approach toward the
chosen target. Existing speed/rotation magnitude validation now also checks
signed body-forward displacement and signed yaw change. This prevents backward
or opposite-turn motion from being accepted solely because its magnitude fits.
Contact can still block or rebound motion under the existing collision exception.

ContactProvider, contact topics, parser, transport delivery, reset service schema,
ROS2/ros_gz, maps and PX4 are unchanged. Collision remains host-unverified for
the required target pair; Closed Loop is deferred until Collision passes.

## Files and tests

Changed: `robot_model.py`, `physics_controller.py`, `tools/verify_v07_runtime.py`,
`tests/test_gazebo_contacts.py`, `tests/test_v07.py`, and this document.

Tests cover SDF semantic resolution of old/new wheel axes, positive drive and
CCW wheel-rate kinematics, quaternion/yaw round trips including wraparound,
signed forward/rotation validation, target bearing/error, actual recorded
fixture approach in both initial yaw directions, one-step reverse-motion
rejection, opposite-turn rejection, and rejection of both wrong obstacles and
boundary_2. The collision fixture rejects any call to the avoidance policy.
All tests construct no Transport Node or Gazebo server.

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=src .venv-ubuntu/bin/python -m pytest -q -m 'not gazebo'
```

Offline regression: **103 passed, 3 deselected** (actual Gazebo integration excluded).

## Next host command only

```bash
PYTHONPATH=src .venv-ubuntu/bin/python tools/verify_v07_runtime.py \
  --stage collision --obstacle \
  --output validation/v071-host/collision-direction-fix
```

Inspect `collision.json`: target static_obstacle_2, decreasing target distance,
world +X approach, and an actual agent/static_obstacle_2 contact pair are required.
The stage explicitly leaves closed_loop NOT REQUESTED.

References:

- https://github.com/gazebosim/sdformat/blob/sdf14/sdf/1.9/joint.sdf
- https://github.com/gazebosim/gz-sim/blob/gz-sim8_8.15.0/src/systems/diff_drive/DiffDrive.cc
- Host collision.json and world.sdf under validation/v071-host/collision-contact-fix.
