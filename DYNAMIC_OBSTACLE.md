# V0.7 更新

V0.7 CODE COMPLETE / ACTUAL GAZEBO VALIDATION PENDING

GAZEBO ACTUAL INTEGRATION: NOT VERIFIED

현재 변경 및 실제/fixture 검증 구분은 VALIDATION.md 및 GAZEBO_INTEGRATION.md를 기준으로 합니다. PHYSICS 동적 장애물 및 Geo 확장은 보류. Safety useful/harmful은 중복 가능한 휴리스틱이며 인과 판정이 아닙니다.

# Dynamic prediction, curriculum and randomization

Grid moving identities follow stable object indices. Previous/current world positions estimate velocity over dt=1 simulation step. Relative velocity subtracts agent motion. The closest-approach approximation reports TTC only if closing and predicted miss distance<0.75. Motion classes: APPROACHING/LEAVING/CROSSING/STATIC/UNKNOWN. Predicted positions and TTC are logged in Sensor Observation and Brain Map V4. The old V0.5 relative-motion field remains compatible.

This linear predictor does not foresee random turns or boundary rebounds. In Grid, one step is treated as a1-second prediction interval. In Gazebo the policy dt is0.1s by default, but live moving-object classification/TTC from LiDAR is not implemented: those fields remain unknown. Gazebo moving entities can still be moved and their actual poses recorded as debug data; debug trajectories are not silently passed as sensor detections.

Domain randomization adds seeded goal_position and moving_speed (1 or2 Grid cell substeps). Intermediate dynamic cells are checked for collisions. Goal randomization picks a statically reachable unoccupied cell. Existing obstacle_position/count flags remain. Gazebo implements goal randomization; obstacle size/lighting randomization are not implemented.

Curriculum retains one learning agent across: Easy static → Normal static → Moving1 → Moving3 → Hard. Every configured interval it evaluates a private policy copy with epsilon0 on10 fresh reset seeds. Success≥threshold promotes one stage. Stage/events are checkpointed; exact resume is tested. Static stages currently use a fixed generated map, so promotion evaluates known geometry, not unseen-map generalization.

Measured600-episode training: Compact reaches stage4 after500, DQN V2 reaches stage4 after600. Thus DQN V2 had **no Hard-stage training episodes** in that run. Its Hard success35%(shield OFF) versus direct-Hard5% is a small, single-seed curriculum-regime comparison with different exposure, not isolated causal proof. Compact curriculum Hard success remained0%; no universal improvement is claimed.

Validation Dynamic Easy/Normal/Hard use moving counts1/2/3, preset density5/10/18%, no Danger Zones, randomized obstacle positions, common held-out seeds. They differ from V0.5's earlier combined hard+danger+moving benchmark, so the earlier0% is not a directly comparable baseline.
