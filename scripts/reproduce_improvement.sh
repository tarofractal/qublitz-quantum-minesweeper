#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
task_python="${MINESWEEPER_PYTHON:-.venv/bin/python}"
"$task_python" scripts/run_tests.py
"$task_python" -m minesweeper simulate --shots 512 --seed 2026 --out results/improvement/regression-simulation
"$task_python" scripts/improve_and_compare.py
"$task_python" scripts/report_improvement.py
