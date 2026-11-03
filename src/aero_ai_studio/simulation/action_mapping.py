"""Versioned, shared discrete-action contracts for simulation backends."""
from aero_ai_studio.simulation.base import ACTIONS

PHYSICS_ACTION_SIGNS={
    'up':(1,0),'down':(-1,0),'left':(0,1),'right':(0,-1),
}


def grid_world_action_mapping():
    """Index semantics used by GridWorld; deliberately distinct from PHYSICS Twist."""
    deltas=((0,-1),(0,1),(-1,0),(1,0))
    return [{'index':index,'action':name,'grid_delta':list(deltas[index])}
            for index,name in enumerate(ACTIONS)]


def gazebo_physics_action_mapping(linear_speed=.5,angular_speed=.8):
    result=[]
    for index,name in enumerate(ACTIONS):
        linear_sign,angular_sign=PHYSICS_ACTION_SIGNS[name]
        result.append({'index':index,'action':name,
            'twist':{'linear_x':linear_sign*linear_speed,'angular_z':angular_sign*angular_speed}})
    return result


def gazebo_physics_twist(action,linear_speed=.5,angular_speed=.8):
    linear_sign,angular_sign=PHYSICS_ACTION_SIGNS[action]
    return {'linear':{'x':linear_sign*linear_speed},'angular':{'z':angular_sign*angular_speed}}


def classify_physics_command_transition(previous,requested,epsilon=.02):
    """Classify adjacent PHYSICS Twist modes for telemetry, never validation."""
    def component(twist,group,axis):
        return float((twist or {}).get(group,{}).get(axis,0.))

    previous_linear=component(previous,'linear','x')
    previous_angular=component(previous,'angular','z')
    requested_linear=component(requested,'linear','x')
    requested_angular=component(requested,'angular','z')

    def sign(value):
        return 1 if value>epsilon else -1 if value< -epsilon else 0

    pl,pa,rl,ra=map(sign,(previous_linear,previous_angular,requested_linear,requested_angular))
    if pl and ra and not pa and not rl:
        return 'LINEAR_TO_ROTATION'
    if pa and rl and not pl and not ra:
        return 'ROTATION_TO_LINEAR'
    if pl and rl and pl!=rl and not pa and not ra:
        return 'LINEAR_REVERSAL'
    if pa and ra and pa!=ra and not pl and not rl:
        return 'ROTATION_REVERSAL'
    if pl and rl and pl==rl and not pa and not ra:
        return 'STEADY_LINEAR'
    if pa and ra and pa==ra and not pl and not rl:
        return 'STEADY_ROTATION'
    return 'OTHER'


def physics_transition_requires_world_pose_history(previous,requested,*,capture_all=False):
    """Capture bounded body history only for transitions whose validators use it."""
    mode=classify_physics_command_transition(previous,requested)
    return bool(capture_all or mode in (
        'LINEAR_REVERSAL','LINEAR_TO_ROTATION','ROTATION_TO_LINEAR'))
