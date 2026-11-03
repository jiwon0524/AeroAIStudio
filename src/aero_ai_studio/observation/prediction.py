from __future__ import annotations
import math


def predict_motion(agent: tuple, objects: list[tuple], previous: dict | None, dt: float = 1.) -> dict:
    if dt<=0:raise ValueError('dt must be positive')
    if not objects:return {'objects':[], 'motion':'UNKNOWN','ttc':None}
    records=[]
    for i,p in enumerate(objects):
        velocity=(0.,0.)
        motion='UNKNOWN'
        ttc=None
        if previous and i<len(previous.get('dynamic_objects',[])):
            old=previous['dynamic_objects'][i]['position']
            velocity=((p[0]-old[0])/dt,(p[1]-old[1])/dt)
            av=((agent[0]-previous['agent'][0])/dt,(agent[1]-previous['agent'][1])/dt)
            rv=(velocity[0]-av[0],velocity[1]-av[1])
            r=(p[0]-agent[0],p[1]-agent[1])
            speed2=rv[0]**2+rv[1]**2
            dot=r[0]*rv[0]+r[1]*rv[1]
            closest=max(0.,-dot/speed2) if speed2 else 0.
            miss=math.hypot(r[0]+closest*rv[0],r[1]+closest*rv[1])
            if speed2 and dot<0 and miss<.75:ttc=closest
            tangential=abs(r[0]*rv[1]-r[1]*rv[0])
            motion='STATIC' if speed2<1e-9 else 'CROSSING' if tangential>abs(dot) else 'APPROACHING' if dot<0 else 'LEAVING'
        records.append({'position':list(p),'velocity':list(velocity),
                        'predicted_position':[p[0]+velocity[0]*dt,p[1]+velocity[1]*dt],
                        'motion':motion,'ttc':ttc})
    nearest=min(records,key=lambda r:math.dist(agent,r['position']))
    return {'objects':records,'motion':nearest['motion'],'ttc':nearest['ttc']}
