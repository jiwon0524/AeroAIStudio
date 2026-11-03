from __future__ import annotations


def trajectory(episode: dict) -> dict:
    steps=episode.get('steps',[])
    if not steps:return {'points':[],'goal':None,'obstacles':[],'collision_point':None}
    def point(step: dict,next_state=False):
        pose=step.get('next_pose' if next_state else 'pose')
        if pose:return [pose['x']-.5,pose['y']-.5]
        return step['new_state' if next_state else 'state']
    points=[point(s) for s in steps]+[point(steps[-1],True)]
    return {'points':points,'goal':steps[-1]['goal'],'obstacles':steps[0]['obstacles'],
            'collision_point':points[-1] if 'collision' in episode.get('reason','') else None,
            'width':steps[0]['width'],'height':steps[0]['height']}
