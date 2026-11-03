# Harmonic set_pose host failure

The supplied `validation/v071-host/straight-movement-fix/runtime_v07.json`
records a timeout on `/world/aero_d8380d88d44c/set_pose`, before Step or
Movement evidence. This is not an installation diagnosis. No Gazebo server,
Transport Node, discovery or service call was executed in the sandbox.

## Request audit

`GazeboEntityController.reset_agent_pose()` in `entity_controller.py` sends
`Pose` → `Boolean` through `HarmonicTransport.request()`. Its classes are
`gz.msgs10.pose_pb2.Pose` (`gz.msgs.Pose`) and
`gz.msgs10.boolean_pb2.Boolean` (`gz.msgs.Boolean`). The agent name comes from
generated metadata, `simple_agent` for PHYSICS. For this scenario the single
reset request is now:

```text
name: "simple_agent"
position { x: 1.5 y: 1.5 z: 0.16 }
orientation { x: 0 y: 0 z: 0 w: 1 }
```

Coordinates/yaw must be finite; orientation is a unit quaternion computed
from yaw. Previously PHYSICS reset unnecessarily sent two poses, first z=.25
and then z=.16. These were valid messages but duplicated initialization work.

The schema matches the exact Sim 8.15.0 `UserCommands.cc` implementation.
`/set_pose` enqueues a command and returns `Boolean.data=true`; that proves
acceptance, not application. The command is applied in a later PreUpdate.
The application is verified after fixed stepping from an observed pose.
`/set_pose/blocking` has different completion semantics and is not substituted.

## Failure mechanism and limits of evidence

Previously `_connect()` waited for CLI world/control and sensor-topic discovery,
then subscribed to pose/stats/sensors. Reset immediately paused and called
set_pose twice with no per-service type/readiness check. `world_loaded` was
marked PASS only after all of reset, stepping and sensor acquisition completed.
Consequently a reset RPC timeout incorrectly appeared as a world loading failure.

The original service RPC used synchronous `node.request(...)` in the same Python
process as subscriptions. Upstream Transport 13's `request_raw` binding calls
`RequestRaw` while retaining the GIL; its `subscribe_raw` callback explicitly
acquires the GIL. A pending callback can therefore block transport receive
processing while a synchronous RPC waits. This is a source-supported failure
path consistent with intermittent service timeouts after subscriptions start;
it is not a confirmed trace of this specific host failure. Service startup
readiness/connection races are also possible. The old report contains neither
advertised service types nor a serialized request, so it cannot distinguish
these causes. Merely extending the timeout does not resolve these paths.

## Changes

- Service RPC uses an explicitly selected `gz service` child process. The
  parent keeps native Python subscriptions and velocity publishers. The child
  inherits the exact partition captured from the parent Node, avoiding GIL
  contention between the parent's callbacks and synchronous service responses.
  There is no silent backend fallback. This applies to control RPC too, since
  it has the same binding behavior. Each call has process startup overhead;
  this change prioritizes runtime correctness over wall-clock throughput.
- Before RPC, the native Node's service discovery is polled with bounded
  .05/.1/.2 second backoff until the requested protobuf types are advertised.
  A schema mismatch fails immediately without sending a request. Advertisement
  alone is not claimed to prove a responsive handler.
- Only absolute `/set_pose` requests retry on transport timeout: at most three
  attempts, at most 2 seconds service response wait each, with .1/.2 second
  backoff. Readiness, subprocess wall time and backoff all share the original
  10 second environment timeout. There is no timeout increase. Identical
  absolute poses are used on retry; callers must not advance physics between
  these retries. Multi-step/control/create/publish are not automatically retried.
  Boolean false, CLI errors, schema errors and malformed responses do not retry.
- Protobuf text serializes the actual request using its canonical descriptors;
  response text is parsed as the actual response protobuf. Boolean false is an
  error. Reports retain schema, payload, backend, attempt timeout, exit code,
  stdout/stderr and decoded response.
- `GazeboEnvironment.prepare()` observes the world and entity pose without
  mutating/resetting the world or advancing physics. The verifier records world,
  entities and pose before reset. Sensor discovery and receipt remain separate.
