from dataclasses import asdict, dataclass
from aero_ai_studio.observation.canonical import CanonicalSensorObservation

RAYS={'up':'front','down':'back','left':'left','right':'right','forward':'front','backward':'back'}


@dataclass(frozen=True)
class SafetyDecision:
    proposed_action: str
    final_action: str
    override: bool
    reason: str
    blocked_actions: tuple[str,...]=()
    useful_override_heuristic: bool=False
    harmful_override_heuristic: bool=False

    def to_dict(self):return asdict(self)


class SafetyLayer:
    def __init__(self, enabled: bool=False, critical_threshold: float=1.05):
        if critical_threshold<0:raise ValueError('Negative safety threshold')
        self.enabled,self.threshold=enabled,critical_threshold

    def check(self, proposed: str, observation, scores: dict) -> SafetyDecision:
        if not self.enabled:return SafetyDecision(proposed,proposed,False,'Disabled')
        c=CanonicalSensorObservation.from_observation(observation)
        blocked={a for a in ('up','down','left','right') if getattr(c,RAYS[a]+'_clearance')<self.threshold}
        # Prediction comes only from the recorded sensor input, not a privileged world snapshot.
        prediction=observation.sensor_state.get('prediction',{})
        x,y=observation.agent_position
        for a,(dx,dy) in {'up':(0,-1),'down':(0,1),'left':(-1,0),'right':(1,0)}.items():
            if any(abs(item['predicted_position'][0]-(x+dx))<.75 and abs(item['predicted_position'][1]-(y+dy))<.75
                   for item in prediction.get('objects',[])):
                blocked.add(a)
        normalized={'forward':'up','backward':'down'}.get(proposed,proposed)
        if normalized not in blocked:return SafetyDecision(proposed,proposed,False,'Allowed',tuple(sorted(blocked)))
        allowed=[a for a in ('up','down','left','right') if a not in blocked]
        replacement=max(allowed,key=lambda a:(scores.get(a,float('-inf')),getattr(c,RAYS[a]+'_clearance'))) if allowed else 'stop'
        static_blocked=getattr(c,RAYS[normalized]+'_clearance')<self.threshold
        return SafetyDecision(proposed,replacement,True,'Clearance/predicted motion blocks proposed direction',tuple(sorted(blocked)),
                              useful_override_heuristic=static_blocked,
                              harmful_override_heuristic=replacement=='stop' or not static_blocked)
