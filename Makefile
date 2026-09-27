.PHONY: setup db app cli eval test lint clean

setup:            ## create .venv and install deps
	bash scripts/setup.sh

db:               ## (re)build books.db deterministically
	.venv/bin/python seed.py

app:              ## run the FastAPI app (frontend + API)
	.venv/bin/uvicorn src.main:app --host 0.0.0.0 --port 8000

cli:              ## interactive terminal chat  (pooch --user-id U301)
	.venv/bin/python -m src.cli

eval:             ## run the 3x repeat evaluation
	.venv/bin/python run_eval.py

test:             ## unit tests (no LLM)
	.venv/bin/pytest -q

clean:            ## remove db, logs, caches
	rm -rf books.db logs data .pytest_cache __pycache__ src/**/__pycache__