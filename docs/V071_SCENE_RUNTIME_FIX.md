# V0.7.1 host scene service investigation

Follow-up: see [set_pose host fix](V071_SET_POSE_FIX.md) for the subsequent
RPC backend/readiness and initialization changes. Native request details below
describe the original implementation.

Scope: native Gazebo Harmonic 8.15.0 Step and Physics Movement validation.
No Gazebo server or Transport Node was started in the sandbox. ROS2 / ros_gz,
PX4 and map features are outside this change.

## Findings

- Exact service entry point: `GazeboEntityController.scene()` in
  `src/aero_ai_studio/gazebo/entity_controller.py`.
- Before this change, `get_pose()` called `scene()`; `_connect()` called
  `spawn_agent()` → `get_pose()` before the first step; `_refresh()` called
  `get_pose()` and then another `scene()`; the verifier called `scene()` again
  for entity existence. Thus a full scene query gated startup and every step.
- Request: `gz.msgs.Empty`, empty payload `{}`. Response: `gz.msgs.Scene`.
- Native Python: `HarmonicTransport.request()` builds messages from
  `gz.msgs10.*_pb2` and calls
  `node.request(service, message, request_class, response_class, timeout_ms)`.
  It does not use `gz service`. CLI discovery uses `gz topic -l` and
  `gz service -l` in the server's partition.
- Transport default timeout is 5 seconds. `GazeboEnvironment` passes its
  default 10 seconds, so this verifier's scene requests used 10000 ms.
- Schema is consistent with Harmonic: its response-only C++ scene callback
  returns `msgs::Scene` (Transport represents the absent request with Empty).
  The Python Transport 13 wrapper takes the same five arguments used here.
  There is no evidence of a schema mismatch in the supplied report.
- Discovery proves advertisement, not successful callback completion. Startup
  readiness or transient response failure remains possible, but cannot be
  established from the recorded discovery and error alone. The previous
  startup retry also did not protect subsequent per-step scene calls.
- The checked-in `validation/v071-host/straight/runtime_v07.json` currently
  records `Fresh contact stream required; fallback disabled`, rather than the
  scene timeout reported in the user message. Both failures can hide Step and
  Movement results in the old verifier. The supplied JSON is preserved.

## Changes and readiness

The simulation path now subscribes to `/world/<world>/pose/info` as
`gz.msgs.Pose_V`. It reads a frame at the current fixed-step simulation time
(with the existing 2 ms tolerance) and requires the agent in that frame.
It uses the same frame for actual-world model positions and entity checks.
Static obstacle and goal presence is observed from Gazebo, not inferred from
SDF metadata. Metadata supplies only the expected names. The complete pose
frame replaces the previous frame; stale/missing agents fail explicitly.
The optional `scene()` API remains available, but startup/reset/step/runtime
validation no longer call it.

Subscriptions precede the first fixed step; entity readiness is checked after
that step. The native velocity publisher waits for `has_connections()` within
the existing timeout before publishing. There is no timeout increase or blind
service retry/backoff. In particular `multi_step` is not retried because a lost
response could cause duplicate simulation advancement. Stream readiness uses
the transport's existing bounded sample wait.

`--stage movement` executes five forward actions, validates actual pose deltas
against commanded speed, and reports simulation-time advancement separately.
Contact freshness is not required for this limited stage; contact and closed
loop are explicitly `NOT REQUESTED`, never PASS. Default `--stage full` retains
strict contact requirements. Independent Step/Movement evidence is preserved
if a later contact or closed-loop check fails. Reports include stepping, pose
validation and actual-world evidence under `progress`.

## References

- Exact Sim 8.15.0 implementation: https://github.com/gazebosim/gz-sim/blob/gz-sim8_8.15.0/src/systems/scene_broadcaster/SceneBroadcaster.cc
  (`SceneInfoService`, `SetupTransport`, `PoseUpdate`).
- Transport 13 Python API: https://gazebosim.org/api/transport/13/python.html
- Locally inspected wrapper: `/usr/lib/python3/dist-packages/gz/transport13/__init__.py`.

## Host commands

First verify the requested Step → Physics Movement stage, using a fresh output
folder so the earlier evidence remains intact:

```bash
PYTHONPATH=src .venv-ubuntu/bin/python tools/verify_v07_runtime.py \
  --stage movement --output validation/v071-host/straight-movement-fix
```

This is a limited-stage result, not proof of full runtime validation. Once it
passes, the full strict run is:

```bash
PYTHONPATH=src .venv-ubuntu/bin/python tools/verify_v07_runtime.py \
  --stage full --output validation/v071-host/straight-full-fix
```

Offline regression command (no actual Gazebo integration):

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=src .venv-ubuntu/bin/python -m pytest -q -m 'not gazebo'
```
