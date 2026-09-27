# Application Vocabulary

Every word/term used in **Ask Your Books**, with a one-line description and
where it lives in the code. If a term is missing here, treat it as a bug in
this glossary, not in the app.

## 1. Business / accounting domain

| Term | Meaning |
|---|---|
| **ORG / organization** | A tenant — one company's books. Table `organizations` (`org_id`, `name`). |
| **user** | A person who can ask questions; always bound to exactly one org. Table `users`. The API takes only `X-User-Id` (e.g. `U301`); the server derives the org. |
| **account** | A ledger head or party. Columns `account_id, org_id, name, grp`. |
| **grp (account group)** | The ledger group of an account — one of: `Bank Accounts`, `Sales Accounts`, `Purchase Accounts`, `Direct Expenses`, `Indirect Expenses`, `Duties & Taxes`, `Sundry Debtors`, `Sundry Creditors`. |
| **Sundry Debtors** | Accounts that owe the company money (receivable parties). |
| **Sundry Creditors** | Accounts the company owes (payable vendors). |
| **voucher** | A double-entry document (a transaction). Table `vouchers` — `voucher_id, org_id, vtype, vdate, number, is_cancelled`. |
| **voucher line** | One leg of a voucher: an account + amount. Table `voucher_lines` — **has no `org_id`**; it is tenant-scoped through its parent `vouchers`. |
| **double-entry** | Every voucher has ≥2 lines that sum to zero. Seed + dataset invariant, asserted in tests. |
| **vtype (voucher type)** | `Sales`, `Purchase`, `Receipt`, `Payment`, `Journal`, `Credit Note`, `Debit Note`. |
| **is_cancelled** | 1 for cancelled vouchers. **Cancelled vouchers are always excluded** from every metric. |
| **party** | A customer (debtor) or vendor (creditor) — an account in `Sundry Debtors`/`Sundry Creditors`. |
| **Shared party** (“Global Traders”) | One party name deliberately present in two orgs — test material for tenant isolation. |
| **bill** | A receivable/payable created by a Sales/Purchase voucher. Table `bills` — `amount_paise` (signed: +receivable, −payable), `outstanding_paise`. |
| **invoice number / voucher number** | Human label like `SA-2504-001`; derived from vtype + month + counter. |
| **due date** | Bill settlement date. |
| **outstanding** | Amount of a bill still unpaid (0 = settled). |
| **overdue** | Bill with `outstanding_paise > 0` and `due_date < TODAY`. |
| **ageing** | Receivables grouped by days overdue into `not_due | 0-30 | 31-60 | 61-90 | 90+`. Whole-day **inclusive** boundaries; implementation `src/core/ageing.py`. |
| **paise** | Money unit: **1 ₹ = 100 paise, always an integer**. Never floats. |
| **amount_paise / *_paise** | Every money column is named `…_paise` and is an integer. |
| **debit / credit** | Double-entry sign convention: in this dataset, party **receivables are positive**, so a debtor's balance is `+` and a creditor's is `−`. |
| **credit note / debit note** | Reversals (returns) — reduce receivables/expenses; excluded from cancelled-filter like regular vouchers but kept in the net totals. |
| **FY (financial year)** | Indian FY: **April – March**. Label `FY 2026-27` = Apr 2026 – Mar 2027. `src/core/fy.py`. |
| **quarter** | Q1 Apr–Jun, Q2 Jul–Sep, Q3 Oct–Dec, Q4 Jan–Mar. Labels like `FY 2026-27 Q2`. |
| **TODAY** | The app's frozen “current day”, configurable (`guardrails.today`, default `2026-10-01`). All relative periods (“this quarter”, “overdue”) resolve against it — not the wall clock. |
| **period** | A `(start, end, label)` triple a tool filters by. Canonical labels: `FY 2026-27`, `FY 2026-27 Q2`, `this month`, `as of <date>`. |

## 2. Agent / LLM layer

| Term | Meaning |
|---|---|
| **chat session** | A conversation (`session_id`); stores user, org, last tool result + period (for follow-ups like “same … last year”). `src/services/chat_service.py`. |
| **tool** | One of the 7 callable endpoints the LLM may pick. Registry `src/tools/registry.py`. |
| **tool call** | A structured `{name, arguments}` request from the LLM. |
| **trace** | The tool-execution log returned per turn: tool name, args, SQL, row count, status, error, latency. `trace` array on every non-clarified response. |
| **handler** | The deterministic Python function behind a tool (`h_*` in `src/services/metrics_service.py`). **All numbers come from handlers + guarded SQL — the LLM never computes.** |
| **metric tool** | Hand-written, parameterized-SQL tool: `expense_by_group`, `income_by_group`, `fy_comparison`, `receivables_ageing`, `top_parties`, `outstanding_bills`. |
| **sql_query tool** | The sandboxed text-to-SQL escape hatch. Read-only, org-scoped, row-limited. |
| **refuse_answer** | An intent; used for out-of-scope requests (e.g. HR data). Response status `refused` and the reason is in **both** `refusal` and `text`. |
| **ask_clarification** | Intent for vague/short questions. Response status `clarifying` with an `options` list. |
| **mock provider** | Deterministic, offline, keyless LLM substitute — keyword dispatch over the registry. Same tool interface as real providers, zero cost, sha-stable for eval. `src/llm/mock.py`. |
| **provider** | `mock \| openai \| groq \| ollama` — the real clients reuse the identical tool/schema interface. |
| **usage / tokens** | Token accounting returned by the LLM client (usage in ChatResult; reported in API response + logs). |
| **clarify options / suggestion chips** | The canned follow-up questions shown in the UI when a turn is `clarifying`. |

