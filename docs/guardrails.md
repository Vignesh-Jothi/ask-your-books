# Guardrails

All of the following are **default-on, config-driven** (config/settings.yaml /
.env). The intent: an AI assistant over financial data must be structurally
incapable of (a) writing, (b) leaking another tenant, (c) runaway cost.

## 1. Read-only, enforced three ways

1. Keyword + parse guard (src/guards/sql_guard.py): comments stripped, a
   blacklist (INSERT/UPDATE/DELETE/DROP/ALTER/CREATE/ATTACH/DETACH/PRAGMA/
   VACUUM/…) scanned, then sqlglot must parse **exactly one statement** of
   type SELECT / WITH / set-operation.
2. Migration guard (tests/test_guards.py): every keyword is re-tested
   disguised in comments and mixed case.
3. Driver level: SQLite opens `mode=ro` **and** `PRAGMA query_only=ON` —
   so even a future bug in our own guards cannot write.

## 2. Tenant scoping in code, never in the prompt

- The org is resolved from `X-User-Id` in the API layer. The prompt never
  mentions org/tenant and the LLM never receives org data as context.
- Every SQL statement is AST-rewritten (sqlglot) so each tenant table is
  wrapped in a subquery with `org_id = '<resolved org>'`, and `voucher_lines`
  is scoped **through its vouchers join** — the only peer data that could be
  mass-exfiltrated.
- The physical database adds RLS for Postgres as a second wall
  (infrastructure/postgres/001-schema-rls.sql).

## 3. Refusal over hallucination

| Situation | Behavior |
|-----------|----------|
| Write/introspection keyword, unknown table, multi-statement, unparseable SQL, sandbox runtime failure | `refused` with the reason; nothing leaks |
| Vague or ambiguous intent | `clarifying` with concrete options (chat loop demands one) |
| Employment/HR questions | `refused` — outside the accounting dataset |
| > `row_limit` rows or > `query_timeout_s` | refused/error, no partial data |

## 4. Cost & abuse controls

- `agent_max_iterations` tool-call budget per turn; `max_tokens` per LLM reply.
- Per-request token + cost accounting (src/services/billing_service.py) and an
  append-only JSONL log (src/services/log_service.py).
- Network rate limiting outside the app (nginx config) plus the built-in
  per-user row/iteration caps.

## 5. Applications to the LLM layer (prompts)

- System prompt marks the assistant as **read-only**, requires it to route via
  tools, forbids stating numbers it has not seen from a tool result, offers
  `ask_clarification`/`refuse_answer` as first-class exits, and lists the
  refusal topics. With the mock provider the same policy text is exercised in
  CI, so a provider swap can't regress the guardrails silently.

Config reference — see `.env.example` for every key (LLM_PROVIDER, LLM_API_KEY,
TODAY, QUERY_TIMEOUT_S, MAX_RESULT_ROWS, AGENT_MAX_ITERATIONS, …).