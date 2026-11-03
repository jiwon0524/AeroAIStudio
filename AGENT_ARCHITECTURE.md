# V0.7 更新

V0.7 CODE COMPLETE / ACTUAL GAZEBO VALIDATION PENDING

GAZEBO ACTUAL INTEGRATION: NOT VERIFIED

현재 변경 및 실제/fixture 검증 구분은 VALIDATION.md 및 GAZEBO_INTEGRATION.md를 기준으로 합니다. PHYSICS 동적 장애물 및 Geo 확장은 보류. Safety useful/harmful은 중복 가능한 휴리스틱이며 인과 판정이 아닙니다.

# Agent interface and persistence

`agents/base.py` defines Agent with reset, select_action, learn, save/load, get_decision_info, get_metadata and capability flags. A Transition holds current Observation, action, reward, next Observation and done. Trainer and Evaluator use this interface; algorithm construction/loading lives in `agents/factory.py`. Algorithm checks are confined to factory/UI/persistence, not the step loop.

QLearningAgent keeps scores/choose/update and the old `(x,y)` JSON keys for compatibility. Compact keys use stable JSON tuple encoding. `reset()` clears the last decision, not learned values or RNG. Both terminal and truncated episodes stop bootstrap, preserving V0.4 semantics.

DQNAgent uses optional CPU PyTorch: Linear22→128→ReLU→128→ReLU→4. It has a bounded uniform ReplayBuffer, Adam, Huber loss, gradient norm clip10, one batch update per4 transitions, and a hard target sync every configured number of environment transitions. Epsilon-greedy uses a private Python RNG; greedy ties are sampled among maximal Q-values. No action masking or scripted navigation policy is added.

Supports: training=True, sensors=True, images=False, continuous actions=False. DQN's decision info contains actual pre-update network output Q-values and the input vector. Hidden activations are not described as thoughts or reasoning.

## Checkpoint / Registry

- Q-table save files add agent_metadata while old files continue to load.
- DQN `model.pt` contains online/target weights, optimizer, ReplayBuffer, RNG, learn step, last loss and input schema metadata. `torch.load(weights_only=True, map_location='cpu')` is used for supported data. Only load models from trusted local sources.
- PT saves are staged, fsync'ed, loaded for validation, then atomically replaced. Checkpoint commits stage the PT file and JSON metadata together before directory rename. Old tabular checkpoints remain supported.
- DQN resume restores all learning state; tests compare resumed parameters and metrics against an uninterrupted run exactly on CPU.
- Registry versions, parent references, notes and evaluation links work for both algorithms. Model size includes optimizer/buffer state and metadata, not just inference weights.
- Evaluation loads a private agent and never calls learn. Source model weights remain byte-for-byte unchanged. It enforces non-overlapping training/evaluation reset seed ranges when provenance is available. Legacy models without recoverable provenance cannot be checked retroactively.
- Basic Python export remains standalone. Compact/DQN Python exports use the installed package's matching Observation encoder; DQN export also requires PyTorch. ONNX/ROS2/PX4 export remain placeholders.

## Generalization

GeneralizationEvaluator first evaluates the training **scenario distribution** with fresh seeds, then an unseen scenario with another disjoint seed range. Options randomize obstacle locations, add moving obstacles and/or generate a different difficulty. It reports reference success, unseen success and their signed gap. Neither reference evaluation nor unseen evaluation reuses training reset seeds. A negative gap is possible; the reference is not a retained training rollout score.

Current limitations: no recurrent policy, double/dueling DQN, prioritized replay, GPU training UI or uncertainty calibration. Sensor-nearest-motion features exist in Observation; compact Q only uses the moving-near flag. DQN uses relative motion but no continuous control. Run comparisons with different episode budgets are descriptive rather than controlled algorithm rankings.

## V0.6 additions

Optional Double DQN uses online argmax with target value, with a numerical test distinguishing5.5 from vanilla max-target91. Replay warm-up and optional clipped learning rewards are checkpointed. Existing defaults preserve vanilla DQN. Safety is external to Agent and logs both proposed/final actions; learning uses proposed action in the shielded transition. Curriculum keeps the same agent across stages and persists stage/events, without updating original weights during promotion evaluation. Native Gazebo factory now implements the same step loop; actual Ubuntu execution is NOT VERIFIED. Current model save/metadata/export preserve these options. The earlier no-Double-DQN limitation above is historical V0.5 text, superseded by this section.
