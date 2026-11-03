import pytest


def pytest_collection_modifyitems(items):
    # Keep the original V0.6 integration source untouched while exposing a marker.
    for item in items:
        if item.path.name=='test_gazebo_integration.py':item.add_marker(pytest.mark.gazebo)