- PHYSICS reset stops the command, sends one pose at z=.16, steps, then verifies
  the observed reset position. The report separates `initialization`,
  `set_pose` (acceptance), `reset_applied` and Step/Movement. A failing reset
  does not erase world-loaded evidence. Initialization phase is also recorded.

Changed code: `transport.py`, `entity_controller.py`, `environment.py`,
`tools/verify_v07_runtime.py`, and new `tools/diagnose_set_pose.py`.
Tests: new `tests/test_gazebo_service_rpc.py` and updated `tests/test_v07.py`.
ROS2/ros_gz, PX4 and maps were not changed.

## Small host diagnosis

Run from the repository root. Use the existing generated world and a dedicated
partition so commands cannot reach another running world. The world starts
paused: do not add `-r`. Keep terminal 1 open.

Terminal 1:

```bash
export GZ_PARTITION=aero_set_pose_diag
gz sim -s --headless-rendering -v 4 \
  validation/v071-host/straight-movement-fix/worlds/aero_d8380d88d44c/world.sdf
```

Terminal 2, first inspect the advertised schema (repeat this read-only command
if startup is still in progress):

```bash
export GZ_PARTITION=aero_set_pose_diag
gz service -i -s /world/aero_d8380d88d44c/set_pose
```

Expected provider types: `gz.msgs.Pose`, `gz.msgs.Boolean`. Then send exactly
one direct request:

```bash
gz service -s /world/aero_d8380d88d44c/set_pose \
  --reqtype gz.msgs.Pose --reptype gz.msgs.Boolean --timeout 2000 \
  --req 'name: "simple_agent", position: {x: 1.5, y: 1.5, z: 0.16}, orientation: {x: 0, y: 0, z: 0, w: 1}'
```

Expected response: `data: true`. This proves service acceptance, not Step or
Movement. A direct call with no response does not pass even if the CLI exits 0.

Alternatively, **instead of that direct request**, use the new one-request
probe to save the same schema/request/response evidence (no auto-retry, no step,
no sensor subscription):

```bash
PYTHONPATH=src .venv-ubuntu/bin/python tools/diagnose_set_pose.py \
  --world aero_d8380d88d44c --partition aero_set_pose_diag \
  --output validation/v071-host/set-pose-once.json
```

If this fails, retain its JSON or the CLI's complete stdout/stderr and stop
there. Stop terminal 1 with Ctrl-C after diagnosis.

After acceptance passes, run the movement stage with fresh evidence:

```bash
PYTHONPATH=src .venv-ubuntu/bin/python tools/verify_v07_runtime.py \
  --stage movement --output validation/v071-host/straight-set-pose-fix
```

Check `set_pose`, `reset_applied`, `step_progress`, `physics_motion`. Contact
and closed-loop remain `NOT REQUESTED` for this limited stage.

## Offline regression

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=src .venv-ubuntu/bin/python -m pytest -q -m 'not gazebo'
```

The adapter fixtures construct no native Node: they use real protobuf classes
with mocked subprocess/discovery results. Coverage includes delayed discovery,
wrong advertised schema, exact wire types/name/pose/partition, Boolean false,
malformed/failed CLI output, bounded identical-pose retries and total budget,
non-retried multi_step, single PHYSICS reset, read-only world preparation,
independent world-loaded evidence after reset failure, and the one-call probe.

Sources:

- https://github.com/gazebosim/gz-sim/blob/gz-sim8_8.15.0/src/systems/user_commands/UserCommands.cc
- https://github.com/gazebosim/gz-transport/blob/gz-transport13/python/src/transport/_gz_transport_pybind11.cc
- https://gazebosim.org/api/transport/13/python.html
- Local data-only inspection: `/usr/lib/python3/dist-packages/gz/transport13/__init__.py`,
  `/usr/share/gz/gz-sim8/worlds/shapes.sdf` and CLI completion flags.

Offline result: **80 passed, 3 deselected** (Gazebo integration excluded).
Actual set_pose / Step / Movement remain host-unverified.
