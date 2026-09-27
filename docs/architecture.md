# Ask Your Books — System Design

A data-question agent over multi-tenant accounting data. Users chat in natural
language; the agent answers from a **read-only**, **tenant-scoped** financial
database. Every number the user sees comes from a guarded query, never from
the LLM "believing" it computed something.

## 1. Big picture

```
┌──────────────┐   ┌────────────────────────────────────────────────────┐
│  frontend/    │   │               src/ (FastAPI app)                  │
│  shadcn-style │──▶│  /api/chat ──▶ ChatService ──▶ LLM client          │
│  static UI    │   │      ▲ (X-User-Id)      │         │               │
└──────────────┘   │      │                    ▼         ▼               │
                   │  SessionStore      tools/registry   prompts+deps    │
                   │      │                    │                         │
                   │      ▼                    ▼                         │
                   │  metrics_service ◀── (metric tools)  llm/ client    │
                   │  sql_query ◀─── SQLGuard ─▶ TenantScope ─▶ DB       │
                   └─────────────────────────────────────────────────────┘
```

Talking to the LLM is expensive and untrustworthy; numbers are the product.
So the agent loop is: **LLM decides intent** (which tool, which period) →
**code executes the number** → **code formats the answer**. The LLM never
returns SQL or computes totals.

## 2. The agent loop (src/services/chat_service.py)

1. Authenticate the user (`X-User-Id` header) → org resolved **in code**
   (`org_service`). The client can never choose an org.
2. Build the system prompt from the OKF entity catalog + org name; inject the
   conversation history (bounded).
3. Ask the LLM for a tool call:
   - Curated tools: `top_parties`, `expense_by_group`, `income_by_group`,
     `receivables_ageing`, `outstanding_bills`, `fy_comparison`,
     `call_party_balance` (via sql_query sandbox).
   - Exit tools: `ask_clarification`, `refuse_answer`.
4. Run the tool **in-process** (metrics_service) or through the
   **SQLGuard + TenantScope** sandbox (`sql_query`).
5. Loop up to `agent_max_iterations`. When the LLM stops calling tools, the
   service synthesizes the answer text from the **last tool's rows** and
   records it as an assistant message with a `meta` marker (follow-ups reuse
   the previous tool + period-shift logic).

Follow-ups ("and the same for last year?"): if the LLM emits no tool call and
a previous tool exists in the session, the service re-runs it with the period
shifted one FY/year (src/core/fy.py `shift_year`). Relative period labels are
canonical strings (`FY 2026-27 Q2`) that re-resolve deterministically.

## 3. Guardrails (defense in depth)

| Layer | Mechanism | Where |
|-------|-----------|-------|
| Read-only schema | `sqlite3` opened `mode=ro` + `PRAGMA query_only=ON` at the driver level — even a bug in our own guards cannot write | `src/db/connection.py` |
| SQL syntax guard | keyword blacklist + sqlglot parse: exactly **one** statement, `SELECT`/`WITH`/set-operations only | `src/guards/sql_guard.py` |
| Table allow-list | every bare table ref must be a known entity | `src/guards/sql_guard.py` |
| Tenant scoping | sqlglot AST rewrite injects `org_id = '<user's org>'` into every tenant-table derived subquery; `voucher_lines` is scoped **through its vouchers join**, so denormalized line data can never leak | `src/guards/tenant.py` |
| Timeout | queries run in a worker thread; `connection.interrupt()` after `query_timeout_s` | `src/db/connection.py` |
| Row limit | result set capped (LIMIT wrapper, `GET ALL` on the rest) | `src/db/connection.py` |
| Application policy | unknown tables / failed sandbox queries / forbidden intents → **refused**; vague intents → **clarify**; HR/employment topics are refused at prompt + tool level | chat loop + mock |
| Cost guard | token budget per turn (`max_tokens`), usage logged per request (`log_service`) | everywhere |

All knobs (timeout, row limit, iteration cap, keywords, blocked tables,
cost-per-1k, provider) live in `config/settings.yaml` + `.env`, never in code
literals.

## 4. Money & domain rules

- Amounts are **integer paise** (`amount_paise`), debits positive / credits
  negative; Indian digit grouping for display (₹12,34,567) — src/core/money.py.
- FY = Apr–Mar. Periods resolve from free text to canonical labels
  (`FY 2026-27 Q2`, months) — src/core/fy.py. `_quarter_bounds` uses real
  month lengths (no Sep-31 bugs).
- Cancelled vouchers (`is_cancelled`) are excluded from every metric.
- Credit notes reduce receivables; `bills.outstanding_paise` tracks the
  remaining balance; ageing buckets are whole-day inclusive
  (`bucket_for`: days ≤ 30 → "0-30", etc.) — src/core/ageing.py.

## 5. Multi-tenancy

- Seed: 3 orgs, users U101/U102 (ORG1), U201 (ORG2), U301/U302 (ORG3).
- Every query path (metrics, sql sandbox) receives `org_id` as a parameter
  injected by the API layer — the LLM never sees or decides it.
- The eval asserts cross-org isolation for plain selects, joins, UNIONS and
  subqueries (tests/test_tenant.py, questions q10/q16/q18).

## 6. LLM providers

`llm/client.py` defines the interface (`chat(messages, tools) -> ChatResult`).
Implementations: `mock` (deterministic, offline — default), `openai_compat`
(OpenAI / Groq / Ollama / any OpenAI-compatible endpoint). Provider, model,
base URL, key, temperature and price-per-1k are all config. The mock exists so
tests/eval/CI are hermetic — the real model only changes *which* tool call is
chosen, never *how* numbers are computed.

## 7. Evaluation (run_eval.py)

20 questions × 3 runs = 60 turns. Each run compares the agent's rows against
an **independently hand-written reference SQL** (same tenant scoping, numeric
comparison within `tol_pct`). Reports accuracy, 3/3 consistency, latency,
token usage and USD cost (mock = $0). See docs/EVALUATION.md.

## 8. Repository map

```
src/core/        domain rules (FY, ageing, money)          src/db/          connection + SQL
src/guards/      sql read-only + tenant scoping            src/llm/         prompts, client, mock
src/services/    chat loop, metrics tools, org, billing    src/tools/       tool registry
src/api/         FastAPI routes (health, chat)             src/okf/         envelope