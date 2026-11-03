# Harmonic Contact and Collision validation

The user's actual Harmonic 8.15.0 results retain Launch, Sensor, Step, Movement
and Reset PASS. Collision is not host-verified yet; Rule Closed Loop failed
with `Fresh contact stream required; fallback disabled`. This change addresses
that contact path. No Gazebo runtime, Transport Node or socket was run in the
Codex sandbox. ROS2/ros_gz, PX4 and maps were not changed.

## Root causes

1. **Wrong stream model.** Sim 8.15.0 Contact.cc publishes only when
   `contact_size() > 0`, and only updates contacts during non-paused physics
   updates. Empty Contacts heartbeats are not published. The declared
   `always_on=true` / `update_rate=1000` does not turn this system into an
   empty-message heartbeat source. Requiring a fresh Contacts frame on every
   normal step therefore aborted the rule loop before the separate collision
   challenge ran.
2. **Wrong topic setting.** The Contact system reads the nested
   `<sensor><contact><topic>`. The generated robot had only `<sensor><topic>`,
   so metadata pointed at `/aero/<world>/contacts` while the actual publisher
   used the default `/world/<world>/model/simple_agent/link/body/sensor/body_contacts/contact`.
   The user's discovery confirms that mismatch. The nested setting is now
   generated correctly; older scoped topics can also be selected from discovery.
3. **Wrong protobuf field assumption.** `gz.msgs.Contacts.contact` contains
   repeated Contact messages. `collision1` and `collision2` are **Entity**
   messages with names/IDs, not strings. The parser now reads these fields and
   retains both original Entity values. Sim 8.15.0 Physics includes collision
   entity names by default. Missing names are an error, never a silent negative.

The world already includes `gz-sim-contact-system`. The `body_contacts` sensor
is attached to link `body`, references the existing `body_collision`, and has
`always_on=true`, `update_rate=1000`. These are covered by the SDF fixture.
No physics, transport RPC, launch, lidar, movement or reset-pose parameters
were changed.

## A: no-contact semantics and safety limits

`ContactProvider` checks that a publisher advertises `gz.msgs.Contacts` and
that subscription succeeds. Native reception assigns a monotonically
increasing receive sequence and retains queued frames. After each fixed step,
following fresh pose and laser acquisition and verified simulation advancement,
we allow a bounded 50 ms wall-time delivery window and consume new contacts.
A still-present publisher and no new event yields `collision=False`, described
as `no_new_contact_event`, not as proof of stream health or Collision PASS.
There is no required fresh contact timestamp during silence.

This interpretation is valid for the event-only system under the assumptions
of the advertised/connected channel and successful transport delivery. Silence
alone cannot distinguish no contact from packet loss. That limitation is
explicit in telemetry. Full validation therefore requires a positive forced
contact before attempting the rule episode. In addition, commanded movement
which is blocked without contact evidence remains an error: it gets an extra
bounded 500 ms delivery wait, then fails if physical movement is outside the
existing tolerance. Geometric proximity never counts as Collision PASS.
Publisher disappearance, wrong schema, malformed contact names/timestamps,
receive-history overflow or simulation-time rewind fail explicitly.

Each reset creates a new contact epoch with a simulation-time floor and
receive-sequence barrier; prior contact events and collision telemetry are
cleared. A late old packet arriving after reset still has an old simulation
timestamp and is excluded. Within an episode, a late contact from an earlier
step is accepted and stops the episode: it is not discarded merely for missing
a one-step freshness window. Future-dated contacts fail. Receive sequence
prevents replay of the same buffered packet; per-contact timestamp (or envelope
stamp when absent) identifies the physics event. Ground/floor and self contacts
are filtered using exact scope components, not substring matches on agent names.

Contact-channel readiness has its own `contact_channel` result during initialization;
a missing contact publisher does not invalidate already observed world/entity poses.

The no-contact challenge additionally observes three physical forward steps
in a free approach region before impact. That result is independent of B.
It never supplies Collision PASS on its own.

## B: forced contact evidence

`--stage collision` selects the obstacle scenario, observes the obstacle pose,
and drives toward `static_obstacle_2` at `(3.5, 1.5)` from the initial approach
at `(1.5, 1.5)`, yaw zero. The agent has to move using Twist commands and fixed
physics steps. It should touch the obstacle's near face with its body before
its center reaches the obstacle center: the expected agent center is near
x=2.825 (obstacle half-width .45 plus body half-length .225). Demanding its
center reach x=3.5 would demand physical interpenetration.

