#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
task_python="${MINESWEEPER_SYSTEM_PYTHON:-python3}"
if command -v python3.12 >/dev/null 2>&1; then
  task_python="${MINESWEEPER_SYSTEM_PYTHON:-python3.12}"
fi
"$task_python" -c 'import sys; assert sys.version_info[:2] == (3,12), "Please use Python 3.12 (set MINESWEEPER_SYSTEM_PYTHON if needed)"'
"$task_python" -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
.venv/bin/python -m pip install -e . --no-deps
.venv/bin/python -m pip check
printf '\nSetup complete. Run: .venv/bin/python -m pytest -q\n'
