# Decision Log

Short form: what, why, what we deliberately did NOT do. Dates = 2026-09/10
build (assessment).

## 1. Numbers are computed in code, LLM only picks tools
Why: LLMs cannot be trusted to arithmetic on finance data; cost/latency too.
Consequence: mock *and* real providers produce identical numbers; eval passes
with mock; non-negotiable design invariant.

## 2. Curated metrics + one guarded `sql_query` escape hatch
Why: 80% of questions (receivables, ageing, expenses, sales, comparisons) hit
5–7 well-tested queries; long tail goes through the sandbox, so the product
never dead-ends on a novel phrasing. The escape hatch is *as guarded* as the
curated path (same SQLGuard + scoping + timeout + row cap).

## 3. sqlglot AST rewriting for tenant scoping (not string concatenation)
Why: writing `WHERE org_id = ?` by string editing an arbitrary user query
fails on subqueries, UNIONS and quoting. AST-level derived-subquery wrapping
works for every shape (tests/test_tenant.py). `voucher_lines` is scoped
**through vouchers** — the denormalized line table cannot be queried without
joining its header, so a cross-org select is structurally impossible.

## 4. Sandbox failures are refusals, not 500s
Why: "no such column" on a rewritten join or a crashed timeout is the guard
speaking, not the server. A user who types `SELECT * FROM voucher_lines WHERE
org_id='ORG1'` gets a clear refusal and the event is logged.

## 5. `at this moment`-style relative periods resolve to canonical labels
Why: follow-ups ("…and last year?") need a resolvable period object. Labels
like `FY 2026-27 Q2` re-parse deterministically; `shift_year` relabels, so
follow-ups don't silently shift the *date range* but keep the *label* (the
original bug).

## 6. Mock provider is a first-class product feature
Why: hermetic CI/eval, zero cost, deterministic demos; the OpenAI-compatible
client (works with OpenAI/Groq/Ollama/LM Studio) is a drop-in for the same
interface. A provider swap can't rot the guardrails because the mock runs the
same policy text and the same tool registry.

## 7. Demo data is deterministic and ends Sep 2026 (TODAY frozen 2026-10-01)
Why: reproducible eval and stable ageing buckets. Cost: "this quarter" on the
frozen date is a *future* quarter with no data — an intentional trap that the
eval corpus phrases around ("last quarter").

## 8. Frontend is static shadcn-style, no build step
Why: the brief asks for shadcn look-and-feel and easy runnability — a
dependency-free static UI served by FastAPI satisfies both. A React+shadcn
port is possible (frontend/ note) but adds a toolchain for zero product value
in the demo.

## Deliberately skipped (YAGNI)
- Multi-model conversation memory (SQLite-backed sessions) — not required;
  in-memory sessions suffice for the eval + demo.
- AuthN (OAuth/JWT) — replaced by the X-User-Id contract + RLS in the
  production schema; real SSO would slot into `org_service`.
- Async streaming UI — polling the same endpoint keeps the demo simple.