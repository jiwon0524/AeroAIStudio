#!/usr/bin/env bash
set -euo pipefail
task_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
task_python="${1:-python3}"
export PYTHONPATH="$task_root/src${PYTHONPATH:+:$PYTHONPATH}"
exec "$task_python" "$task_root/scripts/check_sim_environment.py"
