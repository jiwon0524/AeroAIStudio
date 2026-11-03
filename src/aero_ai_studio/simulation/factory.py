from functools import partial


def environment_factory(simulator='grid',**options):
    if simulator=='grid':
        from aero_ai_studio.simulation.grid_world import GridWorld
        return GridWorld
    if simulator=='gazebo':
        from aero_ai_studio.gazebo.environment import GazeboEnvironment
        return partial(GazeboEnvironment,**options)
    raise ValueError('Unsupported simulator')
