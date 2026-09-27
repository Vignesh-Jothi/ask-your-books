# Module Reference

Every module is small and has one job; shared pieces live in `src/core`,
`src/guards`, `src/db` so nothing is duplicated.

## src/core — domain rules (no I/O)

| Module | Responsibility | Key names |
|--------|----------------|-----------|
| `fy.py` | FY Apr–Mar calendar, quarter bounds, period resolve/shift | `Period`, `resolve_period()`, `shift_year()`, `fy_bounds()`, `_quarter_bounds()` |
| `ageing.py` | receivable ageing buckets (whole-day inclusive) | `BUCKETS`, `bucket_for()`, `bucket_index()` |
| `money.py` | paise math + Indian grouping display | `group_inr()`, `fmt_inr()`, `fmt_abs()` |

## src/db — persistence

| Module | Responsibility |
|--------|----------------|
| `connection.py` | `readonly_conn(path)` (`mode=ro` + `PRAGMA query_only=ON`), `run_readonly(conn, sql, params, row_limit)` (thread + `interrupt()` timeout, LIMIT wrapper), `QueryError` |
| `queries.py` | immutable SQL strings, one query builder per metric |

## src/guards — security (pure functions on SQL)

| Module | Responsibility |
|--------|----------------|
| `sql_guard.py` | `assert_read_only(sql)` (strip comments, keyword blacklist, single SELECT/WITH/SetOperation), `assert_only_allowed_tables(stmt)`, `SQLGuardError` |
| `tenant.py` | `scope_to_org(sql, org_id)` AST rewrite — tenant-table subqueries get `org_id = ?` predicates; `voucher_lines` scoped via vouchers join |

## src/llm — model plumbing

| Module | Responsibility |
|--------|----------------|
| `client.py` | `LLMClient` protocol + `ChatResult` dataclass |
| `prompts.py` | system prompt builder (entity catalog → schema context), tool schemas, refusal/clarify policy text |
| `openai_compat.py` | OpenAI/OpenAI-compatible chat + tool-call API client |
| `mock.py` | deterministic offline dispatcher (the eval/CI provider) |

## src/services — application logic

| Module | Responsibility |
|--------|----------------|
| `chat_service.py` | the agent loop: intent → tool → synthesize; follow-up period shifting; clarify/refuse interception; trace records |
| `metrics_service.py` | one handler per metric tool + the `sql_query` sandbox; all return `MetricResult(rows, sql, period_label)` |
| `org_service.py` | user → org resolution (+ name lookup) |
| `billing_service.py` | token/currency cost per request |
| `log_service.py` | append-only JSONL request/guard log |

## src/tools — wiring

`registry.py` maps tool names → handlers, enforces kwargs, and returns
`ToolResult(status, rows, error, period_label)`.

## src/api — HTTP

`routes.py` `/api/health` + `/api/chat` (X-User-Id header → org), `models.py`
Pydantic request schema. `main.py` boots FastAPI and mounts `/ui`.

## src/okf — Open Knowledge Format

`envelope.py` wraps every payload (see okf/README.md).

## Top level

| File | Purpose |
|------|---------|
| `seed.py` | deterministic demo ledger (3 orgs, 18 months, 20k lines) |
| `run_eval.py` | 3×20-question evaluation vs independent reference SQL |
| `src/cli.py` | interactive terminal chat |
| `config/settings.yaml` + `.env` | every guardrail/cost/provider knob |
| `frontend/` | static shadcn-style chat UI, served at `/ui` |
| `infrastructure/` | Docker, Postgres schema + RLS, deployment units |
| `bruno/` | API collection (health, chat, attack-refusal) |