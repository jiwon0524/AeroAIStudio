from __future__ import annotations


def reward_components(before: dict, after: dict, reason: str, *, version: str='legacy',
                      previous_action: str | None=None, action: str | None=None, clearance: float=10., ttc: float | None=None) -> dict[str,float]:
    collision='collision' in reason
    goal=reason=='goal'
    danger=reason=='danger_zone'
    old=sum(abs(a-b) for a,b in zip(before['agent'],before['goal']))
    new=sum(abs(a-b) for a,b in zip(after['agent'],after['goal']))
    result={'goal':100. if goal else 0.,'collision':-100. if collision else 0.,'danger':-50. if danger else 0.,
            'progress':0.,'time':0.,'smooth':0.,'near_obstacle':0.,'moving_risk':0.,'slow':0.}
    if not (collision or goal or danger):
        result.update(progress=2. if new<old else 0.,time=-1.,slow=-3. if after['agent'] in after.get('slow_zones',[]) else 0.)
        if version=='v2':
            result.update(progress=2.*(old-new),time=-.1,
                          smooth=.05 if previous_action==action else 0.,
                          near_obstacle=-.3*max(0.,1.-clearance),
                          moving_risk=-.5 if ttc is not None and ttc<2 else 0.)
    return result
