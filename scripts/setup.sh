#!/usr/bin/env bash
# One-command setup: create .venv, install deps, build books.db, smoke-test.
set -euo pipefail
cd "$(dirname "$0")/.."

PY=${PYTHON:-python3}
echo "[1/4] creating virtualenv (.venv) ..."
"$PY" -m venv .venv
./.venv/bin/pip install --quiet --upgrade pip
./.venv/bin/pip install --quiet -r requirements.txt

echo "[2/4] seeding books.db (deterministic) ..."
./.venv/bin/python seed.py

echo "[3/4] running unit tests ..."
./.venv/bin/pytest -q

echo "[4/4] smoke eval (mock LLM, 3 questions x 1 run) ..."
./.venv/bin/python run_eval.py --limit 3 --runs 1

echo
echo "Done. Start the app:  make app   (http://localhost:8000)"
echo "     terminal chat:  make cli"