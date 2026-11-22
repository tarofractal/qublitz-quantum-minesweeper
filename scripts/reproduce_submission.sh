#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
task_python="${MINESWEEPER_PYTHON:-.venv/bin/python}"
"$task_python" -m pip check
"$task_python" scripts/run_tests.py
"$task_python" -m minesweeper simulate --shots 512 --seed 2026 --out results/submission-simulation
"$task_python" scripts/analyze_hardware.py
"$task_python" scripts/report_submission.py
