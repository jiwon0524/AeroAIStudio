#!/usr/bin/env bash
set -euo pipefail
mode="${1:---check-only}"
task_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "$mode" == --check-only ]]; then
  exec bash "$task_root/scripts/verify_ubuntu_dev.sh"
fi
if [[ "$mode" != --install ]]; then echo 'Usage: setup_ubuntu_dev.sh --check-only | --install'; exit 2; fi
source /etc/os-release
if [[ "${ID:-}" != ubuntu || "${VERSION_ID:-}" != 24.04 ]]; then
  echo 'Install mode targets Ubuntu 24.04 only; no changes made.'; exit 2
fi
cat <<'PLAN'
Planned changes (only after typing INSTALL):
  sudo apt-get update
  sudo apt-get install --no-remove gz-harmonic python3-gz-transport13 python3-gz-msgs10 python3-venv
  python3 -m venv --system-site-packages .venv-ubuntu
  .venv-ubuntu/bin/python -m pip install -e ".[dev,dqn]"
No repository/keyring, NVIDIA/CUDA, ROS2 or WSL changes are automated.
Configure the official Harmonic binary repository first if needed:
https://gazebosim.org/docs/harmonic/install_ubuntu/
PLAN
read -r -p 'Type INSTALL to perform exactly these changes: ' response
[[ "$response" == INSTALL ]] || { echo 'Cancelled; no changes made.'; exit 0; }
sudo apt-get update
sudo apt-get install --no-remove gz-harmonic python3-gz-transport13 python3-gz-msgs10 python3-venv
cd "$task_root"
python3 -m venv --system-site-packages .venv-ubuntu
.venv-ubuntu/bin/python -m pip install -e '.[dev,dqn]'
exec bash scripts/verify_ubuntu_dev.sh .venv-ubuntu/bin/python
