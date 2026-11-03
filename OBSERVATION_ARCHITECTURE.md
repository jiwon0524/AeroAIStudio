# V0.7 更新

V0.7 CODE COMPLETE / ACTUAL GAZEBO VALIDATION PENDING

GAZEBO ACTUAL INTEGRATION: NOT VERIFIED

현재 변경 및 실제/fixture 검증 구분은 VALIDATION.md 및 GAZEBO_INTEGRATION.md를 기준으로 합니다. PHYSICS 동적 장애물 및 Geo 확장은 보류. Safety useful/harmful은 중복 가능한 휴리스틱이며 인과 판정이 아닙니다.

# Observation System V2

`observation/models.py` defines immutable Observation data, modes and Cell codes. `provider.observe()` converts a simulator snapshot into a **policy observation**. `get_state()` remains a privileged debug/replay snapshot. Trainer/Evaluator log the exact pre-action Observation and encoded input separately from that snapshot.

## Modes and compatibility

| Mode | Contents | Policy use |
|---|---|---|
| BASIC | agent_position, goal_position | Legacy Q encoder uses only (x,y), preserving old Q-table keys |
| LOCAL | Basic positions + 3×3/5×5/7×7 local cells | Compact Q or fixed DQN vector |
| SENSOR | Basic positions + idealized range/proximity/goal/motion features | Compact Q or DQN vector |
| FULL_DEBUG | Local + sensor + full grid | Debug only; TrainingConfig rejects it as a policy mode |

Legacy `extended` Scenario metadata is accepted and maps to SENSOR when requested. ScenarioSpec stays schema_version `0.4` because the additions are compatible; Observation payload version is `0.5`. Old logs without Observation are displayed as **not recorded**, never reconstructed and presented as the original policy input. Old Q-table/checkpoint files default to BASIC.

Cell codes: EMPTY=0, WALL=1, STATIC_OBSTACLE=2, MOVING_OBSTACLE=3, GOAL=4, DANGER=5, SLOW_ZONE=6, AGENT=7. Off-grid cells are WALL. LOCAL does not carry a full grid or global sensor dictionary.

## Idealized Grid sensors

- front/back/left/right are world-aligned north/south/west/east; the agent has no heading. Distances count cells to the first static/dynamic/danger cell or boundary, with adjacent blocked=1.
- Goal distance is Euclidean; direction is one of N/NE/E/SE/S/SW/W/NW/HERE. Goal delta is also available.
- Nearest obstacle and moving object report Euclidean distance and octant. The proximity sensor is idealized and not occlusion-aware. It is not a physical LiDAR simulation.
- Relative motion compares the same indexed object's distance to the old and current agent pose. It includes both agent and object movement. Reset gives UNKNOWN; decreasing/increasing/equal distance gives APPROACHING/LEAVING/STATIC. Objects do not change identity during a GridWorld episode.
- `danger_zone` means a danger cell within Manhattan radius1, not an estimate of future risk.

## Compact encoder

Tuple: `(goal_octant, front_bucket, left_bucket, right_bucket, back_bucket, moving_near, danger_near)`. Range buckets: BLOCKED≤1, NEAR≤3, CLEAR>3. Moving-near≤3 cells. LOCAL derives these features from its visible window only and treats no visible blocker as CLEAR; obstacles beyond the window remain unknown.

The nominal bounded feature combinations are at most 9×3⁴×2×2=2,916, rather than enumerating every 5×5 grid. Absolute position and full obstacle lists are not encoded. Partial observability remains: different maps, detour progress and obstacle velocities can alias into one state. Loop/Timeout are still possible.

## DQN input

Fixed22 floats: goal one-hot9, four bucket values4, moving/danger flags2, normalized cardinal ranges4, goal distance1, moving distance1, relative motion scalar1. Ranges clip at10 cells, goal distance at30. LOCAL lacks global ranges so those slots use defaults; local buckets still carry visible geometry. No shortest path, optimal action, collision mask or debug grid is fed to the network. The raw Observation contains positions, but the DQN vector does not contain absolute agent coordinates.

`state_encoder` config applies to tabular Q only; DQN always uses `sensor_vector_v1`. FULL_DEBUG is never passed as a training observation. The Brain Map may show debug geometry/risk alongside policy evidence and labels that distinction.

## Synchronization

One episode step owns environment before/after snapshots, Observation before/after, actual scores, chosen action, decision type and result. Replay.seek drives Grid, Brain Map, Observation Debug and Timeline together. The Observation Debug panel shows actual full environment on the left and recorded policy data plus encoded features on the right. Training live Grid shows result state while its Observation text explicitly labels pre-action data.

## V0.6 additions

CanonicalSensorObservation unifies meter clearances, goal, source/units, moving motion/TTC and collision_imminent. Grid center ranges subtract0.7; actual Gazebo laser body clearances subtract0.2 and compatibility distances add0.7. ContinuousDistanceDiscretizer provides VERY_NEAR/NEAR/MEDIUM/FAR/CLEAR and LOW/MEDIUM/HIGH risk. The optional canonical Q encoder is actually connected through factory/UI/metadata; legacy compact/basic remain unchanged. Grid prediction adds per-object velocity/predicted_position and TTC. Gazebo moving tracks remain unknown, not inferred from debug entities. See SAFETY_LAYER/REWARD_SYSTEM/DYNAMIC_OBSTACLE for conventions.
