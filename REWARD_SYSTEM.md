# Reward System V2

`training/rewards.py` produces named components; environment metrics and episode steps store the exact breakdown. Total reward is always their sum.

Legacy remains the default: Goal+100, collision−100, danger−50, otherwise time−1 plus progress+2 when Manhattan distance decreases, and Slow−3. The existing Basic regression remains100% evaluation success/38steps.

Optional V2: terminal values remain unchanged. Nonterminal progress=2×(previous Manhattan distance−current distance), time−0.1, repeated same action+0.05, near-obstacle cost−0.3×max(0,1−clearance), and moving-risk−0.5 for estimated TTC<2. Slow remains−3. Terminal steps do not add progress/time/risk/smooth components.

Grid calculates TTC from measured previous/current moving positions. Gazebo currently uses real ray clearance and pose-derived progress but does not identify moving object tracks from the four-ray scan, so its moving TTC reward is absent. It must not invent moving-object labels from LiDAR ranges.

V2's smooth reward and partial observations can still encourage loops; lower collision count does not imply task completion. Compare success, timeout, minimum clearance and interventions as well as reward. Legacy and V2 raw totals are not directly comparable. DQN's optional reward clipping applies only to replay-buffer learning targets; recorded environment rewards/components remain unclipped.
