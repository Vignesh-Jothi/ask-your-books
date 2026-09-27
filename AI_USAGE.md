# AI Usage

This project was built with AI coding assistance, per the assessment's
requirement that AI tools be declared.

## What was used

- **Terrain/agentic coding assistants** (Claude / GPT-class models via pi,
  Cursor-style tooling): authored the majority of the code, tests, docs and
  infrastructure in this repository, under tight human review.
- **Human review**: every module, the guard/test strategy, the eval corpus and
  the docs were reviewed and corrected by the author. The demo data, expected
  results and eval methodology follow the assessment brief and the author's
  domain decisions (FY Apr–Mar, paise, debit-positive rules).

## What AI was NOT used for

- No AI-generated keys, tokens or credentials (there are none of value).
- No model was given access to production/secret data — there is none.
- The **numbers** shown to users and tested by the eval are produced by
  deterministic application code, never by the LLM.

## Guardrails on the AI (product + process)

- The LLM in the product is sandboxed (see `docs/guardrails.md`): read-only
  driver, SQLGuard, sqlglot tenant scoping, timeout/row caps, refuse/clarify
  exits — all config-driven in `config/settings.yaml` / `.env`.
- Default provider is an offline deterministic `mock` so tests/CI are hermetic
  and cost zero; real providers plug into the same interface.
- All prompts, model/org scoping decisions and refusal topics are committed in
  `src/llm/prompts.py` and repeatable across providers.

## Reproducibility

- `requirements.txt` is pinned; `make setup` creates the venv;
  `make test` (37 unit tests) and `make eval` (60-turn evaluation) pass at
  100% / 100% with the mock provider on the deterministic seed.