# AI Usage — how I built this project

Per the assessment's rule that AI assistance be declared: this project was
built with an AI coding agent (Claude-class model used through the `pi`
agentic harness) working from my prompts and the submitted brief, with me
reviewing and correcting every step. This file is only about **how the
project was built** — the product's own embedded LLM is a separate feature
documented in `docs/guardrails.md`.

## How AI was used, phase by phase

| Phase | What the AI did | What I did |
|---|---|---|
| **1. Brief → design** | Read the assessment brief, produced the system design (hybrid metric-tools + sandboxed SQL agent, guard pipeline, OKF catalog, read-only SQLite demo, PostgreSQL RLS production path). | Chose the architecture, kept the dual demo/production story, set the domain rules. |
| **2. Scaffold & tooling** | Wrote Makefile, venv setup script, config loader, `.gitignore`, project layout. | Defined the `make` targets I wanted, verified packaging. |
| **3. Dataset & domain model** | Authored `seed.py` (deterministic 3-org / 18-month double-entry dataset), the FY/ageing/paise helpers, and the SQLite schema. | Set the domain decisions: **FY = Apr–Mar**, **money = integer paise**, cancelled vouchers always excluded, ageing buckets whole-day inclusive, frozen `TODAY`. |
| **4. Guard layer** | Implemented SQLGuard (read-only checks, keyword/parse/table guards) and sqlglot AST tenant scoping. | Defined the threat model and the stance that sandbox failures are refusals, never crashes. |
| **5. LLM layer & tools** | Wrote the provider-agnostic client, deterministic mock, prompt builders, and the metric-tool registry with OpenAI-compatible schemas. | Kept the non-negotiable rule that **numbers are computed by code, never by the LLM**. |
| **6. Services & API** | Built chat orchestration (tool loop, session memory, follow-ups), logging/metrics/billing services, and the FastAPI routes + CLI. | Reviewed the flow end to end; fixed agent-loop and period-label bugs the eval later caught. |
| **7. Tests & eval** | Wrote the unit tests and the 20-question × 3-run eval harness with independent reference SQL. | Authored the questions and expected outcomes; used every failure the harness found to harden the code. |
| **8. Frontend, Bruno, infra** | Produced the shadcn-style static UI, the Bruno collection, and the Docker/Postgres-RLS/systemd/nginx files. | Expanded scope only where the brief demanded it; kept the demo runnable with zero external services. |
| **9. Docs** | Structured and drafted the docs (architecture, modules, data model, guardrails, eval, decisions, infrastructure, glossary) and the README checklists. | Corrected overclaims, added the honest failure analysis. |

## How I verified AI output

- Every module was reviewed by me before it landed; nothing was merged on AI
  say-so.
- Changes had to keep `make test` green (37 unit tests) and `make eval` green
  (60/60 turns, 100% consistent) against the deterministic seed.
- The rewritten seed was byte-verified identical (table-hash diff) to prove
  refactors didn't drift the data.
- The API/UI were smoke-tested live; the eval harness caught 7 real bugs that
  were fixed and regression-locked.

## Disclosure notes

- No AI tool produced keys or credentials, and none were committed (`.env.example`
  ships blank).
- The demo data, expected results and evaluation methodology follow the brief
  plus my domain decisions listed above; AI helped generate them, I set the
  rules and accepted the outputs.
- In the live session I can explain and modify any part of this codebase
  without AI assistance.