## 3. Safety / guard layer

| Term | Meaning |
|---|---|
| **SQLGuard** | The guard pipeline for any SQL that runs: `assert_read_only` + keyword scan + parse + table whitelist + tenant rewrite. `src/guards/sql_guard.py`. |
| **read-only** | Enforced at **three** levels: guard rejection (`SELECT` only; no `INSERT/UPDATE/DELETE/DROP/PRAGMA/ATTACH`), the SQLite connection is `mode=ro` **and** issues `PRAGMA query_only=ON`, and the Postgres role is read-only. |
| **forbidden keywords** | Blacklist exploded into every SQL scrutineered by SQLGuard (`config/settings.yaml → guardrails.forbidden_keywords`). |
| **tenant scoping / scope_to_org** | SQL rewrite that makes a bare table reference touch only one org: direct-`org_id` tables get a `WHERE org_id = '<org>'` wrapper; `voucher_lines` (no `org_id`) is joined through a filtered `vouchers` subquery. `src/guards/tenant.py`. |
| **org leakage** | Any data from another org appearing in a result — the invariant tenant scoping protects (and `q10/q18` attack questions probe). |
| **SQLGuardError / refusal** | A guarded-out or sandbox-runtime-failed request surfaces as a **refusal**, never a crash (status `refused`, reason in `text`). |
| **sandbox failure** | A runtime failure *inside* the rewritten SQL (e.g. an unknown column introduced by the tenant rewrite) → captured as `QueryError` → surfaced as `SQLGuardError` (refusal). |
| **RLS (Postgres)** | Row-Level Security policies as the second tenant wall in the canonical deployment (`infrastructure/postgres/001-schema-rls.sql`). |
| **statement_timeout** | Per-statement time limit in the read-only Postgres role pool (PgBouncer) so one bad query can't stall the org. |

## 4. App / data plumbing

| Term | Meaning |
|---|---|
| **OKF (One Knowledge File)** | The single human/AI-readable catalog + schemas for the dataset: `okf/` (entity catalog JSON + JSON Schemas for chat request/response, metric result, tool call). |
| **envelope** | The uniform API response shape `{status, text, rows, trace, assumption, refusal, …}` — see `okf/schemas/chat.response.json`. |
| **session.messages** | The conversation history mirrored per session (mirrors what the LLM client sees). |
| **last_result / last_period_label** | Session memory of the previous turn's rows + period — what “same … last year?” shifts. |
| **assumption** | Free-text rider on an answer when the agent inferred a period/user input (e.g. `“assuming FY 2026-27”`). |
| **trace_id** | Per-request correlation id written to the audit log (`logs/tool_calls.jsonl`) and echoed in responses. |
| **row_count** | Number of rows a tool returned — in the trace, in logs, and (when >80) with “… and N more”. |
| **latency_ms / tokens** | Per-call observability fields in the trace + logs. |
| **INR formatting** | Display-only: paise → ₹, group integer part into Indian digits (lakh/crore). **Never computed in the browser**; the API still returns raw paise. |

## 5. Eval / QA

| Term | Meaning |
|---|---|
| **corpus** | `tests/questions.json` — 20 questions covering every mandated category × 3 runs. |
| **run** | One execution pass of the corpus (60 turns total). |
| **accuracy / consistency** | accuracy = passed turns ÷ total turns; consistency = questions where all 3 runs agreed. |
| **reference SQL** | The independent, hand-written SQL in the corpus that the agent's numbers are compared against (tolerance `tol_pct`). |
| **attack question (q10–q13, q18)** | Corpus questions written to break isolation (UNION, cross-org `GROUP BY`, DROP/INSERT/PRAGMA, multi-tenant join) — must answer with a refusal or scoped rows. |

## Where names come from

All entity/column names in section 1 mirror the **actual SQLite/Postgres schema**
(`okf/data/entity_catalog.json`, `infrastructure/postgres/001-schema-rls.sql`).
All tool and status names come from `src/tools/registry.py`,
`src/services/metrics_service.py` and `src/services/chat_service.py`.
Period labels come from `src/core/fy.py`; ageing buckets from `src/core/ageing.py`.