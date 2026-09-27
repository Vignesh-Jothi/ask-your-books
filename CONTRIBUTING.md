# Contributing

## Commit convention (required)

This repository follows **Conventional Commits** — every commit message must
match:

```
<type>(<scope>): <imperative summary>
```

- `<type>` — one of:

| type | use for |
|---|---|
| `feat` | a new user-facing capability (endpoint, tool, UI, infra file) |
| `fix` | a bug fix (behavior change back to intended) |
| `refactor` | behavior-preserving restructuring (renames, reorgs) |
| `perf` | a measurable performance change |
| `docs` | documentation only (this file, README, docs/, AI_USAGE.md) |
| `test` | tests and the eval harness only |
| `build` / `ci` | build tooling / CI config |
| `chore` | maintenance with no functional impact (gitignore, deps) |

- `<scope>` — small lowercase area of the codebase, e.g.
  `(guards)`, `(services)`, `(seed)`, `(okf)`, `(eval)`, `(docs)`. Omit when
  the change spans many areas.
- `<imperative summary>` — present tense, lower case, ≤ 72 chars
  (“add …”, “fix …”, “rename …”, never “added/fixed/renamed”).

### Rules

1. **One logical change per commit.** Split unrelated edits across commits —
   the history is meant to read as a changelog.
2. Language: English. Numbers/units as in the domain (paise, not ₹ decimals).
3. Breaking change → add a footer line:

   ```
   BREAKING CHANGE: <what breaks and what callers must do>
   ```

4. Issue references go in the body, not the summary:

   ```
   feat(api): refuse sandbox SQL runtime failures

   Closes #42
   ```

### Examples

```
feat(services): add fy comparison tool for expense vs prior year
fix(guards): reject PRAGMA statements in read-only check
refactor(core): rename shift_year locals to descriptive identifiers
test(eval): assert consistency across 3 runs per question
docs: add application vocabulary glossary
BREAKING CHANGE: chat response rows are now dicts, not lists
```

## Branch naming

`feature/<kebab-case>` · `hotfix/<kebab-case>` · `devops/<name>` — created and
tracked through Vortex (git-flow) tooling in this workspace.

## Definition of done

- `make test` green (pytest).
- `make seed` + `make eval` green where a change touches data, guards or tools.
- No single-letter identifiers; descriptive names + a comment where intent is
  not obvious (see project conventions).
- New domain terms are added to `docs/glossary.md` (the application vocabulary).