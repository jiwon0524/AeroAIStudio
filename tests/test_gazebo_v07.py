import os
import pytest
from aero_ai_studio.gazebo.diagnostics import gazebo_status

pytestmark=[pytest.mark.gazebo,pytest.mark.skipif(os.environ.get('AERO_GAZEBO_INTEGRATION')!='1' or not gazebo_status(probe=False)['available'],reason='Actual Ubuntu/Harmonic runtime unavailable/not enabled')]


@pytest.mark.parametrize('obstacle',[False,True],ids=['straight_goal','front_obstacle_rule'])
def test_actual_physics_sensor_closed_loop(tmp_path,obstacle):
    import importlib.util
    source=__import__('pathlib').Path(__file__).parents[1]/'tools'/'verify_v07_runtime.py'
    spec=importlib.util.spec_from_file_location('v07_smoke',source);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    report=module.run(tmp_path,obstacle=obstacle)
    assert report['status']=='PASS',report
