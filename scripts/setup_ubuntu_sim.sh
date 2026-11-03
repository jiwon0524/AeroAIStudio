#!/usr/bin/env bash
set -eu
# Guidance only: no apt install, repository modification or sudo is executed.
printf '%s\n' 'Aero AI Studio V0.6 target: Ubuntu 24.04 + Gazebo Harmonic' \
 'Review official instructions: https://gazebosim.org/docs/harmonic/install_ubuntu/' \
 'Recommended commands (review and run manually):' \
 '  sudo apt install gz-harmonic python3-gz-transport13 python3-gz-msgs10 python3-venv' \
 '  python3 -m venv --system-site-packages .venv' \
 '  .venv/bin/python -m pip install -e ".[dev,dqn]"' \
 '  .venv/bin/python scripts/check_sim_environment.py' \
 '  AERO_GAZEBO_INTEGRATION=1 .venv/bin/python -m pytest tests/test_gazebo_integration.py -v' \
 'Optional ROS2 Jazzy / ros_gz_bridge is not required for the native transport loop.' \
 'Headless GPU LiDAR still needs Ogre2/EGL rendering capability.'
