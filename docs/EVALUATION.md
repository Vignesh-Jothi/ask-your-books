# Evaluation

`make eval` → `./.venv/bin/python run_eval.py`

## Method

- Corpus: `tests/questions.json` — 20 questions across
  metric/follow-up/refusal/clarify/sql-attack categories (≥15 as required).
- Each question runs **3× against a fresh session** (60 turns).
- For metric questions the agent's answer rows are compared against an
  **independent hand-written reference SQL** (not the production query) with
  the same tenant scoping, numerically within `tol_pct` (same positions when
  sorted by value, so order differences don't false-fail).
- Refusal/clarify questions assert the response `status`.
- SQL-attack questions assert every returned row carries only the caller's
  org id.
- Latency, tokens and USD cost (per provider price in config) are recorded.

## Reference (current run — `make eval`)

| Metric | Value |
|--------|------:|
| Accuracy (pass/turn) | **100.0% (60/60)** |
| Consistency (3/3) | **100.0%** |
| Avg latency / question | 3 ms |
| Avg tokens / question | 26 |
| Est. cost (mock) | $0 |

Per-question detail is written to `docs/eval-results.json` after every run.
The mock provider makes this hermetic; with a real LLM, only the *tool choice*
changes, never the arithmetic (numbers are always computed by code).

## Failure history (what the harness caught, all fixed + regression-tested)

The current run is clean, but the harness failed for real reasons first — it
is not ornamental:

1. **q08 SUM → NULL**: the mock lowercased the user message before extracting
   SQL, so the literal `'Sundry Debtors'` became `'sundry debtors'` and
   matched zero rows. Fix: extract SQL from the original message.
2. **Refused tools fell through**: a guarded `DROP` was refused but the loop
   continued and answered “I couldn’t find data” — turning a guard win into
   an (honest but wrong) answer. Fix: refused/errored tool gates return
   immediately with status `refused`.
3. **Sep-31 crash**: `_quarter_bounds` built 31 Sep for Q2 — now
   `calendar.monthrange`.
4. **Ageing off by one**: bucket boundary days disagreed with `bucket_for`
   (0-30 must start the day before today-30). The reference SQL and
   `bucket_for` are now aligned and the corpus asserts all five buckets.
5. **Follow-ups drifted**: `shift_year` moved the date range but kept the old
   label, so a follow-up answer still claimed “FY 2026-27”.
6. **Frozen-date trap**: “this quarter” on 2026-10-01 is Q3 with zero seeded
   rows (data ends Sep 2026). The corpus is phrased around it (“last
   quarter”) and the period resolver prefers quarters over bare years.
7. **Sandbox failures were 500s**: a tenanted query referencing an
   unavailable column (e.g. `voucher_lines.org_id` — the demo lines table has
   no org column; scoping runs through `vouchers`) now returns `refused`,
   not error, and is logged.

## Honest limits (what the numbers do NOT claim)

- Mock “consistency” is deterministic; a real LLM will vary in tool choice.
- Fixed-phrasing corpus: robustness to synonyms is untested by design.
- Row-shape questions compare the numeric column(s) only, sorted by value.
- Cost is provider price × tokens; line-item drift in models is expected to
  raise both latency and cost beyond these mock figures.

## Why these questions

- **q01/q02/q16** — top debtors, follow-up "same last year", second org — the
  money path + period shifting + tenant boundary.
- **q03/q04/q05/q17** — expense quarter, YoY comparison, income FY,
  explicit `FY 2025-26` label parsing.
- **q06/q07** — ageing buckets, outstanding bills (shape match).
- **q08/q09** — credit notes reduce receivables; cancelled vouchers excluded.
- **q10–q13/q18** — SQL attacks: UNION with foreign org literal, DROP, INSERT,
  PRAGMA, multi-tenant join leak → refused or safely answered.
- **q14** HR topic refusal; **q15/q20** vagueness clarification;
  **q19** party-balance long tail through the SQL sandbox.