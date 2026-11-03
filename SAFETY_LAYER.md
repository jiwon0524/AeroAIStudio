# V0.7 更新

V0.7 CODE COMPLETE / ACTUAL GAZEBO VALIDATION PENDING

GAZEBO ACTUAL INTEGRATION: NOT VERIFIED

현재 변경 및 실제/fixture 검증 구분은 VALIDATION.md 및 GAZEBO_INTEGRATION.md를 기준으로 합니다. PHYSICS 동적 장애물 및 Geo 확장은 보류. Safety useful/harmful은 중복 가능한 휴리스틱이며 인과 판정이 아닙니다.

# Safety Layer V0.6

Optional action shield: proposed action → recorded sensor check → allow/replace/STOP. Default OFF keeps old policies' behavior. UI has separate training and evaluation switches. Shield performance must be reported separately from raw agent performance.

Canonical clearances are in meters. Default critical threshold1.05 assumes a1m kinematic action plus0.05 margin. Grid center distances subtract0.5 obstacle half-cell+0.2 agent radius. Gazebo ray distances subtract0.2 body radius. Change the threshold when changing Gazebo step_size; it is not automatically calibrated.

The shield blocks four directions with insufficient clearance or a tracked object's predicted next cell within0.75 of the candidate destination. It uses the SENSOR Observation, not the privileged debug snapshot. Among allowed candidates it prefers recorded Q score then clearance. If none remain, it returns STOP. STOP cannot prevent another moving object from hitting the agent.

Logs contain proposed_action, final_action, safety.override/reason/blocked_actions, safety_observation and override counts. Q/DQN score outputs stay unchanged. Learning is on the **proposed action and shielded transition**: this models the composite agent+shield environment. It is not proof that an unshielded policy learned to avoid that action. Evaluation weights are never updated.

Safety is not a formal guarantee: cardinal rays miss diagonal obstacles, velocity estimates ignore acceleration/bounce, localization and Gazebo collision logic are approximate. Intervention can convert collisions into loops/timeouts and reduce throughput. Current Dynamic Hard paired test with a frozen V0.5 DQN: success25→45%, collision75→20%, timeout0→35%,551 interventions over20 episodes. Small single-seed results are descriptive. Residual collisions remain.
