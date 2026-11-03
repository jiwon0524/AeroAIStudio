import os
import pytest
from aero_ai_studio.gazebo.diagnostics import gazebo_status
from aero_ai_studio.gazebo.environment import GazeboEnvironment
from aero_ai_studio.scenario.models import ScenarioSpec


@pytest.mark.skipif(os.environ.get('AERO_GAZEBO_INTEGRATION')!='1' or not gazebo_status()['available'],reason='Real Ubuntu Harmonic runtime not enabled/available')
def test_real_gazebo_closed_loop(tmp_path):
    env=GazeboEnvironment(ScenarioSpec(width=10,height=10,goal=(3,3)),root=tmp_path,gui=False)
    try:
        assert env.reset(42)==(0,0)
        first=env.get_agent_observation('sensor').sensor_state['sample_time']
        for action in ['right']*3+['down']*3:
            result=env.step(action)
            if result.terminated or result.truncated:break
        assert result.reason=='goal'
        assert env.get_agent_observation('sensor').sensor_state['sample_time']>first
        assert env.reset(43)==(0,0)
        assert env.step('up').reason=='collision'
    finally:env.close()
    assert env.process.poll() is not None