The old separate challenge targeted the other obstacle at `(7.5,5.5)` by
placing the agent at `(6.5,5.5)`, and it never ran after the rule freshness
failure. It did not test the front obstacle. The new challenge directly tests
the observed front obstacle. For straight scenarios without a front obstacle,
the full stage uses an observed static obstacle and places the agent at a safe
approach distance first; it must still physically approach and contact it.

Collision PASS requires all of:

- three observed no-contact approach steps;
- nonzero physical travel after the approach start and bounded simulation steps;
- a newly received, post-reset Gazebo Contact event;
- agent collision `simple_agent::body::body_collision` and the exact expected
  obstacle model's `body::collision` name, allowing an optional world scope;
- agent pose near the observed target at impact;
- a terminating collision result with source `gazebo_contact`;
- matching raw received Contacts evidence retained by the provider.

No packet, wrong obstacle, stale event, malformed schema, blocked motion with
no contact or a topic advertisement alone cannot pass. `collision.json` records
approach poses/timestamps, A/B results, actual topic, target position, pair names,
receive sequence, epoch and full Contacts messages. The main report preserves
already verified Step/Movement even if the challenge subsequently fails.

Full validation runs this positive challenge **before** the rule loop, resets
the contact epoch, and then runs the rule to the goal. The scripted front-obstacle
avoidance turns left into the open upper region rather than right toward the
near lower boundary. Closed-loop PASS now requires goal completion also for the
obstacle scenario; the old `len(steps)>20` condition was insufficient.

## Host commands

First run the collision diagnostic, preserving earlier host evidence:

```bash
PYTHONPATH=src .venv-ubuntu/bin/python tools/verify_v07_runtime.py \
  --stage collision --obstacle \
  --output validation/v071-host/collision-contact-fix
```

Inspect `runtime_v07.json` and `collision.json`: `no_contact` and
`collision_contact` must PASS, with actual raw messages and the expected pair.
`closed_loop` is `NOT REQUESTED` in this stage. If contact cannot be proven,
retain the error/evidence rather than treating silence as Collision PASS.

After collision passes, verify Rule Closed Loop:

```bash
PYTHONPATH=src .venv-ubuntu/bin/python tools/verify_v07_runtime.py \
  --stage full --obstacle \
  --output validation/v071-host/obstacle-contact-fix
```

This repeats the contact challenge, then resets and requires the rule to reach
the goal. No separate install or ROS command is involved.

## Changed files and offline tests

- `src/aero_ai_studio/gazebo/robot_model.py`: nested Contact topic setting.
- `src/aero_ai_studio/gazebo/contracts.py`: msgs10 Entity parsing and evidence.
- `src/aero_ai_studio/gazebo/contact_provider.py`: event reception and epochs.
- `src/aero_ai_studio/gazebo/transport.py`: topic type readiness and receive
  sequence/history APIs; existing RPC/publish behavior is unchanged.
- `src/aero_ai_studio/gazebo/environment.py`: discovered topic selection,
  event-only collision evaluation and reset barriers/telemetry.
- `tools/verify_v07_runtime.py`: A/B collision stage, evidence, full-stage order
  and goal-completion criterion.
- `tests/test_gazebo_contacts.py`, `tests/test_v06.py`, `tests/test_v07.py`:
  data-only fixture coverage and regression updates.

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=src .venv-ubuntu/bin/python -m pytest -q -m 'not gazebo'
```

Fixtures cover real msgs10 protobuf round-trip parsing, ground/self/reversed
pairs, no-contact silence, publisher loss, late/current/old-reset events, future
time, receive-history loss, native callback sequence assignment, topic type
mismatch, legacy scoped-topic discovery, SDF correctness, positive impact,
wrong obstacle and blocked movement without messages. These fixtures do not
constitute actual Gazebo Collision/Closed Loop PASS.

Official source evidence:

- https://github.com/gazebosim/gz-sim/blob/gz-sim8_8.15.0/src/systems/contact/Contact.cc
  (`Load`, `Publish`, `CreateSensors`, `PostUpdate`).
- https://github.com/gazebosim/gz-sim/blob/gz-sim8_8.15.0/src/systems/physics/Physics.cc
  (`contactsEntityNames`, contact Entity ID/name population).
- https://github.com/gazebosim/gz-msgs/blob/gz-msgs10/proto/gz/msgs/contact.proto
- https://github.com/gazebosim/gz-msgs/blob/gz-msgs10/proto/gz/msgs/contacts.proto
- Installed data-only SDF schema: `/usr/share/sdformat14/1.9/contact.sdf`.

Offline regression result: **91 passed, 3 deselected**. The three excluded
checks are opt-in actual Gazebo integration tests. Collision and Rule Closed
Loop still require the host commands above before any actual PASS claim.
