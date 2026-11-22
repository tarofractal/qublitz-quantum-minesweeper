#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
task_python="${MINESWEEPER_PYTHON:-.venv/bin/python}"
"$task_python" scripts/run_tests.py
"$task_python" -m minesweeper simulate --shots 512 --seed 2026
"$task_python" -m minesweeper demo --level 1 --input +i --error X --location 1 --shots 512
"$task_python" -m minesweeper demo --level 2 --input +i --error Z --location 1 --shots 512
"$task_python" -m minesweeper demo --level 3 --input + --error Y --location 1 --shots 512
"$task_python" -m minesweeper iqm --mode prepare --level 4 --input +i --error Y --location 1 --shots 32 --out results/iqm-prepared
"$task_python" -m minesweeper iqm --mode fake --level 4 --input +i --error Y --location 1 --shots 512 --out results/iqm-fake-noise
"$task_python" scripts/build_deliverables.py
