# agent.md — Ask Your Books

> Single source of truth for AI-agent instructions in this repo. Read this
> file before every session; it only carries the rules that must never be
> violated. `example.agent.md` next to this file is a formatting reference
> from another project — ignore its content.

---

## 1 · What this project is

A small FastAPI app that answers natural-language **accounting** questions
from a books database (SQLite for the demo, Postgres + RLS in
`infrastructure/postgres/` for production). "Bring your own books" data
question-answering agent.

| Concern | Where |
|---------|-------|
| **Chat API** | `src/api/` — `/api/chat`, `/api/health`; envelope schema in `src/okf/` |
| **Agent loop** | `src/services/chat_service.py` (tool loop, session memory, follow-ups, refusals) |
| **LLM layer** | `src/llm/` — mock (default), OpenAI-compatible client, prompts, provider/model tables |
| **Metric tools** | `src/services/metrics_service.py` (hand-written SQL, correct by construction) + schemas in `src/tools/registry.py` |
| **Guards** | `src/guards/` — read-only SQLGuard + sqlglot tenant scoping |
| **Domain math** | `src/core/` — FY, ageing buckets, paise/INR |
| **Seed data** | `seed.py` (deterministic: 3 orgs, 18 months, 10,194 vouchers) |
| **Frontend** | `frontend/` — static shadcn-style UI served at `/ui` (no build step) |
| **Docs / catalog** | `docs/` + `okf/` (entity catalog + JSON Schemas) |
| **Infra** | `infrastructure/` — Docker, Postgres RLS, systemd, nginx |

**Golden rules (shape everything):**
- The LLM only picks intent + tool arguments — **every number is computed by
  code** (metric handlers + guarded SQL). Mock and real providers must produce
  identical answers.
- Default provider is `mock` (offline, deterministic, zero cost). Pointing the
  app at a real LLM takes only `LLM_PROVIDER` + `LLM_API_KEY` (+ optional
  `LLM_MODEL`); everything else is derived (`src/llm/providers.py`).
- Reference date is **frozen** (`TODAY=2026-10-01`, mid FY 2026-27): "this
  quarter" trails into an intentionally empty future — the eval corpus depends
  on this, so don't un-freeze it.

---

## 2 · Orient before you act (every time)

1. **Read the map first.** Start at `README.md` (deliverables, decisions,
   eval), then `docs/glossary.md` (the application vocabulary — use its terms,
   extend it for new ones) and `docs/data-model.md` before touching data code.
2. **Task → files table**:

   | Task | Read/load |
   |------|-----------|
   | New or changed metric | `src/services/metrics_service.py` + `src/tools/registry.py` schemas + `tests/questions.json` |
   | Guard/security change | `src/guards/` + `tests/test_guards.py`, `tests/test_tenant.py` |
   | Period / FY / ageing math | `src/core/fy.py`, `src/core/ageing.py` + `tests/test_fy.py` |
   | Query changes | `src/db/queries.py` |
   | Seed/dataset change | `seed.py` + `tests/test_seed.py` |
   | API shape change | `src/api/` + `src/okf/` schemas + `bruno/` |
   | UI change | `frontend/` (`index.html`, `styles.css`, `app.js`) |
   | Docs update | `docs/` + `docs/glossary.md` for any new term |
   | Commit rules | `CONTRIBUTING.md` (Conventional Commits, required) |

3. **Use the venv.** Always `./.venv/bin/python` / `./.venv/bin/pytest` —
   never the system Python. `make test` runs the suite, `make eval` runs the
   60-turn harness, `make db` regenerates `books.db` (gitignored).
4. **Prove it, don't assume.** Every change lands with evidence: green
   `make test`, and — for anything touching data/guards/tools — a green
   `make eval` (must stay 100% / 100%). After a `seed.py` change, re-seed and
   byte-compare the new DB against the committed hash; after a rename/refactor
   the table hash must be identical.

---

## 3 · Non-negotiable rules

### Correctness of numbers
- **Never let the LLM compute figures.** Numbers come from deterministic
  handlers + guarded SQL; the LLM selects tools only.
- **Domain invariants:** money is integer **paise** (no floats); FY = **Apr–
  Mar**; **cancelled vouchers are always excluded**; ageing buckets are
  whole-day inclusive (`not_due | 0-30 | 31-60 | 61-90 | 90+`); expenses and
  income are shown positive (per-group ABS).
- **Determinism is sacred.** The seed must stay reproducible (fixed random
  seed) and the eval corpus 20 questions × 3 runs must keep passing.

### Safety / multi-tenant (CRITICAL)
- **Every SQL goes through the guard pipeline** — read-only check, SQLGuard
  keyword/parse/table guards, sqlglot org scoping, row/time limits — both for
  metric tools and the `sql_query` sandbox.
- **Sandbox or rewritten-SQL runtime failures are refusals**
  (`SQLGuardError`, status `refused`, reason in `text`), never crashes and
  never row_leaks.
- **The org always comes from the server side** (`X-User-Id` → `org_id`).
  `voucher_lines` has no `org_id` — it is scoped through `vouchers`; do not
  add an `org_id` to it or change the scoping without re-running
  `tests/test_tenant.py` and the attack questions.
- **The runtime DB connection is read-only** (`mode=ro` + `PRAGMA
  query_only=ON`); the Postgres role is read-only too. Writing is never a
  legitimate runtime path.
- **No secrets in code.** `.env.example` ships blank; never commit keys.

### Code & frontend
- **Descriptive identifiers only** — no single-letter names (repo rule).
  Comment where intent isn't obvious.
- **Math never in the browser.** The UI formats INR (display-only); the API
  returns raw paise.

### Git flow (CRITICAL)
- **Merge direction is one-way: feature → develop → main (via release).**
- **Agents never merge.** Do not run `gh pr merge`, `git merge`, or
  `git rebase` on shared branches. Branch integration happens through
  **Vortex** only: `finish-feature`, `finish-hotfix`, `merge-to-devops`,
  `create-release` / `complete-release`. Branch creation goes through Vortex
  (`feature/<name>`, `hotfix/<name>`, `devops/<name>`).
- If a Vortex call fails or returns an ambiguous/`unknown` status, **report
  the observed state as-is and stop** — do not infer success, do not propose a
  manual merge workaround. The user decides.
- **Never push a merge, rebase, conflict-resolution, `reset --hard` or
  force-push to `develop`/`main`** without the user's explicit go-ahead for
  that specific action.
- **Conflict resolution:** fix on the PR's head branch (merge the base into
  the head locally, push the head), never into a shared branch.

### Process
- **Never commit automatically.** Stage with `git add` and wait for the user's
  explicit instruction to commit. Conventional Commits
  (`type(scope): summary`, see `CONTRIBUTING.md`); one logical change per
  commit.
- **A bug fix includes its regression test** — the test that fails on the old
  code and passes on the new one, in the same change.
- **Stay in scope.** Implement only what was asked; no sideways refactors.
- `docs/A_TO_Z_GUIDE.md` and `example.agent.md` are **author-only references —
  never commit them** (both are gitignored).